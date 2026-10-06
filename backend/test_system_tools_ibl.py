"""검사 참조는 원문과 입력을 보존하며 실행은 기존 검사·권한 경계를 지난다."""
import json

import boot_paths  # noqa: F401
import pytest

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


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
