"""표면 티켓 회수 규약 — 표면 대기가 끊겨도 실행 결과 봉투는 잃지 않는다 (F51-1, 2026-08-27)

실측 사고(51회차 긴 문장 실험, 변형 1): 2분 10초짜리 문장이 **실행을 완주해 파일까지
만들었는데**, MCP 표면(mcp_server.execute_ibl)의 HTTP 대기 120초가 먼저 끊겨
`{"error": "timed out"}` 만 남고 최종 봉투(정직 표지 포함)가 증발했다. 백엔드로 직접
돌려서야 `branches_honesty` 를 읽을 수 있었다 — 실행이 산 채로 결과만 잃는 것은 조합
표현력의 실질적 상한이다.

규약: 표면이 티켓을 실어 보내면(hex 8~32자) 백엔드가 시작·결말을 data/spill/ 에 남기고
(cache 계급·24h gc 동승), 표면 타임아웃은 "죽었다"가 아니라 "기다림이 끝났다"는 정직한
봉투(ticket+회수법)가 된다. 회수(`/ibl/recover`)는 3상태를 뭉개지 않는다:
done(원 봉투) / running(진행 중) / unknown(만료 **또는** 미탑재 — 판정 불능은 판정 불능이라 말한다).

실행: .venv/bin/python -m pytest backend/test_surface_ticket_recovery.py
"""
import ast
import json
import os
import sys
import threading
import time
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

from common.spill import (valid_ticket, ticket_begin, ticket_finish,  # noqa: E402
                          ticket_recover, spill_dir)

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _fresh_ticket():
    return uuid.uuid4().hex[:12]


def _cleanup(ticket):
    try:
        os.remove(os.path.join(spill_dir(), f"ticket_{ticket}.json"))
    except OSError:
        pass


def test_T1_티켓_생애주기_running에서_done으로():
    t = _fresh_ticket()
    try:
        assert ticket_begin(t)
        st = ticket_recover(t)
        assert st.get("status") == "running" and st.get("success") is True
        assert st.get("started_at"), "running 상태는 언제 시작했는지 말해야 한다"

        env = {"success": True, "steps_completed": 7, "results": [{"step": 1}]}
        assert ticket_finish(t, env)
        got = ticket_recover(t)
        # 회수는 **원 봉투**를 돌려준다 — 상태 보고서로 갈음하지 않는다.
        assert got.get("steps_completed") == 7
        assert got.get("_recovered_from_ticket") == t
    finally:
        _cleanup(t)


def test_T2_실패도_결말이다():
    """예외로 끝난 실행이 running 으로 영영 남으면 회수자가 '아직 도는 중'으로 오독한다."""
    t = _fresh_ticket()
    try:
        ticket_begin(t)
        ticket_finish(t, {"success": False, "error": "폭발"})
        got = ticket_recover(t)
        assert got.get("success") is False and got.get("error") == "폭발"
    finally:
        _cleanup(t)


def test_T3_티켓_이름은_hex만():
    """네트워크에서 온 값이 파일명이 된다 — 경로 탈출·임의 문자는 문에서 거른다."""
    for bad in ("../../etc/passwd", "ticket_x", "ABCDEF012345", "한글티켓", "", None,
                123, "abc", "f" * 33):
        assert not valid_ticket(bad), f"통과되면 안 되는 티켓: {bad!r}"
        assert not ticket_begin(bad)
        assert not ticket_finish(bad, {})
        assert ticket_recover(bad).get("status") == "invalid"
    assert valid_ticket("deadbeef") and valid_ticket("f" * 32)


def test_T4_기록없음은_모름이지_없음이_아니다():
    """B28-1: '못 봤다'와 '없다'는 다른 사건 — unknown 은 만료·미탑재 두 가설을 다 말한다."""
    got = ticket_recover(_fresh_ticket())
    assert got.get("success") is False and got.get("status") == "unknown"
    assert "만료" in got.get("error", "") and "티켓 없이" in got.get("error", "")


