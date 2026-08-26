"""ibl_predicates.py — 조건식(술어) 언어 (2026-08-22, 프로그램급 IBL M2).

`[if:]`·`[else if:]`·`[case:]`(소스)·(M4) `[repeat:]` 의 조건을 평가한다.
설계 정본: docs/IBL_PROGRAM_GRADE_DESIGN.md §2.1. 헌법(ibl.md '언어의 경계') 문법 1항의
**조건 언어**가 이 모듈이다 — 어휘 이름은 한 글자도 박혀 있지 않다(이름-무검증).

문법:
    expr    := or
    or      := and ( 'or' and )*
    and     := not ( 'and' not )*
    not     := 'not' not | cmp
    cmp     := primary ( OP primary )?          OP ∈ == != > >= < <= matches
    primary := '(' expr ')' | atom
    atom    := 리터럴(숫자·"문자열"·true·false·null)
             | $변수[.경로]                       # 앞 문장이 할당한 값 — 실행 없이 이미 가진 값
             | count(atom) | empty(atom) | exists(atom)
             | node:action{…}[.경로]             # 소스 참조(실행) — 종전 문법 그대로
             | [node:action]{…}[.경로]           # 대괄호 형태도 같은 뜻(AI 술어 [table:brief] 관용)

판정 불능 ≠ 거짓 (B8 부류): 좌변을 못 읽음·변수 미할당·정규식 오류·형 불일치 크기비교는
PredicateError 로 올린다 — 호출자(_execute_condition)가 condition_errors 정직 채널에 싣는다.

AI 술어: `[table:brief]{instruction: "... yes/no"} == "yes"` — brief 의 message 가 좌변값.
yes/no/true/false 리터럴과의 비교는 대소문자·끝 구두점을 무시한다("Yes." == "yes").
"""
import json
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from common.value_semantics import (compare_order, numeric_value, regex_text,
                                    values_equal)

from common.field_path import MISSING as _MISSING, walk_path as _fp_walk  # 경로 해석 한 벌 (2026-08-27)
_KEYWORDS = {"and", "or", "not"}
_OPS2 = ("==", "!=", ">=", "<=")
_OPS1 = (">", "<")
_FUNCS = ("count", "empty", "exists")
_SOURCE_RE = re.compile(r'^\[?\w+:\w+\]?(\{|\.|$)')


class PredicateError(ValueError):
    """조건 판정 불능 — 거짓이 아니다."""


# ── 토큰화 ────────────────────────────────────────────────────────────────────
def tokenize(cond: str) -> List[Tuple[str, str]]:
    """깊이 0(중괄호·대괄호·문자열 밖)에서만 토큰을 자른다.

    kind: 'lp' 'rp' 'op' 'kw' 'atom'. `count($x)` 처럼 이름 뒤에 붙은 괄호는 atom 에 속한다
    (함수 호출), 홀로 선 괄호만 묶음이다.
    """
    toks: List[Tuple[str, str]] = []
    cur: List[str] = []
    depth = 0            # {} [] 깊이
    paren_in_atom = 0    # atom 에 속한 ( ) 깊이
    in_s = False
    q = ""
    i, n = 0, len(cond)

    def flush():
        if cur:
            t = "".join(cur)
            cur.clear()
            low = t.lower()
            if low in _KEYWORDS:
                toks.append(("kw", low))
            elif low == "matches":
                toks.append(("op", "matches"))
            else:
                toks.append(("atom", t))

    while i < n:
        c = cond[i]
        if in_s:
            cur.append(c)
            if c == "\\" and i + 1 < n:
                cur.append(cond[i + 1])
                i += 2
                continue
            if c == q:
                in_s = False
            i += 1
            continue
        if c in "\"'":
            in_s = True
            q = c
            cur.append(c)
            i += 1
            continue
        if c in "{[":
            depth += 1
            cur.append(c)
            i += 1
            continue
        if c in "}]":
            depth -= 1
            cur.append(c)
            i += 1
            continue
        if depth > 0 or paren_in_atom > 0:
            if c == "(":
                paren_in_atom += 1
            elif c == ")":
                paren_in_atom -= 1
            cur.append(c)
            i += 1
            continue
        # 깊이 0
        if c == "(":
            if cur:                       # 함수 호출 — atom 의 일부
                paren_in_atom += 1
                cur.append(c)
            else:
                toks.append(("lp", "("))
            i += 1
            continue
        if c == ")":
            flush()
            toks.append(("rp", ")"))
            i += 1
            continue
        if c.isspace():
            flush()
            i += 1
            continue
        two = cond[i:i + 2]
        if two in _OPS2:
            flush()
            toks.append(("op", two))
            i += 2
            continue
        if c in _OPS1:
            flush()
            toks.append(("op", c))
            i += 1
            continue
        cur.append(c)
        i += 1
    if in_s:
        raise PredicateError(f"조건식의 문자열이 닫히지 않았습니다: {cond[:60]}")
    if depth != 0 or paren_in_atom != 0:
        raise PredicateError(f"조건식의 괄호가 맞지 않습니다: {cond[:60]}")
    flush()
    return toks


