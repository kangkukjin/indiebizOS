"""where_dsl.py — data-ops 의 조건 언어(where 미니 DSL) + 정렬 키.

handler.py 에서 분리(2026-08-22, 1500줄 규칙). 이 모듈은 **행 하나가 조건을 만족하나**
만 판정한다 — 통화를 모르고 변환자를 모른다(handler 는 이 판정을 빌려 쓸 뿐).

조건 언어의 계약(19회차 B19-1 판정):
  · 문자열 "필드 op 값" — 기호(>= <= > < == != =)와 워드(contains/in/matches/
    startswith/endswith/eq/ne/lt/le/gt/ge)를 **같은 계약**으로 판다.
  · 연산자가 없는 문자열은 전-필드 부분일치(검색어).
  · " and " 로 이은 문자열은 **조각 전부가 비교식일 때만** AND 로 나눈다(리스트 형과 같은 뜻).
    조각 하나라도 비교식이 아니면 값 속의 and 이므로 나누지 않는다("제목 contains 국밥 and 라면").
    " or " 는 리스트 형으로 옮길 수 없으므로 조용히 삼키지 않고 정직 거절.
  · 모르는 op·깨진 정규식은 침묵 폴백이 아니라 _WhereError(정직 거절).
  · matches 는 `[if:]` 술어와 같은 뜻(re.search) — 한 몸 안의 두 조건 언어를 같게 둔다.
"""

