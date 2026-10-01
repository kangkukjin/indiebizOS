"""재기동은 새 요청이 아니다: 기준·격리본·검수 단계의 지속성을 장애로 검증한다."""
import json
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
import thread_context as tc
import repair_continuation as journal
import api_repair_continuation as continuation_worker
from test_conscious_supervisor import supervisor, finish  # noqa: F401
from test_repair_continuation import record, consumer  # noqa: F401


def authorize(supervisor, tmp_path, monkeypatch):
    from supervision_store import TurnStore
    monkeypatch.setenv("INDIEBIZ_BASE_PATH", str(tmp_path))
    tc.set_task_origin("user")
    supervisor.repair_granted = True
    supervisor.runner.config = {"id": supervisor.owner, "_project_id": "project"}
    supervisor.store = TurnStore(tmp_path / "data/spill/supervision/review")
    supervisor.runner.ai.process_message_stream = lambda *a, **k: pytest.fail("구현 재실행 금지")


def test_saved_framing_skips_new_consciousness_and_preserves_criteria(tmp_path, monkeypatch):
    from cognitive_consciousness import CognitiveConsciousnessMixin
    row = record(tmp_path, resume_task_id="resume")
    row["framing"]["imagined_ibl"] = "이미 실행한 계획"
    monkeypatch.setattr("pursuit_bind.run_consciousness", lambda *a: pytest.fail("의식 재호출"))
    with tc.actor_context(agent_id="agent", task_id="resume", origin="user"), journal.resuming(row):
        output = CognitiveConsciousnessMixin()._run_consciousness_or_reuse(row["goal"], [], repair=True)
        assert output["achievement_criteria"] == row["framing"]["achievement_criteria"]
        assert output["_framing_source"] == "repair_continuation"
        assert "imagined_ibl" not in output and "imagined_ibl" in row["framing"]


def test_real_pipeline_resumes_without_recall_classifier_or_planner(supervisor, tmp_path, monkeypatch):
    from agent_pipeline import CognitivePipelineMixin
    from cognitive_consciousness import CognitiveConsciousnessMixin
    from pathlib import Path
    authorize(supervisor, tmp_path, monkeypatch)
    class Runner(CognitivePipelineMixin, CognitiveConsciousnessMixin):
        config = {"name": "worker", "id": "worker", "_project_id": "project"}
        project_path = Path(supervisor.project_path)
        _associate = lambda *a, **k: pytest.fail("재연상")
        _decide_request_type = lambda *a, **k: pytest.fail("재분류")
        _run_consciousness = lambda *a, **k: pytest.fail("재규정")
        _build_system_prompt_split = lambda *a: ("stable", "")
        _apply_consciousness_to_history = lambda self, history, co: history
        _after_response_async = lambda *a, **kw: None
    runner = Runner()
    runner.ai = supervisor.runner.ai
    runner.ai._provider = None
    runner.ai.process_message_stream = lambda **kw: iter([{"type": "final", "content": "남은 검사 완료"}])
    supervisor.runner = runner
    monkeypatch.setattr("system_ai_core._switch_to_role", lambda *a: None)
    monkeypatch.setattr("consciousness_agent.system_ai_call", lambda *a, **kw: "ACHIEVED")
    row = record(tmp_path, goal=supervisor.message, agent_id=supervisor.owner,
                 resume_task_id=supervisor.task, result={"outcome": "healthy"})
    with journal.resuming(row):
        events = list(runner._cognitive_stream_body(row["goal"], []))
    assert not [e for e in events if e["type"] == "error"]
    assert tc.get_goal_eval_outcome()["achieved"]


@pytest.mark.parametrize("change", [{"goal": "다른 목표"}, {"agent_id": "other"},
                                    {"resume_task_id": "other"}, {"authorized_origin": "training"}])
def test_continuation_cannot_transfer_authority(tmp_path, change):
    row = record(tmp_path, resume_task_id="resume")
    with tc.actor_context(agent_id="agent", task_id="resume", origin="user"), journal.resuming({**row, **change}):
        with pytest.raises(ValueError, match="신원"):
            journal.inherited_framing(row["goal"])


