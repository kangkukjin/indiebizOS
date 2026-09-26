"""General composition contracts across reference, function and reuse boundaries."""
import json

import boot_paths  # noqa: F401
import pytest

from ibl_v2_adapters import Adapter, Adapted
from ibl_v2_compile import compile_program
from ibl_v2_ir import pack
from ibl_v2_runtime import Runtime
from ibl_run_journal import Journal, reusable_receipts
from test_ibl_v2_assets import memory  # noqa: F401 -- isolated existing memory/workflow fixture


def adapter(run, *, result="Number", effects=None, **extra):
    return Adapter({"version": 1, "params": {}, "result": result,
                    "effects": effects or ["read_external"],
                    "implementation_fingerprint": "same", **extra}, run)


@pytest.fixture
def boundary(tmp_path, monkeypatch):
    import ibl_v2_adapters
    import ibl_v2_store
    import ibl_v2_learning
    import ibl_run_journal
    import model_result_view
    from supervision_store import TurnStore
    store = TurnStore(tmp_path / "evidence")
    monkeypatch.setattr(model_result_view, "evidence_store", lambda: store)
    monkeypatch.setattr(ibl_run_journal, "journal_root", lambda _: tmp_path / "runs")
    monkeypatch.setattr(ibl_v2_adapters, "load_registry", lambda *a: {})
    monkeypatch.setattr(ibl_v2_store, "definitions", lambda: {})
    monkeypatch.setattr(ibl_v2_learning, "record_functions", lambda *a: None)
    return store


@pytest.mark.parametrize("path", [None, ["value", "rows"], ["value", "rows", 0]])
def test_reference_roundtrip_retains_partial_source_and_origin(boundary, tmp_path, path):
    from system_tools_ibl import _execute_ibl_unified_impl
    rows = {"rows": [{"n": 2}]}
    original = Runtime(compile_program("return [t:read]{}", {
        "t:read": adapter(lambda *_: Adapted(rows, {"incomplete": True}), result="Record")
    })).run()
    ref = boundary.evidence(json.dumps(original))
    input_ref = {"$ref": ref["id"], **({"path": path} if path is not None else {})}
    for _ in range(2):
        result = json.loads(_execute_ibl_unified_impl({
            "edition": 2, "code": "[def:pass]($v){return $v}\nreturn [fn:pass]{v:$x}",
            "inputs": {"x": input_ref}}, str(tmp_path)))
        assert result["success"] is True and result["source_complete"] is False
        stored = json.loads(boundary.read_evidence(result["result_ref"]["id"], 0, None)["text"])
        origin = next(e for e in stored["evidence"] if e["kind"] == "input_ref")["origin"]
        assert origin["id"] == input_ref["$ref"]
        assert origin["evidence"]["fingerprint"]
        input_ref = {"$ref": result["result_ref"]["id"]}
    expected = rows if path is None else rows["rows"] if len(path) == 2 else rows["rows"][0]
    assert result["value"] == expected


def test_reference_business_flags_stay_data_and_evidence_is_queryable(boundary, tmp_path):
    from system_tools_ibl import _execute_ibl_unified_impl
    value = {"error": "traceback", "source_complete": False}
    original = {"edition": 2, "success": True, "source_complete": True,
                "value": value, "value_wire": {"protocol": "ibl-value/1", "data": pack(value)}}
    ref = boundary.evidence(json.dumps(original))
    result = json.loads(_execute_ibl_unified_impl({
        "edition": 2, "code": "return {value:$x, proof:evidence($x)}",
        "inputs": {"x": {"$ref": ref["id"]}}}, str(tmp_path)))
    assert result["success"] and result["source_complete"]
    assert result["value"]["value"] == value
    assert any(e["kind"] == "input_ref" for e in result["value"]["proof"]["events"])


def test_resume_identity_includes_reference_evidence():
    from ibl_run_journal import identity
    plan = compile_program("return $x", inputs={"x": 1})
    a = identity(plan, {"x": 1}, ".", None, input_evidence={"x": {"id": "one"}})
    b = identity(plan, {"x": 1}, ".", None, input_evidence={"x": {"id": "two"}})
    assert a != b


