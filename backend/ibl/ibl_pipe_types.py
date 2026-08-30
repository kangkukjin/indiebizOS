"""ibl_pipe_types.py — 파이프 정적 타입 검사 (returns 선언의 소비자, 2026-08-29)

어휘는 `returns: items|transform|scalar|effect` 를 이미 선언하는데(사실상 타입),
실행 전 검사는 조건식($변수 미할당)만 있고 파이프 타입 정합은 없었다 — 선언만
있고 소비자가 없는 자리("판 홈을 안 쓴다" 부류). 여기가 그 소비자다.

규칙 (보수적 — 확실히 틀린 모양만 실행 전에 거절한다):

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

  T2. **이음매 기아** (2026-08-30) — 같은 문장 안의 인접 이음매 `A >> B` 에서
      B 가 변환자인데 A 가 통화를 내지 않는 effect 라 B 가 굶는다 → 실행 전 정직
      거절. 실행하면 "items 통화를 찾지 못했습니다"(런타임)로 죽던 자리를 실행
      전에 같은 판정으로 앞당긴다. 실측 동기: `[limbs:browser]{op:"click"} >>
      [table:filter]` 부류.

      ★A 의 통화는 **op 단위로 해소한다** — returns 는 액션 단위가 기본이지만
      사전은 이미 `ops.returns`(op 별 오버라이드)와 `returns_variants`(param=값
      조건부, B36-3)를 선언한다. 액션 단위로만 읽으면 오거절이 난다(코퍼스
      3,676건 실측 26건 — 전부 op·param 조건부 통화의 오독). 해소 규칙은
      ibl_ops.op_returns 와 동일(한 벌).

      기권(오탐 방지 — 판정 불능은 전부 통과): op 가 동적($변수·미선언)이거나
      A 가 특수 step(병렬·블록·폴백·$방출) · A 통화가 scalar(파일 읽기·스크립트
      stdout 등 **데이터 의존 승격**이 있어 정적 확답 불가 — 코퍼스 실측으로
      기각된 부류) · B 가 items 직접 적재 · 문장 경계(통화가 안 넘는 자리라
      이음매가 아님 — 그 머리는 T1 의 관할).

병렬 뒤 첫 변환자=이항 검사(F13-2)는 기존 관문이 담당 — 여기 중복하지 않는다.
검사는 registry(설치 사전)의 returns 선언만 본다 — 액션 이름을 여기 넣지 말 것
(표준/사전 경계: transform 인지 아닌지는 사전이 판정한다).
"""
from typing import Any, Dict, List, Optional, Tuple

# 자기 규약을 따로 가진 특수 step — 통화 판정 기권 대상 (T1 통과 목록과 한 벌)
_SPECIAL_KEYS = ("_parallel", "_var_emit", "_assign", "_goal",
                 "_condition", "_case", "_try", "_repeat")


def _action_def(node: str, action: str) -> Optional[Dict[str, Any]]:
    try:
        from ibl_registry import load_nodes_installed
        cfg = (load_nodes_installed().get("nodes", {})
               .get(node, {}).get("actions", {}).get(action))
        return cfg if isinstance(cfg, dict) else None
    except Exception:
        return None  # 사전을 못 읽으면 검사 포기(실행 불변) — 검사기가 실행을 죽이면 안 된다


def _returns_of(node: str, action: str) -> Optional[str]:
    cfg = _action_def(node, action) or {}
    return cfg.get("returns")


def _is_dynamic(v: Any) -> bool:
    """param 값이 실행 시점에야 정해지는가 ($변수·{{바인딩}}) — 정적 판정 기권."""
    return isinstance(v, str) and ("$" in v or "{{" in v)


def _variant_returns(action_def: Dict[str, Any], params: Dict[str, Any]):
    """returns_variants('param=값: 통화', B36-3) 해소 — (통화|None, 기권 여부).

    param 이 리터럴로 변형값과 일치=그 통화, param 이 실렸는데 동적=기권(전체),
    미해당=None(op/액션 해소로 진행). 소비자가 여기 처음 생겼다 — 종전엔
    returns_drift_sweep(조사 스크립트)만 읽던 선언이다."""
    rv = action_def.get("returns_variants")
    if not isinstance(rv, dict):
        return None, False
    for key, ret in rv.items():
        if not isinstance(key, str) or "=" not in key:
            continue
        p, want = key.split("=", 1)
        if p not in params:
            continue
        v = params[p]
        if _is_dynamic(v):
            return None, True
        lit = {True: "true", False: "false"}.get(v, str(v))
        if lit == want and isinstance(ret, str):
            return ret, False
    return None, False


