"""IBL 값 의미론의 단일 코어.

값 분류·조건 동등성·순서·정렬·그룹/관계 식별·숫자 관측은 여기 한 벌만 둔다.
호출자는 판정 불능을 자기 오류 봉투로 번역할 수 있지만 값의 의미를 다시 정하지 않는다.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, IntEnum
import math
import re
from typing import Any


_SEQUENCES = (list, tuple)
_INTEGER_TEXT = re.compile(r"^[+-]?\d+$")
_YESNO_TEXT = {"yes", "no", "true", "false"}


class ValueKind(str, Enum):
    NULL = "null"
    BOOL = "bool"
    NUMBER = "number"
    TEXT = "text"
    STRUCTURE = "structure"
    OTHER = "other"


class OrderResult(IntEnum):
    LESS = -1
    EQUAL = 0
    GREATER = 1


@dataclass(frozen=True)
class ClassifiedValue:
    """원값을 한 번 분류한 결과. number/text는 비교 가능한 정규형이다."""

    kind: ValueKind
    original: Any
    number: Any = None
    text: str | None = None


def freeze_structure(value: Any, scalar_identity: Callable[[Any], Any]):
    """JSON 구조를 해시 가능한 재귀 튜플로 만든다(dict 무순서·list 순서 보존)."""
    if isinstance(value, _SEQUENCES):
        return "list", tuple(freeze_structure(item, scalar_identity) for item in value)
    if isinstance(value, dict):
        pairs = [(freeze_structure(key, scalar_identity),
                  freeze_structure(item, scalar_identity))
                 for key, item in value.items()]
        pairs.sort(key=repr)
        return "dict", tuple(pairs)
    return scalar_identity(value)


def structural_equal(left: Any, right: Any,
                     scalar_equal: Callable[[Any, Any], bool]) -> bool:
    """스칼라 정책을 구조 안쪽까지 재귀 적용한다(dict 무순서·list 순서 보존)."""
    if isinstance(left, dict) or isinstance(right, dict):
        if not isinstance(left, dict) or not isinstance(right, dict):
            return False
        if len(left) != len(right):
            return False
        unmatched = list(right.items())
        for left_key, left_value in left.items():
            found = next((i for i, (right_key, right_value) in enumerate(unmatched)
                          if structural_equal(left_key, right_key, scalar_equal)
                          and structural_equal(left_value, right_value, scalar_equal)), None)
            if found is None:
                return False
            unmatched.pop(found)
        return True
    if isinstance(left, _SEQUENCES) or isinstance(right, _SEQUENCES):
        return (isinstance(left, _SEQUENCES) and isinstance(right, _SEQUENCES)
                and len(left) == len(right)
                and all(structural_equal(a, b, scalar_equal)
                        for a, b in zip(left, right)))
    return scalar_equal(left, right)


def numeric_value(value: Any):
    """유한 숫자를 읽되 정수 정밀도는 보존한다.

    JSON 통화에 유한 숫자로 실을 수 없는 NaN/Infinity와 실수 오버플로는 숫자 관측이
    아니다. 정수까지 무조건 float로 접으면 2**53 이후의 서로 다른 식별자가 같아지므로
    정수 표기는 Python의 임의정밀도 int로 유지한다.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    try:
        text = str(value).replace(",", "").strip()
        if text.endswith("%"):
            text = text[:-1].strip()
        if _INTEGER_TEXT.fullmatch(text):
            return int(text)
        number = float(text)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def classify_value(value: Any) -> ClassifiedValue:
    """IBL 공개 값의 타입과 비교 정규형을 한 번만 결정한다."""
    if value is None:
        return ClassifiedValue(ValueKind.NULL, value)
    if isinstance(value, bool):
        return ClassifiedValue(ValueKind.BOOL, value,
                               text=str(value).casefold())
    if isinstance(value, (dict, *_SEQUENCES)):
        return ClassifiedValue(ValueKind.STRUCTURE, value)
    number = numeric_value(value)
    if number is not None:
        return ClassifiedValue(ValueKind.NUMBER, value, number=number)
    if isinstance(value, str):
        text = value.strip().casefold()
        yesno = text.rstrip(".!。").strip()
        if yesno in _YESNO_TEXT:
            text = yesno
        return ClassifiedValue(ValueKind.TEXT, value,
                               text=text)
    return ClassifiedValue(ValueKind.OTHER, value)


