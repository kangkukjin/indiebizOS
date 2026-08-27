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
    "vars_dropped",       # 블록 몸이 할당한 변수가 경계 밖으로 못 나갔다 (B49-2)
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


def assigned_in_body(body: Any) -> list:
    """블록 몸이 **스스로 할당하는** 변수 이름들 — 경계가 무엇을 떨궜는지 신고하려고.

    파서는 몸의 모양(파이프 list · 단일 dict · 분기 action)과 무관하게 할당 자리에
    `_assign_name` 을 남긴다 — 판별이 한 벌로 족한 이유다(모양마다 손으로 열거하면
    빠진 모양에서 조용해진다 — 이 모듈이 존재하는 바로 그 이유)."""
    out: list = []

    def _walk(b: Any) -> None:
        if isinstance(b, list):
            for x in b:
                _walk(x)
        elif isinstance(b, dict):
            n = b.get("_assign_name") or (b.get("name") if b.get("_assign") else None)
            if isinstance(n, str) and n and n not in out:
                out.append(n)

    _walk(body)
    return out


def note_vars_dropped(out: Any, body: Any, kept: Any = ()) -> Any:
    """몸이 할당했지만 바깥으로 못 나간 변수를 봉투에 신고한다 (★B49-2, 49회차 상상훈련).

    실측 — 몸 안에서 *태어난* 변수는 소리 없이 사라졌고, 뒤따르는 읽기는 원인을 엉뚱한
    곳에 돌렸다:

        [if: 1 == 1]{$k = 7}
        [if: $k == 7]{[self:time]}[else]{[sense:host]{op:"status"}}
          → "조건 평가 실패 1건 — 판정 불능"   ← 조건 탓처럼 들리지만 진범은 경계다

    `[repeat:]` 은 **바깥에 이미 있던** 이름만 되쓰고(`_var_updates` — step_results 에
    슬롯이 있어야 한다), `[if]/[case]/[try]` 는 몸의 할당을 아예 추적하지 않는다.
    그래서 `$n = 0` 을 미리 둔 *재할당*만 살아남는 비대칭이 생겼다.

    이 함수는 그 비대칭을 **없애지 않는다** — 블록이 스코프를 만드는지 아닌지는 언어
    개정 사안이라 사용자 판정 몫이다. 다만 떨궜다는 사실을 조용히 두지 않는다:
    48회차가 연 "정직 표지가 조합 경계를 못 건넌다" 부류의 같은 처방.

    통화 계약 불침범 — dict 봉투에만 싣는다(스칼라를 감싸면 하류 통화가 깨진다.
    F19-1 이 `_branch_meta` 를 side-channel 로 뺀 것과 같은 판정).
    """
    names = [n for n in assigned_in_body(body) if n not in (kept or ())]
    if names and isinstance(out, dict):
        out.setdefault("vars_dropped", names)
    elif names:
        print(f"[IBL_BLOCK] vars_dropped={names} (비-dict 블록 결과 — 봉투로만 신고)")
    return out


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
