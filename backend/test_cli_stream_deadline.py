"""CLI 프로바이더 무출력 마감 — "거절도 실패도 아닌 무한 대기"의 회귀 가드 (2026-09-01).

실측 사고(유튜브 팁 보고서 09-01 06:06): `[table:each]` 2행째의 `[self:struct]` 원샷이
**23분 동안 돌아오지 않았다**. 로그의 마지막 줄은 호출 시작(`call: session=new …`)이고
짝이 되는 `result …ms` 줄이 영영 없다. 뿌리는 이 파일이 시험하는 자리였다:

    for raw_line in proc.stdout:      # ← 한도 없음. 자식이 파이프를 연 채 침묵하면 영원.
        …
    proc.wait(timeout=DEFAULT_TIMEOUT_SEC)   # ← 한도는 **여기**, 즉 EOF 이후에만 있었다.

즉 유일한 시간 한도가 "이미 다 뱉은 자식이 안 죽는" 사실상 없는 사건을 지키고 있었고,
진짜로 멈추는 자리는 무방비였다 — 한도가 있다는 착시.

이 시험이 지키는 계약:
  ① 출력 없이 침묵하는 자식은 STREAM_IDLE_TIMEOUT_SEC 안에 **끊긴다** (무한 대기 금지).
  ② 끊김은 조용한 빈 응답이 아니라 **정직한 error 이벤트**로 나온다.
  ③ 실패 **범주**가 값으로 남는다(last_failure_kind="deadline") — 형식 되먹임 재시도를
     범주 오류로 붙이지 않기 위한 근거(oneshot_facade).
  ④ 말하는 자식(느린 실행)은 죽이지 않는다 — 침묵만이 죽음의 근거다.

실행: .venv/bin/python -m pytest backend/test_cli_stream_deadline.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

from providers.cli_provider import CliSubprocessProvider  # noqa: E402


class _FakeCli(CliSubprocessProvider):
    """실제 CLI 대신 파이썬 한 줄을 자식으로 띄우는 시험용 어댑터."""

    CLI_LABEL = "FakeCli"
    CLI_DISPLAY = "FakeCli"
    STATE_PREFIX = "fakecli"
    STREAM_IDLE_TIMEOUT_SEC = 1.0     # 시험용 — 실물은 600초
    STREAM_IDLE_POLL_SEC = 0.1

    CHILD_CODE = "import time; time.sleep(60)"   # 서브클래스가 덮는다

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._client = {"binary": sys.executable}
        self.disable_session_persistence = True

    @classmethod
    def _find_binary(cls):
        return sys.executable

    def _build_command(self, **kwargs):
        return [sys.executable, "-u", "-c", self.CHILD_CODE]

    def _build_env(self):
        return dict(os.environ)

    def _translate_stream_event(self, event, accumulated_text, start_time):
        if event.get("type") == "text":
            return [({"type": "text", "content": event.get("content", "")},
                     accumulated_text + event.get("content", ""))]
        return []

    def _mcp_bridge_acquire(self):
        return None

    def _mcp_bridge_release(self, handle):
        return None

    def _write_system_prompt_file(self):
        return None

    def _save_images_to_temp(self, images):
        return []


def _make(cls=_FakeCli, **over):
    p = cls(api_key="", model="fake", system_prompt="", tools=[])
    for k, v in over.items():
        setattr(p, k, v)
    return p


def test_침묵하는_자식은_마감에_끊긴다():
    """①②③ — 무한 대기가 유한한 정직 실패가 된다."""
    p = _make()
    started = time.time()
    events = list(p.process_message_stream("안녕", history=[]))
    elapsed = time.time() - started

    assert elapsed < 15, f"마감이 안 걸렸다 — {elapsed:.1f}초 (무한 대기 재발)"
    # ★거짓 통과 방지: 자식이 즉사해서 빨랐던 게 아니라 **마감이 끊은 것**이어야 한다.
    assert elapsed >= _FakeCli.STREAM_IDLE_TIMEOUT_SEC, (
        f"{elapsed:.2f}초 만에 끝났다 — 자식이 마감 전에 죽었다면 이 시험은 아무것도 안 지킨다")
    assert events, "이벤트가 하나도 없다 — 조용한 빈 응답은 금지"
    last = events[-1]
    assert last.get("type") == "error", f"끊김이 error 로 안 나왔다: {last}"
    assert "무응답 마감" in last.get("content", ""), last.get("content")
    assert p.last_failure_kind == "deadline", "실패 범주가 값으로 안 남았다"


def test_동기_호출도_같은_마감을_받는다():
    """process_message(원샷 경로)도 문자열 하나로 착지한다 — 매달리지 않는다."""
    p = _make()
    started = time.time()
    text = p.process_message("안녕", history=[])
    assert time.time() - started < 15
    assert "무응답 마감" in text
    assert p.last_failure_kind == "deadline"


class _TalkingCli(_FakeCli):
    """마감보다 촘촘히 말하면서 마감보다 오래 도는 자식 — 느림은 죽음이 아니다."""
    CHILD_CODE = (
        "import json,sys,time\n"
        "for i in range(8):\n"
        "    print(json.dumps({'type':'text','content':str(i)}));sys.stdout.flush()\n"
        "    time.sleep(0.3)\n"
    )


def test_말하는_자식은_안_죽인다():
    """④ — 총 실행시간(≈2.4초)이 마감(1초)을 넘어도 침묵이 없으면 완주한다."""
    p = _make(_TalkingCli)
    events = list(p.process_message_stream("안녕", history=[]))
    texts = [e for e in events if e.get("type") == "text"]
    assert len(texts) == 8, f"말하는 자식이 잘렸다: {events}"
    assert p.last_failure_kind is None
    assert not any(e.get("type") == "error" for e in events)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
