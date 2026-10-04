"""정기 실행의 신원(2026-10-04): 무소유 스케줄이 시스템 AI 의 수리 그랜트에 편승하던 것.

사건: 10-03~04 매시 뉴스 작업이 시스템 AI 수리 중에 돌면 task_id="" 폴백(red_grant.active_grant 의
"신원 유실 심")으로 수리 그랜트를 열어 수리 사본 안에서 실행됐다 — 사본에 outputs/ 가 없어
FileNotFoundError. 정기 실행에 고유 task_id 를 주면 "task_id 는 자기 슬롯만 연다"는 기존 규칙이
막는다. 실행 ID 없는 호출도 권한을 빌리지 못한다. 스케줄 위임은 그 task_id 를 그대로 쓴다.
"""
import boot_paths  # noqa: F401
import pytest

import red_grant as rg
import repair_context
import thread_context as tc


@pytest.fixture(autouse=True)
def _clean():
    rg.revoke_grant()
    saved = tc.snapshot()
    yield
    rg.revoke_grant()
    tc.restore(saved)


def _system_ai_is_repairing():
    rg.issue_grant(agent_id="system_ai", task_id="task_sysai_repair01", reason="수리 중")
    assert rg.active_grant(task_id="task_sysai_repair01", agent_id="system_ai")


def test_scheduled_pipeline_runs_outside_the_repair_grant(monkeypatch, tmp_path):
    import ibl_v2_entry
    from ibl_scheduled import execute_scheduled
    _system_ai_is_repairing()
    # 종전 사고 신원도 이제 닫힌다 — 실행 ID 누락은 권한 공유가 아니다.
    with tc.actor_context(agent_id="system_ai", task_id="", origin="scheduler"):
        assert repair_context.active() is None
    seen = []

    def handle(payload, run_path, agent_id=None):
        seen.append((tc.get_current_agent_id(), tc.get_current_task_id(), repair_context.active()))
        return {"success": True, "final_result": "ok", "results": []}

    monkeypatch.setattr(ibl_v2_entry, "handle_request", handle)
    for _ in range(2):
        assert execute_scheduled("return 1", str(tmp_path), None)["success"]
    assert [s[0] for s in seen] == ["system_ai", "system_ai"]
    assert all(s[1].startswith("task_schedule_") and s[2] is None for s in seen)
    assert seen[0][1] != seen[1][1]
    assert not tc.get_current_task_id()


def test_scheduled_workflow_run_gets_its_own_task(monkeypatch):
    import workflow_engine
    from calendar_actions import CalendarActionsMixin
    _system_ai_is_repairing()
    seen = {}

    def run(workflow_id, run_path, params=None):
        seen.update(task=tc.get_current_task_id(), grant=repair_context.active(), channel=tc.get_call_channel())
        return {"success": True}

    monkeypatch.setattr(workflow_engine, "execute_workflow", run)

    class Scheduler(CalendarActionsMixin):
        def _log(self, *a, **k):
            pass

        def _should_notify_result(self, task, result):
            return False

    assert Scheduler()._action_run_workflow({"action_params": {"workflow_id": "x"}})["success"]
    assert seen["task"].startswith("task_schedule_") and seen["grant"] is None and seen["channel"] == "scheduler"


def test_scheduled_delegation_parent_is_the_run_task(monkeypatch, tmp_path):
    import system_ai_memory as sam
    import system_ai_tools as sat
    monkeypatch.setattr(sam, "MEMORY_DB_PATH", tmp_path / "memory.db")
    tool_input = {"project_id": "__없는_프로젝트__", "agent_id": "a", "message": "m"}
    with tc.actor_context(agent_id="system_ai", task_id="task_schedule_test01", origin="scheduler"):
        tc.set_call_channel("scheduler", override=True)
        reply = sat._execute_call_project_agent(tool_input)
    assert reply.startswith("오류: 프로젝트")
    parent = sam.get_task("task_schedule_test01")
    assert parent and parent["requester"] == "scheduler" and parent["status"] == "completed"
    # 부모 기록이 이미 있는 신원은 스케줄 분기를 타지 않는다(기존 러너 경로).
    sam.create_task(task_id="task_schedule_test02", requester="scheduler", requester_channel="scheduler", original_request="m")
    with tc.actor_context(agent_id="system_ai", task_id="task_schedule_test02", origin="scheduler"):
        tc.set_call_channel("scheduler", override=True)
        sat._execute_call_project_agent(tool_input)
    assert sam.get_task("task_schedule_test02")["status"] != "completed"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
