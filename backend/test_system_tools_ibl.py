"""검사 참조는 원문과 입력을 보존하며 실행은 기존 검사·권한 경계를 지난다."""
import json

import boot_paths  # noqa: F401
import pytest

import ibl_v2_entry
from ibl_edition import source_edition
import model_result_view as view
import system_tools_ibl as tools
from supervision_store import TurnStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    result = TurnStore(tmp_path / "evidence")
    monkeypatch.setattr(view, "evidence_store", lambda: result)
    return result


def run(request, tmp_path):
    return json.loads(tools._execute_ibl_unified(request, str(tmp_path)))


def test_checked_program_reuses_exact_inputs_budget_and_reference_provenance(store, tmp_path):
    source = store.evidence({"edition": 2, "success": True, "value": [{"title": "10월 5일", "n": 3}]})
    request = {"edition": 2, "code": "return $rows[0].title", "check": True,
               "inputs": {"rows": {"$ref": source["id"]}}, "budget": {"steps": 321},
               "value_protocols": ["ibl-value/1"]}
    checked = run(request, tmp_path)
    assert checked["ok"], checked
    args = checked["execute_args"]
    assert set(args) == {"code"}
    resolved, error = tools._resolve_checked_code(args)
    assert not error and resolved["inputs"] == request["inputs"]
    assert resolved["budget"] == request["budget"]
    assert resolved["value_protocols"] == request["value_protocols"]
    assert "check" not in resolved
    out = run(args, tmp_path)
    assert out["success"] and out["value"] == "10월 5일", out
    assert out["inputs_resolved"], out


def test_checked_defaults_are_snapshots_and_explicit_overrides_replace_whole_argument(store, tmp_path):
    inputs = {"x": 3, "unused": "keep original"}
    checked = run({"edition": 2, "check": True, "code": "return $x + 1",
                   "inputs": inputs, "budget": {"steps": 300}}, tmp_path)
    inputs["x"] = 100
    args = checked["execute_args"]
    assert run(args, tmp_path)["value"] == 4
    resolved, error = tools._resolve_checked_code({**args, "inputs": {"x": 8}, "budget": {"steps": 400}})
    assert not error and resolved["inputs"] == {"x": 8} and resolved["budget"] == {"steps": 400}
    assert run({**args, "inputs": {"x": 8}}, tmp_path)["value"] == 9
    invalid = run({**args, "inputs": {}}, tmp_path)
    assert invalid.get("success") is not True and invalid.get("executed") is False, invalid


def test_checked_handle_does_not_reuse_masked_inputs(store, tmp_path):
    checked = run({"edition": 2, "check": True, "code": "return $config",
                   "inputs": {"config": {"api_key": "DEMO_KEY_PLACEHOLDER"}}}, tmp_path)
    assert checked["ok"] and "execute_args" not in checked


def test_old_code_only_handle_still_works_and_revised_code_uses_saved_inputs(store, tmp_path):
    old = store.evidence({"kind": "checked_program", "code": "return $x"})
    assert run({"code": f"$checked:{old['id']}", "edition": 2, "inputs": {"x": 7}}, tmp_path)["value"] == 7
    checked = run({"edition": 2, "check": True, "code": "return $x + 1", "inputs": {"x": 7}}, tmp_path)
    changed = run({**checked["execute_args"], "code_edits": [{"old": "+ 1", "new": "+ 2"}]}, tmp_path)
    assert changed["success"] and changed["value"] == 9


@pytest.mark.parametrize("source,requested,expected", [
    ("[fn:値]{}", None, 1),
    ("[fn:値]{}", 1, 1),
    ("[fn:値]{}", 2, 2),
    ("#!ibl edition=1\n[fn:値]{}", None, 1),
    ("#!ibl edition=2\n[fn:値]{}", None, 2),
])
def test_describe_matches_execution_edition(
        tmp_path, monkeypatch, source, requested, expected):
    described, executed = [], []

    def describe(actions, allowed, *, edition, program):
        described.append(edition)
        return {"actions": [{"action": "fn:値", "definition": {"edition": edition}}]}

    def execute(req, *args, **kwargs):
        executed.append(source_edition(req["code"], req.get("edition")))
        return {"success": True, "edition": executed[-1], "value": "once"}

    monkeypatch.setattr(view, "describe_actions", describe)
    monkeypatch.setattr(ibl_v2_entry, "handle_request", execute)
    request = {"code": source, "describe": ["fn:値"]}
    if requested is not None:
        request["edition"] = requested
    result = json.loads(tools._execute_ibl_unified_impl(request, str(tmp_path)))
    assert described == executed == [expected], (described, executed, result)
    assert result["success"] is True


