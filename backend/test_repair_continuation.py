"""적용 대기→재기동→검증/보완의 연결. 실제 모델·라이브 재기동 없이 장애 경계를 재현한다."""
import json
from types import SimpleNamespace

import pytest
import boot_paths  # noqa: F401
import repair_continuation as journal
from restart_protocol import atomic_json, read_json
from test_conscious_supervisor import supervisor, finish  # noqa: F401
import thread_context as tc


def scheduled(base, task="task-repair", result=None):
    job_path = base / "data/system_ai_state/repair_sessions" / (task + ".apply.json")
    job = {"key": task, "task_id": task, "repo": str(base), "scheduled_at": "now",
           "restart_request_id": "red-test", "post_verify": result, "verify_cmd": "run-check"}
    atomic_json(job_path, job)
    atomic_json(job_path.with_name(task + ".json"), {"status": "apply_scheduled"})
    return job_path


def record(base, **changes):
    task = changes.get("task_id", "task-repair")
    path = scheduled(base, task)
    row = {"task_id": task, "root_task_id": task, "attempt": 1, "failures": [],
           "job_path": str(path), "scheduled_at": "now", "status": "waiting_apply",
           "authorized_origin": "user", "goal": "영어 표시를 마무리해줘 #repair",
           "project_id": "project", "agent_id": "agent", "system_ai": False,
           "framing": {"achievement_criteria": "실제 화면에서 확인"}, "store": "/old/evidence",
           "response": "적용 예약", **changes}
    return journal.save(row, base)


def receipt(base, task="task-repair", outcome="healthy"):
    atomic_json(base / "data/restart_control/results/red-test.json", {"outcome": outcome})
    atomic_json(base / "data/system_ai_state/red_backups" / task / "result.json", {"outcome": outcome})


def test_scheduled_repair_is_pending_and_never_calls_final_model(supervisor, monkeypatch, tmp_path):
    monkeypatch.setenv("INDIEBIZ_BASE_PATH", str(tmp_path))
    scheduled(tmp_path, supervisor.task)
    tc.set_task_origin("user")
    supervisor.repair_granted = True
    supervisor.runner.config = {"id": "agent", "_project_id": "project"}
    monkeypatch.setattr("final_evaluator.invoke", lambda *a, **k: pytest.fail("적용 전 완료 평가"))
    events = finish(supervisor, "수정 적용을 예약했습니다")
    assert "적용 대기" in events[-1]["content"]
    assert tc.get_goal_eval_outcome()["status"] == "PENDING_APPLY"
    row = journal.read(supervisor.task, tmp_path)
    assert row["goal"] == supervisor.message and row["store"] == str(supervisor.store.directory)
    assert journal.task_state(supervisor.task, tmp_path) == "waiting"


@pytest.mark.parametrize("origin,granted,cancelled", [("training", True, False), (None, True, False),
                                                     ("user", False, False), ("user", True, True)])
def test_no_continuation_without_live_user_authorization(supervisor, monkeypatch, tmp_path, origin, granted, cancelled):
    scheduled(tmp_path, supervisor.task)
    tc.set_task_origin(origin)
    supervisor.repair_granted = granted
    monkeypatch.setattr(supervisor, "cancelled", lambda: cancelled)
    assert journal.defer(supervisor, "draft", tmp_path) is None
    assert journal.read(supervisor.task, tmp_path) is None


def test_waits_for_controller_receipt_even_when_verify_output_exists(tmp_path):
    row = record(tmp_path)
    assert journal.outcome(row, tmp_path) is None
    receipt(tmp_path, outcome="rolled_back")
    assert journal.outcome(row, tmp_path)["outcome"] == "rolled_back"
    changed = read_json(row["job_path"])
    changed["scheduled_at"] = "replaced"
    atomic_json(row["job_path"], changed)
    with pytest.raises(ValueError, match="판본"):
        journal.outcome(row, tmp_path)


@pytest.fixture
def consumer(monkeypatch, tmp_path):
    import api_repair_continuation as consumer
    monkeypatch.setenv("INDIEBIZ_BASE_PATH", str(tmp_path))
    deliveries, settled = [], []
    monkeypatch.setattr(consumer, "_deliver_blocked", lambda row: deliveries.append(row))
    def settle(row, status, response, base):
        current = journal.read(row["task_id"], base)
        journal.save({**current, "status": status}, base)
        settled.append(status)
    monkeypatch.setattr(consumer, "_settle", settle)
    return consumer, deliveries, settled


