"""정직 표지(honesty marker)의 단일 소스.

부분 실패·경로 변경이 일어났다는 *사실*을 나르는 봉투 키들이다. 이 목록이 한 곳에
없어서 표지가 **조합 경계를 건널 때마다 그 자리에서 손으로 열거**됐고, 열거에서 빠진
키는 조용히 사라졌다 — 같은 속(屬)의 결함이 네 번 반복됐다:

  · B24-1(24회차) 병렬 — 가지 '전체 실패'만 신고, 가지 *안*의 부분 실패는 침묵
  · B27-4(27회차) 블록 몸통 — skipped_steps·condition_errors·_caught 세 키만 건졌음
  · F35-1(35회차) 폴백 — `_fallback_used` 가 봉투 최상위에 없어 첨 가지 결과로 착각됨
  · B48-1/2(48회차) try · 병렬 — 아래 각 수리 지점의 주석 참조

교재(`data/common_prompts/fragments/12_ibl_only.md` — "정직 표지를 읽어라")가
가르치는 키와 이 목록이 어깋나면 모델은 없는 표지를 찾게 된다 — 둘은 함께 움직인다.

★이 모듈은 **잎**이다(형제 모듈을 import 하지 않는다) — workflow_engine · ibl_control_blocks ·
workflow_parallel 이 서로를 순환 참조하지 않고 같은 목록을 볼 수 있게 하려고.
"""
from typing import Any, Dict, Optional

#: 목록형 — 여러 건이 쌓이므로 이어붙인다.
HONESTY_LIST_KEYS = (
    "skipped_steps",      # [on_error:] 가 건너뛴 step
    "condition_errors",   # [if:] 판정 불능
    "_caught",            # [try] 가 삼킨 오류 전문
    "errors",             # [table:each] 의 행별 실패(원 행 + _error)
    "branches_failed",    # 병렬 가지 전체 실패
    "empty_notes",        # 0행 사유
)

#: 수량형 — 0 이 아니면 신고한다.
HONESTY_COUNT_KEYS = (
    "error_count",        # each 행별 실패 수
    "passthrough_rows",   # each do 가 통화를 안 내서 원 행이 흘렀다
    "rows_replaced",      # each do 결과가 원 행을 대체했다(출처 행 소실)
    "rows_dropped",       # 원천 절단
    "rows_in",            # emitter 가 입력을 받았으나 쓸 수 없었다
    "statements_failed",  # 독립 문장 실패 수
)

#: 플래그/값형 — 참이거나 비지 않으면 신고한다.
HONESTY_FLAG_KEYS = (
    "truncated",          # 원천 절단
    "_fallback_used",     # ?? 가 갈아탔 — 데이터의 *출처가 바뀜다*
    "halted",             # [repeat:] 상한으로 중단
)

HONESTY_KEYS = HONESTY_LIST_KEYS + HONESTY_COUNT_KEYS + HONESTY_FLAG_KEYS


def markers_of(env: Any) -> Dict[str, Any]:
    """봉투 하나에서 정직 표지만 걷어 돌려준다(통화·데이터는 건드리지 않는다).

    문자열 봉투(JSON 직렬된 가지 결과)도 받는다 — 병렬 가지는 문자열로 돌아오므로
    여기서 풀지 않으면 호출부마다 같은 파싱을 다시 쓰게 된다.
    """
    if isinstance(env, str):
        s = env.strip()
        if s[:1] not in "{[":
            return {}
        try:
            import json
            env = json.loads(s)
        except Exception:
            return {}
    if not isinstance(env, dict):
        return {}
    out: Dict[str, Any] = {}
    for k in HONESTY_LIST_KEYS:
        v = env.get(k)
        if v:
            out[k] = v
    for k in HONESTY_COUNT_KEYS:
        v = env.get(k)
        if isinstance(v, (int, float)) and v:
            out[k] = v
    for k in HONESTY_FLAG_KEYS:
        v = env.get(k)
        if v:
            out[k] = v
    return out


def merge_into(env: Any, into: Optional[dict]) -> None:
    """`markers_of` 의 누산 판 — 목록은 이어붙이고 수량은 더하고 플래그는 올린다."""
    if into is None:
        return
    m = markers_of(env)
    for k, v in m.items():
        if k in HONESTY_LIST_KEYS:
            bucket = into.setdefault(k, [])
            if isinstance(v, list):
                bucket.extend(v)
            else:
                bucket.append(v)
        elif k in HONESTY_COUNT_KEYS:
            into[k] = (into.get(k) or 0) + v
        else:
            into[k] = v
