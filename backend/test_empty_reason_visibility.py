"""0행의 *이유*가 파이프 중간에서 사라지지 않는다 (29회차 관찰의 수리, 2026-08-23)

29회차 상상훈련이 실측한 것:

    [table:since]{...}                      → {"items": [], "count": 0, "seeded": true,
                                               "note": "첫 검침 — 기준선 3행 저장…"}   ← 정직
    [table:since]{...} >> [table:filter]{…} → 0건.  note 는 어디에도 없다.            ← 사라짐

사용자는 *"처음이라 기준선만 세웠다"* 와 *"새 것이 없다"* 를 구별할 수 없다.
통화({items:[...]})에는 "왜 비었는가"를 실을 자리가 없고, 중간 step 의 결과는 다음
step 의 결과에 덮이기 때문이다. 이 몸엔 이미 halted/skipped_steps/branches_failed 를
봉투 표면으로 승격하는 규약이 있으므로, 같은 규약을 하나 더 세운 것이 이 수리다.

판정은 **모양으로만** 한다 — 어휘 이름을 엔진에 심지 않는다(IBL 헌법 '명사의 자리'):
  "통화가 0행인데 note 를 달고 있는 **중간** step" 하나가 조건 전부다.
마지막 step 은 final_result 로 이미 보이므로 싣지 않는다(토큰 중복 0).

실행: .venv/bin/python -m pytest backend/test_empty_reason_visibility.py
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401

import ibl_engine  # noqa: E402
from ibl.workflow_engine import execute_pipeline  # noqa: E402


def _run(script):
    """action 이름 → 결과 로 굳힌 파이프를 돌린다."""
    steps = [{"node": "table", "action": a} for a in script]
    orig = ibl_engine.execute_ibl
    ibl_engine.execute_ibl = lambda ti, pp, agent_id=None: dict(script[ti.get("action")])
    try:
        return execute_pipeline(steps, "/tmp")
    finally:
        ibl_engine.execute_ibl = orig


SEEDED = {"success": True, "items": [], "count": 0, "seeded": True,
          "note": "첫 검침 — 기준선 3행 저장. 다음 호출부터 새 행만 흐릅니다."}
EMPTY = {"success": True, "items": [], "count": 0}
ROWS = {"success": True, "items": [{"x": 1}]}


def test_E1_중간_0행의_사유가_봉투로_올라온다():
    out = _run({"since": SEEDED, "filter": EMPTY})
    assert out["success"] is True
    notes = out.get("empty_notes")
    assert notes, "0행의 사유가 통째로 사라졌다 — 사용자는 0건만 본다"
    assert notes[0]["step"] == 1
    assert notes[0]["action"] == "table:since"
    assert "첫 검침" in notes[0]["note"]
    assert "0행 사유" in out.get("warning", "")


def test_E2_사유_없는_0행은_아무_소리도_내지_않는다():
    """'새 것이 없다'는 평범한 0건 — 여기에 경고를 달면 잡음이 된다."""
    out = _run({"since": EMPTY, "filter": EMPTY})
    assert "empty_notes" not in out
    assert "warning" not in out


def test_E3_마지막_step_은_싣지_않는다():
    """final_result 로 이미 보인다 — 중복 토큰 0."""
    out = _run({"filter": ROWS, "since": SEEDED})
    assert "empty_notes" not in out, "마지막 step 의 note 를 봉투에 중복으로 실었다"


def test_E4_행이_있으면_note_가_있어도_싣지_않는다():
    """승격 조건은 '0행 + note' 다. 행이 있으면 사용자가 결과로 본다."""
    out = _run({"a": {"success": True, "items": [{"x": 1}], "note": "참고"},
                "b": ROWS})
    assert "empty_notes" not in out


def test_E5_items_키가_없으면_대상이_아니다():
    """note 는 이 몸에서 널리 쓰이는 낱말이고 사용자 데이터이기도 하다
    (notebook 의 메모 등). 통화 0행이라는 모양이 없으면 건드리지 않는다."""
    out = _run({"a": {"success": True, "note": "노트북 메모"}, "b": ROWS})
    assert "empty_notes" not in out


def test_E6_다른_경고와_함께_실려도_서로_지우지_않는다():
    """경고 생산자가 넷 — 한 키에 덮어쓰면 뒤엣것이 앞엣것을 지운다(B24-1 부류)."""
    steps = [{"node": "table", "action": "since"},
             {"node": "table", "action": "mid"},
             {"node": "table", "action": "last"}]
    script = {"since": SEEDED, "mid": dict(SEEDED, note="두 번째 사유"), "last": ROWS}
    orig = ibl_engine.execute_ibl
    ibl_engine.execute_ibl = lambda ti, pp, agent_id=None: dict(script[ti.get("action")])
    try:
        out = execute_pipeline(steps, "/tmp")
    finally:
        ibl_engine.execute_ibl = orig
    assert len(out["empty_notes"]) == 2
    assert "첫 검침" in out["warning"] and "두 번째 사유" in out["warning"]


if __name__ == "__main__":
    # 러너는 하나다 — 직접 실행도 pytest 에 위임한다(28회차: 두 번째 러너는 조용히 0건).
    raise SystemExit(pytest.main([__file__] + __import__("sys").argv[1:]))