def test_description_only_keeps_current_authoring_edition(tmp_path, monkeypatch):
    seen = []

    def describe(actions, allowed, *, edition, program):
        seen.append(edition)
        return {"actions": [], "executed": False}

    monkeypatch.setattr(view, "describe_actions", describe)
    result = json.loads(tools._execute_ibl_unified_impl(
        {"code": "", "describe": ["fn:値"]}, str(tmp_path)))
    assert seen == [2] and result["executed"] is False


@pytest.mark.parametrize("check_first,fresh", [(False, False), (True, False), (False, True)])
def test_revision_reuses_reads_and_inputs_through_optional_check(store, tmp_path, monkeypatch, check_first, fresh):
    import ibl_engine

    calls = []

    def quote(step, *args, **kwargs):
        calls.append(step)
        return {"success": True, "items": [{"symbol": "fixture", "current_price": 100}]}

    monkeypatch.setattr(ibl_engine, "execute_ibl", quote)
    code = '''$quotes=[table:each]{items:$symbols} {
  $q=[sense:stock]{op:"quote",ticker:$it}
  return $q
}
return $quotes >> [table:select]{columns:["symbol","current_price"]}'''
    inputs = {"symbols": [f"FIX{i}" for i in range(18)]}
    request = {"edition": 2, "code": code, "inputs": inputs, "budget": {"steps": 4000}}
    failed = run(request, tmp_path)
    assert failed["success"] is False and len(calls) == 18, failed
    assert "items" in failed["error"] and "flat_map" in failed["error"], failed
    args = {**failed["revise_args"], "code_edits": [
        {"old": "items:$symbols", "new": 'items:$symbols,mode:"flat_map"'},
        {"old": "return $q\n", "new": "return $q.items\n"},
    ]}
    if fresh:
        args["reuse"] = None
    resolved, error = tools._resolve_checked_code(args)
    assert error is None and resolved["inputs"] == inputs
    assert resolved["budget"] == request["budget"]
    if check_first:
        checked = run({**args, "check": True}, tmp_path)
        assert checked["ok"] and len(calls) == 18, checked
        args = checked["execute_args"]
    out = run(args, tmp_path)
    assert out["success"] and len(out["value"]) == 18, out
    assert len(calls) == (36 if fresh else 18)
    if not fresh:
        assert out["reuse"]["reused_calls"] == 18, out


def test_compile_revision_preserves_inputs_and_explicit_overrides(store, tmp_path):
    code = '# ' + 'long program ' * 30 + '\nreturn $x + $missing'
    failed = run({"edition": 2, "code": code, "inputs": {"x": 3}, "check": True}, tmp_path)
    args = {**failed["revise_args"], "code_edits": [{"old": "$missing", "new": "2"}]}
    assert run(args, tmp_path)["value"] == 5
    assert run({**args, "inputs": {"x": 8}}, tmp_path)["value"] == 10


@pytest.mark.parametrize("status,changed", [("interrupted", True), ("uncertain", False), ("suspended", False)])
def test_revision_does_not_replay_writes_or_uncertain_runs(store, status, changed):
    result = {"executed": True, "success": False, "run_status": status,
              "continuation": {"state_change_possible": changed,
                               "reuse_args": {"reuse": {"run_id": "fixture"}}}}
    tools._offer_code_revision(result, "return 1")
    assert "revise_args" not in result


def test_revision_does_not_restore_masked_inputs(store):
    result = {"executed": False, "ok": False, "issues": [{"code": "UNKNOWN_VARIABLE"}]}
    tools._offer_code_revision(result, "# " + "long " * 70 + "\nreturn $missing",
                               {"inputs": {"config": {"api_key": "DEMO_KEY_PLACEHOLDER"}}})
    assert "revise_args" not in result


def test_revision_preserves_explicit_model_refresh_policy(store):
    result = {"executed": True, "success": False, "run_status": "interrupted",
              "continuation": {"state_change_possible": False,
                               "reuse_args": {"reuse": {"run_id": "current"}}}}
    tools._offer_code_revision(result, "return 1",
                               {"reuse": {"run_id": "previous", "models": False}})
    args = {**result["revise_args"], "code_edits": [{"old": "1", "new": "2"}]}
    resolved, error = tools._resolve_checked_code(args)
    assert not error and resolved["reuse"] == {"run_id": "current", "models": False}


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))


def test_search_partial_survives_model_tool_boundary(store, tmp_path, monkeypatch):
    import ibl_engine
    raw = {'success': False, 'error': 'one query failed',
           'items': [{'title': 'kept', 'query': 'ok'}],
           'errors': [{'query': 'bad', 'error': 'timeout'}],
           'sections': [{'query': 'ok', 'count': 1}, {'query': 'bad', 'count': 0}]}
    monkeypatch.setattr(ibl_engine, 'execute_ibl', lambda *a, **kw: raw)
    out = run({'edition': 2, 'code': '[sense:search]{queries:["ok","bad"]}'}, tmp_path)
    assert not out['success'] and out['diagnostic']['has_partial'], out
    assert out['diagnostic']['partial'] == raw