def test_T5_표면이_타임아웃을_다른_실패와_분간한다(monkeypatch):
    """mcp_server._post_backend — read 타임아웃(TimeoutError)과 connect 타임아웃
    (URLError(reason=TimeoutError))은 마커를 얻고, 다른 실패는 종전대로."""
    sys.path.insert(0, _REPO)
    import urllib.error
    import mcp_server

    def _raise(exc):
        def _f(*a, **k):
            raise exc
        return _f

    for exc in (TimeoutError("timed out"),
                urllib.error.URLError(TimeoutError("timed out"))):
        monkeypatch.setattr(mcp_server.urllib.request, "urlopen", _raise(exc))
        out = json.loads(mcp_server._post_backend("/ibl/execute", {}, 1))
        assert out.get("_surface_timeout") is True, f"{exc!r} 가 마커를 못 얻었다"

    monkeypatch.setattr(mcp_server.urllib.request, "urlopen",
                        _raise(urllib.error.URLError("connection refused")))
    out = json.loads(mcp_server._post_backend("/ibl/execute", {}, 1))
    assert "_surface_timeout" not in out, "타임아웃 아닌 실패가 타임아웃으로 오독됐다"


def test_T6_타임아웃_봉투는_회수법을_가르친다():
    sys.path.insert(0, _REPO)
    import mcp_server
    env = json.loads(mcp_server._surface_timeout_envelope("abc123def456", 120))
    assert env["success"] is False and env["surface_timeout"] is True
    assert env["ticket"] == "abc123def456"
    # 봉투의 note 는 표면을 가리지 않고 사용법을 안내한다(resume 선례 — B23-1 교훈).
    assert "recover" in env["note"] and "abc123def456" in env["note"]
    assert "계속 돌고" in env["error"], "타임아웃 봉투는 '실행은 살아 있다'를 말해야 한다"


def test_T7_배선이_모든_출구에_서_있다():
    """게이트가 *호출부*에 서 있는지 — 헬퍼만 있고 안 쓰면 아무것도 막지 못한다(O10 선례).

    api_ibl.execute_ibl_code 의 출구는 셋(문자열 반환·정상 봉투·예외)이고, 셋 모두
    ticket_finish 를 지나야 한다. mcp_server 는 실행 payload 에 ticket 을 싣는다."""
    api_src = open(os.path.join(_REPO, "backend", "surface", "api_ibl.py"), encoding="utf-8").read()
    calls = [n for n in ast.walk(ast.parse(api_src))
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "ticket_finish"]
    assert len(calls) >= 3, f"ticket_finish 호출이 {len(calls)}곳 — 출구 셋을 다 못 덮는다"
    assert "ticket_begin" in api_src

    mcp_src = open(os.path.join(_REPO, "mcp_server.py"), encoding="utf-8").read()
    assert 'payload["ticket"]' in mcp_src, "표면이 티켓을 안 싣는다 — 봉투가 남을 자리가 없다"
    assert "_surface_timeout_envelope" in mcp_src


def test_T8_회수_엔드포인트가_저장소와_같은_판정을_한다():
    """/ibl/recover 라우트는 ticket_recover 의 얇은 통로다 — 판정이 갈리면 드리프트."""
    sys.path.insert(0, os.path.join(_REPO, "backend", "surface"))
    import asyncio
    from api_ibl import recover_ibl_result, RecoverRequest
    t = _fresh_ticket()
    try:
        ticket_begin(t)
        got = asyncio.run(recover_ibl_result(RecoverRequest(ticket=t)))
        assert got.get("status") == "running"
        ticket_finish(t, {"success": True, "done": 1})
        got = asyncio.run(recover_ibl_result(RecoverRequest(ticket=t)))
        assert got.get("done") == 1
    finally:
        _cleanup(t)


# ── T9~T13: 회수의 유한 대기 (2026-09-01) ─────────────────────────────────
# 왜 생겼나: 회수의 유일한 처방이 "잠시 후 다시 물으세요"뿐이라, 멈춘 실행을 기다리는
# 주행이 셸 `sleep` 으로 대기를 흉내 내다 무너졌다(전경 sleep 은 하네스가 막고 배경
# sleep 은 즉시 반환 → 4~5초 간격 폴링). 09-01 06:00 실측: 도구 호출 45건 중 16건
# (회수 폴링 9 + sleep 7)이 **기다리는 데만** 쓰였다. 형제 낱말
# `[self:script]{op:"status", wait}` 가 이미 갖고 있던 유한 대기를 같은 계약으로 옮긴다.