import re


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
    """
    if a is None:
        return False
    try:
        return re.search(str(b), str(a)) is not None
    except re.error as e:
        raise _WhereError(f"정규식 오류 '{b}': {e}")


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
    "contains": lambda a, b: str(b).lower() in str(a).lower(),
    "in": lambda a, b: (a in b) if isinstance(b, (list, tuple, set)) else (str(a).lower() in str(b).lower()),
    "matches": _op_matches,
    "startswith": lambda a, b: str(a).lower().startswith(str(b).lower()),
    "endswith": lambda a, b: str(a).lower().endswith(str(b).lower()),
}


def _apply_op(op, left, right):
    """연산자 하나 적용 — 모르는 op 은 침묵 `==` 폴백이 아니라 정직 거절(B19-1)."""
    fn = _OPS.get(str(op).lower())
    if fn is None:
        raise _WhereError(f"지원하지 않는 연산자 '{op}' — 쓸 수 있는 것: {', '.join(sorted(_OPS))}")
    return fn(left, right)


def _as_num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except Exception:
        return None


def _num_eq(a, b):
    na, nb = _as_num(a), _as_num(b)
    if na is not None and nb is not None:
        return na == nb
    return str(a).strip().lower() == str(b).strip().lower()


def _num_cmp(a, b):
    na, nb = _as_num(a), _as_num(b)
    if na is not None and nb is not None:
        return (na > nb) - (na < nb)
    sa, sb = str(a), str(b)
    return (sa > sb) - (sa < sb)


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
    if len(val) >= 2 and val[0] in "\"'" and val[-1] == val[0]:
        val = val[1:-1]  # 따옴표 제거
    return field, op, val


_CONJ_RE = re.compile(r"\s+(and|or)\s+", re.IGNORECASE)


def _split_conjunction(where):
    """" and " 로 이은 문자열 → 조각 목록 · 나눌 수 없으면 None.

    ★2026-08-24 B36-1(주거 보고서 실측): `"price >= 200000000 and price <= 400000000"` 은
    _CMP_RE 의 비탐욕 필드 때문에 (price, >=, "200000000 and price <= 400000000") 으로 읽혔다.
    값이 숫자가 아니니 _num_cmp 가 문자열 비교로 내려앉아 3천만원이 '2억 이상'을 통과했고
    (같은 60행 입력에서 28행 통과), 봉투는 success: true 였다 — 조용히 틀린 답.
    '상한만 무시'가 아니라 **두 조건이 다 무의미해지는** 사고다.

    나누는 조건은 **조각 전부가 비교식**일 때뿐 — 값 속의 and("제목 contains 국밥 and 라면")
    를 쪼개면 멀쩡하던 검색이 죽는다. 그 경우엔 옛 동작(단일 비교)을 그대로 둔다.
    """
    if not isinstance(where, str):
        return None
    parts = _CONJ_RE.split(where)
    if len(parts) < 3:
        return None
    frags = [p.strip() for p in parts[0::2]]
    if not all(_parse_where_str(f) for f in frags):
        return None  # 값 속의 and — 옛 동작 유지
    if any(str(c).lower() == "or" for c in parts[1::2]):
        raise _WhereError(
            "where 문자열의 'or' 는 지원하지 않습니다 — 리스트 형([\"조건\", \"조건\"])은 AND 뿐입니다. "
            "OR 이 필요하면 조건마다 따로 거른 뒤 [table:union] >> [table:dedup] 으로 합치세요."
        )
    return frags


def _match(item, where):
    """item(dict) 이 where 조건을 만족하나.

    where 형태:
      - str "필드 op 값"  : 연산자(기호 >= <= > < == != = · 워드 contains/in/matches/
                            startswith/endswith/eq/ne/lt/le/gt/ge)가 있으면 단일 비교로 파싱
                            (예 "연도 >= 2000" · "아파트명 matches 자이").
                            모델이 자연스럽게 쓰는 SQL식 문자열을 침묵 부분일치로 삼키지 않는다.
      - str "A and B"    : 조각이 전부 비교식이면 AND 분해 (리스트 형과 같은 뜻, B36-1).
                            값 속의 and 는 안 쪼갠다. ' or ' 는 정직 거절.
      - str S            : 연산자 없으면 아무 필드 값에 S가 부분일치 (전 필드 substring)
      - {field, op, value}: SQL식 단일 조건 (op 기본 ==; field=col/column 별칭)
      - {col: value, ...}: 각 열=값 동등(AND) 단축형
      - [cond, cond, ...]: AND 결합
    """
    if where is None or where == "":
        return True
    if isinstance(where, str):
        frags = _split_conjunction(where)
        if frags:  # "A and B" → 리스트 형과 같은 뜻 (B36-1)
            return all(_match(item, f) for f in frags)
        parsed = _parse_where_str(where)
        if parsed:  # 기호·워드 연산자가 든 문자열 → 단일 비교 (침묵 부분일치 함정 제거)
            field, op, val = parsed
            return _apply_op(op, item.get(field), val)
        s = where.lower()
        return any(s in str(v).lower() for v in item.values())
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
    def key(item):
        v = item.get(str(field)) if isinstance(item, dict) else None
        n = _as_num(v)
        # 숫자 먼저(0) 안정 정렬, 그다음 문자열(1). None은 맨 뒤.
        if v is None:
            return (2, 0.0, "")
        if n is not None:
            return (0, n, "")
        return (1, 0.0, str(v).lower())
    return key


def _sort_records(records, field, desc=False):
    """수치→문자열→결측 순서는 고정하고, 각 값 부류 안의 방향만 뒤집는다.

    ``sorted(..., reverse=True)`` 는 값뿐 아니라 종류 표지까지 뒤집어 None 과 문자열을
    숫자보다 앞으로 보냈다. 결측값은 정렬 방향과 무관하게 끝에 두는 것이 계약이다.
    """
    key = _sort_key(field)
    buckets = {0: [], 1: [], 2: []}
    for row in records:
        buckets[key(row)[0]].append(row)
    return (sorted(buckets[0], key=key, reverse=desc)
            + sorted(buckets[1], key=key, reverse=desc)
            + buckets[2])


def _where_fields(where):
    """where 조건이 명시적으로 가리키는 필드 이름들(존재 검증용).

    전-필드 substring 형태(연산자 없는 문자열)는 필드를 지목하지 않으므로 [].
    """
    if isinstance(where, str):
        frags = _split_conjunction(where)
        if frags:  # 조각마다 필드를 지목한다 — 존재 검증도 조각 단위로 (B36-1)
            return [_parse_where_str(f)[0] for f in frags]
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