def test_function_contracts_expose_scoped_transitive_effects_and_defaults():
    registry = {"t:read": adapter(lambda *_: 1),
                "t:write": adapter(lambda *_: 2, effects=["write_external"])}
    source = ('[def:read]($x=3){return [t:read]{} + $x}\n'
              '[def:outer](){return [fn:read]{}}\n'
              '[def:pure]($x=4){return $x + 1}\n'
              '[def:write](){return [t:write]{}}\n'
              'return [fn:outer]{}')
    # Calls in arithmetic are deliberately rejected; use explicit bindings.
    source = source.replace('return [t:read]{} + $x', '$v=[t:read]{}; return $v + $x')
    plan = compile_program(source, registry)
    assert not plan.issues, plan.report()
    contracts = {c["name"]: c for c in plan.function_contracts.values()}
    assert contracts["outer"]["effects"] == ["read_external"]
    assert contracts["outer"]["actions"] == ["t:read"]
    assert contracts["pure"]["effects"] == ["pure"]
    assert contracts["pure"]["actions"] == []
    assert contracts["read"]["default_expressions"] == {"x": "3"}
    assert contracts["read"]["pipe_input"] == "x"
    assert contracts["write"]["effects"] == ["write_external"]
    assert Runtime(plan).run()["value"] == 4


def receipts(tmp_path, registry, source="return [t:read]{}"):
    with Journal(tmp_path, "first") as journal:
        out = Runtime(compile_program(source, registry), journal=journal).run()
        run_id = journal.run_id
    assert out["success"], out
    return reusable_receipts(tmp_path, run_id), run_id


def test_changed_contract_invalidates_read_reuse_with_same_implementation(tmp_path):
    calls = []
    registry = {"t:read": adapter(lambda *_: 1)}
    reusable, run_id = receipts(tmp_path, registry)
    changed = {"t:read": adapter(lambda *_: calls.append(1) or {"n": 2}, result="Record")}
    out = Runtime(compile_program("return [t:read]{}", changed),
                  reusable=reusable, reuse_run=run_id).run()
    assert out["success"] and out["value"] == {"n": 2}
    assert calls == [1] and out["reuse"]["reused_calls"] == 0


def test_changed_dependency_invalidates_read_reuse_without_contract_change(tmp_path):
    state = {"revision": 1}
    contract = adapter(None).contract
    registry = {"t:read": Adapter(contract, lambda *_: state["revision"],
                                 dependency=lambda _: dict(state))}
    reusable, run_id = receipts(tmp_path, registry)
    state["revision"] = 2
    out = Runtime(compile_program("return [t:read]{}", registry),
                  reusable=reusable, reuse_run=run_id).run()
    assert out["success"] and out["value"] == 2
    assert out["reuse"]["reused_calls"] == 0


@pytest.mark.parametrize("effects", [["write_external"], ["model"], ["unknown"]])
def test_effect_barrier_invalidates_later_reads_even_through_functions(tmp_path, effects):
    state = {"n": 1}
    calls = []
    def read(*_):
        calls.append(state["n"])
        return state["n"]
    def write(*_):
        state["n"] += 1
        return state["n"]
    registry = {"t:read": adapter(read), "t:write": adapter(write, effects=effects)}
    reusable, run_id = receipts(tmp_path, registry)
    calls.clear()
    source = ('[def:change](){return [t:write]{}}\n'
              '$before=[t:read]{}; $write=[fn:change]{}; '
              'return {before:$before, after:[t:read]{}}')
    out = Runtime(compile_program(source, registry), reusable=reusable, reuse_run=run_id).run()
    assert out["success"] and out["value"] == {"before": 1, "after": 2}, out
    assert calls == [2] and out["reuse"]["reused_calls"] == 1


def test_reused_recording_can_replay_the_edited_program(tmp_path):
    registry = {"t:read": adapter(lambda *_: 7)}
    reusable, run_id = receipts(tmp_path, registry)
    plan = compile_program("$x=[t:read]{}; return $x + 1", registry)
    out = Runtime(plan, reusable=reusable, reuse_run=run_id).run()
    assert out["success"] and out["reuse"]["reused_calls"] == 1
    replayed = Runtime(plan, recordings=out["recordings"], replay=True).run()
    assert replayed["success"] and replayed["value"] == 8, replayed


