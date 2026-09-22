"""입력 비용·행 보존·실제 스크립트 stdin 경계의 회귀. 외부 모델만 고정한다."""
import copy
import importlib.util
import json
from pathlib import Path
import sys

import boot_paths  # noqa: F401
import pytest
import oneshot_facade

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AI = load("evolution_ai", "data/packages/installed/tools/ai-ops/handler.py")
S = load("evolution_script", "data/packages/installed/tools/system_essentials/script_ops.py")


@pytest.fixture
def transform(monkeypatch):
    calls = []
    def run(output, **params):
        def model(prompt, system):
            calls.append((prompt, system))
            return output, None
        monkeypatch.setattr(oneshot_facade, "oneshot_json", model)
        return json.loads(AI._transform({"instruction": "주석 추가", **params}))
    run.calls = calls
    return run


def test_projection_preserves_large_original_and_input_order(transform):
    original = [{"title": "a", "raw": "가" * 70000}, {"title": "b", "optional": 3}]
    before = copy.deepcopy(original)
    out = transform([{"_i": 1, "note": "둘"}, {"_i": 0, "note": "하나"}],
                    items=original, input_fields=["title", "optional"], preserve_rows=True)
    assert out["success"] and [r["title"] for r in out["items"]] == ["a", "b"]
    assert out["items"][0]["raw"] == original[0]["raw"] and original == before
    prompt = transform.calls[0][0]
    assert '"raw"' not in prompt and '"optional": null' not in prompt
    assert len(prompt) < 200


@pytest.mark.parametrize("output", [[], [{"_i": 0}], [{"_i": 0}, {"_i": 0}],
    [{"_i": 0}, {"_i": 2}], [{"_i": 0}, {"note": "x"}], [{"note": "x"}],
    [{"_i": False}, {"_i": 1}], [{"_i": 0.0}, {"_i": 1}]])
def test_preserve_rows_rejects_incomplete_or_ambiguous_mapping(transform, output):
    out = transform(output, items=[{"a": 1}, {"a": 2}], preserve_rows=True)
    assert out["success"] is False


def test_projected_hidden_fields_cannot_be_overwritten(transform):
    for key in ("raw", "path", "_ai"):
        out = transform([{"_i": 0, key: "changed"}],
                        items=[{"title": "x", key: "original"}], input_fields=["title"])
        assert out["success"] is False


@pytest.mark.parametrize("params", [{"input_fields": []}, {"input_fields": ["a", "a"]},
    {"input_fields": ["_i"]}, {"input_fields": [2]}, {"preserve_rows": "true"}])
def test_bad_contract_fails_even_on_empty_input(transform, params):
    assert not transform([], items=[], **params)["success"]
    assert not transform.calls


def test_missing_projection_and_size_fail_before_model(transform):
    assert not transform([], items=[{"a": 1}], input_fields=["absent"])["success"]
    out = transform([], items=[{"text": "한" * 61000}], input_fields=["text"])
    assert out["error_type"] == "input_size" and out["input_chars"] > out["limit_chars"]
    assert out["input_bytes"] > out["input_chars"] and not transform.calls


def test_legacy_filter_and_output_projection_are_unchanged(transform):
    src = [{"a": 1}, {"a": 2}]
    out = transform([{"_i": 1, "note": "둘"}], items=src, fields=["note"])
    assert out["success"] and out["rows_dropped"] == 1
    assert set(out["items"][0]) == {"note", "_ai"}
    assert transform([{"other": 4}], items=src)["_merge"] == "full"


@pytest.fixture
def script(tmp_path, monkeypatch):
    path = tmp_path / "echo.py"
    path.write_text('import sys,json\na=json.load(sys.stdin)\nprint(json.dumps({"items":[a]}))\n')
    monkeypatch.setattr(S, "_read_registry", lambda: {"echo": {"file": str(path)}})
    monkeypatch.setattr(S, "_script_path", lambda entry: path)
    monkeypatch.setattr(S, "_resolve_interpreter", lambda *a: (sys.executable, None))
    monkeypatch.setattr(S, "_RUN_DIR", tmp_path / "logs")
    monkeypatch.setattr(S, "_update_state", lambda *a, **k: None)
    return S


@pytest.mark.parametrize("as_json", [False, True])
def test_actual_subprocess_gets_whole_envelope_unchanged(script, as_json):
    envelope = {"items": [{"payload": {"value": "~workspace/raw"}, "user": [1, 2]}],
                "partial": True, "errors": ["source failed"], "truncated": True,
                "rows_unprocessed": 3, "provenance": {"url": "fixture"}, "success": False}
    out = script.op_run({"id": "echo", "input_as": "data", "args": {"op": "accept"},
                         "_prev_result": json.dumps(envelope) if as_json else envelope})
    assert out["success"] and out["items"][0] == {"op": "accept", "data": envelope}