# ── 파싱 (AST = 튜플) ─────────────────────────────────────────────────────────
class _Parser:
    def __init__(self, toks: List[Tuple[str, str]], src: str):
        self.t = toks
        self.i = 0
        self.src = src

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def parse(self):
        if not self.t:
            raise PredicateError("빈 조건식입니다.")
        node = self.p_or()
        if self.i < len(self.t):
            k, v = self.peek()
            raise PredicateError(
                f"조건식에 해석되지 않은 토큰 '{v}' — 두 값 사이엔 비교 연산자(== != > >= < <= matches)나 "
                f"and/or 가 있어야 합니다. 자연어 조건은 평가되지 않습니다: '{self.src[:60]}'")
        return node

    def p_or(self):
        left = self.p_and()
        while self.peek() == ("kw", "or"):
            self.take()
            left = ("or", left, self.p_and())
        return left

    def p_and(self):
        left = self.p_not()
        while self.peek() == ("kw", "and"):
            self.take()
            left = ("and", left, self.p_not())
        return left

    def p_not(self):
        if self.peek() == ("kw", "not"):
            self.take()
            return ("not", self.p_not())
        return self.p_cmp()

    def p_cmp(self):
        left = self.p_primary()
        k, v = self.peek()
        if k == "op":
            self.take()
            right = self.p_primary()
            return ("cmp", v, left, right)
        return left

    def p_primary(self):
        k, v = self.take()
        if k == "lp":
            node = self.p_or()
            if self.take() != ("rp", ")"):
                raise PredicateError(f"닫는 괄호가 없습니다: '{self.src[:60]}'")
            return node
        if k == "atom":
            return ("atom", v)
        if k is None:
            raise PredicateError(f"조건식이 피연산자 없이 끝났습니다: '{self.src[:60]}'")
        raise PredicateError(f"조건식에서 예상치 못한 토큰 '{v}': '{self.src[:60]}'")


def parse_condition(cond: str):
    return _Parser(tokenize(cond), cond).parse()


# ── atom 분류 ─────────────────────────────────────────────────────────────────
def classify_atom(text: str) -> Tuple[str, Any]:
    """('literal', 값) | ('var', (이름, 경로)) | ('func', (이름, 내부 atom 텍스트)) | ('source', 'node:action{…}[.f]') | ('unknown', text)"""
    t = text.strip()
    if not t:
        return "unknown", t
    if (t[0] == '"' and t[-1] == '"') or (t[0] == "'" and t[-1] == "'"):
        return "literal", t[1:-1]
    low = t.lower()
    if low in ("true", "false"):
        return "literal", (low == "true")
    if low in ("null", "none"):
        return "literal", None
    try:
        return "literal", (int(t) if re.fullmatch(r"-?\d+", t) else float(t))
    except ValueError:
        pass
    if t.startswith("$"):
        from common.ibl_vars import REF_RE
        m = REF_RE.fullmatch(t)
        if not m:
            return "unknown", t
        from common.ibl_vars import split_ref
        name, raw_path = split_ref(m)
        return "var", (name, raw_path[1:] if raw_path else None)
    m = re.fullmatch(r"(\w+)\((.*)\)", t, re.DOTALL)
    if m and m.group(1).lower() in _FUNCS:
        return "func", (m.group(1).lower(), m.group(2).strip())
    if t.startswith("["):
        # [node:action]{…}[.f] → node:action{…}[.f]
        m2 = re.match(r"^\[(\w+:\w+)\](.*)$", t, re.DOTALL)
        if m2:
            t = m2.group(1) + m2.group(2)
    if _SOURCE_RE.match(t):
        return "source", t
    return "unknown", t


def referenced_vars(cond: str) -> List[str]:
    """조건식이 참조하는 $변수 이름(중복 제거, 등장 순)."""
    seen: List[str] = []
    from common.ibl_vars import find_names
    for name in find_names(cond or ""):
        if name not in seen:
            seen.append(name)
    return seen


# ── 값 보조 ───────────────────────────────────────────────────────────────────
def _load_var(raw: Any) -> Any:
    """step 결과(대개 JSON 문자열)를 값으로."""
    if isinstance(raw, str):
        s = raw.strip()
        if s[:1] in "{[":
            try:
                return json.loads(s)
            except Exception:
                return raw
    return raw