def test_local_function_saved_and_recomposed_tracks_transitive_revision(memory, tmp_path, monkeypatch):
    import ibl_run_journal
    import ibl_v2_adapters
    from ibl_v2_store import action, describe, definitions
    from ibl_v2_entry import handle_request
    monkeypatch.setattr(ibl_run_journal, "journal_root", lambda _: tmp_path / "runs")
    monkeypatch.setattr(ibl_v2_adapters, "load_registry", lambda *a: {})
    source = '#!ibl edition=2\n[def:scale]($rows,$factor=2){return $rows >> [table:each]{return $it * $factor}}'
    assert memory.add_examples_batch([{"intent": "입력 목록 배수", "ibl_code": source,
                                       "alias": "scale", "category": "phrase", "nodes": "table"}]) == 1
    outer = '#!ibl edition=2\n[def:compose]($values){return [fn:scale]{rows:$values}}'
    saved = action("save", {"code": outer}, str(tmp_path))
    assert saved["success"], saved
    before = describe("compose")
    assert before["callable_contract"]["required"] == ["values"]
    assert before["callable_contract"]["effects"] == ["pure"]
    request = {"edition": 2, "code": "return [fn:compose]{values:$input}", "inputs": {"input": [1, 2]}}
    first = handle_request(request, str(tmp_path))
    assert first["success"] and first["value"] == [2, 4], first
    with memory._get_connection() as conn:
        conn.execute("UPDATE ibl_examples SET ibl_code=? WHERE alias='scale'", (source.replace('factor=2', 'factor=3'),))
        conn.commit()
    after = describe("compose")
    assert before["plan_hash"] != after["plan_hash"]
    second = handle_request(request, str(tmp_path))
    assert second["success"] and second["value"] == [3, 6], second
    # A saved function has only its declared inputs, never the caller's locals.
    assert compile_program("return [fn:compose]{}", definitions=definitions()).issues


def test_phrase_surfaces_share_call_and_preserve_applicability():
    from ibl_usage_db import UsageExample
    from ibl_usage_rag import IBLUsageRAG
    from hippo_tree import phrase_call_line, phrase_expand_card
    import xml.etree.ElementTree as ET
    source = '#!ibl edition=2\n[def:component]($rows){return $rows}'
    observed = json.dumps({"kind": "list", "keys": ["id"]})
    provenance = json.dumps({"applicability": '전체 범위가 제공된 목록 <부분>에는 미완료를 명시',
                             "private_source": "never-show"})
    row = {"id": 1, "alias": "component", "ibl_code": source, "returns": "List<Record>",
           "signature": "rows", "returns_observed": observed, "provenance": provenance}
    example = UsageExample(1, "목록 전달", source, "table", "phrase", 1, .9, "test", -1,
                           alias="component", signature="rows", returns="List<Record>",
                           returns_observed=observed, provenance=provenance)
    xml = ET.fromstring(IBLUsageRAG._format_references(None, [], phrases=[example]))
    ref = xml.find("ref")
    line = phrase_call_line("component", source, row["returns"], "rows", observed=observed, call_only=True)
    assert line in ref.text and line in phrase_expand_card(row)
    assert ref.attrib["applicability"] == json.loads(provenance)["applicability"]
    assert "적용 조건:" in phrase_expand_card(row)
    assert "never-show" not in ET.tostring(xml, encoding="unicode") + phrase_expand_card(row)


@pytest.mark.parametrize("source", ['[self:time]', '#!ibl edition=2\n[def:f](){return 1}'])
@pytest.mark.parametrize("review,excluded", [({"decision": "hold"}, True),
                                           ({"decision": "quarantine"}, True),
                                           ({"static_status": "invalid"}, True),
                                           ({"decision": "compatibility"}, False), ({}, False)])
def test_callable_exposure_policy_is_shared_by_editions(source, review, excluded):
    from corpus_policy import callable_exclusion_reason
    assert bool(callable_exclusion_reason({"ibl_code": source,
                                          "provenance": {"corpus_review": review}})) is excluded


