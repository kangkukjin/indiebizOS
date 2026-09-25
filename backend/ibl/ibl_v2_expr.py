"""Edition 2 pure operations; numeric observations belong to value_semantics."""
from dataclasses import dataclass
from decimal import Decimal
import json
import operator
from common.value_semantics import (numeric_value, values_equal, compare_order,
                                    order_matches, list_membership, public_result)
from ibl_v2_ir import Fault, ResultValue, Unit, projection


# (minimum, maximum) argument counts; shared by compiler and evaluator.
BUILTINS = {"len": (1, 1), "has": (2, 2), "get": (3, 3), "json": (1, 1),
            "number": (1, 1), "text": (1, 1), "abs": (1, 1), "round": (1, 2),
            "min": (1, 1000), "max": (1, 1000), "sum": (1, 1),
            "is_ok": (1, 1), "unwrap": (1, 1), "error_of": (1, 1),
            "evidence": (1, 1), "reduce": (3, 3)}


@dataclass(frozen=True)
class Closure:
    params: tuple
    body: object
    env: dict


@dataclass(frozen=True)
class Builtin:
    """An internal callable reference, never an ordinary JSON value."""
    name: str


def check_arity(name, count):
    if name not in BUILTINS:
        raise Fault("BUILTIN", f"알 수 없는 내장 함수: {name}")
    lower, upper = BUILTINS[name]
    if not lower <= count <= upper:
        raise Fault("ARITY", f"{name}의 인자 수는 {lower}~{upper}개입니다.")


def boolean(value):
    if type(value) is not bool:
        raise Fault("BOOL_REQUIRED", "조건에는 Bool이 필요합니다.")
    return value


def number(value):
    result = numeric_value(value)
    if result is None:
        raise Fault("NUMBER_REQUIRED", "산술에는 관측 가능한 유한 숫자가 필요합니다.")
    return result


def scalar_text(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float, Decimal)):
        return str(value)
    raise Fault("TEXT_REQUIRED", "Text·Number·Bool만 문자열로 바꿀 수 있습니다. 구조에는 json()을 쓰세요.")


def binary(op, left, right):
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
            raise Fault("LIST_REQUIRED", "in의 오른쪽은 List입니다.")
        return list_membership(left, right)
    if op == "+" and isinstance(left, str) and isinstance(right, str):
        return left + right
    if op == "+" and isinstance(left, list) and isinstance(right, list):
        return left + right
    a, b = number(left), number(right)
    if op == "**" and abs(b) > 10000:
        raise Fault("ARITHMETIC_BUDGET", "거듭제곱 지수 예산을 초과했습니다.", kind="budget")
    # Decimal/int preserve exact observations; mixing a float observation is
    # normalized through the shared number parser, never a private text parser.
    if isinstance(a, Decimal) and isinstance(b, float):
        b = Decimal(str(b))
    if isinstance(b, Decimal) and isinstance(a, float):
        a = Decimal(str(a))
    operation = {"+": operator.add, "-": operator.sub, "*": operator.mul,
                 "/": operator.truediv, "%": operator.mod, "**": operator.pow}[op]
    return operation(a, b)


def pure_call(name, args):
    check_arity(name, len(args))
    first = args[0]
    if name == "len":
        if not isinstance(first, (str, list, dict)):
            raise Fault("SIZED_REQUIRED", "len에는 Text, List, Record가 필요합니다.")
        return len(first)
    if name in ("has", "get"):
        if not isinstance(first, dict) or not isinstance(args[1], str):
            raise Fault("RECORD_REQUIRED", "has/get은 Record와 Text 키를 받습니다.")
        return args[1] in first if name == "has" else first.get(args[1], args[2])
    if name == "json":
        # Unit/Result/Callable are not silently serialized as business JSON.
        return json.dumps(public_result(first), ensure_ascii=False, allow_nan=False)
    if name == "number":
        return number(first)
    if name == "text":
        return scalar_text(first)
    if name == "abs":
        return abs(number(first))
    if name == "round":
        if len(args) == 2 and type(args[1]) is not int:
            raise Fault("INTEGER_REQUIRED", "round의 자릿수는 정수입니다.")
        return round(number(first), args[1]) if len(args) == 2 else round(number(first))
    if name in ("min", "max", "sum"):
        values = first if len(args) == 1 and isinstance(first, list) else args
        numbers = [number(v) for v in values]
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
