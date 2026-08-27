"""where_dsl.py — data-ops 의 조건 언어(where 미니 DSL) + 정렬 키.

handler.py 에서 분리(2026-08-22, 1500줄 규칙). 이 모듈은 **행 하나가 조건을 만족하나**
만 판정한다 — 통화를 모르고 변환자를 모른다(handler 는 이 판정을 빌려 쓸 뿐).

조건 언어의 계약(19회차 B19-1 판정):
  · 문자열 "필드 op 값" — 기호(>= <= > < == != =)와 워드(contains/in/matches/
    startswith/endswith/eq/ne/lt/le/gt/ge)를 **같은 계약**으로 판다.
  · 연산자가 없는 문자열은 전-필드 부분일치(검색어).
  · " and "/" or " 로 이은 문자열은 **조각 전부가 비교식일 때만** 논리식으로 나눈다.
    우선순위는 SQL 과 같다 — or 가 가장 낮고 and 가 그 위("A and B or C" = (A and B) or C).
    (or 지원 = 2026-08-27 filter 마찰 수리 — 옛 정직 거절은 ep1879 실측에서 모델의
    자연스러운 SQL 식 문장을 두 번 죽였다. 거절보다 지원이 근본 수리다.)
  · 조각이 전부 비교식이 아니면(연산자가 어디에도 없으면) 통째 값/전-필드 검색 — 옛 동작.
    **비교식과 비-비교식이 섞이면 중의성 정직 거절**("summary contains 복층 and 테라스" 는
    '둘 다 포함'인지 '값 속의 and' 인지 문장만으로 판정 불능 — 옛 동작은 값으로 읽어
    조용한 0건을 냈다, ep1879 실측). 값 속의 and/or 는 구조형 {field,op,value} 로.
  · 모르는 op·깨진 정규식은 침묵 폴백이 아니라 _WhereError(정직 거절).
  · matches 는 `[if:]` 술어와 같은 뜻(re.search) — 한 몸 안의 두 조건 언어를 같게 둔다.
  · 비교 필드가 없거나 null 이면 !=/ne·순서 비교는 불일치. 모르는 값을 "다르다/더 크다"고
    주장하지 않는다. 결측 동등 검색은 구조형 {field,op:"eq",value:null} 로 가능하다.
  · 크기 순서는 양쪽이 숫자이거나 양쪽이 문자열일 때만 정의한다. 서로 다른 타입의 표시
    문자열을 임의로 비교하지 않으며 문자열 양끝 공백은 조건·정렬 표면에서 무시한다.
  · **ISO 8601 표기만 날짜다**(2026-08-27 사용자 판정) — 같은 순간은 표기·시간대가 달라도
    같고(Z↔+00:00·날짜만↔그날 00:00), naive/aware 혼합·표기 밖 문자열("08/25/2026")과의
    순서는 판정 불능(정직 거절). 달력 위반은 수선 없이 텍스트.
  · 부분일치(contains/startswith/endswith/in)·목록 멤버십은 common.value_semantics 한 벌 —
    eq 의 텍스트 정규화(양끝 공백·casefold·NFC)를 승계하고, 결측·구조 좌변은 아무것도
    주장하지 않는다(list 좌변의 contains 만 원소 멤버십). 46회차 B46-1~5.
"""

import re

from common.value_semantics import (compare_order, list_membership, numeric_value,
                                    regex_text, sort_records, text_match,
                                    value_sort_key, values_equal)


# ───────────────────────── where 미니 DSL ─────────────────────────

class _WhereError(Exception):
    """where 조건 자체가 틀렸다 — 행 판정 실패가 아니라 문장 오류(정직 거절용).

    ★2026-08-22 상상훈련 19회차 B19-1: 옛 코드는 모르는 op 을 조용히 `==` 로 폴백해,
    약속한 연산자가 안 통해도 0건이 '없음'처럼 나갔다. 조건이 틀렸으면 결과가 아니라
    오류를 내야 한다(침묵-삼킴 금지 계약 ⑧′와 같은 부류).
    """