def walk_path(obj: Any, path: Optional[str]) -> Any:
    """점 경로 추출 — dict 키와 리스트 인덱스(숫자). 부재는 _MISSING.

    걷는 규칙의 정본은 common.field_path 한 벌이다(2026-08-27 경로 방언 통일).
    """
    return _fp_walk(obj, path) if path else obj


def _num(v: Any) -> Optional[float]:
    return numeric_value(v)


def _count(v: Any, label: str) -> int:
    if isinstance(v, list):
        return len(v)
    if isinstance(v, dict):
        if isinstance(v.get("items"), list):
            return len(v["items"])
        for k in ("count", "total"):
            n = _num(v.get(k))
            if n is not None:
                return int(n)
    raise PredicateError(f"count({label}): 목록(items)이 아니라 개수를 셀 수 없습니다 — "
                         f"값의 모양: {type(v).__name__}")


def _empty(v: Any) -> bool:
    if v is None or v == "" or v == [] or v == {}:
        return True
    if isinstance(v, dict) and isinstance(v.get("items"), list):
        return len(v["items"]) == 0
    if isinstance(v, str):
        return not v.strip()
    return False


# ── 평가 ─────────────────────────────────────────────────────────────────────
class Evaluator:
    """resolve_source(text) -> (값, 오류문|None) 은 호출자가 준다(실행 엔진 의존 역전)."""

    def __init__(self, resolve_source: Callable[[str], Tuple[Any, Optional[str]]],
                 var_values: Optional[Dict[str, Any]] = None):
        self.resolve_source = resolve_source
        self.vars = var_values or {}
        self.first_left: Any = _MISSING   # matched_value 메타용 — 첫 좌변 실측값

    # atom → 값 (checked=True 면 경로 부재를 _MISSING 으로 돌려준다)
    def atom_value(self, text: str, checked: bool = False) -> Any:
        kind, payload = classify_atom(text)
        if kind == "literal":
            return payload
        if kind == "var":
            name, path = payload
            if name not in self.vars:
                raise PredicateError(
                    f"변수 ${name} 이(가) 이 문장 앞에서 할당되지 않았습니다 — "
                    f"`${name} = [node:action]{{...}}` 문장을 먼저 두세요.")
            base = _load_var(self.vars[name])
            # 스칼라 봉투(식 할당·reduce: {value, message}) 는 경로 없이 쓰면 value 가 값 (M6)
            if path is None and isinstance(base, dict) and "value" in base and not isinstance(base.get("items"), list):
                return base["value"]
            v = walk_path(base, path)
            if v is _MISSING:
                if checked:
                    return _MISSING
                hint = ""
                if isinstance(base, dict):
                    hint = f" 사용 가능한 필드: {sorted(k for k in base.keys() if isinstance(k, str) and not k.startswith('_'))[:16]}"
                raise PredicateError(f"${name}.{path} 경로가 값에 없습니다.{hint}")
            return v
        if kind == "func":
            fname, inner = payload
            if fname == "exists":
                v = self.atom_value(inner, checked=True)
                return v is not _MISSING and v is not None
            v = self.atom_value(inner)
            if fname == "count":
                return _count(v, inner)
            return _empty(v)
        if kind == "source":
            v, err = self.resolve_source(payload)
            if err:
                if checked and "경로" in err:
                    return _MISSING
                raise PredicateError(f"조건 좌변 '{payload}' 에서 값을 읽지 못했습니다 — {err}")
            return v
        raise PredicateError(
            f"'{text}' 은(는) 소스 참조(node:action)·$변수·리터럴·술어 함수(count/empty/exists) "
            f"어느 것도 아닙니다 — 자연어 조건은 평가되지 않습니다.")

    def _note_left(self, v: Any):
        if self.first_left is _MISSING:
            self.first_left = v

    def eval(self, node) -> bool:
        tag = node[0]
        if tag == "or":
            return self.eval(node[1]) or self.eval(node[2])
        if tag == "and":
            return self.eval(node[1]) and self.eval(node[2])
        if tag == "not":
            return not self.eval(node[1])
        if tag == "atom":
            v = self.atom_value(node[1])
            self._note_left(v)
            if isinstance(v, dict) and isinstance(v.get("items"), list):
                return len(v["items"]) > 0
            return bool(v)
        if tag == "cmp":
            _, op, left, right = node
            lv = self._operand(left)
            self._note_left(lv)
            rv = self._operand(right)
            return self.compare(op, lv, rv, left, right)
        raise PredicateError(f"알 수 없는 조건 노드: {tag}")

    def _operand(self, node) -> Any:
        if node[0] == "atom":
            return self.atom_value(node[1])
        # 괄호 묶인 하위 식이 피연산자 자리에 오면 그 진릿값
        return self.eval(node)

    @staticmethod
    def compare(op: str, lv: Any, rv: Any, lnode=None, rnode=None) -> bool:
        if op == "matches":
            if lv is None:
                raise PredicateError("matches 좌변이 null 입니다.")
            lv_text = regex_text(lv)
            if lv_text is None:
                # 구조(list/dict)를 repr 로 정규식에 먹이면 따옴표·괄호가 우연 판정을
                # 만든다(B46-4). 판정 불능은 거짓이 아니다 — 정직 오류 채널로.
                raise PredicateError(
                    f"matches 좌변이 목록/사전({type(lv).__name__})입니다 — "
                    "텍스트 필드를 경로로 지목하세요.")
            try:
                return re.search(regex_text(str(rv)), lv_text) is not None
            except re.error as e:
                raise PredicateError(f"정규식 오류 '{rv}': {e}")
        if op in ("==", "!="):
            eq = values_equal(lv, rv)
            return eq if op == "==" else not eq
        order = compare_order(lv, rv)
        if order is None:
            raise PredicateError(
                f"크기 비교({op}) 불가 — 좌변 {type(lv).__name__}({str(lv)[:40]!r}) 과 "
                f"우변 {type(rv).__name__}({str(rv)[:40]!r}) 은 숫자·날짜(ISO 8601)·문자열 중 "
                "같은 종류여야 합니다.")
        if op == ">":
            return order > 0
        if op == ">=":
            return order >= 0
        if op == "<":
            return order < 0
        if op == "<=":
            return order <= 0
        raise PredicateError(f"알 수 없는 비교 연산자 {op}")


