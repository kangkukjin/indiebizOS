"""
ibl_exec_each.py — [table:each] 실행기(행마다 $it 치환 → 파이프 실행) + 입력 통화 추출.

2026-08-23 ibl_executors.py 에서 이사(1500줄 규칙). 재수출 = ibl_executors.
"""
import os
import re
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from common.currency import currency_shape_note


# ── [table:each] — 문장을 값으로 받는 유일한 변환자 (2026-08-15 고차 문장 M2) ──────────
# 왜 이 낱말이 필요했나: table 의 다른 13 변환자는 전부 데이터→데이터라, "찾은 것 *각각에*
# 대해 ~해라"를 이 언어로 쓸 방법이 없었다. 그래서 문장이 늘 "가져와서 정리해 사람에게"
# 2단에서 끝났고(코퍼스 실측: 파이프 평균 길이 2.45·2단이 72%), 항목 단위 싱크
# (notify_user·channel_send·delegate·publish)는 파이프에 한 번도 들어오지 못했다
# (미조합 액션 68/150 의 다수가 이 부류). 설계 정본: docs/HIGHER_ORDER_SENTENCE_DESIGN.md
_EACH_DEFAULT_LIMIT = 20

# 스칼라 행(문자열·숫자)을 dict 로 감쌀 때 쓰는 필드 이름.
# ★출력 감싸기와 $it 치환이 *같은* 이름을 봐야 한다 — 두 자리가 어긋나면
#   결과 행이 `{"value": "가", "_error": "행에 없는 필드: value"}` 처럼
#   필드를 보여주면서 없다고 말하는 자기모순이 난다(2026-08-17 실측 버그).
_EACH_SCALAR_FIELD = "value"
_EACH_MAX_SUBSTEPS = 200


def _each_escape(value: Any) -> str:
    """치환 값을 IBL 문자열 리터럴 안에 안전하게 넣을 형태로 만든다.

    파서(`ibl_parser_values._extract_string`)는 따옴표 안에서 `\\` 다음 글자를 리터럴로
    받으므로, 백슬래시와 양쪽 따옴표만 이스케이프하면 '…' / "…" 어느 쪽에 놓여도 문자열이
    조기 종료되지 않는다(제목에 따옴표가 든 행이 문장을 깨뜨리던 부류의 차단).
    """
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        s = json.dumps(value, ensure_ascii=False)
    else:
        s = str(value)
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")


def _inside_string(text: str, pos: int) -> bool:
    """text[pos] 자리가 IBL 문자열 리터럴 **안**인가 (따옴표·백슬래시 이스케이프 인식)."""
    q = None
    i = 0
    while i < pos:
        c = text[i]
        if q:
            if c == "\\":
                i += 2
                continue
            if c == q:
                q = None
        elif c in "\"'":
            q = c
        i += 1
    return q is not None