def test_evaluator_timeout_resumes_only_review_after_restart(supervisor, tmp_path, monkeypatch, consumer):
    from repair_resume import restore_review
    authorize(supervisor, tmp_path, monkeypatch)
    module, deliveries, settled = consumer
    def unavailable(*a, **kw):
        raise TimeoutError("평가 서비스 일시 장애")
    monkeypatch.setattr("consciousness_agent.system_ai_call", unavailable)
    assert "평가 대기" in finish(supervisor, "실제 검사 완료")[-1]["content"]
    row = journal.read(supervisor.task, tmp_path)
    assert row["status"] == "waiting_review" and row["review_failures"] == 1
    assert journal.task_state(supervisor.task, tmp_path) == "waiting"
    assert tc.get_goal_eval_outcome()["status"] == "PENDING_REVIEW"
    module.process_pending(tmp_path, "new", lambda r: pytest.fail("재시도 시각 이전 호출"))
    row["retry_at"] = 0
    journal.save(row, tmp_path)
    monkeypatch.setattr("consciousness_agent.system_ai_call", lambda *a, **kw: "ACHIEVED")
    def evaluate_only(item):
        supervisor.task = item["resume_task_id"]
        restore_review(supervisor, item)
        final = finish(supervisor, supervisor.store.text)[-1]["content"]
        return {"response": final, "evaluation": tc.get_goal_eval_outcome()}
    module.process_pending(tmp_path, "new", evaluate_only)
    assert settled == ["completed"] and not deliveries
    assert journal.read(row["task_id"], tmp_path)["status"] == "completed"


def test_review_rejects_changed_artifact_without_model_or_implementation(supervisor, tmp_path, monkeypatch):
    from repair_resume import restore_review
    from supervision_store import digest
    authorize(supervisor, tmp_path, monkeypatch)
    supervisor.store.put_response("저장된 결과")
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("before")
    packet = {"context": {"criteria_contract": {"criteria": [{"id": "C1", "text": "조건"}]}}}
    snapshot = {"response": supervisor.store.manifest(), "delivery": None,
                "files": {str(artifact): {"hash": digest("before"), "mode": "text"}}}
    row = journal.review_checkpoint(supervisor, packet, snapshot, tmp_path)
    artifact.write_text("changed by another task")
    restore_review(supervisor, row)
    output = finish(supervisor, supervisor.store.text)[-1]["content"]
    assert "증거 재사용 불가" in output and not tc.get_goal_eval_outcome()["achieved"]


def test_explicit_unknown_is_not_retried_as_service_failure(supervisor, tmp_path, monkeypatch):
    authorize(supervisor, tmp_path, monkeypatch)
    monkeypatch.setattr("consciousness_agent.system_ai_call", lambda *a, **kw:
                        "UNKNOWN\nUNKNOWN_REASON: blocked\n실제 기기를 사용할 수 없습니다")
    finish(supervisor, "실제 기기 확인 불가")
    assert journal.read(supervisor.task, tmp_path)["status"] == "blocked"


def test_review_failures_keep_pending_and_stop_automatic_calls(supervisor, tmp_path, monkeypatch):
    authorize(supervisor, tmp_path, monkeypatch)
    supervisor.store.put_response("완료 후보")
    row = journal.review_checkpoint(supervisor, {}, {}, tmp_path)
    for _ in range(3):
        assert journal.finish_review(supervisor, {"status": "UNKNOWN", "retryable": True, "reason": "offline"}, tmp_path)
    saved = journal.read(row["task_id"], tmp_path)
    assert saved["status"] == "waiting_review" and saved["retry_at"] is None
    journal.cancel_pending("project", supervisor.owner, tmp_path)
    assert journal.cancelled(saved, tmp_path)


def test_review_stream_runs_evaluator_without_executor(supervisor, tmp_path, monkeypatch):
    from repair_resume import review_stream
    authorize(supervisor, tmp_path, monkeypatch)
    monkeypatch.setattr("consciousness_agent.system_ai_call", lambda *a, **kw: None)
    finish(supervisor, "구현·검사 결과")
    row = journal.read(supervisor.task, tmp_path)
    supervisor.task = row["resume_task_id"]
    supervisor.runner._refresh_execution_prompt = lambda *a, **kw: None
    monkeypatch.setattr("system_ai_core._switch_to_role", lambda *a: None)
    monkeypatch.setattr("consciousness_agent.system_ai_call", lambda *a, **kw: "ACHIEVED")
    with tc.actor_context(agent_id=supervisor.owner, task_id=supervisor.task, origin="user"), journal.resuming(row):
        events = list(review_stream(supervisor.runner, supervisor, row))
        assert tc.get_goal_eval_outcome()["achieved"]
    assert events[-1]["content"] == "구현·검사 결과"