def evaluate(cond: str, resolve_source, var_values: Optional[Dict[str, Any]] = None) -> Tuple[bool, Any]:
    """(판정 bool, 첫 좌변 실측값|None). 판정 불능은 PredicateError."""
    tree = parse_condition(cond)
    ev = Evaluator(resolve_source, var_values)
    ok = ev.eval(tree)
    left = None if ev.first_left is _MISSING else ev.first_left
    return bool(ok), left


# ── 정적 검수 (dry-run) ───────────────────────────────────────────────────────
def validate_condition(cond: str, known_vars: Optional[List[str]] = None) -> Optional[str]:
    """실행 없이 조건식의 모양을 검사 — 경고문 또는 None.

    조종실 dry-run(/ibl/validate)·교재가 약속한 "자연어 조건은 미리 소리 낸다"의 자리.
    """
    try:
        tree = parse_condition(cond)
    except PredicateError as e:
        return str(e)
    problems: List[str] = []
    grounded = [False]

    def walk(node):
        tag = node[0]
        if tag == "atom":
            kind, payload = classify_atom(node[1])
            if kind == "unknown":
                problems.append(f"'{node[1]}' 은(는) 소스 참조·$변수·리터럴·술어 함수 어느 것도 아닙니다")
            elif kind in ("var", "source"):
                grounded[0] = True
                if kind == "var" and known_vars is not None and payload[0] not in known_vars:
                    problems.append(f"${payload[0]} 이(가) 앞 문장에서 할당되지 않았습니다")
            elif kind == "func":
                ik, ip = classify_atom(payload[1])
                if ik == "unknown":
                    problems.append(f"{payload[0]}({payload[1]}) 의 인자가 소스 참조·$변수가 아닙니다")
                else:
                    grounded[0] = True
                    if ik == "var" and known_vars is not None and ip[0] not in known_vars:
                        problems.append(f"${ip[0]} 이(가) 앞 문장에서 할당되지 않았습니다")
            return
        for child in node[1:]:
            if isinstance(child, tuple):
                walk(child)

    walk(tree)
    if not grounded[0] and not problems:
        return ("조건식 경고: 조건에 실행 소스(node:action)도 $변수도 없습니다 — 상수 조건은 늘 같은 분기를 타므로 "
                "분기가 아닙니다. 예: [if: count($r) > 0] / [if: sense:host{op: \"status\"}.cpu_percent > 80]")
    if problems:
        return ("조건식 경고: " + "; ".join(problems) +
                ". 실행 시 이 조건은 '판정 불능'으로 분기를 보류합니다(거짓 아님). "
                '예: [if: count($r) > 0 and $r.items.0.price < 100] / [if: sense:host{op: "status"}.cpu_percent > 80]')
    return None
