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


if __name__ == "__main__":
    # 러너는 하나다 — 직접 실행도 pytest 에 위임한다.
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
