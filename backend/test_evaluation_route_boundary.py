"""의식 없는 턴의 늦은 평가 승격과 전달/완료 대기 회귀."""
import json
import time

import boot_paths  # noqa: F401
import pytest
import thread_context as tc
from test_conscious_supervisor import supervisor  # noqa: F401


def test_no_consciousness_cannot_be_promoted_by_failure_stall_or_milestone(supervisor, monkeypatch):
    def forbidden(*a, **kw):
        pytest.fail("의식 없는 턴에 감독/평가 모델 호출")

    monkeypatch.setattr("supervisor_runtime.invoke", forbidden)
    monkeypatch.setattr("final_evaluator.invoke", forbidden)
    supervisor.configure(None)
    tc.clear_goal_eval_outcome()
    for _ in range(4):
        supervisor.run_tool("unknown_writer", {}, lambda: {"success": False, "error": "실행 실패"})
    supervisor.trigger = "job_stalled"
    supervisor.tick(now=time.monotonic() + 10000)
    supervisor.review("milestone", paused=True)
    assert not list(supervisor.finalize("실행 결과", [], lambda ev: None))
    assert not supervisor.enabled and supervisor.reviews == 0
    assert tc.get_goal_eval_outcome() is None
    assert not (supervisor.store.directory / "review_status.json").exists()


@pytest.mark.parametrize("framing", [None, {"task_framing": "단순 확인", "achievement_criteria": ""}])
def test_notification_without_consciousness_is_delivered_without_review(supervisor, monkeypatch, framing):
    from system_tools import execute_send_notification
    sent = []
    supervisor.configure(framing)
    monkeypatch.setattr("notify_dispatch.notify_user", lambda **kw: sent.append(kw) or True)
    result = json.loads(execute_send_notification({"title": "완료", "message": "결과"}, "."))
    assert result["success"] and result["delivered_to_launcher"]
    assert not result.get("queued_for_review") and len(sent) == 1
    assert not supervisor.evaluation_enabled and not supervisor.delivery.manifest()




if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