def _op_matches(a, b):
    """정규식 매칭 — `[if:]` 조건 언어의 matches 와 같은 뜻(re.search).

    두 조건 언어(블록 술어 / where 미니 DSL)의 문법을 같게 두기 위한 낱말이다.
    한쪽에서 배운 표현이 다른 쪽에서 죽으면 그 자체가 마찰이다(19회차 판정).
    결측·구조 좌변은 불일치 — repr 문자열을 정규식에 먹이지 않는다(B46-4).
    """
    a_text = regex_text(a)
    if a_text is None:
        return False
    try:
        return re.search(regex_text(str(b)), a_text) is not None
    except re.error as e:
        raise _WhereError(f"정규식 오류 '{b}': {e}")


# 부분일치(contains/startswith/endswith/in)·멤버십의 판정은 common.value_semantics
# 한 벌이다(46회차 B46-1·3·4·5) — 사설 str().lower() 는 eq 의 텍스트 계약(공백·
# casefold·NFC)을 승계하지 못했고, 결측을 "None" 텍스트로 승격해 참을 주장했다.
_OPS = {
    "==": lambda a, b: _num_eq(a, b),
    "eq": lambda a, b: _num_eq(a, b),
    "!=": lambda a, b: not _num_eq(a, b),
    "ne": lambda a, b: not _num_eq(a, b),
    "<": lambda a, b: _num_cmp(a, b) < 0,
    "lt": lambda a, b: _num_cmp(a, b) < 0,
    "<=": lambda a, b: _num_cmp(a, b) <= 0,
    "le": lambda a, b: _num_cmp(a, b) <= 0,
    ">": lambda a, b: _num_cmp(a, b) > 0,
    "gt": lambda a, b: _num_cmp(a, b) > 0,
    ">=": lambda a, b: _num_cmp(a, b) >= 0,
    "ge": lambda a, b: _num_cmp(a, b) >= 0,
    "contains": lambda a, b: text_match("contains", a, b),
    "in": lambda a, b: list_membership(a, b),
    "matches": _op_matches,
    "startswith": lambda a, b: text_match("startswith", a, b),
    "endswith": lambda a, b: text_match("endswith", a, b),
}

_ORDER_OPS = {"<", "lt", "<=", "le", ">", "gt", ">=", "ge"}
_NULL_LEFT_REJECTING_OPS = _ORDER_OPS | {"!=", "ne"}


def _apply_op(op, left, right):
    """연산자 하나 적용 — 모르는 op 은 침묵 `==` 폴백이 아니라 정직 거절(B19-1)."""
    op = str(op).lower()
    fn = _OPS.get(op)
    if fn is None:
        raise _WhereError(f"지원하지 않는 연산자 '{op}' — 쓸 수 있는 것: {', '.join(sorted(_OPS))}")

    # B37-1·G37-1(2026-08-25): 희소 행의 None 을 문자열 "None" 으로 승격하면
    # `None > 10` 이 사전식으로 참이고, `None != 10` 도 관측 없이 참이 된다.
    # 왼쪽 결측은 다름·순서를 주장하지 않는다. 순서의 오른쪽 결측도 판정 불능이다.
    # eq 는 결측 검색({field, op:"eq", value:null})을 보존하려고 막지 않는다.
    if left is None and op in _NULL_LEFT_REJECTING_OPS:
        return False
    if right is None and op in _ORDER_OPS:
        return False
    return fn(left, right)


def _as_num(v):
    return numeric_value(v)


def _num_eq(a, b):
    """호환 이름 — 실제 동등성은 common.value_semantics 한 벌이다."""
    return values_equal(a, b)


def _num_cmp(a, b):
    """호환 이름 — 공통 순서의 판정 불능만 filter 오류로 번역한다."""
    order = compare_order(a, b)
    if order is not None:
        return int(order)
    raise _WhereError(
        f"크기 비교 불가 — 좌변 {type(a).__name__}({str(a)[:40]!r}) 과 "
        f"우변 {type(b).__name__}({str(b)[:40]!r}) 은 숫자·날짜(ISO 8601)·문자열 중 "
        "같은 종류여야 합니다"
    )


_CMP_RE = re.compile(r"^\s*(.+?)\s*(>=|<=|==|!=|>|<|=)\s*(.+?)\s*$")