@pytest.mark.parametrize("outcome", ["healthy", "rolled_back"])
def test_resume_once_with_original_goal_and_apply_result(tmp_path, consumer, outcome):
    module, deliveries, settled = consumer
    row = record(tmp_path)
    calls = []
    def execute(item):
        calls.append(item)
        assert journal.current() == item
        assert item["goal"] == row["goal"] and item["result"]["outcome"] == outcome
        return {"response": "라이브 검증 완료", "evaluation": {"achieved": True}}
    module.process_pending(tmp_path, "g2", execute)
    assert not calls
    receipt(tmp_path, outcome=outcome)
    module.process_pending(tmp_path, "g2", execute)
    module.process_pending(tmp_path, "g2", execute)
    module.process_pending(tmp_path, "g3", execute)
    assert len(calls) == 1 and settled == ["completed"] and not deliveries


def test_dead_worker_resumes_same_identity_without_recounting_failure(tmp_path, consumer):
    module, _, _ = consumer
    row = record(tmp_path)
    receipt(tmp_path, outcome="rolled_back")
    row = journal.claim(row, "dead", journal.outcome(row, tmp_path), tmp_path)
    calls = []
    def execute(item):
        calls.append(item)
        assert item["resume_task_id"] == row["resume_task_id"]
        assert len(item["failures"]) == 1
        return {"response": "완료", "evaluation": {"achieved": True}}
    module.process_pending(tmp_path, "dead", execute)
    assert not calls
    module.process_pending(tmp_path, "new", execute)
    assert len(calls) == 1


def test_child_apply_survives_parent_finish_and_is_not_completed(tmp_path, consumer):
    module, _, settled = consumer
    parent = record(tmp_path)
    receipt(tmp_path)
    def execute(row):
        child = record(tmp_path, task_id=row["resume_task_id"], root_task_id=row["root_task_id"],
                       parent_task_id=row["task_id"], attempt=2)
        journal.save({**row, "status": "continued", "child_task_id": child["task_id"]}, tmp_path)
        return {"response": "재적용 대기", "evaluation": {"achieved": False, "status": "PENDING_APPLY"}}
    module.process_pending(tmp_path, "g2", execute)
    assert journal.read(parent["task_id"], tmp_path)["status"] == "continued"
    assert not settled


def test_cancellation_prevents_queued_resume(tmp_path, consumer):
    module, _, settled = consumer
    row = record(tmp_path)
    receipt(tmp_path)
    journal.cancel_pending("other-project", base=tmp_path)
    assert not journal.cancelled(row, tmp_path)
    journal.cancel_pending("project", "agent", tmp_path)
    module.process_pending(tmp_path, "g2", lambda row: pytest.fail("취소 뒤 실행"))
    assert settled == ["cancelled"]


def test_unknown_after_recovery_is_explicitly_blocked_not_completed(tmp_path, consumer):
    module, deliveries, settled = consumer
    record(tmp_path)
    receipt(tmp_path)
    module.process_pending(tmp_path, "g2", lambda row: {"response": "외부 조건 미충족",
                           "evaluation": {"achieved": False, "status": "UNKNOWN", "reason": "접근 불가"}})
    assert settled == ["blocked"] and deliveries[0]["reason"] == "접근 불가"


def test_repeated_same_apply_failure_does_not_spin_models(tmp_path):
    result = {"outcome": "rolled_back", "post_verify": {"exit_code": 1, "stdout": "broken"}}
    first = journal.claim(record(tmp_path), "g", result, tmp_path)
    second = journal.claim(record(tmp_path, failures=first["failures"], attempt=2), "g", result, tmp_path)
    third = journal.claim(record(tmp_path, failures=second["failures"], attempt=3), "g", result, tmp_path)
    assert third["status"] == "blocked" and "3회" in third["reason"]


