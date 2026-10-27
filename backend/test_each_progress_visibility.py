"""진행 신고의 좌표·회차 — "멈춤과 느림이 구별 불가"의 회귀 가드 (2026-09-01).

실측 사고(유튜브 팁 보고서 09-01 06:06): 4편짜리 팬아웃

    [table:each]{items: [4편], do: "[limbs:youtube]{op:'transcript'} >> [self:struct]{…}"}

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
import threading
import uuid

import pytest

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


@pytest.mark.parametrize("parallel", [1, "auto", 2], ids=["sequential", "auto", "parallel"])
def test_단일step_프로그램도_자기_좌표를_신고한다(parallel, monkeypatch, tmp_path):
    from ibl_v2_adapters import Adapter
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    from ibl_run_journal import Journal
    seen=[]
    def observe(rt,args):
        seen.append(args['n'])
        return args['n']
    adapter=Adapter({'version':1,'params':{'n':'Number'},'result':'Number','effects':['read_external']},observe)
    option='' if parallel=='auto' else f',parallel:{parallel}'
    source='[table:each]{items:[1,2]'+option+'}{[test:observe]{n:$it}}'
    plan=compile_program(source,{'test:observe':adapter})
    assert not plan.issues,plan.report()
    with Journal(tmp_path,plan.fingerprint) as journal:
        out=Runtime(plan,journal=journal).run()
        calls=journal.db.execute('SELECT id,receipt FROM calls').fetchall()
    assert out['success'] and sorted(seen)==[1,2],out
    assert len(calls)==2 and len({row[0] for row in calls})==2
    assert all(row[1] for row in calls)
    assert out['resume']['run_id']==journal.run_id



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


# ---------------------------------------------------------------------------------------------
# 2026-10-27 긴문장 99회차 — 회수 티켓 표면에서 each 회차가 전무(L99-1)·note 에 좌표 없음(L99-2)·
# 제출 직후 unknown 창(L99-5). 아래는 spill 함수 단위 + **실 Runtime 과 티켓의 교차** 시험 — 종전엔 이 파일이
# spill 만, test_progress_to_chat 이 버스만 봐서 교차점이 없었다.


def test_좌표_신고는_회차를_동봉하고_손잡이를_보존한다():
    """L99-1 — 좌표 갱신이 beat 의 회차를 지우지 않고, each 밖 좌표는 옛 행을 남기지 않으며, 실행 손잡이는 산다."""
    t = _fresh()
    try:
        ticket_progress(t, {"edition": 2, "resume": {"run_id": "r1"}, "plan_hash": "h"})   # 손잡이(announce)
        ticket_progress(t, {"step": 1, "of": 0, "action": "self:write"})
        ticket_beat(t, {"row": 2, "rows": 6, "row_label": "2"})
        ticket_progress(t, {"step": 2, "of": 0, "action": "self:script", "detail": {"row": 2, "rows": 6, "row_label": "2"}})
        p = _progress(t)
        assert p["step"] == 2 and p["action"] == "self:script", p
        assert p["detail"] == {"row": 2, "rows": 6, "row_label": "2"}, "행 안 액션 좌표가 회차를 지웠다"
        assert p["resume"] == {"run_id": "r1"} and p["plan_hash"] == "h", "좌표 신고가 실행 손잡이를 지웠다"
        ticket_progress(t, {"step": 3, "of": 0, "action": "self:read"})      # each 밖으로 나간 좌표
        p = _progress(t)
        assert "detail" not in p, "each 가 끝났는데 옛 행이 남았다"
        assert p["resume"] == {"run_id": "r1"}, p
    finally:
        _cleanup(t)


def test_note_는_분모_미지여도_좌표를_적는다():
    """L99-2 — of=0(미지)이 좌표를 숨기지 않는다. 분모가 있으면 종전처럼 N/M."""
    from common.spill import _progress_note
    note = _progress_note({"step": 2, "of": 0, "action": "self:script", "updated_at": "x"})
    assert "step 2 self:script" in note, note
    assert "/0" not in note, "거짓 분모"
    note = _progress_note({"step": 2, "of": 5, "action": "self:script", "updated_at": "x",
                           "detail": {"row": 3, "rows": 6, "row_label": "c"}})
    assert "step 2/5 self:script" in note and "each 3/6행(c)" in note, note


@pytest.mark.parametrize("parallel", [1, 2], ids=["sequential", "parallel"])
def test_실행_중_회수에_회차와_좌표가_함께_보인다(parallel, monkeypatch):
    """L99-1·L99-2 교차 — 실 Runtime 이 표면 티켓을 집고 each 를 돌 때, 행 안에서 회수하면 좌표·회차·note 가 함께 있다."""
    import ibl_v2_runtime
    from ibl_v2_adapters import Adapter
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    monkeypatch.setattr(ibl_v2_runtime, "_PROGRESS_MIN_INTERVAL_S", 0.0)
    t = _fresh()
    prev = tc.get_surface_ticket(), tc.get_progress_ticket()
    seen = []
    def observe(rt, args):
        env = ticket_recover(t)
        seen.append((args["n"], env.get("progress") or {}, env.get("note") or ""))
        return args["n"]
    adapter = Adapter({'version': 1, 'params': {'n': 'Number'}, 'result': 'Number', 'effects': ['read_external']}, observe)
    option = f",parallel:{parallel}" if parallel > 1 else ""
    plan = compile_program("[table:each]{items:[1,2,3]" + option + "}{[test:observe]{n:$it}}", {"test:observe": adapter})
    assert not plan.issues, plan.report()
    try:
        tc.set_surface_ticket(t)
        tc.set_progress_ticket(None)
        out = Runtime(plan).run()
    finally:
        tc.set_surface_ticket(prev[0])
        tc.set_progress_ticket(prev[1])
    try:
        assert out["success"], out
        assert len(seen) == 3
        for n, prog, note in seen:
            assert prog.get("action") == "test:observe", (n, prog)
            assert (prog.get("detail") or {}).get("rows") == 3, ("행 회차가 회수 표면에 없다", n, prog)
            assert 1 <= prog["detail"]["row"] <= 3, prog
            assert "each " in note and "/3행" in note and "test:observe" in note and "step " in note, note
            if parallel == 1:
                assert prog["detail"]["row"] == n and prog["step"] == n, (n, prog)
        rows = sorted(p["detail"]["row"] for _, p, _ in seen) if parallel == 1 else None
        assert rows in (None, [1, 2, 3]), rows
    finally:
        _cleanup(t)


def test_실행_손잡이는_첫_액션_뒤에도_남는다(monkeypatch, tmp_path):
    """수리 중 발견 — Journal.announce 가 집히기 전 표면 티켓에 run_id 손잡이를 쓰고, 좌표 신고가 그것을 지우지 않는다."""
    import ibl_v2_runtime
    from ibl_v2_adapters import Adapter
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    from ibl_run_journal import Journal
    monkeypatch.setattr(ibl_v2_runtime, "_PROGRESS_MIN_INTERVAL_S", 0.0)
    t = _fresh()
    prev = tc.get_surface_ticket(), tc.get_progress_ticket()
    seen = []
    def observe(rt, args):
        seen.append(dict((ticket_recover(t) or {}).get("progress") or {}))
        return args["n"]
    adapter = Adapter({'version': 1, 'params': {'n': 'Number'}, 'result': 'Number', 'effects': ['read_external']}, observe)
    plan = compile_program("[test:observe]{n:1}", {"test:observe": adapter})
    try:
        tc.set_surface_ticket(t)
        tc.set_progress_ticket(None)
        with Journal(tmp_path, plan.fingerprint) as journal:
            journal.announce(plan.fingerprint)
            assert _progress(t).get("resume", {}).get("run_id") == journal.run_id, "손잡이가 티켓에 안 닿았다"
            out = Runtime(plan, journal=journal).run()
            run_id = journal.run_id
    finally:
        tc.set_surface_ticket(prev[0])
        tc.set_progress_ticket(prev[1])
    try:
        assert out["success"], out
        assert seen and seen[0].get("action") == "test:observe", seen
        assert seen[0].get("resume") == {"run_id": run_id}, ("좌표 신고가 손잡이를 지웠다", seen)
    finally:
        _cleanup(t)


def test_each_밖_같은_액션은_접히지_않고_옛_행을_지운다():
    """검토 발견(2026-10-27) — 접기 간격(0.25초)을 **그대로 둔 채**: each 직후 같은 액션이 이어지면 종전엔 좌표 신고가
    접혀 티켓에 each 의 마지막 행이 그 액션 내내 남았다. 접기 키에 회차를 넣어 each 밖 첫 좌표는 즉시 신고한다."""
    from ibl_v2_adapters import Adapter
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    t = _fresh()
    prev = tc.get_surface_ticket(), tc.get_progress_ticket()
    seen = []
    def observe(rt, args):
        env = ticket_recover(t)
        seen.append((args["n"], dict(env.get("progress") or {}), env.get("note") or ""))
        return args["n"]
    adapter = Adapter({'version': 1, 'params': {'n': 'Number'}, 'result': 'Number', 'effects': ['read_external']}, observe)
    plan = compile_program("[table:each]{items:[1,2]}{[test:a]{n:$it}}; [test:a]{n:9}", {"test:a": adapter})
    assert not plan.issues, plan.report()
    try:
        tc.set_surface_ticket(t)
        tc.set_progress_ticket(None)
        out = Runtime(plan).run()
    finally:
        tc.set_surface_ticket(prev[0])
        tc.set_progress_ticket(prev[1])
    try:
        assert out["success"], out
        inside = [p for n, p, _ in seen if n in (1, 2)]
        after = [(p, note) for n, p, note in seen if n == 9]
        assert [p["detail"]["row"] for p in inside] == [1, 2], inside
        assert len(after) == 1 and "detail" not in after[0][0], ("each 가 끝났는데 옛 행이 남았다", after)
        assert "each " not in after[0][1] and "test:a" in after[0][1], after[0][1]
    finally:
        _cleanup(t)


def test_시작_표식은_청소보다_먼저_쓰고_청소는_드물다(monkeypatch):
    """L99-5 — ticket_begin 은 표식을 먼저 쓰고(gc 가 볼 때 이미 있다), gc 는 프로세스당 60초에 한 번."""
    import common.spill as spill
    tickets, saw = [], []
    def fake_gc(*a, **k):
        saw.append(os.path.exists(os.path.join(spill_dir(), f"ticket_{tickets[-1]}.json")))
        return 0
    monkeypatch.setattr(spill, "gc", fake_gc)
    monkeypatch.setattr(spill, "_last_gc_at", 0.0)
    try:
        for _ in range(3):
            tickets.append(uuid.uuid4().hex[:12])
            assert ticket_begin(tickets[-1])
        assert saw == [True], ("gc 가 표식 전에 돌았거나 매 티켓 돌았다", saw)
    finally:
        for t in tickets:
            _cleanup(t)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
