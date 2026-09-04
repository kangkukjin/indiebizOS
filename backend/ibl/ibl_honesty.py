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
    # rows_in 은 2026-08-29 제명 — "받았으나 못 씀" 의미의 발신자는 전수 스윕 결과 전부
    # success:False 경로(office_ops·visualization·doc_build, 이미 오류로 신고됨)였고,
    # 성공 경로의 rows_in>0 은 ai-ops(table:ai/brief)의 **정보성 입력 계수**뿐이다.
    # 표지 승격은 성공한 마지막 통화·생존 가지에만 닿으므로 이 키는 원리적으로
    # 오탐만 가능했다(실측: brief 완전 성공에 "부분 실패 신고" 경고 — 늑대소년).
    "statements_failed",  # 독립 문장 실패 수
)

#: 플래그/값형 — 참이거나 비지 않으면 신고한다.
HONESTY_FLAG_KEYS = (
    "truncated",          # 원천 절단
    "_fallback_used",     # ?? 가 갈아탔 — 데이터의 *출처가 바뀜다*
    "halted",             # [repeat:] 상한으로 중단
    "_criteria_retried",  # criteria 미달 → 재시도본이 통과 — 출력의 *출처가 재시도*다 (ibl_quality)
)

HONESTY_KEYS = HONESTY_LIST_KEYS + HONESTY_COUNT_KEYS + HONESTY_FLAG_KEYS

#: 위 표지 가운데 **실패가 아니라 경로·출처의 사실**을 나르는 것 — 승격 경고문이 이것들을
#: "부분 실패·절단" 이라 부르면 늑대소년이 된다 (B51-4 · 53회차 관찰 ①: each 로 효과를
#: 돌리면 매번 `passthrough_rows` 에 "부분 실패" 경고가 붙어 다음 진짜 경보를 죽였다).
#: 경고문의 낱말은 이 분류가 정한다 — 호출부가 키를 보고 손으로 가르지 않는다.
HONESTY_ROUTE_KEYS = (
    "passthrough_rows",   # do 가 통화를 안 내서 원 행이 흘렀다 — 실패 아님
    "rows_replaced",      # do 결과가 원 행을 대체했다 — 출처 행 소실의 사실
    "_fallback_used",     # 출처가 바뀌었다
    "_criteria_retried",  # 출력의 출처가 재시도본이다
)


#: 봉투 규모 불변식 (2026-09-04, ep2814 실측): `total` 은 **items 가 뽑힌 셀 수 있는 모집단의 수**다
#: — 그래서 `total > len(items)` 면 표본이고 봉투는 스스로 `truncated` 를 켜야 한다
#: (data-ops `_restate_scope` 가 이 정의로 하류에서 truncated 를 되살린다). 제공자의 추정치
#: (네이버 검색 "18,804,311건", 카카오 total_count 따위)는 모집단이 아니므로 `total` 이라
#: 부르면 안 된다 — 그런 수는 `total_estimate` 로 낸다. 실측: 네이버 검색 뒤에 table 낱말이
#: 하나만 붙어도 "부분 실패·절단" 경고가 매번 붙었다(한 턴에 3/9 봉투) — 늑대소년.
SCOPE_ESTIMATE_KEY = "total_estimate"


def scope_violation(env: Any) -> Optional[str]:
    """봉투가 규모 불변식을 깨면 사유 한 줄, 아니면 None.

    검사 대상은 items 통화를 낸 봉투뿐(items 가 list 이고 total 이 정수). 위반 = total 이
    items 수보다 큰데 truncated 를 스스로 켜지 않았다 — 원천이 표본임을 침묵하거나,
    추정치를 total 이라 부른 것 둘 중 하나다. 어느 쪽이든 원천(핸들러)의 명사를 고친다.
    """
    if isinstance(env, str):
        s = env.strip()
        if s[:1] != "{":
            return None
        try:
            import json
            env = json.loads(s)
        except Exception:
            return None
    if not isinstance(env, dict):
        return None
    items = env.get("items")
    total = env.get("total")
    if not isinstance(items, list) or isinstance(total, bool) or not isinstance(total, int):
        return None
    if total > len(items) and not env.get("truncated"):
        return (f"total {total} > items {len(items)} 인데 truncated 없음 — 표본이면 truncated 를 켜고, "
                f"제공자 추정치면 {SCOPE_ESTIMATE_KEY} 로 내라")
    return None