def test_rollback_preserves_original_verify_failure(tmp_path, monkeypatch):
    from restart_red import verify_after_boot
    job_path = scheduled(tmp_path)
    manifest = tmp_path / "data/system_ai_state/red_backups/task-repair/manifest.json"
    atomic_json(manifest, {"files": {"backend/example.py": "before.py"}})
    failed = {"ran": True, "exit_code": 7, "stdout": "assert language == en", "stderr": "failure"}
    calls, reports = [], []
    monkeypatch.setattr("red_apply._run_post_verify", lambda *a: calls.append(1) or failed)
    staging = SimpleNamespace(task_key=lambda x: x, write_followup=lambda *a: reports.append(a[-1]))
    monkeypatch.setattr("red_apply._load_handler", lambda *a: SimpleNamespace(_staging_mod=lambda: staging))
    state = {"generation": "new", "request": {"operation": "red_apply", "payload": {
        "manifest_path": str(manifest), "job_path": str(job_path)}}}
    assert verify_after_boot(tmp_path, state) is False
    assert verify_after_boot(tmp_path, {**state, "rollback_attempted": True}) is True
    assert calls == [1]
    assert read_json(job_path)["post_verify"] == failed
    assert reports[-1]["post_verify"] == failed
    assert read_json(manifest.with_name("result.json"))["post_verify"] == failed


def test_task_database_does_not_complete_pending_apply(tmp_path, monkeypatch):
    from conversation_db import ConversationDB
    monkeypatch.setenv("INDIEBIZ_BASE_PATH", str(tmp_path))
    record(tmp_path)
    db = ConversationDB(str(tmp_path / "conversation.db"))
    db.create_task("task-repair", "user@gui", "gui", "수리", "agent")
    assert db.complete_task("task-repair", "예약")
    assert db.get_task("task-repair")["status"] == "waiting"
    assert db.get_task("task-repair")["completed_at"] is None
    row = journal.read("task-repair", tmp_path)
    journal.save({**row, "status": "completed"}, tmp_path)
    assert db.complete_task("task-repair", "실제 완료")
    assert db.get_task("task-repair")["status"] == "completed"


def test_unknown_evidence_returns_to_executor_and_rechecks_raw_proof(supervisor, monkeypatch):
    proof = supervisor.store.evidence("중간 검사 실제 출력: en -> ko -> en PASS")
    calls = []
    def evaluate(prompt, **kw):
        calls.append(prompt)
        if len(calls) == 1:
            return "UNKNOWN\nUNKNOWN_REASON: evidence\nC1 검사 결과 원문이 필요합니다."
        assert "중간 검사 실제 출력" in prompt
        return "ACHIEVED"
    def stream(prompt, **kw):
        assert "부족한 증거만" in prompt
        supervisor.tool({"op": "evidence", "id": proof["id"]})
        supervisor.tool({"op": "keep", "reason": "기존 원문 검증 확인"})
        yield {"type": "final", "content": "PATCH_DONE"}
    monkeypatch.setattr("consciousness_agent.system_ai_call", evaluate)
    supervisor.runner.ai.process_message_stream = stream
    assert finish(supervisor, "구현 결과")[-1]["content"] == "구현 결과"
    assert len(calls) == 2 and tc.get_goal_eval_outcome()["achieved"]


@pytest.mark.parametrize("reason", ["criteria", "blocked"])
def test_unknown_non_evidence_does_not_start_blind_repair(supervisor, monkeypatch, reason):
    monkeypatch.setattr("consciousness_agent.system_ai_call", lambda *a, **kw:
                        f"UNKNOWN\nUNKNOWN_REASON: {reason}\n사용자 확인이 필요합니다.")
    supervisor.runner.ai.process_message_stream = lambda *a, **kw: pytest.fail("무관한 자동 보완")
    assert "미승인" in finish(supervisor, "대기")[-1]["content"]


def test_evidence_recovery_does_not_spend_defect_repair(supervisor, monkeypatch):
    calls, repairs = [], []
    def evaluate(*args, **kwargs):
        calls.append(1)
        return ["UNKNOWN\nUNKNOWN_REASON: evidence\nC1 원문 필요",
                'NOT_ACHIEVED\nSEVERITY: 2\nREPAIR_SCOPE: research\nREPAIR_BLOCK_IDS: ["0"]\n'
                'DEFECTS: [{"criterion_id":"C1","evidence":"실제 화면에 한국어 잔존","repair":"누락 연결 수정"}]',
                "ACHIEVED"][len(calls) - 1]
    def stream(*a, **kw):
        repairs.append(1)
        supervisor.tool({"op": "keep", "reason": "증거 확보" if len(repairs) == 1 else "실제 결함 보완"})
        yield {"type": "final", "content": "PATCH_DONE"}
    monkeypatch.setattr("consciousness_agent.system_ai_call", evaluate)
    supervisor.runner.ai.process_message_stream = stream
    finish(supervisor, "결과")
    assert len(calls) == 3 and len(repairs) == 2 and tc.get_goal_eval_outcome()["achieved"]


