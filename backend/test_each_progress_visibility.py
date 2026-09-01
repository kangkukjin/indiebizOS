"""진행 신고의 좌표·회차 — "멈춤과 느림이 구별 불가"의 회귀 가드 (2026-09-01).

실측 사고(유튜브 팁 보고서 09-01 06:06): 4편짜리 팬아웃

    [table:each]{items: [4편], do: "[sense:video]{op:'transcript'} >> [self:struct]{…}"}

가 23분을 멈췄는데 회수(`/ibl/recover`)는 여덟 번을 물어도 똑같이
`step 2/2 [self:struct] 진행 중(마지막 갱신 06:06:47)` 이었다. 두 가지가 거짓이었다:

  ① **좌표가 프로그램의 것이 아니었다.** 프로그램은 `[table:each]` 한 step 인데
     `step 2/2` 는 each **1행째 하위 파이프**의 좌표다. 단일 step 프로그램은
     execute_pipeline 을 안 지나 아무도 티켓을 안 집었고, 안쪽에서 처음 만난
     파이프가 주워 자기 좌표를 프로그램 좌표인 양 신고했다.
  ② **회차가 없었다.** 그 하위 파이프가 티켓을 집으며 비웠으므로(claim-by-clear)
     2·3·4행은 신고할 수단이 없었다 — 시각이 1행 시작에 얼었다.

계약(정본=ibl/ibl_progress.py): **좌표는 소유하고, 움직임은 공유한다.**

실행: .venv/bin/python -m pytest backend/test_each_progress_visibility.py
"""
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401

import thread_context as tc  # noqa: E402
from common.spill import (ticket_begin, ticket_progress, ticket_beat,  # noqa: E402
                          ticket_recover, spill_dir)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _fresh():
    t = uuid.uuid4().hex[:12]
    ticket_begin(t)
    return t


def _cleanup(t):
    try:
        os.remove(os.path.join(spill_dir(), f"ticket_{t}.json"))
    except OSError:
        pass


def _progress(t):
    return (ticket_recover(t) or {}).get("progress") or {}


def test_안쪽은_바깥의_좌표를_못_덮는다():
    """① — beat 은 detail 만 만진다. step/of/action 은 소유자의 것."""
    t = _fresh()
    try:
        ticket_progress(t, {"step": 1, "of": 1, "action": "[table:each]"})
        ticket_beat(t, {"substep": 2, "substeps": 2, "subaction": "[self:struct]"})
        p = _progress(t)
        assert p["step"] == 1 and p["of"] == 1 and p["action"] == "[table:each]", p
        assert p["detail"]["substep"] == 2, p
    finally:
        _cleanup(t)


def test_회차와_마지막_움직임이_보인다():
    """② — 행이 넘어갈 때마다 시각이 새로 찍힌다(멈춤 ↔ 느림 판별의 유일한 증거)."""
    t = _fresh()
    try:
        ticket_progress(t, {"step": 1, "of": 1, "action": "[table:each]"})
        ticket_beat(t, {"row": 2, "rows": 4, "row_label": "CFGyFW9Z6ug"})
        note = ticket_recover(t).get("note", "")
        assert "each 2/4행" in note, note
        assert "마지막 움직임" in note, note
    finally:
        _cleanup(t)


def test_단일step_프로그램도_자기_좌표를_신고한다():
    """①의 뿌리 — `[table:each]` 한 문장을 실제로 돌려 좌표·회차를 함께 확인한다.

    사고 당일과 같은 모양(단일 step + 하위 2단 파이프)이라, 옛 코드에서는
    `[self:struct]` 자리의 하위 좌표가 프로그램 좌표로 올라왔다.
    """
    from system_tools_ibl import _execute_ibl_unified_impl
    t = _fresh()
    _prev, _prevp = tc.get_surface_ticket(), tc.get_progress_ticket()
    try:
        tc.set_surface_ticket(t)
        tc.set_progress_ticket(None)
        code = ('[table:each]{items: [{"id": "A"}, {"id": "B"}], '
                'do: "[self:datetime]{} >> [self:datetime]{}", on_error: "continue"}')
        _execute_ibl_unified_impl({"code": code}, _ROOT)
        p = _progress(t)
        # 좌표 = 프로그램의 것 (하위 파이프의 step 2/2 가 아니다)
        assert p.get("action") == "[table:each]", p
        assert (p.get("step"), p.get("of")) == (1, 1), p
        # 회차 = 마지막으로 손댄 행 (여기까지 왔다는 증거)
        d = p.get("detail") or {}
        assert d.get("rows") == 2 and d.get("row") == 2, d
        assert d.get("row_label") == "B", d
    finally:
        tc.set_surface_ticket(_prev)
        tc.set_progress_ticket(_prevp)
        _cleanup(t)


def test_티켓_없는_실행은_아무_파일도_안_만든다():
    """신고는 부수적이다 — 표면 티켓이 없으면 조용히 아무것도 하지 않는다."""
    from ibl_progress import claim, beat
    _prev, _prevp = tc.get_surface_ticket(), tc.get_progress_ticket()
    try:
        tc.set_surface_ticket(None)
        tc.set_progress_ticket(None)
        assert claim(3) is None
        beat({"row": 1, "rows": 3})      # 예외 없이 무해 통과
    finally:
        tc.set_surface_ticket(_prev)
        tc.set_progress_ticket(_prevp)


def test_소유는_한_벌이다():
    """claim 은 집으면서 소유 슬롯을 비운다 — 두 번째 claim 은 빈손(안쪽이 못 덮는다)."""
    from ibl_progress import claim
    t = _fresh()
    _prev, _prevp = tc.get_surface_ticket(), tc.get_progress_ticket()
    try:
        tc.set_surface_ticket(t)
        assert claim(1) == t
        assert claim(1) is None, "안쪽 실행이 좌표 소유권을 또 집었다"
        assert tc.get_progress_ticket() == t, "신고권은 아래로 내려가야 한다"
    finally:
        tc.set_surface_ticket(_prev)
        tc.set_progress_ticket(_prevp)
        _cleanup(t)


def test_끝난_티켓은_진행이_안_덮인다():
    """결말(done)은 신고가 절대 덮지 않는다 — ticket_progress 와 같은 규율."""
    from common.spill import ticket_finish
    t = _fresh()
    try:
        ticket_finish(t, {"success": True, "steps_completed": 2})
        assert ticket_beat(t, {"row": 9, "rows": 9}) is False
        env = ticket_recover(t)
        assert env.get("steps_completed") == 2, env
    finally:
        _cleanup(t)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
