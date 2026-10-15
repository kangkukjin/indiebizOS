"""보이는 실행을 못 띄운 예약 문장(2026-10-14): 시스템 AI 창이 없자 30분 뒤 '음악 정지'가
WS 30초 대기 뒤 아무것도 실행하지 않고 '1회 작업 완료'로 사라졌다. 창은 표시 방식일 뿐이므로
같은 문장을 소유자 신원으로 직접 실행해야 하고, 실제 실패는 실패로 기록돼야 한다.
"""
import sys
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest

from calendar_actions import CalendarActionsMixin


@pytest.fixture
def host(monkeypatch):
    notices, ran = [], []
    monkeypatch.setitem(sys.modules, "notification_manager", SimpleNamespace(
        get_notification_manager=lambda: SimpleNamespace(
            success=lambda **kw: notices.append(("ok", kw)),
            warning=lambda **kw: notices.append(("warn", kw)))))
    h = CalendarActionsMixin()
    h.logs = []
    h._log = h.logs.append
    h._open_window_and_wait_ws = lambda *a, **k: None   # 창·WS 없음

    def direct(steps, run_path, agent_id, edition=None, inputs=None):
        ran.append((steps, agent_id))
        return {"success": True, "final_result": "stopped"}

    monkeypatch.setattr(CalendarActionsMixin, "_execute_scheduled_pipeline", staticmethod(direct))
    return SimpleNamespace(h=h, notices=notices, ran=ran)


STOP = "[limbs:guestpc]{op:\"ibl\",limb:\"삼성1\",code:\"[limbs:music]{op:'stop'}\"}"


def test_system_ai_schedule_runs_directly_when_window_unavailable(host):
    task = {"id": "evt_x", "title": "삼성1 음악 30분 정지", "owner_project_id": "__system_ai__",
            "owner_agent_id": "system_ai", "action_params": {"pipeline": STOP}}
    result = host.h._action_run_pipeline(task)
    assert host.ran == [(STOP, "system_ai")]
    assert result["success"] is True
    assert result["visible_unavailable"] == "시스템 AI 창/WS 연결 실패"
    assert host.notices and host.notices[0][0] == "ok"


def test_agent_schedule_runs_directly_when_window_unavailable(host):
    task = {"id": "evt_y", "title": "t", "owner_project_id": "없는프로젝트",
            "owner_agent_id": "a", "action_params": {"pipeline": STOP}}
    result = host.h._action_run_pipeline(task)
    assert host.ran == [(STOP, "a")]
    assert result["visible_unavailable"] == "프로젝트 창/WS 연결 실패"


def test_injection_failure_is_not_retried_directly(host):
    # 창은 열렸으나 주입 단계에서 실패 — 시작됐을 수 있으므로 두 번 실행하지 않는다.
    host.h._open_window_and_wait_ws = lambda *a, **k: "client-1"
    host.h._inject_message_via_ws = lambda *a, **k: {"success": False, "error": "주입 실패"}
    task = {"id": "evt_z", "title": "t", "owner_project_id": "__system_ai__",
            "owner_agent_id": "system_ai", "action_params": {"pipeline": STOP}}
    result = host.h._action_run_pipeline(task)
    assert host.ran == [] and result["success"] is False


def test_one_shot_failure_is_logged_as_failure(monkeypatch, tmp_path):
    import calendar_manager as cmod
    logs = []
    cm = cmod.CalendarManagerBase.__new__(cmod.CalendarManagerBase)
    cm.config = {"events": [{"id": "e1", "title": "정지", "repeat": "none", "action": "boom"}]}
    cm.actions = {"boom": lambda task: {"success": False, "error": "시스템 AI 창/WS 연결 실패"}}
    cm._save_config = lambda: None
    cm._log = logs.append
    cm._execute_task(cm.config["events"][0])
    assert "1회 작업 실패 — 시스템 AI 창/WS 연결 실패, 비활성화됨: 정지" in logs
    assert not any("작업 완료" in line for line in logs)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
