"""ibl_safety.py — 액션 부작용 분류의 **단일 소스**.

"이 액션을 실행하면 세계가 바뀌는가(되돌릴 필요가 있는가)"를 판정한다. 두 소비자가 쓴다:
  · `api_ibl._load_safety_map` — 조종실 dry-run 의 부작용 라벨(read/write/unknown)
  · `scripts/ibl_health_check.py` — 계기 verify 의 read-only 게이팅(safe=True 만 실행)

## 왜 파생인가 (2026-07-18)
예전엔 경량 LLM 이 액션 목록을 훑어 분류한 결과를 `data/self_check_plan.json` 에 캐시했다.
그 생성 경로가 2026-06-27 커밋(065c5a9)에서 삭제됐는데 **캐시 파일과 소비자는 남아서**,
3주 넘게 118개짜리 낡은 목록이 판정을 대신해 왔다(현재 157개, `table` 노드는 통째로 미분류).
같은 판정이 두 파일에 복제돼 있기까지 했다.

→ LLM 캐시를 되살리는 대신 **이미 선언된 것에서 파생**한다. `returns:` 는 src yaml 에
   전 액션 필수로 선언돼 있고 `build --check` 가 지킨다. 새 액션이 생기면 자동으로 분류된다
   (사람도 LLM 도 개입 없음). 유령 목록이 다시 생길 수 없는 구조.

## 두 축이 다르다는 정직한 예외
`returns:` 는 **통화 모양**이지 **부작용**이 아니다. 대부분은 일치하지만
(`effect` = 세계를 바꿈 / `items`·`scalar`·`transform` = 읽기), 어긋나는 부류가 있다:
카메라·마이크는 데이터를 *반환*하지만(scalar) 실제로 셔터를 누르고 녹음을 시작한다.
그런 액션은 src yaml 에 `side_effect: true` 로 **선언**한다 — 코드에 이름을 박지 않는다
(헌법: 어휘는 데이터로. `architecture_ibl_standard_core`).

## op 축 (2026-08-05, 감사 부채 ③)
액션 단위 분류는 `[self:music]{op:"library"}` 같은 **읽기 op 를 쓰기 액션 안에 가둔다**.
op 별 해소는 `ibl_ops` 가 단일 소스이고, 이 파일은 그 위의 지도 빌더다:
`build_safety_map`(액션 롤업 — op 를 모르는 자리) / `build_op_safety_map`(op 단위).
"""

from typing import Dict, Tuple

from ibl_ops import any_op_side_effect, op_names, op_side_effect


def is_side_effect(action_def: dict, op: str = None) -> bool:
    """액션(또는 그 안의 op 하나) → 부작용이 있는가.

    ① op 를 주면 op 단위 해소(`ibl_ops.op_side_effect` — 조이기=자동, 풀기=명시).
    ② op 없이 부르면 **롤업**: op 중 하나라도 부작용이면 부작용(보수적).
       op 가 없는 액션은 선언적 override → `returns: effect` 파생 순.
    """
    if op is not None:
        return op_side_effect(action_def, op)
    return any_op_side_effect(action_def)


def build_safety_map(nodes: dict) -> Dict[Tuple[str, str], bool]:
    """레지스트리 nodes → {(node, action): safe(bool)}. safe=True 는 '부작용 없음'.

    액션 롤업이라 보수적이다 — op 하나만 쓰기여도 액션은 unsafe.
    op 를 아는 자리(dry-run·fixture)는 `build_op_safety_map` 을 쓸 것.
    """
    out: Dict[Tuple[str, str], bool] = {}
    for node_name, node_def in (nodes or {}).items():
        for action_name, action_def in ((node_def or {}).get("actions") or {}).items():
            out[(node_name, action_name)] = not is_side_effect(action_def)
    return out


def build_op_safety_map(nodes: dict) -> Dict[Tuple[str, str, str], bool]:
    """레지스트리 nodes → {(node, action, op): safe(bool)}. op 없는 액션은 미등재."""
    out: Dict[Tuple[str, str, str], bool] = {}
    for node_name, node_def in (nodes or {}).items():
        for action_name, action_def in ((node_def or {}).get("actions") or {}).items():
            for op in op_names(action_def):
                out[(node_name, action_name, op)] = not op_side_effect(action_def, op)
    return out


def _live_nodes() -> dict:
    from ibl_registry import _load_nodes_config
    return (_load_nodes_config() or {}).get("nodes") or {}


def load_safety_map() -> Dict[Tuple[str, str], bool]:
    """라이브 레지스트리에서 안전 분류를 파생(백엔드 프로세스용)."""
    try:
        return build_safety_map(_live_nodes())
    except Exception:
        return {}


def load_op_safety_map() -> Dict[Tuple[str, str, str], bool]:
    """라이브 레지스트리에서 op 단위 안전 분류를 파생."""
    try:
        return build_op_safety_map(_live_nodes())
    except Exception:
        return {}