def test_current_idiom_list_does_not_fall_back_to_old_held_definition(tmp_path):
    import sqlite3
    from ibl_access import _current_idiom_rows
    with sqlite3.connect(tmp_path / "list.db") as conn:
        conn.execute('CREATE TABLE ibl_examples(intent,ibl_code,success_count,fail_count,topic,alias,returns,signature,provenance,updated_at)')
        conn.executemany('INSERT INTO ibl_examples VALUES(?,?,?,?,?,?,?,?,?,?)', [
            ('old', '[self:time]', 5, 0, '', 'f', 'Record', '', '{}', '2026-01-01'),
            ('new', '#!ibl edition=2\n[def:f](){return 1}', 0, 0, '', 'f', 'Number', '',
             json.dumps({'corpus_review': {'decision': 'hold'}}), '2026-09-27')])
        rows = conn.execute('SELECT intent,ibl_code,success_count,fail_count,topic,alias,returns,signature FROM ibl_examples').fetchall()
        assert _current_idiom_rows(conn, rows, 'returns', 'signature') == []


def test_description_consumes_runtime_contract_including_schema_resolved_parameters(monkeypatch):
    import ibl_access
    import ibl_registry
    import ibl_v2_adapters
    from model_result_view import describe_actions
    calls = []
    resolved = {"version": 1, "params": {"schema_only": "Text"}, "required": [],
                "result": "Record", "effects": ["unknown"], "implementation_fingerprint": "private"}
    monkeypatch.setattr(ibl_access, "load_nodes_raw", lambda: {"nodes": {"self": {"actions": {
        "one": {"description": "first", "params": {"stale": "bad"}},
        "two": {"description": "second"}}}}})
    monkeypatch.setattr(ibl_registry, "self_can_run", lambda *a: True)
    def registry(*_):
        calls.append(1)
        return {"self:one": Adapter(resolved, None), "self:two": Adapter(resolved, None)}
    monkeypatch.setattr(ibl_v2_adapters, "load_registry", registry)
    result = describe_actions(["self:one", "self:two"], {"self"}, edition=2)
    assert calls == [1]
    for row in result["actions"]:
        contract = row["definition"]["callable_contract"]
        assert contract["params"] == {"schema_only": "Text"}
        assert "implementation_fingerprint" not in contract and "params" not in row["definition"]


def test_idiom_map_cache_expires_on_review_change_in_wal(tmp_path, monkeypatch):
    import sqlite3
    import runtime_utils
    import ibl_access
    import ibl_registry
    import vocabulary_state
    data = tmp_path / "data"
    (data / "idioms").mkdir(parents=True)
    source = '#!ibl edition=2\n[def:f](){return 1}'
    (data / "idioms" / "curated.json").write_text(json.dumps({"idioms": [
        {"name": "f", "always_on": True, "body": source}]}))
    monkeypatch.setattr(runtime_utils, "get_base_path", lambda: tmp_path)
    monkeypatch.setattr(ibl_registry, "code_is_own", lambda _: True)
    monkeypatch.setattr(vocabulary_state, "revision", lambda: 1)
    monkeypatch.setattr(ibl_access, "_idioms_cache", {"text": None, "t": 0, "key": None})
    conn = sqlite3.connect(data / "ibl_usage.db")
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('CREATE TABLE ibl_examples(intent,ibl_code,success_count,fail_count,topic,alias,returns,signature,provenance,updated_at,created_at,always_on)')
        conn.execute('INSERT INTO ibl_examples VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                     ('pure', source, 1, 0, '', 'f', 'Number', '', '{}', 'now', 'now', 1))
        conn.commit()
        assert '[fn:f]' in ibl_access.idioms_map(None)
        conn.execute('UPDATE ibl_examples SET provenance=?', (json.dumps({"corpus_review": {"decision": "hold"}}),))
        conn.commit()
        assert '[fn:f]' not in ibl_access.idioms_map(None)
        assert 'f' not in ibl_access.exposed_idiom_names(None)
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