# 워드 연산자(contains/in/matches/startswith/…)도 기호 연산자와 **같은 계약**으로 판다.
# ★2026-08-22 상상훈련 19회차 B19-1: 옛 _CMP_RE 는 기호만 파서 `"아파트명 matches 자이"`
# 같은 문자열이 통째로 전-필드 substring 검색어가 되어 조용히 0건이 나왔다 — 액션 자신이
# 약속한 op 이 모델이 가장 많이 쓰는 문자열 형태에서만 안 지켜지던 비대칭.
# 양쪽 공백을 요구하므로 'startswith' 안의 'in' 같은 부분일치엔 안 걸린다.
_WORD_OPS = tuple(sorted((k for k in _OPS if k.isalpha()), key=len, reverse=True))
_WORD_CMP_RE = re.compile(r"^\s*(.+?)\s+(" + "|".join(_WORD_OPS) + r")\s+(.+?)\s*$", re.IGNORECASE)


def _parse_where_str(where):
    """문자열 where → (field, op, value) · 연산자가 없으면 None(전-필드 substring).

    _match 와 _where_fields 가 **같은 눈**으로 문자열을 읽게 하는 단일 소스 —
    두 자리가 갈리면 '필드는 검증 안 되고 판정만 되는' 비대칭이 다시 생긴다.
    """
    if not isinstance(where, str):
        return None
    m = _CMP_RE.match(where)
    if m:
        field, op, val = m.group(1).strip(), m.group(2), m.group(3).strip()
        if op == "=":
            op = "=="
    else:
        m = _WORD_CMP_RE.match(where)
        if not m:
            return None
        field, op, val = m.group(1).strip(), m.group(2).lower(), m.group(3).strip()
    if len(val) >= 2 and val[0] in "\"'" and val[-1] == val[0]:  # vj-ok: 인용부호 짝 검사
        val = val[1:-1]  # 따옴표 제거
    return field, op, val


_CONJ_RE = re.compile(r"\s+(and|or)\s+", re.IGNORECASE)


def _split_bool(where):
    """" and "/" or " 로 이은 문자열 → OR-of-AND 조각 구조 [[frag, …], …] · 나눌 수 없으면 None.

    ★2026-08-24 B36-1(주거 보고서 실측): `"price >= 200000000 and price <= 400000000"` 은
    _CMP_RE 의 비탐욕 필드 때문에 (price, >=, "200000000 and price <= 400000000") 으로 읽혔다.
    값이 숫자가 아니니 _num_cmp 가 문자열 비교로 내려앉아 3천만원이 '2억 이상'을 통과했고
    (같은 60행 입력에서 28행 통과), 봉투는 success: true 였다 — 조용히 틀린 답.

    ★2026-08-27 filter 마찰 수리(ep1879 실측 2건):
      · " or " — 옛 정직 거절을 **지원**으로 바꾼다. 우선순위 = SQL(or 최하위):
        "A and B or C" = [[A,B],[C]]. 거절문이 가르치던 union>>dedup 우회는 세 문장짜리
        일을 만들었고, 모델은 그냥 or 를 계속 썼다 — 언어가 화자를 따라간다.
      · 비교식·비-비교식 **혼합은 중의성 정직 거절** — 옛 동작은 값 속의 and 로 읽어
        ("summary contains 복층 and 테라스" → '복층 and 테라스' 리터럴 검색) 조용한
        0건을 냈다. 어느 뜻인지 문장만으로 알 수 없으니 고쳐 쓸 두 형태를 안내한다.
    조각 전부가 비-비교식이면(연산자가 어디에도 없으면) None — 통째 전-필드 검색(옛 동작).
    """
    if not isinstance(where, str):
        return None
    parts = _CONJ_RE.split(where)
    if len(parts) < 3:
        return None
    frags = [p.strip() for p in parts[0::2]]
    conns = [str(c).lower() for c in parts[1::2]]
    parsed = [bool(_parse_where_str(f)) for f in frags]
    if not any(parsed):
        return None  # 연산자가 어디에도 없다 — 통째 값/전-필드 검색
    if not all(parsed):
        bad = [f for f, ok in zip(frags, parsed) if not ok]
        raise _WhereError(
            f"조건이 중의적입니다 — and/or 로 이었는데 비교식이 아닌 조각이 있습니다: {bad}. "
            "두 조건 모두라면 조각마다 '필드 op 값' 으로 쓰고"
            "(예: \"summary contains 복층 and summary contains 테라스\"), "
            "값 자체에 and/or 가 든 검색이라면 구조형 {field: \"필드\", op: \"contains\", "
            "value: \"… and …\"} 로 쓰세요."
        )
    groups = [[frags[0]]]
    for conn, frag in zip(conns, frags[1:]):
        if conn == "or":
            groups.append([frag])
        else:
            groups[-1].append(frag)
    return groups


