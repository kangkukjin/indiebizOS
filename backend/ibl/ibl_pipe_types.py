"""ibl_pipe_types.py — 파이프 정적 타입 검사 (returns 선언의 소비자, 2026-08-29)

어휘는 `returns: items|transform|scalar|effect` 를 이미 선언하는데(사실상 타입),
실행 전 검사는 조건식($변수 미할당)만 있고 파이프 타입 정합은 없었다 — 선언만
있고 소비자가 없는 자리("판 홈을 안 쓴다" 부류). 여기가 그 소비자다.

v1 규칙 하나 (보수적 — 확실히 틀린 모양만 실행 전에 거절한다):

  T1. **머리 변환자** — 파이프의 첫 실행 step 이 transform 액션인데
      들어오는 통화도 없고(items param·$변수 방출·블록 통화 없음) 변환할
      대상이 없다 → 실행 전 정직 거절. 실행하면 빈 입력 위에서 rows_in:0
      "성공"이나 불투명한 런타임 오류가 나던 자리.

  통과(오탐 방지): items param 명시(언어 개정 2026-08-28 ③ — 변환자 items
  개방) · `$변수 >>` 머리(_var_emit 이 통화 방출) · 병렬/폴백/블록 머리(각자
  규약 보유 — 병렬 뒤 이항 검사는 F13-2 가 이미 집행) · 블록 몸(has_incoming
  =True — 직전 통화가 $items 로 들어온다, ibl_control_blocks 가 _prev_result 로 전달).

  ★each 의 do 하위 파이프는 면제가 **아니다**(2026-08-30 정정 — 옛 판은 "직전
  통화가 들어온다"고 적었으나 실제 계약은 $it 치환뿐, 통화 유입이 없다). do 안
  머리 변환자도 대상이 없으면 똑같이 거절하되, 처방이 다르므로(each_do=True)
  "표 전체 변환은 바깥 파이프로, do 안은 $it.필드 액션으로" 를 가르친다.

병렬 뒤 첫 변환자=이항 검사(F13-2)는 기존 관문이 담당 — 여기 중복하지 않는다.
검사는 registry(설치 사전)의 returns 선언만 본다 — 액션 이름을 여기 넣지 말 것
(표준/사전 경계: transform 인지 아닌지는 사전이 판정한다).
"""
from typing import Any, Dict, List, Optional


def _returns_of(node: str, action: str) -> Optional[str]:
    try:
        from ibl_registry import load_nodes_installed
        cfg = (load_nodes_installed().get("nodes", {})
               .get(node, {}).get("actions", {}).get(action)) or {}
        return cfg.get("returns")
    except Exception:
        return None  # 사전을 못 읽으면 검사 포기(실행 불변) — 검사기가 실행을 죽이면 안 된다


def head_transform_error(steps: List[Dict[str, Any]],
                         has_incoming: bool = False,
                         each_do: bool = False) -> Optional[str]:
    """T1 위반이면 안내 문장을, 아니면 None. 판정 불능은 전부 None(보수적)."""
    if has_incoming or not steps:
        return None
    head = steps[0]
    if not isinstance(head, dict):
        return None
    # 통화를 스스로 만들거나 자기 규약이 따로 있는 머리 — 검사 대상 아님
    if any(head.get(k) for k in ("_parallel", "_var_emit", "_assign", "_goal",
                                 "_condition", "_case", "_try", "_repeat")):
        return None
    if "_fallback_chain" in head:
        return None
    node = head.get("_node") or head.get("node") or ""
    action = head.get("action") or ""
    if not node or not action:
        return None
    if _returns_of(node, action) != "transform":
        return None
    params = head.get("params") or {}
    if isinstance(params, dict) and "items" in params:
        return None  # 변환 대상을 직접 실었다(언어 개정 ③)
    if each_do:
        # do 하위 파이프에는 통화가 흐르지 않는다(행은 $it 치환뿐) — 일반 처방
        # ("앞에 생산자")는 do 안에서 오도다. 행 전체 변환은 each 의 일이 아니라
        # 바깥 파이프의 일이다(실측 2026-08-30: items:"$it" 류 우회는 작동하지 않는다).
        return (f"[{node}:{action}] 는 변환자(returns: transform)인데 변환할 통화가 없습니다 — "
                f"each 의 do 안에는 직전 통화가 흐르지 않고 행은 $it 치환으로만 들어옵니다. "
                f"표 전체를 변환하려면 each 를 빼고 바깥 파이프에 두세요"
                f"([생산자] >> [{node}:{action}]). do 안에서는 행 필드를 "
                f"$it.필드 로 참조하는 액션을 쓰세요.")
    return (f"[{node}:{action}] 는 변환자(returns: transform)인데 변환할 통화가 없습니다 — "
            f"파이프 머리에 서 있고 items 도 받지 않았습니다. "
            f"앞에 생산자를 두거나([생산자] >> [{node}:{action}]), "
            f"items 로 대상을 직접 실으세요([{node}:{action}]{{items: [...], …}}). "
            f"저장된 $변수라면 `$이름 >> [{node}:{action}]` 로 방출하세요.")