def test_T9_끝난_티켓은_기다리지_않는다():
    """done/unknown/invalid 는 기다릴 이유가 없다 — 즉답이어야 한다."""
    from common.spill import ticket_wait
    t = _fresh_ticket()
    try:
        ticket_begin(t)
        ticket_finish(t, {"success": True, "steps_completed": 3})
        started = time.time()
        env = ticket_wait(t, 30)
        assert env.get("steps_completed") == 3
        assert time.time() - started < 1.0, "끝난 티켓을 기다렸다"
    finally:
        _cleanup(t)
    started = time.time()
    assert ticket_wait("deadbeef1234", 30).get("status") == "unknown"
    assert ticket_wait("나쁜티켓", 30).get("status") == "invalid"
    assert time.time() - started < 1.0, "기록 없는/형식 틀린 티켓을 기다렸다"


def test_T10_대기_중_결말이_나면_그때_돌아온다():
    """폴링 왕복 없이 한 번의 호출이 결말을 물어온다 — 이 낱말의 존재 이유."""
    from common.spill import ticket_wait
    t = _fresh_ticket()
    try:
        ticket_begin(t)
        threading.Timer(1.0, lambda: ticket_finish(t, {"success": True, "steps_completed": 9})).start()
        started = time.time()
        env = ticket_wait(t, 30)
        elapsed = time.time() - started
        assert env.get("steps_completed") == 9, env
        assert 0.5 < elapsed < 10, f"{elapsed:.1f}초 — 결말을 기다리지 않았거나 너무 늦게 돌아왔다"
    finally:
        _cleanup(t)


def test_T11_대기가_끝나는_것과_실행이_끝나는_것은_다르다():
    """상한까지 안 끝나면 running 을 정직하게 — 실패로 위장하지 않는다(F51-1 규율)."""
    from common.spill import ticket_wait
    t = _fresh_ticket()
    try:
        ticket_begin(t)
        env = ticket_wait(t, 3)
        assert env.get("status") == "running", env
        assert env.get("success") is True, "기다림이 끝난 것을 실패로 만들면 안 된다"
        assert env.get("waited") is not None, "얼마를 기다렸는지 말해야 한다"
        assert "기다림이 끝난" in (env.get("note") or ""), env.get("note")
    finally:
        _cleanup(t)


def test_T12_wait_상한은_줄이고_신고한다():
    """`[self:script]{op:"status", wait}` 와 같은 규율 — 조용히 깎지 않는다(silent clamp 금지)."""
    import common.spill as spill_mod
    from common.spill import ticket_wait
    t = _fresh_ticket()
    _orig = spill_mod.TICKET_MAX_WAIT_S
    try:
        ticket_begin(t)
        spill_mod.TICKET_MAX_WAIT_S = 2          # 시험용 — 실물 240
        env = ticket_wait(t, 9999)
        assert "줄임" in (env.get("note") or ""), env.get("note")
        assert env.get("waited") <= 4
    finally:
        spill_mod.TICKET_MAX_WAIT_S = _orig
        _cleanup(t)


def test_T13_표면이_wait_를_나른다():
    """엔드포인트·MCP 표면 둘 다 통로를 가져야 한다 — 한쪽만 늘리면 안내대로 보낸 값이
    조용히 사라진다(B23-1 이 겪은 부류: 봉투가 안내한 파라미터가 pydantic 에서 탈락)."""
    sys.path.insert(0, os.path.join(_REPO, "backend", "surface"))
    import asyncio
    from api_ibl import recover_ibl_result, RecoverRequest
    t = _fresh_ticket()
    try:
        ticket_begin(t)
        ticket_finish(t, {"success": True, "done": 1})
        got = asyncio.run(recover_ibl_result(RecoverRequest(ticket=t, wait=5)))
        assert got.get("done") == 1, "wait 를 준 회수가 결말을 못 가져왔다"
    finally:
        _cleanup(t)
    mcp_src = open(os.path.join(_REPO, "mcp_server.py"), encoding="utf-8").read()
    assert '"wait": _w' in mcp_src, "MCP 표면이 wait 를 백엔드로 안 나른다"
    assert 'wait: 120' in mcp_src, "타임아웃 봉투가 wait 통로를 안내하지 않는다(통로 미지정)"


if __name__ == "__main__":
    # 러너는 하나다 — 직접 실행도 pytest 에 위임한다.
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
