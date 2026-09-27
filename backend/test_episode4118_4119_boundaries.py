"""Search episodes: actual legacy function/pipeline/adapter boundaries, isolated I/O."""
import importlib.util
import json
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

from common.currency import fn_result_payload
from ibl_control_blocks import _execute_fn
from ibl_function_result import compact_execution
from ibl_v2_adapters import decode_envelope
from ibl_v2_ir import Fault
from supervision_store import TurnStore

ROOT = Path(__file__).resolve().parents[1]
BODY = ('$return = $목록 >> [table:filter]{where:{field:"text",op:"matches",value:$패턴},'
        'context:{before:0,after:0,by:"url",limit:2}}')


@pytest.fixture
def boundary(monkeypatch, tmp_path):
    import ibl_engine
    import ibl_usage_db
    import supervision_store
    import workflow_store
    from tool_context import ToolContext
    spec = importlib.util.spec_from_file_location(
        "_episode4119_dataops", ROOT / "data/packages/installed/tools/data-ops/handler.py")
    dataops = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dataops)
    state = {"code": BODY, "feedback": [], "events": [], "leaf_calls": 0}
    store = TurnStore(tmp_path / "evidence")
    monkeypatch.setattr(supervision_store, "current_evidence_store", lambda: store)
    monkeypatch.setattr("episode_logger.record_trajectory_event",
                        lambda kind, data=None: state["events"].append((kind, data)))
    monkeypatch.setattr(workflow_store, "get_workflow", lambda name: None)

    class DB:
        def find_phrase_by_alias(self, name):
            return {"ibl_code": state["code"], "alias": name}

        def update_success_by_code(self, code, ok, **kw):
            state["feedback"].append(ok)
            return True

    monkeypatch.setattr(ibl_usage_db, "IBLUsageDB", DB)
    original = ibl_engine._execute_ibl_impl

    def leaf(request, project, agent=None):
        if request.get("_node") == "table" and request.get("action") == "filter":
            state["leaf_calls"] += 1
            return dataops.execute(request.get("params") or {}, ToolContext(project, "data_filter"))
        return original(request, project, agent)

    monkeypatch.setattr(ibl_engine, "_execute_ibl_impl", leaf)

    def run(value, code=None):
        if code is not None:
            state["code"] = code
        return _execute_fn({"_node": "fn", "action": "발췌", "params": {
            "목록": value, "패턴": "wanted"}}, str(tmp_path), "test")

    return run, state, store


def test_large_intermediates_fold_after_return_selection_and_are_readable(boundary):
    run, state, store = boundary
    rows = {"items": [{"text": "unselected" * 40000, "url": "one"},
                      {"text": "wanted quote", "url": "two"}]}
    out = run(rows)
    assert out["success"], out
    assert state["feedback"] == [True]
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


def test_wrong_parallel_branch_is_input_mismatch_not_bad_definition(boundary):
    run, state, store = boundary
    out = run([{"success": True, "source": "search", "items": [{"title": "candidate"}]},
               {"items": [{"text": "wanted", "url": "apply"}]}])
    assert out["success"] is False
    assert out["failure_origin"]["kind"] == "input_shape"
    assert out["failure_origin"]["parameter"] == "목록"
    assert out["failure_origin"]["input_contract"]["missing_fields"] == ["text"]
    assert "넘긴 값" in out["hint"] and "def" not in out
    assert state["feedback"] == []
    ev = next(data for kind, data in state["events"] if kind == "ibl.function_feedback")
    assert ev["success"] is False and ev["attributed"] is False
    with pytest.raises(Fault) as caught:
        decode_envelope(out, {"value_path": ""})
    details = caught.value.details
    assert details["failure_origin"] == out["failure_origin"]
    assert details["execution_ref"]["id"] == out["execution_ref"]["id"]
    assert "def" not in details
    fixed = run({"items": [{"text": "wanted", "url": "apply"}]})
    assert fixed["success"] and state["feedback"] == [True]


def test_internal_bad_shape_is_not_misattributed_to_caller(boundary):
    run, state, _ = boundary
    code = ('$x = {items:[{title:"wrong field"}]}\n'
            '$return = $x >> [table:filter]{where:{field:"text",op:"matches",value:"wanted"}}')
    out = run({"items": [{"text": "wanted", "url": "good"}]}, code)
    assert out["success"] is False
    assert out["failure_origin"]["kind"] == "unknown"
    assert state["feedback"] == [] and "def" not in out


def test_confirmed_definition_syntax_failure_still_has_feedback_and_definition(boundary):
    run, state, _ = boundary
    out = run({}, '[table:filter]{')
    assert out["success"] is False
    assert out["failure_origin"] == {"kind": "definition", "definition_failure": True}
    assert state["feedback"] == [False]
    assert out["def"].startswith("[def:")
    with pytest.raises(Fault) as caught:
        decode_envelope(out, {"value_path": ""})
    assert caught.value.details["def"] == out["def"]


def test_opaque_failure_keeps_evidence_without_false_blame(boundary, monkeypatch):
    run, state, _ = boundary
    monkeypatch.setattr("workflow_engine.execute_pipeline", lambda *a, **k: {
        "success": False, "error": "원천 접근 실패", "results": [], "final_result": None})
    out = run({})
    assert out["success"] is False and out["error"] == "원천 접근 실패"
    assert out["failure_origin"]["kind"] == "unknown"
    assert not state["feedback"] and "def" not in out


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
        assert part["items"] == [{"text": "wanted", "url": part["items"][0]["url"]}]
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
