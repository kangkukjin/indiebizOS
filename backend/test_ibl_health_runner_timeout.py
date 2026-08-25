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


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
