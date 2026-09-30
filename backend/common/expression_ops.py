"""Edition 2 pure operations; numeric observations belong to value_semantics."""
from dataclasses import dataclass
from decimal import Decimal
import json
import operator
from common.value_semantics import (values_equal, compare_order,
                                    order_matches, list_membership, public_result,
                                    normalized_text, arithmetic_numbers)
from common.expression_functions import CONTRACTS, call as value_call
from common.expression_ir import Fault, Node, ResultValue, Unit, projection


# (minimum, maximum) argument counts; shared by compiler and evaluator.
BUILTINS = {"len": (1, 1), "has": (2, 2), "get": (2, 3), "json": (1, 1),
            "number": (1, 1), "text": (1, 1), "abs": (1, 1), "round": (1, 2),
            "min": (1, 1000), "max": (1, 1000), "sum": (1, 1),
            "is_ok": (1, 1), "unwrap": (1, 1), "error_of": (1, 1),
            "evidence": (1, 1), "reduce": (3, 3)}

BUILTINS.update({name: spec[:2] for name, spec in CONTRACTS.items()})


@dataclass(frozen=True)
class Closure:
    params: tuple
    body: object
    env: dict


@dataclass(frozen=True)
class Builtin:
    """An internal callable reference, never an ordinary JSON value."""
    name: str


def free_names(node, bound=frozenset()):
    """Lexical dependencies of a pure expression, including nested lambdas.

    Capturing the entire frame retains unrelated results/callables and makes
    subsequent request fingerprints depend on work the callback never reads.
    Inner parameters shadow outer names, but inner free names must still be
    available when the outer closure creates that inner closure.
    """
    if isinstance(node, Node):
        if node.kind == "ref":
            return {node.data["name"]} - bound
        if node.kind == "lambda":
            return free_names(node.data["body"], bound | set(node.data["params"]))
        return free_names(node.data, bound)
    if isinstance(node, dict):
        children = node.values()
    elif isinstance(node, (list, tuple)):
        children = node
    else:
        children = ()
    result = set()
    for child in children:
        result.update(free_names(child, bound))
    return result


# 다른 언어의 관용 이름 → 이 언어의 내장 함수. 가까운 철자(difflib)로는 못 잇는 짝만 적는다
# (count→len 을 모르는 모델이 BUILTIN 거절을 받고 같은 이름을 다시 쓰던 자리 — 76회차 T24·F72-2 재확인).
_BUILTIN_SYNONYMS = {"count": "len", "length": "len", "size": "len", "str": "text", "string": "text",
                     "int": "number", "float": "number", "includes": "contains", "has_text": "contains",
                     "distinct": "unique", "sort": "sorted", "concat": "join", "lowercase": "lower",
                     "uppercase": "upper", "trim": "strip", "items": "entries"}


def unknown_builtin_message(name):
    """알 수 없는 내장 함수 이름의 진단 문장 — 컴파일·실행 두 자리가 같은 문장을 쓴다."""
    from difflib import get_close_matches
    near = [_BUILTIN_SYNONYMS[name]] if name in _BUILTIN_SYNONYMS else []
    near += [c for c in get_close_matches(name, BUILTINS, n=3, cutoff=0.6) if c not in near]
    return f"알 수 없는 내장 함수: {name}" + (f". 비슷한 내장 함수: {', '.join(near)}" if near else "")


def check_arity(name, count):
    if name not in BUILTINS:
        raise Fault("BUILTIN", unknown_builtin_message(name))
    lower, upper = BUILTINS[name]
    if not lower <= count <= upper:
        raise Fault("ARITY", f"{name}의 인자 수는 {lower}~{upper}개입니다.")


def boolean(value):
    if type(value) is not bool:
        raise Fault("BOOL_REQUIRED", "조건에는 Bool이 필요합니다.")
    return value


def number(value):
    try:
        return arithmetic_numbers([value])[0]
    except ValueError as exc:
        preview = repr(value)[:240]
        raise Fault("NUMBER_REQUIRED", f"number(): 유한 숫자로 해석할 수 없습니다: {preview}. "
                    "해석 실패는 null이 아니라 오류입니다. [try]/[catch]로 처리하세요.",
                    details={"operation": "number", "input_preview": preview,
                             "input_type": type(value).__name__, "expected": "finite number"}) from exc