@pytest.mark.parametrize("params", [{}, {"_prev_result": None}, {"_prev_result": []},
    {"_prev_result": "not json"}, {"_prev_result": {"items": []}, "args": {"data": 1}},
    {"_prev_result": {"items": []}, "args_file": "missing.json"},
    {"_prev_result": {"items": []}, "input_as": ""}])
def test_input_as_conflicts_never_launch_process(script, monkeypatch, params):
    monkeypatch.setattr(script.subprocess, "run", lambda *a, **k: pytest.fail("subprocess launched"))
    assert not script.op_run({"id": "echo", "input_as": "data", **params})["success"]


def test_empty_envelope_and_non_identifier_key(script):
    out = script.op_run({"id": "echo", "input_as": "user.payload", "_prev_result": {"items": []}})
    assert out["items"] == [{"user.payload": {"items": []}}]


def test_actual_stdin_through_function_each_and_spill(script, tmp_path, monkeypatch):
    import ibl_engine
    import workflow_engine
    from ibl_parser import parse_with_vars
    from common import spill
    monkeypatch.setattr(spill, "_root", lambda: str(tmp_path / "spill"))
    original = ibl_engine._execute_ibl_impl
    def leaf(ti, project, agent_id=None):
        if ti.get("_node") == "self" and ti.get("action") == "script":
            return script.op_run(ti["params"])
        return original(ti, project, agent_id)
    monkeypatch.setattr(ibl_engine, "_execute_ibl_impl", leaf)
    code = '''[def:전달]{
      [self:script]{op:"run",id:"echo",args:{op:"accept"},input_as:"data"}
    }
    [table:each]{items:[{id:"a",payload:{x:1},user:"reader"}],limit:1,collect:true} {
      [table:take]{items:[$it],n:1} >> [fn:전달]{}
    }'''
    result = workflow_engine.execute_pipeline(parse_with_vars(code)[0], str(tmp_path))
    assert result["success"], result
    body = result["final_result"]
    if isinstance(body, str):
        body = json.loads(body)
    assert body["items"][0]["data"]["items"] == [{"id": "a", "payload": {"x": 1}, "user": "reader"}]
    envelope = {"items": [{"text": "가" * 70000}], "partial": True, "errors": ["fixture"]}
    ref = spill.spill_write(json.dumps(envelope, ensure_ascii=False))
    from workflow_binding import _auto_inject_prev
    ti = _auto_inject_prev({"params": {"id": "echo", "input_as": "data"}}, ref)
    out = script.op_run(ti["params"])
    assert out["items"][0]["data"] == envelope


def test_expired_spill_and_non_run_input_as_fail_before_execution(script, monkeypatch):
    monkeypatch.setattr(script.subprocess, "run", lambda *a, **k: pytest.fail("subprocess launched"))
    out = script.op_run({"id": "echo", "input_as": "data", "_prev_result": {
        "items": [], "_spilled": True, "ref": {"path": "/nonexistent/ibl-evolution.json"}}})
    assert not out["success"] and "복원 실패" in out["error"]
    handler = load("evolution_essentials", "data/packages/installed/tools/system_essentials/handler.py")
    from tool_context import ToolContext
    result = json.loads(handler.execute({"op": "remove", "id": "echo", "input_as": "data"},
                                       ToolContext("/tmp", "script_op")))
    assert not result["success"] and "run 전용" in result["error"]


def test_member_transfer_prepares_same_envelope_without_hub_paths(tmp_path, monkeypatch):
    import threading
    import member_runtime
    import member_profile
    import member_bridge
    import principal
    envelope = {"items": [{"payload": {"value": "~workspace/member"}}],
                "partial": True, "errors": [{"source": "fixture"}], "truncated": True}
    calls = []
    monkeypatch.setattr(member_bridge, "request", lambda command: calls.append(command) or {"success": True})
    token = principal.set_transport(principal.OWNER)
    try:
        with principal.narrow(principal.member("A", 4, "devA")), member_runtime.turn_scope(
                tmp_path, "devA", "script", threading.Event(), {}):
            entry = member_profile.entry("self", "script")
            result = member_bridge.execute(entry, {"op": "run", "id": "echo", "input_as": "data",
                "args": {"path": "~workspace/member"}, "_prev_result": json.dumps(envelope)})
            assert result["success"], result
            assert calls == [{"op": "script", "action": "run", "id": "echo",
                              "args": {"path": "~workspace/member", "data": envelope}}]
            failed = member_bridge.execute(entry, {"op": "run", "id": "echo", "input_as": "data",
                "args_file": "/must-not-read-hub.json", "_prev_result": json.dumps(envelope)})
            assert not failed["success"] and len(calls) == 1
    finally:
        principal.reset_transport(token)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