def _conditional_scalar_equal(left: Any, right: Any) -> bool:
    """filter와 블록 술어가 공유하는 스칼라 동등성."""
    a, b = classify_value(left), classify_value(right)
    if ValueKind.NULL in (a.kind, b.kind):
        return a.kind is b.kind
    if a.kind is ValueKind.NUMBER and b.kind is ValueKind.NUMBER:
        return a.number == b.number
    # 기존 공개 계약: false == "false". bool은 숫자와는 절대 같지 않다.
    if ValueKind.BOOL in (a.kind, b.kind):
        return (a.kind in (ValueKind.BOOL, ValueKind.TEXT)
                and b.kind in (ValueKind.BOOL, ValueKind.TEXT)
                and a.text == b.text)
    if a.kind is ValueKind.TEXT and b.kind is ValueKind.TEXT:
        return a.text == b.text
    if a.kind is ValueKind.OTHER and b.kind is ValueKind.OTHER:
        return type(left) is type(right) and left == right
    return False


def values_equal(left: Any, right: Any) -> bool:
    """조건 언어 전체의 재귀 동등성(dict 무순서·list 순서 보존)."""
    return structural_equal(left, right, _conditional_scalar_equal)


def compare_order(left: Any, right: Any) -> OrderResult | None:
    """공개 값의 크기 순서. 정의되지 않은 조합은 ``None``이다."""
    a, b = classify_value(left), classify_value(right)
    if a.kind is ValueKind.NUMBER and b.kind is ValueKind.NUMBER:
        return OrderResult((a.number > b.number) - (a.number < b.number))
    if a.kind is ValueKind.TEXT and b.kind is ValueKind.TEXT:
        return OrderResult((a.text > b.text) - (a.text < b.text))
    return None


def numeric_observations(values):
    """유한 숫자 관측만 원순서로 반환한다."""
    return [classified.number for value in values
            if (classified := classify_value(value)).kind is ValueKind.NUMBER]


def _group_scalar_identity(value):
    """groupby는 JSON 타입을 보존하고 native int/float만 number로 합친다."""
    if value is None:
        return "null", None
    if isinstance(value, bool):
        return "bool", value
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return "number", str(value).casefold()
        return "number", value
    if isinstance(value, str):
        return "string", value
    try:
        hash(value)
        return f"{type(value).__module__}.{type(value).__qualname__}", value
    except TypeError:
        return f"{type(value).__module__}.{type(value).__qualname__}", repr(value)


def group_identity(value):
    """그룹 키의 엄격한 타입·구조 식별자."""
    return freeze_structure(value, _group_scalar_identity)


def _relation_scalar_identity(value):
    return re.sub(r"\s+", " ", str("" if value is None else value).strip().casefold())


def relation_identity(value):
    """join/merge/dedup의 느슨한 관계 키 식별자."""
    return freeze_structure(value, _relation_scalar_identity)


def value_sort_key(field: str, number_parser=numeric_value):
    """숫자(0)→문자열(1)→결측(2) 버킷의 행 정렬 키."""
    def key(item):
        value = item.get(str(field)) if isinstance(item, dict) else None
        if value is None:
            return 2, 0.0, ""
        if number_parser:
            number = number_parser(value)
            if number is not None:
                return 0, number, ""
        classified = classify_value(value)
        text = (classified.text if classified.kind is ValueKind.TEXT
                else str(value).strip().casefold())
        return 1, 0.0, text
    return key


def sort_records(records, field: str, descending: bool = False,
                 number_parser=numeric_value):
    """버킷 순서는 고정하고 숫자·문자열 버킷 안에서만 방향을 적용한다."""
    key = value_sort_key(field, number_parser)
    buckets = {0: [], 1: [], 2: []}
    for row in records:
        buckets[key(row)[0]].append(row)
    return (sorted(buckets[0], key=key, reverse=descending)
            + sorted(buckets[1], key=key, reverse=descending)
            + buckets[2])
