"""ibl_progress.py — 표면 티켓 진행 신고의 **단일 소유자** (2026-09-01).

무엇을 고치려고 생겼나 — 실측 사고(유튜브 팁 보고서, 09-01 06:06):

    [table:each]{items: [4편], do: "[sense:video]{op:'transcript'} >> [self:struct]{…}"}

이 문장이 23분 동안 멈췄는데, 회수(`/ibl/recover`)는 8번을 물어도 똑같이
`step 2/2 [self:struct] 진행 중 (마지막 갱신 06:06:47)` 만 돌려줬다. 세 가지가 겹쳤다:

  ① **좌표가 거짓이었다.** 프로그램은 `[table:each]` **한 step** 이다. `step 2/2` 는
     each 의 **1행째 하위 파이프**(transcript >> struct)의 좌표인데, 그게 프로그램의
     좌표인 양 올라갔다. 단일 step 프로그램은 초크포인트가 execute_pipeline 을
     지나지 않고 바로 실행하므로(system_tools_ibl 의 `len(parsed)==1` 분기),
     티켓을 아무도 안 집었고 **첫 하위 파이프가 주워서** 자기 좌표를 신고했다.
  ② **회차가 없었다.** 그 하위 파이프가 티켓을 집으며 비웠으므로(claim-by-clear)
     2·3·4행은 아무 신고도 못 했다. 그래서 `updated_at` 이 1행 시작 시각에 얼었다.
  ③ 그 결과 **멈춤과 느림이 구별 불가**였다. 얼어붙은 시각 하나로는 "죽었다"와
     "오래 걸린다"가 같은 모양이라, 사람이 23분을 기다리는 것 말고 할 게 없었다.

규율 — **좌표는 소유하고, 움직임은 공유한다.**

  · 소유(claim): 프로그램의 좌표(step/of/action)를 **아는 자**가 한 번만 집는다.
    파이프면 파이프 실행기(workflow_engine), 단일 step 이면 초크포인트
    (system_tools_ibl). 소유자는 step 경계마다 `report_step` 으로 좌표를 갱신한다.
  · 공유(beat): 그 아래 모든 실행(each 의 행, 하위 파이프, 블록, 병렬 가지)은
    `beat` 로 **detail 칸만** 갱신한다. 좌표는 절대 덮지 않는다 — 안쪽이 바깥의
    좌표를 덮는 것이 ① 의 거짓말이었다.
  · beat 은 마지막 쓴 놈이 이긴다. 그게 옳다: 우리가 알고 싶은 것은 "어느 깊이든
    **마지막으로 움직인 시각**"이고, 그 시각이 멈춤과 느림을 가르는 유일한 증거다.

스레드 경계: 소유 슬롯(surface_ticket)과 신고 슬롯(progress_ticket)은 둘 다
thread_context 에 산다 — `snapshot()/restore()` 가 통째로 옮기므로 워커 스레드로
내려간 실행(오프로드 풀·병렬 가지)도 같은 규약을 그대로 쓴다.
"""
from typing import Optional


def claim(total: int = 0) -> Optional[str]:
    """표면 티켓의 **좌표 소유권**을 집는다 — 집으면서 소유 슬롯을 비운다.

    비우는 이유는 종전과 같다: 안쪽 실행이 같은 티켓을 또 집어 자기 좌표를 프로그램
    좌표로 신고하는 것을 막는다. 달라진 것은 **비우기만 하지 않는다**는 점이다 —
    신고 슬롯에 남겨, 아래 모든 깊이가 `beat` 으로 움직임을 말할 수 있게 한다.

    반환: 티켓(소유자가 됐다) 또는 None(표면 티켓 없는 실행 — 신고 대상 없음).
    """
    try:
        from thread_context import (get_surface_ticket, set_surface_ticket,
                                    set_progress_ticket)
    except Exception:
        return None
    try:
        ticket = get_surface_ticket()
        if not ticket:
            return None
        set_surface_ticket(None)      # 좌표 소유권은 한 벌 (claim-by-clear)
        set_progress_ticket(ticket)   # 움직임 신고권은 아래 전부에게
        return ticket
    except Exception:
        return None


def report_step(ticket: Optional[str], step: int, of: int, action: str) -> None:
    """소유자의 좌표 갱신 — best-effort(신고가 본 실행을 깨지 않는다)."""
    if not ticket:
        return
    try:
        from common.spill import ticket_progress
        ticket_progress(ticket, {"step": step, "of": of, "action": action})
    except Exception:
        pass


def beat(detail: dict) -> None:
    """소유자가 아닌 자리의 움직임 신고 — detail 칸만 갱신하고 시각을 새로 찍는다.

    키 이름은 자리마다 다르게 (겹치면 서로를 지운다):
      · [table:each]        → row / rows / row_label
      · 하위 파이프         → substep / substeps / subaction
    """
    if not detail:
        return
    try:
        from thread_context import get_progress_ticket
        ticket = get_progress_ticket()
        if not ticket:
            return
        from common.spill import ticket_beat
        ticket_beat(ticket, detail)
    except Exception:
        pass
