"""Historical result readback and current JSON adapter boundaries, isolated I/O."""
import importlib.util
import json
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

from common.currency import fn_result_payload
from ibl_function_result import compact_execution
from ibl_v2_adapters import decode_envelope
from ibl_v2_ir import Fault
from supervision_store import TurnStore

ROOT = Path(__file__).resolve().parents[1]
BODY = ('$return = $목록 >> [table:filter]{where:{field:"text",op:"matches",value:$패턴},'
        'context:{before:0,after:0,by:"url",limit:2}}')


@pytest.fixture
def boundary(monkeypatch, tmp_path):
    import supervision_store
    store = TurnStore(tmp_path / 'evidence')
    monkeypatch.setattr(supervision_store, 'current_evidence_store', lambda: store)
    state = {'leaf_calls':0}
    def run(value):
        # A deterministic JSON tool fixture, not a language interpreter. Old
        # completed envelopes remain readable after their executor is removed.
        state['leaf_calls'] += 1
        selected = {'items':[row for row in value['items'] if 'wanted' in row['text']]}
        return compact_execution({'success':True,'_fn_result':True,'final_result':selected,
            'results':[{'step':1,'result':value},{'step':2,'result':selected}]})
    return run, state, store


def test_large_intermediates_fold_after_return_selection_and_are_readable(boundary):
    run, state, store = boundary
    rows = {"items": [{"text": "unselected" * 40000, "url": "one"},
                      {"text": "wanted quote", "url": "two"}]}
    out = run(rows)
    assert out["success"], out
    found, value = fn_result_payload(out)
    assert found and value["items"] == [{"text": "wanted quote", "url": "two"}]
    assert len(json.dumps(out)) < 15000
    assert all("result" not in row for row in out["results"])
    saved = json.loads(store.read_evidence(out["execution_ref"]["id"], 0, None)["text"])
    assert "unselected" * 40000 in json.dumps(saved)
    assert saved["final_result"] == out["final_result"]
    import model_result_view as view
    page = view.read_result({**out["execution_ref"]["read_args"], "limit": 60000})
    chunks = [page["text"]]
    while page["next_read"]:
        page = view.read_result(page["next_read"])
        chunks.append(page["text"])
    assert json.loads("".join(chunks)) == saved["results"]
    assert state["leaf_calls"] == 1  # readback never reruns the function


@pytest.mark.parametrize('source', [BODY, '[table:filter]{',
    '$x={items:[{title:"wrong field"}]};$return=$x', '[def:f]{$return=1}'])
def test_historical_functions_are_not_replayed_or_credited(source, monkeypatch):
    from ibl_v2_entry import handle_request
    import ibl_engine
    monkeypatch.setattr(ibl_engine, 'execute_ibl', lambda *a, **k: pytest.fail('historical effect'))
    monkeypatch.setattr('capability_history.record_function_call', lambda *a, **k: pytest.fail('historical credit'))
    out = handle_request({'edition':1,'code':source})
    assert not out['success'] and not out['executed'] and 'EDITION_UNSUPPORTED' in str(out)


def test_current_definition_error_is_reported_before_tools():
    from ibl_v2_entry import handle_request
    out=handle_request({'edition':2,'code':'[def:f](){[table:filter]{'} )
    assert not out['success'] and not out['executed']


@pytest.mark.parametrize("value", [None, 3, "본문", [1, 2], {"results": ["business data"]}])
def test_return_value_and_recovery_metadata_are_unchanged(boundary, value):
    _, _, store = boundary
    out = {"success": False, "final_result": value,
           "results": [{"step": 1, "result": "large" * 10000}],
           "resume": {"step": 2}, "resume_vars": {"vars": ["a"]},
           "traceback": {"frames": [], "error": "fail"},
           "branches_failed": [{"branch": 1, "error": "fail"}]}
    folded = compact_execution(out)
    for key in ("final_result", "resume", "resume_vars", "traceback", "branches_failed", "success"):
        assert folded[key] == out[key]
    assert json.loads(store.read_evidence(folded["execution_ref"]["id"], 0, None)["text"]) == out
    assert compact_execution(folded) is folded
    assert "result" in out["results"][0]  # original never mutated


def test_evidence_store_failure_keeps_original_and_does_not_turn_success_into_failure(boundary, monkeypatch):
    _, _, store = boundary
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr(store, "evidence", fail)
    out = {"success": True, "final_result": 3, "results": [{"step": 1, "result": 3}]}
    folded = compact_execution(out)
    assert folded["success"] and folded["results"] == out["results"]
    assert "execution_ref_error" in folded and "execution_ref" not in folded


def test_parallel_failure_keeps_small_success_values_and_original_steps(boundary):
    run, state, store = boundary
    from ibl_v2_adapters import Adapter, Adapted
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime

    def call(runtime, args):
        raw = run({"items": [{"text": "noise" * 90000, "url": "noise"},
                             {"text": "wanted", "url": args["url"]}]})
        value, evidence = decode_envelope(raw, {"value_path": ""})
        return Adapted(value, evidence)

    def blocked(runtime, args):
        raise Fault("TOOL", "source blocked")

    contract = {"version": 1, "params": {"url": "Text"}, "required": ["url"],
                "result": "Record", "effects": ["read_external"],
                "adapter": {"protocol": "legacy-envelope", "value_path": ""}}
    registry = {"sense:excerpt": Adapter(contract, call), "sense:blocked": Adapter(contract, blocked)}
    plan = compile_program('return [sense:excerpt]{url:"a"} & [sense:blocked]{url:"b"} '
                           '& [sense:excerpt]{url:"c"}', registry)
    out = Runtime(plan).run()
    assert out["success"] is False and out["source_complete"] is False
    partial = out["diagnostic"]["partial"]
    assert len(partial) == 2
    assert len(json.dumps(out, ensure_ascii=False)) < 30000
    for part in partial:
        assert part["final_result"]["items"] == [{"text": "wanted", "url": part["final_result"]["items"][0]["url"]}]
        stored = store.read_evidence(part["execution_ref"]["id"], 0, None)
        assert "noise" * 90000 in stored["text"]
    assert state["leaf_calls"] == 2


def test_compacted_ref_is_scoped_to_issuing_store(boundary, monkeypatch, tmp_path):
    run, _, _ = boundary
    out = run({"items": [{"text": "wanted", "url": "a"}]})
    import model_result_view as view
    monkeypatch.setattr("supervision_store.current_evidence_store", lambda: TurnStore(tmp_path / "other"))
    with pytest.raises(FileNotFoundError):
        view.read_result(out["execution_ref"]["read_args"])


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
