"""Edition-aware missing-call diagnostics, with legacy execution preserved."""
import boot_paths  # noqa: F401
import pytest

import ibl_control_blocks as control
import ibl_usage_db
import ibl_v2_store
import member_runtime
import workflow_store


@pytest.fixture
def missing_legacy(monkeypatch):
    monkeypatch.setattr(member_runtime, "is_member", lambda: False)
    monkeypatch.setattr(workflow_store, "get_workflow", lambda name: None)

    class DB:
        def find_phrase_by_alias(self, name):
            return None

        def phrase_aliases(self, limit):
            return ["기존함수"]

    monkeypatch.setattr(ibl_usage_db, "IBLUsageDB", DB)


def call(name="설정확인"):
    return control._execute_fn(
        {"action": name, "params": {"PC": "시험PC"}}, ".", None)


@pytest.mark.parametrize("conflict", [False, True])
def test_legacy_reports_current_definition_without_execution(
        missing_legacy, monkeypatch, conflict):
    known = ibl_v2_store.Library()
    known.add("설정확인", "#!ibl edition=2\n[def:설정확인]($PC){return $PC}",
              "관용구:설정확인")
    if conflict:
        known.add("설정확인", "other", "저장본:겹침")
    monkeypatch.setattr(ibl_v2_store, "library", lambda: known)
    result = call()
    assert result.get("error_code") == "FN_EDITION_REQUIRED", result
    assert result["success"] is False and result["executed"] is False
    assert result["required_edition"] == 2
    assert "edition:2" in result["error"] and "#!ibl edition=2" in result["error"]
    assert "없습니다" not in result["error"]


def test_actually_missing_call_keeps_unknown_name_diagnostic(
        missing_legacy, monkeypatch):
    monkeypatch.setattr(ibl_v2_store, "library", lambda: ibl_v2_store.Library())
    result = call("없는함수")
    assert result["success"] is False
    assert "없는함수" in result["error"] and "기존함수" in result["error"]
    assert result.get("error_code") != "FN_EDITION_REQUIRED"


def test_member_cannot_discover_owner_definition(monkeypatch):
    monkeypatch.setattr(member_runtime, "is_member", lambda: True)

    def forbidden():
        raise AssertionError("owner library read")

    monkeypatch.setattr(ibl_v2_store, "library", forbidden)
    result = call()
    assert result["error_type"] == "permission"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
