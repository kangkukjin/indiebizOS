"""ibl_ops.py — **op 축 해소의 단일 소스** (2026-08-05 감사 부채 ③).

## 문제: `returns` 는 액션 단위인데, 통화를 가르는 건 op 다

`self:business_item` 하나에 `list`(목록=items)와 `delete`(효과=effect)가 함께 산다.
액션 단위 `returns:` 로는 둘 중 하나만 말할 수 있어, 전 패키지가 둘 중 하나를 택했다:

  · **정직**: 모든 op 를 items 로 래핑(music-player)
  · **거짓말**: items 선언 후 대다수 op 는 effect 반환(business/guest-helper/memory —
    `guest-helper/ibl_actions.yaml` 에는 자백 주석까지 있었다)

부작용 축도 같은 병을 앓았다. `side_effect: true` 는 액션 통째에 걸리므로,
`[self:music]{op:"library"}` 같은 **읽기 전용 op 가 쓰기 액션 안에 갇혀** 자동 검증
(ibl_health_check §1B read-only 게이트)에서 통째로 생략됐다 — 32개 fixture 가 그랬다.

## 해결: op 별 **선언적 override**, 액션 선언은 기본값

src yaml 의 `ops` 블록에 형제 맵 둘을 허용한다(둘 다 선택):

```yaml
ops:
  default: list
  values:            # 기존 그대로 — {op: 설명}. 프롬프트 카탈로그가 읽는 유일한 맵.
    list: 아이템 목록
    delete: 아이템 삭제 (item_id 필수)
  returns:           # op 별 통화. 선언 없는 op 는 액션 returns 를 상속.
    delete: effect
  side_effect:       # op 별 부작용. 아래 해소 규칙 참조.
    list: false
```

★`values` 를 `{op: {desc, returns}}` 중첩형으로 바꾸지 **않은** 이유: `values` 는
프롬프트 카탈로그·조종실 UI·capability card·오프라인 인코딩 평가 등 8곳이 `{op: str}`
로 읽는다. 모양을 바꾸면 놓친 소비자 하나가 조용히 `[object Object]` 를 뿜는다(그 중
하나는 **모든 에이전트 턴의 프롬프트**다). 형제 맵은 순수 가산이라 기존 독자를 못 깬다.
키 드리프트는 빌드 가드(`ops.returns`/`ops.side_effect` 키 ⊆ `ops.values` 키)가 막는다.

## 부작용 해소 규칙 — **조이는 건 자동, 푸는 건 명시**

  ① `ops.side_effect[op]` 가 bool 이면 그것 (op 가 직접 말함)
  ② 액션이 `side_effect:` 를 bool 로 선언했으면 그것 (보수적 액션 플래그는 **끈적하다**
     — op 가 명시적으로 `false` 를 말하기 전엔 안 풀린다)
  ③ 없으면 해소된 op returns 가 effect 인지로 파생

②가 핵심이다. 액션 플래그는 "통화 모양과 부작용이 어긋난다"(카메라·마이크: scalar 를
반환하지만 셔터를 누른다)를 뜻하기도 하므로, op 가 items 를 선언했다고 자동으로 안전해지면
무인 루프가 셔터를 누르게 된다. 반대로 items 액션 안의 op 가 `returns: effect` 를
선언하면 **자동으로** 위험 판정된다(조이는 방향엔 마찰이 없다).

소비자: `ibl_safety`(부작용 분류) · `api_ibl`(조종실 dry-run 라벨) ·
`ibl_health_check`(read-only 게이트 + 통화 판정).
"""
from typing import Any, Dict, List, Optional

# op 통화로 허용되는 값. transform 은 제외 — group:transform 액션(table 노드)은
# op 분기가 없고, 파이프 변환자는 액션 단위로만 성립한다.
OP_RETURNS_ENUM = {"items", "scalar", "effect"}


def ops_block(action_def: Any) -> Dict[str, Any]:
    """액션 정의 → ops 블록(없으면 빈 dict)."""
    if not isinstance(action_def, dict):
        return {}
    ops = action_def.get("ops")
    return ops if isinstance(ops, dict) else {}


def op_values(action_def: Any) -> Dict[str, Any]:
    """{op: 설명} 맵(없으면 빈 dict)."""
    values = ops_block(action_def).get("values")
    return values if isinstance(values, dict) else {}


def op_names(action_def: Any) -> List[str]:
    return list(op_values(action_def).keys())


def default_op(action_def: Any) -> Optional[str]:
    d = ops_block(action_def).get("default")
    return d if isinstance(d, str) else None


def resolve_op(action_def: Any, params: Optional[dict] = None) -> Optional[str]:
    """호출 파라미터에서 실제 실행될 op 를 해소. op 미지정이면 default.

    ★선언된 op 가 아니면 None — 오타·유령 op 를 '기본 op 인 척' 삼키지 않는다
    (판정 소비자는 None 을 '미분류'로 보수 처리한다).
    """
    values = op_values(action_def)
    if not values:
        return None
    op = (params or {}).get("op") or default_op(action_def)
    if isinstance(op, str) and op in values:
        return op
    return None


def op_desc(action_def: Any, op: str) -> str:
    v = op_values(action_def).get(op)
    return v if isinstance(v, str) else ""


def op_returns(action_def: Any, op: Optional[str]) -> Optional[str]:
    """op 의 통화. op 별 선언이 없으면 액션 `returns` 상속."""
    if not isinstance(action_def, dict):
        return None
    if op:
        declared = ops_block(action_def).get("returns")
        if isinstance(declared, dict):
            r = declared.get(op)
            if isinstance(r, str):
                return r
    return action_def.get("returns")


def op_side_effect(action_def: Any, op: Optional[str]) -> bool:
    """op 의 부작용 여부. 해소 규칙은 모듈 독스트링 참조(조이기=자동, 풀기=명시)."""
    if not isinstance(action_def, dict):
        return True  # 알 수 없으면 보수적으로 '부작용 있음'
    if op:
        declared = ops_block(action_def).get("side_effect")
        if isinstance(declared, dict) and isinstance(declared.get(op), bool):
            return declared[op]
    action_flag = action_def.get("side_effect")
    if isinstance(action_flag, bool):
        return action_flag           # ② 끈적한 액션 플래그 — op 가 말해야 풀린다
    return op_returns(action_def, op) == "effect"


def any_op_side_effect(action_def: Any) -> bool:
    """액션 롤업 — op 중 하나라도 부작용이면 액션 단위로는 부작용.

    op 를 모르는 소비자(액션 이름만 아는 자리)를 위한 보수적 요약이다.
    """
    if not isinstance(action_def, dict):
        return True
    names = op_names(action_def)
    if not names:
        return op_side_effect(action_def, None)
    return any(op_side_effect(action_def, o) for o in names)
