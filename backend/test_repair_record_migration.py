"""수리 기준 이전: 승인/취소/증거는 그대로, 과제 완료 의도는 보존된 기준에만 반영."""
import copy
import json
from pathlib import Path
import importlib.util
import pytest
import boot_paths  # noqa: F401

_spec = importlib.util.spec_from_file_location("repair_record_migration", Path(__file__).parents[1] / "scripts/migrate_pursuit_records.py")
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)


def record():
    return {"task_id": "task", "status": "blocked", "authorized_origin": "user",
            "framing": {"scope": "pursuit", "pursuit_id": "old", "achievement_criteria": "이번 단계"},
            "criteria_contract": {"criteria": [{"id": "C1", "text": "원래 기능"}]},
            "pursuit": {"id": "old", "goal_criteria": "정정 전 목표"},
            "done_request": {"id": "old", "goal_criteria": "정정한 전체 목표", "version": 3}}


def test_saved_completion_criteria_preserved_once_without_reviving_old_goal():
    old = record(); original = copy.deepcopy(old)
    new = migration.convert_record(old)
    assert old == original and migration.convert_record(new) == new
    assert new["status"] == "blocked" and new["authorized_origin"] == "user"
    assert new["completion_review_required"]
    assert [c["text"] for c in new["criteria_contract"]["criteria"]] == ["원래 기능", "정정한 전체 목표"]
    assert new["criteria_contract"]["previous_overall_goal"] == "정정 전 목표"
    assert "pursuit" not in new and "done_request" not in new
    assert "pursuit_id" not in new["framing"]


def test_missing_contract_uses_saved_framing_without_inventing_criteria():
    old = record(); old.pop("criteria_contract")
    assert migration.convert_record(old)["criteria_contract"]["criteria"][0]["text"] == "이번 단계"
    old["framing"] = {}
    with pytest.raises(ValueError, match="완료 기준"):
        migration.convert_record(old)


def test_review_snapshot_and_bytes_contract_are_not_rewritten():
    old = record()
    old["snapshot"] = {"response": {"hash": "saved"}, "files": {"file": {"hash": "bytes"}}}
    old["packet"] = {"context": {"criteria_contract": old["criteria_contract"], "completion_request": old["done_request"]}}
    new = migration.convert_record(old, review=True)
    assert new["snapshot"] == old["snapshot"]
    assert "completion_request" not in new["packet"]["context"]
    assert new["packet"]["context"]["criteria_contract"]["criteria"][-1]["text"] == "정정한 전체 목표"


def test_apply_keeps_backup_and_rejects_concurrent_modification(tmp_path):
    path = tmp_path / "data/system_ai_state/repair_continuations/task.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(record()))
    original = path.read_bytes()
    changes, errors = migration.prepare(tmp_path)
    assert not errors and len(changes) == 1
    path.write_text("{}")
    with pytest.raises(ValueError, match="바뀌었습니다"):
        migration.apply(tmp_path, changes, tmp_path / "data/_backups/test")
    path.write_bytes(original)
    migration.apply(tmp_path, changes, tmp_path / "data/_backups/test")
    assert (tmp_path / "data/_backups/test" / path.relative_to(tmp_path)).read_bytes() == original
    assert migration.prepare(tmp_path) == ({}, [])


if __name__ == "__main__":
    import pytest
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