def _each_literal(value: Any) -> str:
    """따옴표 **밖** 자리에 놓일 값의 IBL 리터럴 표기 (B27-3, 27회차).

    `$it` 치환은 문장을 파싱하기 **전에** 텍스트로 이뤄진다. 그래서 치환된 값은 자기가 놓인
    자리의 문법을 만족해야 하는데, 지금까지는 어느 자리든 **맨몸 텍스트**를 넣었다.
    파라미터 자리에서는 저자가 따옴표를 직접 쓰므로(`{message: '$it.title'}`) 우연히 맞았고,
    조건 자리에서는 저자가 따옴표를 쓸 수 없으므로(`$변수` 는 원래 맨몸으로 쓰는 문법) 깨졌다.
    실측(2026-08-23):
        [self:body]{days: 2, limit: 3} >> [table:each]{do: "[if: $it.영역 matches 'backend']{…} [else]{…}"}
        → condition: "backend/ibl matches 'backend'"
          "'backend/ibl' 은(는) 소스 참조·$변수·리터럴·술어 함수 어느 것도 아닙니다"
    값은 옳게 뽑혔는데 **따옴표가 없어서** 판정 불능이 됐고, 판정 불능이라 else 도 보류되어
    each 의 전 행이 실패했다. 즉 `each × [if:]` — 목록의 각 행을 조건으로 가르는, 가장 자연스러운
    교차 — 가 통째로 말할 수 없는 문장이었다(전 코퍼스 3,582문장에 이 교차 0건).

    ★근본 자리: 값을 만드는 곳이 아니라 **자리를 아는 곳**이 표기를 정해야 한다.
    숫자·불리언·null 은 맨몸이 곧 리터럴이므로 그대로 두고(조건의 크기 비교가 문자열로
    변질되지 않게), 그 밖은 따옴표를 씌운다. 실측으로 확인한 조건 문법의 수용 형태:
        [if: 'backend/ibl' matches 'backend'] ✓   [if: 3 > 1] ✓   [if: true] ✓
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return json.dumps(value)
    return '"' + _each_escape(value) + '"'


def _each_substitute(sentence: str, row: Any, var: str) -> Tuple[str, list]:
    """문장 안의 `$it.필드` / `$it` 를 행 값으로 치환. 반환: (치환된 문장, 없는 필드 목록).

    ★없는 필드는 조용히 빈 값으로 만들지 않고 목록으로 돌려준다 — 호출자가 그 행을
    실패로 표시한다(빈 문자열로 밀어 넣으면 "성공처럼 보이는 오동작"이 된다).
    ★필드 패턴은 유니코드(`[^\\W\\d]\\w*`) — 옛 `[A-Za-z_]` 전용은 `$it.없는필드` 같은
    한글 필드가 매칭 밖이라 `$it` 만 치환되고 `.필드` 가 리터럴 잔존했다(F14-1, 14회차 실측:
    빈/쓰레기 쿼리가 _ok:true 로 완주).
    """
    missing: list = []

    def _render(value: Any, at: int) -> str:
        """자리를 보고 표기를 고른다 (B27-3) — 따옴표 안이면 본문만, 밖이면 리터럴로."""
        return _each_escape(value) if _inside_string(sentence, at) else _each_literal(value)

    def _sub(m):
        # group(1)=괄호형 경로(`${it.title}`), group(2)=맨몸 경로(`$it.title`)
        field = ((m.group(1) if m.group(1) is not None else m.group(2)) or "").lstrip(".")
        if not field:
            return _render(row, m.start())
        if isinstance(row, dict):
            if field not in row:
                missing.append(field)
                return m.group(0)
            return _render(row.get(field), m.start())
        # 스칼라 행: 호출자가 출력에서 {_EACH_SCALAR_FIELD: row} 로 감싸므로
        # `$it.value` 도 그 값 자체로 푼다(`$it` 와 같은 뜻). 그 밖의 필드는 정직하게 없음.
        if field == _EACH_SCALAR_FIELD:
            return _render(row, m.start())
        missing.append(field)
        return m.group(0)

    from common.ibl_vars import ref_pattern
    pattern = re.compile(ref_pattern(var))
    return pattern.sub(_sub, sentence), missing


def _each_foreign_vars(do: str, var: str) -> list:
    """do 문장 안에서 **해석되지 않을** `$변수` 이름 목록 (F14-1, 2026-08-20 14회차).

    행 참조(`$<var>`)·예약어 `$items`·do 안에서 자기 할당된 변수는 정상.
    그 밖의 `$이름` 은 어떤 행에서도 치환되지 않고 리터럴로 하류에 흘러간다 —
    14회차 실측: `as:"google"` 지정 후 `$it.title` 이 통째로 구글 검색어가 되어
    무관한 결과 30건이 success 로 완주했다(유령 변수의 침묵 통과).
    ★외부 파이프의 `$변수` 는 each 실행 전에 상위 해석기가 이미 치환하므로,
    여기 남은 것은 전부 오타/참조명 불일치다.
    """
    from common.ibl_vars import REF_RE, split_ref
    # 자기 할당(`$x = …`) — 경계 판정만 표기 모듈로 옮기고, "= 뒤가 오면 할당" 이라는
    # 옛 규칙은 그대로 둔다(`==` 도 할당으로 세는 관용까지 포함 — 무회귀).
    assigned = set()
    for m in REF_RE.finditer(do):
        name, path = split_ref(m)
        if not path and re.match(r"\s*=", do[m.end():]):
            assigned.add(name)
    foreign = []
    for name, _path in (split_ref(m) for m in REF_RE.finditer(do)):
        if name == var or name == "items" or name in assigned or name[0].isdigit():
            continue
        if name not in foreign:
            foreign.append(name)
    return foreign


def _stamp_depth(steps: Any, depth: int) -> None:
    """파싱된 step 들에 중첩 깊이를 찍는다(병렬 branches·폴백 체인 포함)."""
    if not isinstance(steps, list):
        return
    for st in steps:
        if not isinstance(st, dict):
            continue
        st["_depth"] = depth
        for key in ("branches", "_fallback_chain", "body", "catch", "finally", "_branch_steps"):
            v = st.get(key)
            _stamp_depth(v if isinstance(v, list) else ([v] if isinstance(v, dict) else None), depth)


def _each_input_rows(params: dict) -> Tuple[Optional[list], Any]:
    """입력 통화(items)를 꺼낸다. 반환: (행 목록 또는 None, 파싱된 봉투).

    규약은 data-ops 변환자와 **같다**(2026-08-15 대칭 수리): 파이프 입력(`_prev_result`)이
    먼저이고, 그게 없을 때만 params 에서 통화를 직접 받는다 — 단독 호출·자가점검·
    리터럴 씨앗 지원. 옛 each 는 `_prev_result` 만 읽어, 다른 13 변환자가 전부 받는
    `items: [...]` 리터럴을 혼자 거부했다("받은 봉투: str"). 하필 문형을 곱셈으로 바꾸는
    유일한 고차 변환자가 항상 앞에 생산자를 요구하던 셈이다.
    """
    prev = params.get("_prev_result")
    # 스필 참조 봉투면 본문으로 (M5 자동 스필 — 소비자는 투명하게 읽는다)
    from common.spill import resolve_ref_str
    prev, _ref_err = resolve_ref_str(prev)
    if _ref_err:
        return None, {"error": _ref_err}
    obj = prev
    if isinstance(prev, str):
        s = prev.strip()
        obj = None
        if s.startswith("{") or s.startswith("["):
            try:
                obj = json.loads(s)
            except Exception:
                obj = prev          # JSON 아닌 문자열 — 아래에서 통화 없음으로 진단된다
        elif s:
            obj = prev
    if obj is None:                  # 파이프 입력 없음 → params 에서 통화 수용
        if params.get("items") is not None:
            # ★B19-2 (2026-08-22 상상훈련 19회차): `items: "$r.items"` 는 변수 치환이
            # 통화를 **JSON 문자열**로 넣는다. 옛 코드는 그 문자열을 그대로 items 자리에
            # 담아 "items 를 찾지 못했습니다 — 받은 봉투: ['items']" 라는 자기모순 거절이
            # 났다(같은 문장이 take 에선 통과 — 읽는 쪽이 갈렸다). 정본 =
            # common.currency.coerce_items_payload — data-ops·ai-ops 도 같은 눈을 쓴다.
            from common.currency import coerce_items_payload
            _rows = coerce_items_payload(params["items"])
            obj = {"items": _rows if _rows is not None else params["items"]}
        elif params.get("table") is not None:
            obj = {"table": params["table"]}

    if isinstance(obj, dict):
        from common.currency import derive_items
        obj = derive_items(obj)
        rows = obj.get("items")
        return (rows if isinstance(rows, list) else None), obj
    if isinstance(obj, list):
        return obj, obj
    return None, obj


def _each_carry(rows: list, base: dict, keep: list) -> list:
    """부모 행의 지목된 필드를 결과 행에 승계 — 옛 `flatten{keep: […]}` 의 자리 이동.

    옛 관용구 `each >> flatten{keep: ["city"]}`(retired-ok: 그 관용구가 하던 일을 keep 이
    어떻게 승계했는지 설명하는 자리) 는 팬아웃 결과에 "어느 부모에서 왔는지"를
    붙이는 유일한 방법이었다. each 가 통화를 그대로 내게 되면서 flatten 이 파이프에서
    빠지므로, 그 능력이 사라지지 않도록 부모 행이 아직 손에 있는 이 자리로 옮긴다
    (능력을 없애는 개정이 아니라 자리를 옮기는 개정이다).

    충돌은 flatten 과 같은 규율 — 조용히 덮지 않고 `_2` 접미를 붙인다(침묵 오선택 금지).
    """
    if not keep:
        return rows
    carry = {k: base.get(k) for k in keep if k in base}
    if not carry:
        return rows
    out = []
    for r in rows:
        merged = dict(r)
        for k, v in carry.items():
            name = k
            while name in merged:
                name += "_2"
            merged[name] = v
        out.append(merged)
    return out


def _each_success_rows(final: Any, base: dict):
    """성공한 행 하나가 통화에 기여할 행들.

    `do` 의 결과가 통화면 그 행들을, 통화가 아니면(효과·스칼라 — notify·write 등)
    **원 행**을 그대로 흘린다. "결과가 통화가 아닐 땐 빈손" 으로 두면 종착 액션 파이프
    (`… >> [table:each]{do: "[self:notify_user]{…}"}`)가 통화를 잃어 어느 행에 대해
    실행됐는지조차 안 보인다 — 그건 옛 봉투가 유일하게 잘하던 일이라 버리지 않는다.

    통화 판정은 몸의 단일 게이트 `common.currency.derive_items` 가 한다(여기서 items/
    table/blocks 를 각자 알아보지 않는다 — 판정기가 둘이면 갈라진다).
    """
    from common.currency import derive_items

    if isinstance(final, list):
        return [r if isinstance(r, dict) else {_EACH_SCALAR_FIELD: r} for r in final], True
    if isinstance(final, dict):
        derived = derive_items(final)
        rows = derived.get("items") if isinstance(derived, dict) else None
        if isinstance(rows, list):
            return [r if isinstance(r, dict) else {_EACH_SCALAR_FIELD: r} for r in rows], True
    # 통화 아님 — 원 행을 흘린다. 봉투가 이 사실을 말한다(두 번째 반환값). 결과를 행에
    # 병합해 만들어 내지 않는다: 이름 충돌을 조용히 처리할 방법이 없고, 없는 통화를
    # 있는 척하는 게 이 몸이 가장 싫어하는 부류다.
    return [dict(base)], False


def _execute_table_each(params: dict, project_path: str, agent_id: str = None) -> Any:
    """[table:each]{do, as, limit, on_error} — items 의 각 행에 IBL 문장을 적용.

    통화 계약(2026-08-23 언어 개정 — 사용자 판정): **성공은 통화로, 실패는 봉투로.**

    옛 계약은 출력 행을 `원 행 + _ok + (_error|_result)` 봉투로 쌌다. 명분은 "원 행 보존 =
    `>> [table:filter]{where:"_ok == false"}` 로 실패만 추리기"였는데, 실측하니 코퍼스
    3,582문장에서 `_ok` 를 쓴 문장이 **0건**이었다. 반대로 그 봉투 때문에 뒤에 붙는 변환자가
    전부 "그 필드 없다"로 끊겨서, `each` 는 항상 `>> [table:flatten]` 을 동반해야 하는
    2낱말 관용구였다(each 문장 49건 중 15건이 flatten 동반, 최다 후속). 즉 **한 번도 안 쓰인
    관용구를 위해 매번 쓰이는 관용구를 끊고 있었다.**

    그리고 이 몸은 이미 다른 답을 갖고 있었다 — `halted_steps`·`skipped_steps`·
    `branches_failed`·`empty_notes` 가 전부 **부분 실패는 봉투로** 나른다. each 만
    2026-08-15 에 그 규약이 서기 전에 만들어져 실패를 통화 *안*에 섞고 있었다.
    IBL 에서 유일하게 통화-in/통화-out 이 아닌 변환자였다.

    새 계약:
      · 성공 행 → `do` 의 결과가 통화면 그 행들을, 통화가 아니면(효과·스칼라) **원 행**을
        그대로 흘린다. 통화 판정은 `common.currency.derive_items` 하나가 한다.
      · 실패 행 → 통화에 섞지 않고 봉투 `errors: [{원 행…, _error}]` + `error_count` 로.
        침묵 금지는 그대로다 — 부분 실패면 `warning` 을 반드시 싣는다.
      · 전 행 실패는 여전히 상위로 전파한다.

    `on_error: "keep"` (언어 개정 2026-08-28, 사용자 판정 "언어의 한계는 다 고쳐"):
      실패 행을 `{원 행…, _error}` 로 **통화에도** 흘린다 — 후속 문장이
      `[table:filter]{where: {field:"_error", op:"eq", value:null}}` / exists 로 성공·실패를
      가르고, 실패 행만 뽑아 교체·재시도(안티조인·재팬아웃)를 문장 안에서 조합할 수 있게.
      2026-08-23 개정이 은퇴시킨 옛 `_ok` 상시 봉투의 재발이 아니다 — 그때는 전 문장이
      비용을 냈고(코퍼스 사용 0건), 이번엔 실패를 데이터로 쓰겠다고 선언한 문장만 켠다.
      진단층(errors+traceback)은 keep 이어도 그대로 싣는다(경계 규약 예외 없음).
    """
    from ibl_parser import parse as ibl_parse, IBLSyntaxError
    from workflow_engine import execute_pipeline

    do = params.get("do")
    if isinstance(do, list):
        do = "\n".join(str(x) for x in do if str(x).strip())
    if not do or not str(do).strip():
        return {"success": False, "items": [], "count": 0,
                "error": "each: do(각 행에 적용할 IBL 문장)가 필요합니다. "
                         "예) [table:each]{do: \"[self:notify_user]{message: '$it.title'}\"}"}
    do = str(do)
    var = (str(params.get("as") or "it").lstrip("$").strip()) or "it"

    # ★유령 변수 사전 차단 (F14-1): 어떤 행에서도 치환되지 않을 `$이름` 은 저작 오류라
    # 행 단위가 아니라 문장 단위로 즉시 거절한다 — 모든 행이 같은 이유로 실패할 운명이고,
    # 옛 동작(리터럴 잔존→하류 실행)은 "성공처럼 보이는 오동작"이었다.
    foreign = _each_foreign_vars(do, var)
    if foreign:
        return {"success": False, "items": [], "count": 0,
                "error": (f"each: do 안에 해석되지 않는 변수 "
                          f"{', '.join('$' + f for f in foreign)} — 행 참조 이름은 '${var}'"
                          f"{' (as 로 지정됨)' if var != 'it' else ''} 입니다. "
                          f"행 값은 '${var}.필드' 로 참조하세요.")}

    rows, envelope = _each_input_rows(params)
    if rows is None:
        shape = currency_shape_note(envelope)
        return {"success": False, "items": [], "count": 0,
                "error": f"each: 입력에서 items 통화를 찾지 못했습니다. 받은 봉투: {shape} — "
                         f"each 는 목록의 각 행에 문장을 적용합니다. 파이프(>>) 뒤에 놓거나, "
                         f"단독으로 쓰려면 items 를 직접 주세요. "
                         f'예: [table:each]{{items: [{{"city": "서울"}}], do: "[sense:weather]{{city: \'$it.city\'}}"}}'}

    try:
        limit = int(params.get("limit") if params.get("limit") is not None else _EACH_DEFAULT_LIMIT)
    except (TypeError, ValueError):
        limit = _EACH_DEFAULT_LIMIT
    if limit < 0:
        limit = _EACH_DEFAULT_LIMIT
    on_error = str(params.get("on_error") or "continue").strip().lower()
    keep = params.get("keep") or []
    if not isinstance(keep, list):
        keep = [keep]
    keep = [str(k) for k in keep]
    depth = int(params.get("_depth") or 0)

    target = rows[:limit]
    skipped = max(0, len(rows) - len(target))
    out_items: list = []
    errors: list = []
    ok_n = err_n = substeps = 0
    halted: Optional[str] = None

    processed = noncurrency = currency_n = 0
    # 트레이스백 경계 규약(docs/IBL_TRACEBACK_HANDOFF.md): 행 하나의 실패에도 do 문장
    # 안의 경로가 붙는다. 동일 오류의 무거운 상세(py_tail·input)는 첫 행에만(fold_heavy).
    from ibl_traceback import build_tb, push_frame, tb_of, py_tail_of, fold_heavy
    _tb_seen: dict = {}
    _tb_folds = 0

    def _row_tb(tb, row_no: int):
        nonlocal _tb_folds
        push_frame(tb, {"kind": "each", "item": row_no, "of": len(target)})
        if fold_heavy(tb, _tb_seen, row_no):
            _tb_folds += 1
        return tb

    for idx, row in enumerate(target):
        processed += 1
        base = dict(row) if isinstance(row, dict) else {_EACH_SCALAR_FIELD: row}

        sentence, missing = _each_substitute(do, row, var)
        if missing:
            err_n += 1
            # 필드 힌트도 잘렸으면 잘렸다고 말한다 (F18-1 부류 — 침묵 클램프 금지):
            # 12개에서 끊긴 목록을 전부로 읽으면 있는 필드를 없다고 오판한다.
            if isinstance(row, dict):
                _names = sorted(row.keys())
                avail = (_names[:12] + [f"…외 {len(_names) - 12}개"]) if len(_names) > 12 else _names
            else:
                avail = [_EACH_SCALAR_FIELD]
            _emsg = f"행에 없는 필드: {', '.join(sorted(set(missing)))} (행 필드: {avail})"
            errors.append({**base, "_error": _emsg,
                           "_traceback": _row_tb(build_tb(_emsg, "binding"), idx + 1)})
            if on_error == "keep":
                out_items.append({**base, "_error": _emsg})
            if on_error == "stop":
                halted = "on_error"
                break
            continue

        try:
            steps = ibl_parse(sentence)
        except IBLSyntaxError as e:
            err_n += 1
            errors.append({**base, "_error": f"IBL 문법 오류: {e}",
                           "_traceback": _row_tb(build_tb(f"IBL 문법 오류: {e}", "syntax"),
                                                 idx + 1)})
            if on_error == "keep":
                out_items.append({**base, "_error": f"IBL 문법 오류: {e}"})
            if on_error == "stop":
                halted = "on_error"
                break
            continue

        substeps += len(steps)
        if substeps > _EACH_MAX_SUBSTEPS:
            halted = "budget"
            break

        _stamp_depth(steps, depth + 1)
        # each 의 do 는 *문자열*이라 행마다 새로 파싱된다 — 바깥에서 찍힌 워크플로우 호출
        # 스택이 여기서 끊기면, 워크플로우 → each → 자기 워크플로우 사슬이 가드를 우회한다.
        _wf_stack = params.get("_wf_stack")
        if _wf_stack:
            from workflow_contract import _stamp_wf_stack
            _stamp_wf_stack(steps, _wf_stack)
        try:
            res = execute_pipeline(steps, project_path, agent_id=agent_id)
        except Exception as e:  # 실행기 자체가 터진 경우도 행 단위로 정직하게
            res = {"success": False, "error": f"{type(e).__name__}: {e}",
                   "traceback": build_tb(f"{type(e).__name__}: {e}", "exception",
                                         py_tail=py_tail_of(e))}

        final = res.get("final_result") if isinstance(res, dict) else res
        if isinstance(final, str):
            s2 = final.strip()
            if s2.startswith("{") or s2.startswith("["):
                try:
                    final = json.loads(s2)
                except Exception:
                    pass

        if isinstance(res, dict) and not res.get("success", True):
            err_n += 1
            # do 문장 안의 트레이스백을 승계하고 each 프레임 한 칸을 얹는다 — 어느 행의,
            # 몇 번째 step 에서, 무슨 입력으로 죽었는지가 행별로 남는다(경계 규약에 예외 없음).
            _rtb = tb_of(res) or build_tb(res.get("error") or "실행 실패")
            errors.append({**base, "_error": res.get("error") or "실행 실패",
                           "_traceback": _row_tb(_rtb, idx + 1)})
            if on_error == "keep":
                out_items.append({**base, "_error": res.get("error") or "실행 실패"})
            if on_error == "stop":
                halted = "on_error"
                break
        else:
            ok_n += 1
            _rows_from, _was_currency = _each_success_rows(final, base)
            if _was_currency:
                _rows_from = _each_carry(_rows_from, base, keep)
            out_items.extend(_rows_from)
            if not _was_currency:
                noncurrency += 1
            else:
                currency_n += 1

    # 중단 시 남은 행은 '처리 안 함'으로 정직하게 집계 (조용히 사라지지 않게)
    if halted:
        # ★출력 행 수 ≠ 처리한 입력 행 수 다(한 행이 N행을 낼 수 있다) — 처리 수로 센다.
        skipped += len(target) - processed

    out: Dict[str, Any] = {
        "items": out_items,
        "count": len(out_items),
        "rows_processed": processed,
        "ok_count": ok_n,
        "error_count": err_n,
    }
    notes = []
    if errors:
        # 실패는 통화에 섞지 않고 봉투로 — halted_steps·branches_failed·empty_notes 와 같은 규약.
        out["errors"] = errors
        if _tb_folds:
            # 접었으면 접었다고 말한다(침묵 클램프 금지) — 원형은 detail_at 이 가리키는 행에.
            notes.append(f"동일 오류의 트레이스백 상세(py_tail·input)는 첫 발생 행에만 원형으로 "
                         f"남기고 {_tb_folds}건은 detail_at 참조로 접었습니다.")
    if noncurrency:
        # ★침묵 금지: 통화를 안 내는 do(효과·스칼라)면 원 행이 그대로 흘렀다는 사실을 말한다.
        #   말 없이 원 행을 흘리면 소비자가 그걸 do 의 결과로 오독한다.
        out["passthrough_rows"] = noncurrency
        notes.append(f"{noncurrency}행의 do 가 통화를 내지 않아(효과·스칼라) **원 행**을 "
                     f"그대로 흘렸습니다 — 통화에 있는 값은 do 의 결과가 아닙니다.")
    if currency_n:
        # ★B32-1 (32회차): 위 신고의 **거울**. 지금까지 한 방향(스칼라→원 행 통과)만 말하고
        #   반대 방향(do 가 통화를 내어 **원 행이 대체됨**)은 침묵했다. 실측: 2행을 넣었더니
        #   10행이 나오고(검색 결과), 어느 행에서 나왔는지 통화에도 봉투에도 없었다.
        #   병렬 do 는 열 이름이 통째로 'value' 로 바뀌어 정체가 더 지워졌다.
        #   행 수가 조용히 바뀌는 것은 하류 판단을 통째로 어긋나게 한다("3곳 조회했는데 10건?").
        #   ★한 방향만 신고하는 비대칭이 결함이었으므로 처방도 그 자리 한 곳이다 — 소비자마다
        #   추적 코드를 심는 길(열거)은 반드시 뒤처진다. keep 이 이미 답을 갖고 있으니 가리킨다.
        out["rows_replaced"] = currency_n
        # keep 지정 여부로 안내를 가른다(2026-08-29 ⑥) — keep 을 이미 준 호출에 "keep 을
        # 쓰세요"라고 말하면 작동 중인 처방이 미적용으로 읽힌다(안내문의 늑대소년).
        if keep:
            notes.append(f"{currency_n}행의 do 가 통화를 내어 **원 행이 do 결과로 대체**됐습니다"
                         f"(입력 {processed}행 → 출력 {len(out_items)}행) — 원 행의 필드 "
                         f"{keep} 는 keep 으로 각 행에 보존돼 있습니다.")
        else:
            notes.append(f"{currency_n}행의 do 가 통화를 내어 **원 행이 do 결과로 대체**됐습니다"
                         f"(입력 {processed}행 → 출력 {len(out_items)}행) — 어느 행에서 나온 결과인지는 "
                         f"통화에 남지 않습니다. 원 행의 필드를 함께 보려면 keep: [\"필드\"] 를 쓰세요.")
    # ★`collect` 은퇴(2026-08-23): 이 파라미터가 하던 일("_result 를 이어붙인 하나의 items")이
    #   이제 기본 동작이다. 낱말을 남겨 두면 "켜야 되는 것"으로 읽혀 어휘가 무거워진다.
    if skipped:
        if halted == "budget":
            notes.append(f"하위 스텝 예산({_EACH_MAX_SUBSTEPS}) 초과로 중단 — {skipped}건 미처리")
        elif halted == "on_error":
            notes.append(f"on_error=stop 으로 중단 — {skipped}건 미처리")
        else:
            notes.append(f"limit={limit} 로 앞에서 잘랐습니다 — {skipped}건 미처리")
        out["skipped"] = skipped
    if on_error == "keep" and err_n:
        # keep = 실패를 데이터로 쓰겠다는 선언 — 실패 행이 통화에 섞였음을 반드시 말한다.
        notes.append(f"on_error=keep: 실패 {err_n}행이 _error 표식과 함께 통화에 흘렀습니다 — "
                     f"[table:filter]{{where: {{field: \"_error\", op: \"eq\", value: null}}}} 로 "
                     f"성공만, exists 로 실패만 가를 수 있습니다.")
    # 전 행 실패만 상위로 전파한다. 부분 실패는 파이프를 끊지 않되 반드시 보이게 한다.
    # ★on_error=keep 은 전량 실패도 통화로 흘린다 — 실패를 소비하겠다고 선언한 문장의
    #   후속(교체·재시도)이 바로 그 경우에 일할 수 있어야 한다(warning 은 위에서 실림).
    if processed and ok_n == 0 and on_error != "keep":
        out["success"] = False
        out["error"] = (f"each: {err_n}건 전부 실패 — 첫 오류: "
                        f"{errors[0].get('_error') if errors else '실행 실패'}")
        # 전량 실패 = 문장이 죽는다 — 첫 실패 행의 트레이스백이 문장 트레이스백이 된다
        # (첫 행이라 py_tail·input 원형 보유). 파이프가 이걸 승계해 위 프레임을 얹는다.
        if errors and isinstance(errors[0].get("_traceback"), dict):
            out["traceback"] = errors[0]["_traceback"]
    elif not processed:
        if not rows:
            # ★F17 (2026-08-17 상상훈련 12회차): 입력 0행은 실수가 아니라 정당한 빈손 —
            # 0회 실행=성공(공허 참)으로 0건 통화를 내려 파이프가 완주하게 한다.
            # take/filter 는 빈손을 통과시키는데 each 만 실패로 파이프를 끊던 비대칭
            # (검색 0건 >> each >> flatten 이 step 3 에서 죽던 실측 — retired-ok: 은퇴
            #  전에 일어난 사건의 기록이다. P14 빈손 계약 정합).
            out["success"] = True
            out["message"] = "each: 입력 0행 — 실행 0회 (빈 목록)"
        else:
            out["success"] = False
            out["error"] = f"each: limit={limit} 로 처리한 행이 없습니다 — limit 을 확인하세요."
    else:
        out["success"] = True
        if err_n:
            # ★부분 실패가 통화에서 안 보이게 됐으므로(성공만 흐른다) 봉투가 더 크게 말해야
            #   한다 — 침묵 금지. 소비자가 warning 하나만 봐도 부분성을 안다.
            out["warning"] = (f"[each] {err_n}/{processed}행 실패 (성공 {ok_n}) — 통화에는 성공분만 "
                              f"흐릅니다. 실패한 원 행과 사유는 봉투의 errors 를 보세요.")
            notes.append(f"{err_n}/{processed}건 실패 (성공 {ok_n}) — errors 참조")
    if notes:
        out["message"] = " / ".join(notes)
    return out