def scalar_text(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    from common.value_semantics import integer_value
    integer = integer_value(value)
    if integer is not None:
        return str(integer)
    if isinstance(value, (str, int, float, Decimal)):
        return normalized_text(str(value))
    if value is None:
        raise Fault("TEXT_REQUIRED", "Text·Number·Bool만 문자열로 바꿀 수 있습니다. 이 값은 null입니다 — "
                    "보간·text() 앞에서 `$x == null ? '없음' : text($x)`처럼 가르세요.",
                    details={"actual": "Null", "expected": "Bool | Number | Text"})
    raise Fault("TEXT_REQUIRED", "Text·Number·Bool만 문자열로 바꿀 수 있습니다. 구조에는 json()을 쓰세요.",
                details={"actual": type(value).__name__, "expected": "Bool | Number | Text"})


def binary(op, left, right, *, legacy=False):
    if op in ("==", "!="):
        equal = values_equal(left, right)
        return equal if op == "==" else not equal
    if op in ("<", ">", "<=", ">="):
        result = compare_order(left, right)
        if result is None:
            raise Fault("UNORDERED", "서로 비교할 수 없는 값입니다.")
        return order_matches(result, {"<": "lt", ">": "gt", "<=": "le", ">=": "ge"}[op])
    if op == "in":
        if not isinstance(right, list):
            raise Fault("LIST_REQUIRED", "in의 오른쪽은 List입니다. 문자열 부분 검색에는 contains(text, part)를 쓰세요.")
        return list_membership(left, right)
    if op == "+" and isinstance(left, str) and isinstance(right, str):
        return normalized_text(left + right)
    if op == "+" and isinstance(left, list) and isinstance(right, list):
        return left + right
    operation = {"+": operator.add, "-": operator.sub, "*": operator.mul,
                 "/": operator.truediv, "//": operator.floordiv, "%": operator.mod, "**": operator.pow}[op]
    if legacy:
        if op == "**" and isinstance(right, (int, float, Decimal)) and abs(right) > 10000:
            raise Fault("ARITHMETIC_BUDGET", "거듭제곱 지수 예산을 초과했습니다.", kind="budget")
        return operation(left, right)
    try:
        a, b = arithmetic_numbers([left, right])
    except ValueError as error:
        raise Fault("NUMBER_REQUIRED", str(error)) from error
    if op == "**" and abs(b) > 10000:
        raise Fault("ARITHMETIC_BUDGET", "거듭제곱 지수 예산을 초과했습니다.", kind="budget")
    # Keep floor division/remainder's existing sign convention for Decimal.
    if op in ("//", "%") and any(isinstance(n, Decimal) for n in (a, b)):
        quotient, remainder = divmod(a, b)
        if remainder and (a < 0) != (b < 0):
            quotient -= 1
            remainder += b
        return int(quotient) if op == "//" else remainder
    result = operation(a, b)
    return int(result) if op == "//" else result


def pure_call(name, args, *, tick=lambda: None, callback=None):
    check_arity(name, len(args))
    if name in CONTRACTS:
        return value_call(name, args, tick, callback)
    check_arity(name, len(args))
    first = args[0]
    if name == "len":
        if not isinstance(first, (str, list, dict)):
            raise Fault("SIZED_REQUIRED", "len에는 Text, List, Record가 필요합니다.")
        return len(normalized_text(first) if isinstance(first, str) else first)
    if name in ("has", "get"):
        if not isinstance(first, dict) or not isinstance(args[1], str):
            raise Fault("RECORD_REQUIRED", "has/get은 Record와 Text 키를 받습니다.")
        # get 의 기본값은 생략하면 null 이다(2026-09-30 개정).
        return args[1] in first if name == "has" else first.get(args[1], args[2] if len(args) > 2 else None)
    if name == "json":
        # Unit/Result/Callable are not silently serialized as business JSON.
        try:
            return json.dumps(public_result(first, strict=True), ensure_ascii=False, allow_nan=False)
        except ValueError as error:
            raise Fault(getattr(error, "code", "NON_JSON_RESULT"), str(error)) from error
    if name == "number":
        return number(first)
    if name == "text":
        return scalar_text(first)
    if name == "abs":
        return abs(number(first))
    if name == "round":
        if len(args) == 2:
            from common.value_semantics import integer_value
            digits = integer_value(args[1])   # 값이 정수인 Number(2.0·4/2)는 자릿수로 받는다 — 인덱스와 같은 판정
            if digits is None:
                raise Fault("INTEGER_REQUIRED", "round의 자릿수는 정수입니다.")
            return round(number(first), digits)
        return round(number(first))
    if name in ("min", "max", "sum"):
        values = first if len(args) == 1 and isinstance(first, list) else args
        numbers = []
        for value in values:
            tick()
            if isinstance(value, str):
                raise Fault("NUMBER_REQUIRED", f"{name}은 Number 전용입니다. Text 목록은 sorted(목록)[0] 또는 sorted(목록)[-1]로 비교하세요.")
            numbers.append(number(value))
        numbers = arithmetic_numbers(numbers)
        return {"min": min, "max": max, "sum": sum}[name](numbers)
    if name in ("is_ok", "unwrap", "error_of"):
        if not isinstance(first, ResultValue):
            raise Fault("RESULT_REQUIRED", f"{name}에는 Result가 필요합니다.")
        if name == "is_ok":
            return first.ok
        if name == "unwrap":
            if not first.ok:
                raise Fault("UNWRAP_ERR", "Err은 unwrap할 수 없습니다.", details=projection(first.error))
            return first.value
        if first.ok:
            raise Fault("ERROR_OF_OK", "Ok에는 오류가 없습니다.")
        return first.error
    raise Fault("BUILTIN", f"직접 실행할 수 없는 내장 함수: {name}")
