"""수리 root 원장(G3·G5): 단일 전이 계약 — revision·fencing·종결·재개·전달 분리."""
import pytest
import boot_paths  # noqa: F401
import repair_root as R


def test_open_is_idempotent_and_transition_bumps_revision(tmp_path):
    row = R.open_root(tmp_path, "task-1", {"goal": "고쳐줘", "entrance": "system_ai"})
    assert row["stage"] == "diagnose" and row["revision"] == 0
    assert R.open_root(tmp_path, "task-1", {"goal": "다른 원문"})["request"]["goal"] == "고쳐줘"
    row = R.transition(tmp_path, "task-1", stage="prepare", outcome="checks_running", next_action="검사 실행")
    assert row["revision"] == 1 and row["stage"] == "prepare" and row["outcomes"]["repair"] == "checks_running"
    assert row["history"][-1]["change"]["stage"] == "prepare"
    with pytest.raises(R.StaleRevision):
        R.transition(tmp_path, "task-1", expected_revision=0, stage="check")
    assert R.transition(tmp_path, "task-1", expected_revision=1, stage="check")["stage"] == "check"


def test_fencing_token_rejects_late_owner(tmp_path):
    R.open_root(tmp_path, "task-2", {})
    token = R.claim(tmp_path, "task-2", "controller", ttl_s=600)
    with pytest.raises(R.StaleOwner):
        R.transition(tmp_path, "task-2", fence="old-owner", stage="activate")
    row = R.transition(tmp_path, "task-2", fence=token, stage="activate", service="active_new_generation")
    assert row["stage"] == "activate" and row["outcomes"]["service"] == "active_new_generation"
    # 소유자가 없는 전이(fence 생략)는 허용된다 — 관측자 갱신.
    R.transition(tmp_path, "task-2", evidence={"note": 1})


def test_unknown_stage_rejected_and_projection_reports_terminal(tmp_path):
    R.open_root(tmp_path, "task-3", {})
    with pytest.raises(ValueError):
        R.transition(tmp_path, "task-3", stage="teleport")
    R.close(tmp_path, "task-3", complete=False, reason="원 증상 재현 불가", resume_condition="재현 입력 확보 뒤 재개")
    view = R.projection(tmp_path, "task-3")
    assert view["terminal"] and not view["complete"] and view["stage"] == "incomplete"
    assert view["resume_condition"] == "재현 입력 확보 뒤 재개" and view["repair_outcome"] == "incomplete"
    # 종결 뒤 재개는 새 시도다.
    row = R.transition(tmp_path, "task-3", stage="diagnose", outcome="in_progress")
    assert row["attempt"] == 2 and row["cost"]["resumes"] == 1
    R.close(tmp_path, "task-3", complete=True, reason="완료", symptom_recheck={"verdict": "verified", "note": "활성 확인"})
    view = R.projection(tmp_path, "task-3")
    assert view["complete"] and view["symptom_recheck"]["verdict"] == "verified" and view["resume_condition"] is None


def test_delivery_is_orthogonal_to_completion(tmp_path):
    R.open_root(tmp_path, "task-4", {})
    R.close(tmp_path, "task-4", complete=True, reason="완료")
    event = R.delivery_event_id("task-4", "done")
    R.note_delivery(tmp_path, "task-4", "failed", event, "채널 끊김")
    view = R.projection(tmp_path, "task-4")
    assert view["complete"] and view["delivery_status"] == "failed"
    R.note_delivery(tmp_path, "task-4", "delivered", event)
    view = R.projection(tmp_path, "task-4")
    assert view["complete"] and view["delivery_status"] == "delivered" and view["stage"] == "complete"


def test_controller_results_map_to_stages(tmp_path):
    from restart_protocol import atomic_json
    job = tmp_path / "data/system_ai_state/repair_sessions/task-5.apply.json"
    atomic_json(job, {"key": "task-5", "task_id": "task-5", "repo": str(tmp_path)})
    R.note_controller_result(tmp_path, str(job), {"outcome": "restarted", "code_digest": "gen1", "generation_dir": "/g1"}, {})
    assert R.projection(tmp_path, "task-5")["stage"] == "activate"
    assert R.projection(tmp_path, "task-5")["artifact"]["generation"] == "gen1"
    R.note_controller_result(tmp_path, str(job), {"outcome": "rolled_back", "note": "boot failed"}, {})
    view = R.projection(tmp_path, "task-5")
    assert view["repair_outcome"] == "activation_failed" and view["service_health"] == "recovered_previous"
    assert view["resume_condition"]
    R.note_controller_result(tmp_path, str(job), {"outcome": "apply_rejected", "error": "충돌"}, {})
    assert R.projection(tmp_path, "task-5")["stage"] == "check"


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