def _match(item, where):
    """item(dict) 이 where 조건을 만족하나.

    where 형태:
      - str "필드 op 값"  : 연산자(기호 >= <= > < == != = · 워드 contains/in/matches/
                            startswith/endswith/eq/ne/lt/le/gt/ge)가 있으면 단일 비교로 파싱
                            (예 "연도 >= 2000" · "아파트명 matches 자이").
                            모델이 자연스럽게 쓰는 SQL식 문자열을 침묵 부분일치로 삼키지 않는다.
      - str "A and B or C": 조각이 전부 비교식이면 논리식 분해 — 우선순위는 SQL 과 같다
                            (or 최하위: (A and B) or C). 비교식·비-비교식 혼합은 중의성
                            정직 거절, 연산자가 어디에도 없으면 통째 전-필드 검색 (B36-1→08-27).
      - str S            : 연산자 없으면 아무 필드 값에 S가 부분일치 (전 필드 substring)
      - {field, op, value}: SQL식 단일 조건 (op 기본 ==; field=col/column 별칭)
      - {col: value, ...}: 각 열=값 동등(AND) 단축형
      - [cond, cond, ...]: AND 결합
    """
    if where is None or where == "":
        return True
    if isinstance(where, str):
        groups = _split_bool(where)
        if groups:  # OR-of-AND — "A and B or C" = (A and B) or C
            return any(all(_match(item, f) for f in g) for g in groups)
        parsed = _parse_where_str(where)
        if parsed:  # 기호·워드 연산자가 든 문자열 → 단일 비교 (침묵 부분일치 함정 제거)
            field, op, val = parsed
            return _apply_op(op, item.get(field), val)
        # 전-필드 substring 도 contains 와 같은 한 벌 — 사설 str().lower() 는 결측을
        # "None" 텍스트로 승격시키고(B46-3 의 잔당, 46회차 후속 census 가 적발)
        # 구조 값을 repr 로 읽었다. 스칼라 필드만 텍스트 공간에서 검색한다.
        return any(text_match("contains", v, where) for v in item.values())
    if isinstance(where, list):
        return all(_match(item, w) for w in where)
    if isinstance(where, dict):
        field = where.get("field") or where.get("col") or where.get("column")
        if field is not None:  # 구조형 {field, op, value}
            op = str(where.get("op", "==")).lower()
            return _apply_op(op, item.get(str(field)), where.get("value"))
        # 단축형 {col: value, ...} — 모두 동등(AND)
        return all(_num_eq(item.get(str(k)), v) for k, v in where.items())
    return True


# ───────────────────────── sort 키 (수치 인식) ─────────────────────────

def _sort_key(field):
    return value_sort_key(field, _as_num)


def _sort_records(records, field, desc=False):
    """수치→문자열→결측 순서는 고정하고, 각 값 부류 안의 방향만 뒤집는다.

    ``sorted(..., reverse=True)`` 는 값뿐 아니라 종류 표지까지 뒤집어 None 과 문자열을
    숫자보다 앞으로 보냈다. 결측값은 정렬 방향과 무관하게 끝에 두는 것이 계약이다.
    """
    return sort_records(records, field, desc, _as_num)


def _where_fields(where):
    """where 조건이 명시적으로 가리키는 필드 이름들(존재 검증용).

    전-필드 substring 형태(연산자 없는 문자열)는 필드를 지목하지 않으므로 [].
    """
    if isinstance(where, str):
        groups = _split_bool(where)
        if groups:  # 조각마다 필드를 지목한다 — 존재 검증도 조각 단위로 (B36-1)
            return [_parse_where_str(f)[0] for g in groups for f in g]
        parsed = _parse_where_str(where)
        return [parsed[0]] if parsed else []
    if isinstance(where, list):
        out = []
        for w in where:
            out.extend(_where_fields(w))
        return out
    if isinstance(where, dict):
        f = where.get("field") or where.get("col") or where.get("column")
        if f:
            return [str(f)]
        return [str(k) for k in where.keys() if k not in ("op", "value")]
    return []