def step_currency(step: Any) -> Optional[str]:
    """플레인 step 의 선언 통화(items|scalar|transform|effect) — op·param 조건부까지 해소.

    None = 기권(특수 step·미지 액션·동적 op·변형 param 동적). 판정 불능은 전부
    None — 검사기는 확실할 때만 말한다."""
    if not isinstance(step, dict):
        return None
    if any(step.get(k) for k in _SPECIAL_KEYS) or "_fallback_chain" in step:
        return None
    node = step.get("_node") or step.get("node") or ""
    action = step.get("action") or ""
    if not node or not action:
        return None
    ad = _action_def(node, action)
    if not isinstance(ad, dict):
        return None
    params = step.get("params") if isinstance(step.get("params"), dict) else {}
    ret_v, abstain = _variant_returns(ad, params)
    if abstain:
        return None
    if ret_v:
        return ret_v
    try:
        from ibl_ops import op_values, resolve_op, op_returns
        if op_values(ad):
            raw = params.get("op")
            if raw is not None and (not isinstance(raw, str) or _is_dynamic(raw)):
                return None          # 동적 op — 실행 시점에야 정해진다
            op = resolve_op(ad, params)
            if op is None:
                return None          # 유령 op — 다른 관문의 관할, 여기선 기권
            return op_returns(ad, op)
    except Exception:
        return None
    return ad.get("returns")


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


def seam_starvation_error(steps: List[Dict[str, Any]]) -> Optional[Tuple[int, str]]:
    """T2 위반이면 (위반 step 의 0-기반 인덱스, 안내 문장)을, 아니면 None.

    같은 문장 안의 인접 이음매만 본다 — 문장 경계(_seq_boundary)는 통화가 안
    넘는 자리라 이음매가 아니고, 특수 step(병렬·블록·폴백·$방출)은 각자 규약
    보유라 기권. 판정 불능은 전부 None(보수적)."""
    if not isinstance(steps, list):
        return None
    for i in range(1, len(steps)):
        b = steps[i]
        if not isinstance(b, dict) or b.get("_seq_boundary"):
            continue
        if any(b.get(k) for k in _SPECIAL_KEYS) or "_fallback_chain" in b:
            continue
        b_node = b.get("_node") or b.get("node") or ""
        b_action = b.get("action") or ""
        if not b_node or not b_action:
            continue
        if _returns_of(b_node, b_action) != "transform":
            continue
        b_params = b.get("params") if isinstance(b.get("params"), dict) else {}
        if "items" in b_params:
            continue  # 변환 대상을 직접 실었다(언어 개정 ③) — 이음매 통화가 필요 없다
        a = steps[i - 1]
        if step_currency(a) != "effect":
            continue  # items·transform=흐른다, scalar=데이터 의존 승격 가능성(기권), None=판정 불능
        a_node = a.get("_node") or a.get("node") or ""
        a_action = a.get("action") or ""
        a_params = a.get("params") if isinstance(a.get("params"), dict) else {}
        _op = a_params.get("op")
        a_label = f"[{a_node}:{a_action}]" + (f'{{op: "{_op}"}}' if isinstance(_op, str) else "")
        return (i, f"{a_label} 는 통화를 내지 않는 effect 인데 뒤의 [{b_node}:{b_action}] 는 "
                   f"변환자(returns: transform)입니다 — 이 이음매에서 변환할 items 가 굶습니다. "
                   f"사이에 생산자를 두거나([{a_node}:{a_action}] 뒤에 [생산자] >> [{b_node}:{b_action}]), "
                   f"[{b_node}:{b_action}]{{items: [...], …}} 로 대상을 직접 실으세요. "
                   f"저장해 둔 $변수라면 `$이름 >> [{b_node}:{b_action}]` 로 방출하세요.")
    return None
