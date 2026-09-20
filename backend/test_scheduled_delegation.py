"""주간 포식 재조사의 직접 발화 → cross 위임 → 부모 원장·컨텍스트 회귀."""
import sys
import threading
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest

import system_ai_memory as memory
import thread_context as tc
from calendar_actions import CalendarActionsMixin


@pytest.fixture
def scheduled(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "MEMORY_DB_PATH", tmp_path / "tasks.db")
    monkeypatch.setattr(memory, "DATA_PATH", tmp_path)
    previous = tc.snapshot()
    tc.clear_all_context()
    notices, history, children = [], [], []
    target = SimpleNamespace(
        config={"id": "agent_test", "name": "조사자"},
        db=SimpleNamespace(create_task=lambda **kw: children.append(kw)),
    )
    runner = SimpleNamespace(
        agent_registry={"fixture:agent_test": target},
        internal_messages={}, _lock=threading.Lock(),
    )
    monkeypatch.setitem(sys.modules, "agent_runner", SimpleNamespace(AgentRunner=runner))
    monkeypatch.setitem(sys.modules, "notification_manager", SimpleNamespace(
        get_notification_manager=lambda: SimpleNamespace(
            success=lambda **kw: notices.append(kw),
            warning=lambda **kw: notices.append(kw))))
    import trigger_engine
    monkeypatch.setattr(trigger_engine, "add_history", lambda **kw: history.append(kw))
    import ibl_routing
    from routing_system import _delegate_unified
    monkeypatch.setitem(ibl_routing._SYSTEM_CAPS, "delegate", _delegate_unified)
    host = CalendarActionsMixin()
    host._log = lambda text: None
    task = {"id": "evt_test", "title": "[IBL] forage_resurvey_fixture",
            "action_params": {"trigger_id": "trg_test", "pipeline":
                '[others:delegate]{scope:"cross", agent_id:"fixture/조사자", '
                'message:"프로젝트 폴더를 재조사해 기억을 갱신해라"}'}}
    yield SimpleNamespace(host=host, task=task, notices=notices,
                          history=history, children=children, runner=runner)
    tc.restore(previous)


def test_ownerless_schedule_delegates_with_durable_parent(scheduled):
    s = scheduled
    result = s.host._action_run_pipeline(s.task)
    assert result["success"], result
    assert result["queued"] is True
    parent = memory.get_task(result["delegation_task_ids"][0])
    assert parent["status"] == "pending"
    assert parent["requester"] == "scheduler"
    assert parent["pending_delegations"] == 1
    assert s.children[0]["parent_task_id"] == parent["task_id"]
    child_id = s.children[0]["task_id"]
    assert s.runner.internal_messages["fixture:agent_test"][0]["task_id"] == child_id
    assert s.history[0]["success"] is True
    assert s.notices[0]["title"] == "스케줄 위임 접수"
    assert tc.get_current_task_id() is None and not tc.did_call_agent()
    # 기존 결과 회수기가 부모를 찾아 응답을 누적할 수 있어야 한다.
    assert memory.decrement_pending_and_update_context(parent["task_id"], new_response={
        "child_task_id": child_id, "response": "재조사 완료"}) == 0
    assert "재조사 완료" in memory.get_task(parent["task_id"])["delegation_context"]


@pytest.mark.parametrize("failure", [False, True])
def test_non_delegating_pipeline_preserves_context_without_system_task(scheduled, monkeypatch, failure):
    import workflow_engine
    tc.set_current_task_id("caller_task")
    tc.set_current_agent_id("caller")
    caller_origin = "user"
    tc.set_task_origin(caller_origin)
    tc.set_called_agent(True)

    def execute(*args, **kwargs):
        # same 위임은 프로젝트 DB를 쓰므로 시스템 DB의 부모를 끼워 넣으면 안 된다.
        assert not tc.get_current_task_id()
        assert tc.get_task_origin() == "scheduler"
        if failure:
            raise RuntimeError("pipeline failed")
        return {"success": True}

    monkeypatch.setattr(workflow_engine, "execute_pipeline", execute)
    result = scheduled.host._action_run_pipeline(scheduled.task)
    assert result["success"] is (not failure)
    assert not memory.MEMORY_DB_PATH.exists()
    assert tc.get_current_task_id() == "caller_task"
    assert tc.get_current_agent_id() == "caller"
    assert tc.get_task_origin() == "user" and tc.did_call_agent()