def describe_promoted(keys) -> str:
    """승격된 표지 이름들을 **뜻대로 갈라** 한 문장으로 — 실패·절단 / 경로·출처 (B51-4).

    호출부(workflow_engine 승격 경고)가 낱말을 고르지 않고 여기서 받는다 — 표지가 늘거나
    분류가 바뀌어도 경고문이 자동으로 따라오게(HONESTY_KEYS 한 벌과 같은 이유)."""
    ks = sorted(str(k) for k in (keys or []))
    route = [k for k in ks if k in HONESTY_ROUTE_KEYS]
    fail = [k for k in ks if k not in HONESTY_ROUTE_KEYS]
    parts = []
    if fail:
        parts.append("부분 실패·절단(" + ", ".join(fail) + ")")
    if route:
        parts.append("경로·출처 표지(" + ", ".join(route) + " — 실패가 아니라 *어떻게 흘렀나*의 사실)")
    return " + ".join(parts)


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
            # ★값으로도 내려간다 — 몸은 평탄하지 않다. `[if:]` 의 할당은 blk 자신이 아니라
            #   `branches[].action` 안에 있고, `[try]` 는 body/catch/finally 아래에 있다.
            #   49회차 판(내려가지 않음)은 평탄한 몸(repeat 의 step 리스트·단일 action dict)만
            #   맞아서 구멍이 안 보였다 — 파서가 블록 통째로 물어 오자 이름 0개가 나왔다.
            for v in b.values():
                if isinstance(v, (list, dict)):
                    _walk(v)

    _walk(body)
    return out


def var_updates_from(body: Any, out: Any) -> Dict[str, Any]:
    """블록 몸이 할당한 이름 → **되쓸 값 문자열** (★V49-1, 사용자 판정 A 2026-08-27).

    블록이 스코프를 만들지 않으려면 경계가 "무엇이 할당됐고 그 값이 무엇인지"를 바깥에
    돌려줘야 한다. `assigned_in_body` 의 짝 — 저쪽은 *이름만*, 이쪽은 *이름과 값*.

    값의 모양은 문장 단위 할당과 **같은 규약**이다: 그 할당 step 의 결과를 직렬화한 문자열
    (`step_results[N]` 에 들어가는 것과 동형). 그래야 `$k` 참조가 v4 추출을 똑같이 타고,
    블록 안에서 태어났는지 밖에서 태어났는지가 읽는 쪽에 보이지 않는다.

    body 가 단일 dict 면 out 자체가 그 변수의 값이고, list(파이프)면 out 봉투의
    `results[]` 에서 step 별로 집는다(`_run_body` 의 by_idx 와 같은 배선).
    """
    import json as _json

    def _ser(v: Any) -> str:
        return v if isinstance(v, str) else _json.dumps(v, ensure_ascii=False, default=str)

    ups: Dict[str, Any] = {}
    if isinstance(body, dict):
        n = body.get("_assign_name")
        if isinstance(n, str) and n:
            ups[n] = _ser(out)
    elif isinstance(body, list):
        by = {}
        if isinstance(out, dict):
            for r in (out.get("results") or []):
                if isinstance(r, dict) and isinstance(r.get("step"), int) and "result" in r:
                    by[r["step"] - 1] = r["result"]
        for i, s in enumerate(body):
            n = s.get("_assign_name") if isinstance(s, dict) else None
            if isinstance(n, str) and n and i in by:
                ups[n] = _ser(by[i])
    return ups


def carry_var_updates(out: Any, body: Any):
    """블록 몸의 할당을 바깥으로 되쓰게 봉투에 싣는다 — **몸 결과가 평문 스칼라여도**.

    ★2026-08-27(범위밖 판정턴): V49-1 의 되쓰기가 두 자리 모두 `isinstance(out, dict)`
    뒤에 있어, 몸이 스칼라를 내면 `_var_updates` 가 통째로 사라졌다. 실측:

        [if: 1 == 1]{$k = [self:time]}
        [if: $k matches "2026"]{…}[else]{…}
          → "변수 $k 이(가) 이 문장 앞에서 할당되지 않았습니다"  ← 파서는 팬텀 슬롯을
            발급했고(variables={'k': 1000000}) 몸도 성공했는데 경계에서 값이 증발

    `vars_dropped` 표지조차 dict 에만 붙으므로(아래 note_vars_dropped) 이 경로는
    **완전 침묵**이었다 — B48-1 이 `_caught` 에서 고친 "평문 스칼라라는 세 번째 모양"의
    같은 부류. 처방도 같다: 되쓸 것이 있을 때만 `{"result": …}` 로 승격한다
    (api_ibl 이 어차피 하는 래핑이라 소비자가 보는 최종 JSON 모양은 불변,
    승격 조건이 '몸에 할당이 있다' 라서 사정거리도 그 문장들로 한정된다).

    반환: `(out, ups)` — out 은 승격됐을 수 있으므로 호출자는 반환값을 써야 한다.
    """
    ups = var_updates_from(body, out)
    if ups and not isinstance(out, dict):
        out = {"result": out}
    if ups and isinstance(out, dict):
        out.setdefault("_var_updates", ups)
    return out, ups


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