@pytest.mark.parametrize("exit_code,phase", [(0, "verify_remaining"), (9, "repair_active")])
def test_active_check_failure_does_not_rollback_or_repeat(tmp_path, monkeypatch, exit_code, phase):
    row = record(tmp_path, result={"outcome": "healthy", "active_verify_cmd": "test-and-commit"})
    calls = []
    monkeypatch.setattr("red_apply._run_post_verify", lambda *a: calls.append(a) or {"exit_code": exit_code})
    checked = continuation_worker.active_check(row, tmp_path)
    assert checked["phase"] == phase and checked["result"]["outcome"] == "healthy"
    continuation_worker.active_check(journal.read(row["task_id"], tmp_path), tmp_path)
    assert len(calls) == 1


def test_interrupted_active_check_is_reconciled_not_blindly_replayed(tmp_path, monkeypatch):
    row = record(tmp_path, result={"outcome": "healthy", "active_verify_cmd": "commit"},
                 active_verify={"state": "running", "command": "commit"})
    monkeypatch.setattr("red_apply._run_post_verify", lambda *a: pytest.fail("중복 부수효과"))
    assert continuation_worker.active_check(row, tmp_path)["phase"] == "repair_active"


def test_verification_preserves_failure_tail_and_full_output(tmp_path, monkeypatch):
    import red_apply
    monkeypatch.setattr(red_apply, "_wait_healthy", lambda *a: True)
    monkeypatch.setattr("subprocess.run", lambda *a, **kw:
                        SimpleNamespace(returncode=1, stdout="build output\n" * 1000, stderr="ACTUAL FAILURE"))
    result = red_apply._run_post_verify(str(tmp_path), "check")
    assert result["truncated"] and "ACTUAL FAILURE" in result["output"]
    from pathlib import Path
    full = json.loads(Path(result["output_path"]).read_text())
    assert full["output"].endswith("ACTUAL FAILURE") and len(full["output"]) > len(result["output"])


def test_apply_schedule_distinguishes_before_and_after_activation(tmp_path, monkeypatch):
    from test_repair_staging import _load_handler, _make_repo
    staging = _load_handler()._staging_mod()
    repo = _make_repo(tmp_path / "repo")
    monkeypatch.setenv("INDIEBIZ_REPAIR_NO_SPAWN", "1")
    monkeypatch.setattr(staging, "_grant_identity", lambda: ("parent", "agent", "수리"))
    monkeypatch.setattr(staging, "_current_episode_id", lambda *a: None)
    session = staging.ensure_session(str(repo), "parent")
    result = staging._schedule_deferred_apply(str(repo), session, [], "read-check", "write-and-commit")
    assert result["scheduled"]
    job = json.loads((repo / staging.SESSION_DIRNAME / "parent.apply.json").read_text())
    assert job["verify_cmd"] == "read-check" and job["active_verify_cmd"] == "write-and-commit"


def test_rollback_reuses_staged_files_and_dependencies(tmp_path, monkeypatch):
    from test_repair_staging import _load_handler, _make_repo
    staging = _load_handler()._staging_mod()
    repo = _make_repo(tmp_path / "repo")
    monkeypatch.setattr(staging, "_repair_owner", lambda: "agent")
    original = staging.ensure_session(str(repo), "parent")
    wt = repo / original["worktree"]
    (wt / "backend/cognition/victim.py").write_text("VALUE='repaired'\n")
    (wt / "installed_dependency").write_text("keep")
    original["status"] = "applied"
    original["files"] = {str(repo / "backend/cognition/victim.py"): {
        "staged": str(wt / "backend/cognition/victim.py"), "op": "write"}}
    staging._save_session(str(repo), original)
    row = {"task_id": "parent", "resume_task_id": "child", "result": {"outcome": "rolled_back"}}
    with tc.actor_context(agent_id="agent", task_id="child", origin="user"), journal.resuming(row):
        resumed = staging.ensure_session(str(repo), "child")
    assert resumed["worktree"] == original["worktree"] and resumed["files"] == original["files"]
    staging._remove_worktree(str(repo), staging.read_session(str(repo), "parent"))
    assert (wt / "installed_dependency").read_text() == "keep"
    assert "repaired" in (wt / "backend/cognition/victim.py").read_text()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