@pytest.mark.parametrize("exception", [False, True])
def test_failed_dispatch_closes_parent(scheduled, monkeypatch, exception):
    if exception:
        def fail(**kwargs):
            raise RuntimeError("child write failed")
        scheduled.runner.agent_registry["fixture:agent_test"].db.create_task = fail
    else:
        scheduled.task["action_params"]["pipeline"] = (
            '[others:delegate]{scope:"cross", agent_id:"nonexistent_schedule_fixture/absent", '
            'message:"재조사"}')
    result = scheduled.host._action_run_pipeline(scheduled.task)
    assert result["success"] is False
    with memory._get_connection() as conn:
        parents = conn.execute("SELECT * FROM tasks").fetchall()
    assert len(parents) == 1 and parents[0]["status"] == "completed"
    assert parents[0]["pending_delegations"] == 0
    assert "오류" in parents[0]["result"]
    assert not scheduled.children
    assert tc.get_current_task_id() is None


def test_parent_stays_for_fast_child_report(scheduled, monkeypatch):
    from system_ai_runner import SystemAIRunner
    # 실제 AI 호출 없이 원장의 완료 처리를 검증할 수 있도록 러너는 시작하지 않는다.
    original = scheduled.runner.agent_registry["fixture:agent_test"].db.create_task

    def fast_child(**kwargs):
        original(**kwargs)
        memory.decrement_pending_and_update_context(kwargs["parent_task_id"], new_response={
            "child_task_id": kwargs["task_id"], "response": "완료"})

    scheduled.runner.agent_registry["fixture:agent_test"].db.create_task = fast_child
    result = scheduled.host._action_run_pipeline(scheduled.task)
    parent = memory.get_task(result["delegation_task_ids"][0])
    assert parent["pending_delegations"] == 0
    assert parent["status"] == "pending" and result["queued"]
    monkeypatch.setattr("system_ai_runner.save_conversation", lambda *a, **k: None)
    SystemAIRunner._finalize_task(object.__new__(SystemAIRunner), parent["task_id"], "재조사 완료")
    assert memory.get_task(parent["task_id"])["status"] == "completed"


def test_chat_delegation_keeps_existing_parent(scheduled):
    from routing_system import _delegate_unified
    memory.create_task("chat_parent", "user@gui", "gui", "기존 대화")
    tc.set_current_task_id("chat_parent")
    reply = _delegate_unified({"scope": "cross", "agent_id": "fixture/조사자",
                               "message": "재조사"}, ".")
    assert "위임했습니다" in reply
    assert scheduled.children[0]["parent_task_id"] == "chat_parent"
    assert tc.get_current_task_id() == "chat_parent"


def test_repeated_schedules_get_separate_parents(scheduled):
    first = scheduled.host._action_run_pipeline(scheduled.task)
    second = scheduled.host._action_run_pipeline(scheduled.task)
    ids = [r["delegation_task_ids"][0] for r in (first, second)]
    assert ids[0] != ids[1]
    assert [c["parent_task_id"] for c in scheduled.children] == ids
    assert all(memory.get_task(i)["pending_delegations"] == 1 for i in ids)


@pytest.mark.parametrize("body", ["완료한 원문\n/outputs/report.html", "부분 실패: 자료를 읽지 못했습니다."])
def test_scheduled_result_delivery_never_calls_model_and_preserves_failure(scheduled, monkeypatch, body):
    from system_ai_runner import SystemAIRunner
    parent_id = scheduled.host._action_run_pipeline(scheduled.task)["delegation_task_ids"][0]
    child_id = scheduled.children[0]["task_id"]
    memory.decrement_pending_and_update_context(parent_id, new_response={
        "child_task_id": child_id, "response": body})
    runner = object.__new__(SystemAIRunner)
    runner._sync_gear = lambda: None
    runner._run_cognitive_message = lambda *a, **k: pytest.fail("완료 전달에 모델 호출")
    # self.ai조차 만들지 않은 러너로 실제 메시지 경계를 검증한다.
    saved = []
    monkeypatch.setattr("system_ai_runner.save_conversation", lambda *a, **k: saved.append((a, k)))
    monkeypatch.setattr(SystemAIRunner, "internal_messages", [
        {"task_id": parent_id, "from_agent": "조사자", "content": "이 텍스트 대신 원장을 읽어야 함"},
        {"task_id": parent_id, "from_agent": "조사자", "content": "중복 도착"}])
    runner._check_internal_messages()
    assert memory.get_task(parent_id)["status"] == "completed"
    assert [a[1] for a, k in saved if a and a[0] == "assistant"] == [body]


def test_pending_or_chat_delegation_is_not_auto_finalized(scheduled):
    from system_ai_runner import SystemAIRunner
    runner = object.__new__(SystemAIRunner)
    parent_id = scheduled.host._action_run_pipeline(scheduled.task)["delegation_task_ids"][0]
    assert not runner._finish_scheduled_report(parent_id)
    memory.create_task("ordinary_chat", "user@gui", "gui", "調査")
    assert not runner._finish_scheduled_report("ordinary_chat")
    assert memory.get_task(parent_id)["status"] == "pending"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
