"""IBL 건강 검사 러너의 시간 예산 회귀.

전수 fixture가 실제로 약 4분 28초 걸리는데 러너가 300초에 끊어, 외부 API 지연 한 번만
겹쳐도 조종실에 '검사기 자체 실행 실패'가 남았다. 시간 예산과 사람이 읽는 오류를 고정한다.
"""
import subprocess


def test_health_runner_allows_full_fixture_sweep_and_reports_timeout(monkeypatch):
    import world_pulse_health as health

    seen = {}

    def _timeout(*args, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", _timeout)
    events = health.run_ibl_health_check()

    assert seen["timeout"] == health.IBL_HEALTH_CHECK_TIMEOUT_S == 600
    assert len(events) == 1 and events[0]["success"] is False
    message = events[0]["error_message"]
    assert "600초" in message
    assert "외부 fixture 응답 지연" in message
    assert "Command '" not in message, "잘린 subprocess 원문 대신 원인·예산을 보여줘야 한다"


class _Done:
    def __init__(self, stdout, rc=0):
        self.stdout, self.stderr, self.returncode = stdout, "", rc


def test_health_runner_hands_parent_capability_to_script(monkeypatch):
    """재기동 drain 중에도 점검 호출이 접수되려면 자식 스크립트가 러너의 실행 자격을 물려받아야
    한다(2026-09-15 09:29 골든파이프 0/5 가짜 RED 의 뿌리 — 자격 없는 호출은 전부 503)."""
    import runtime_work
    import world_pulse_health as health

    seen = {}
    monkeypatch.setattr(runtime_work, "parent_token", lambda: "cap-abc123")

    def _run(*args, **kwargs):
        # 러너는 같은 함수 안에서 형제 스크립트(red_safety_selftest 등)도 subprocess 로 돌린다 —
        # 점검 스크립트 호출만 골라 env 를 본다.
        if str(args[0][1]).endswith("ibl_health_check.py"):
            seen["env"] = kwargs.get("env")
            return _Done('@@HEALTH_JSON@@ {"static_ok": true, "currency": {"green": 1, "yellow": 0, "red": 0, "reds": []}, '
                         '"golden_pipes": {"passed": 5, "total": 5, "fails": []}, "operators": {"passed": 7, "total": 7}}\n')
        return _Done("")

    monkeypatch.setattr(subprocess, "run", _run)
    events = health.run_ibl_health_check()

    assert seen["env"]["INDIEBIZ_RUNTIME_PARENT"] == "cap-abc123"
    by_action = {ev["action"]: ev for ev in events}
    assert by_action["golden_pipes"]["success"] and by_action["operators"]["success"] and by_action["currency"]["success"]


def test_health_runner_reports_admission_abort_as_incomplete_not_red(monkeypatch):
    """스크립트가 접수 중단으로 스스로 멈추면 섹션별 RED 가 아니라 '미완' 한 항목이어야 한다."""
    import world_pulse_health as health

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Done(
        '‼ 점검 중단\n@@HEALTH_JSON@@ {"aborted": "admission_closed", "detail": "재기동을 위해 새 작업 접수를 잠시 중단했습니다."}\n'
        if str(a[0][1]).endswith("ibl_health_check.py") else ""))
    events = health.run_ibl_health_check()

    assert len(events) == 1
    ev = events[0]
    assert ev["action"] == "ibl_health_check" and ev["success"] is False
    assert ev["data_quality"] == "audit_incomplete"
    assert "접수 중단" in ev["error_message"] and "재기동" in ev["error_message"]


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