def test_file_lock_prevents_duplicate_workers(tmp_path, consumer):
    from restart_protocol import OwnerLock
    module, _, _ = consumer
    row = record(tmp_path)
    receipt(tmp_path)
    lock = OwnerLock(journal.directory(tmp_path) / (journal.key(row["task_id"]) + ".lock"))
    assert lock.acquire()
    try:
        module.process_pending(tmp_path, "g2", lambda row: pytest.fail("잠금 중복 실행"))
    finally:
        lock.close()


def test_project_resume_uses_owner_pipeline_without_fake_user_message(tmp_path, monkeypatch):
    import api_agents
    from conversation_db import ConversationDB
    previous = tc.snapshot()
    monkeypatch.setenv("INDIEBIZ_BASE_PATH", str(tmp_path))
    monkeypatch.setattr(api_agents, "project_manager", SimpleNamespace(get_project_path=lambda project: tmp_path))
    monkeypatch.setattr("episode_logger.EpisodeLogger.start_episode", lambda *a, **k: None)
    monkeypatch.setattr("episode_logger.EpisodeLogger.end_episode", lambda *a, **k: None)
    row = record(tmp_path)
    row = journal.claim(row, "g2", {"outcome": "healthy"}, tmp_path)
    calls = []
    def stream(message, history, **kwargs):
        calls.append((message, kwargs))
        assert tc.get_task_origin() == "user"
        assert tc.get_current_task_id() == row["resume_task_id"]
        assert "원래 사용자가 승인" in kwargs["extra_role"]
        tc.set_goal_eval_outcome(True, status="ACHIEVED")
        yield {"type": "final", "content": "라이브 확인 완료"}
    runner = SimpleNamespace(config={"name": "데이터"}, cognitive_stream=stream)
    try:
        answer = api_agents._run_agent_command("project", "agent", runner, row["goal"], continuation=row)
        assert answer["evaluation"]["achieved"] and len(calls) == 1
        db = ConversationDB(str(tmp_path / "conversations.db"))
        assert db.get_task(row["resume_task_id"])["parent_task_id"] == row["task_id"]
        with db.get_connection() as conn:
            rows = conn.execute("SELECT content FROM messages").fetchall()
            assert [r[0] for r in rows] == ["라이브 확인 완료"]
    finally:
        tc.restore(previous)


def test_system_ai_pending_is_not_marked_complete(tmp_path, monkeypatch):
    import system_ai_memory as memory
    monkeypatch.setenv("INDIEBIZ_BASE_PATH", str(tmp_path))
    monkeypatch.setattr(memory, "MEMORY_DB_PATH", tmp_path / "memory.db")
    record(tmp_path)
    memory.create_task("task-repair", "user@gui", "system_ai", "수리")
    assert memory.complete_task("task-repair", "적용 예약")
    assert memory.get_task("task-repair")["status"] == "waiting"
    assert memory.get_task("task-repair")["completed_at"] is None


def test_pending_apply_episode_does_not_look_achieved():
    from episode_logger import _final_evaluation_result
    assert _final_evaluation_result("[GoalEval] 최종 판정: PENDING_APPLY") == "PENDING_APPLY"


def test_activate_schedules_independent_resume_only_when_idle(tmp_path, monkeypatch):
    import api_repair_continuation as consumer
    import runtime_work
    monkeypatch.setenv("INDIEBIZ_BASE_PATH", str(tmp_path))
    record(tmp_path)
    calls, bound = [], []
    work = SimpleNamespace(phase="ACTIVE", generation="g2", snapshot=lambda: {"active_roots": 1})
    monkeypatch.setattr(runtime_work, "registry", lambda: work)
    monkeypatch.setattr(consumer, "_last_scan", 0)
    monkeypatch.setattr(consumer, "process_pending", lambda *a: calls.append(a))
    def bind(fn, label):
        bound.append(label)
        return fn
    monkeypatch.setattr(runtime_work, "bind_lease", bind)
    monkeypatch.setattr(consumer.threading, "Thread", lambda target, **k: SimpleNamespace(start=target))
    consumer.kick()
    assert not calls and not bound
    work.snapshot = lambda: {"active_roots": 0, "active_children": 0}
    monkeypatch.setattr(consumer, "_last_scan", 0)
    consumer.kick()
    assert calls == [(tmp_path, "g2")] and bound == ["repair-continuation"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
