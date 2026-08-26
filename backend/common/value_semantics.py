"""IBL 값 의미론의 단일 코어.

값 분류·조건 동등성·순서·정렬·그룹/관계 식별·숫자 관측은 여기 한 벌만 둔다.
호출자는 판정 불능을 자기 오류 봉투로 번역할 수 있지만 값의 의미를 다시 정하지 않는다.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from enum import Enum, IntEnum
import json
import math
import re
import unicodedata
from typing import Any


_SEQUENCES = (list, tuple)
_INTEGER_TEXT = re.compile(r"^[+-]?[0-9]+$")
# 선언된 숫자 표기만 숫자다: 자릿수 구분은 3자리 정군("1,234,567"), 소수점·지수·백분율.
# "1,,000"·"12,34"(유럽식 소수)·"1_000" 을 조용히 수선해 읽으면 오독이 관측으로 위장된다.
_NUMBER_TEXT = re.compile(
    r"^[+-]?(?:(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]*)?|\.[0-9]+)"
    r"(?:[eE][+-]?[0-9]+)?(?:[ \t]*%)?$"
)
_YESNO_TEXT = {"yes", "no", "true", "false"}
# 선언된 날짜 표기만 날짜다 — **ISO 8601** (2026-08-27 사용자 판정: "ISO 8601만 날짜로 선언").
# 날짜(YYYY-MM-DD) + 선택 시각(T 또는 공백 구분, 초·소수초 선택) + 선택 시간대(Z/±HH:MM).
# "08/25/2026"·"2026.8.25" 를 조용히 날짜로 수선해 읽으면 오독이 관측으로 위장된다
# (숫자 문법 엄격화와 같은 판정). 표기가 맞아도 달력이 거부하면(2026-13-45) 날짜가 아니다.
_DATETIME_TEXT = re.compile(
    r"^\d{4}-\d{2}-\d{2}"
    r"(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})?)?$"
)


class ValueKind(str, Enum):
    NULL = "null"
    BOOL = "bool"
    NUMBER = "number"
    DATETIME = "datetime"
    TEXT = "text"
    STRUCTURE = "structure"
    OTHER = "other"


class OrderResult(IntEnum):
    LESS = -1
    EQUAL = 0
    GREATER = 1


@dataclass(frozen=True)
class ClassifiedValue:
    """원값을 한 번 분류한 결과. number/text/moment 는 비교 가능한 정규형이다."""

    kind: ValueKind
    original: Any
    number: Any = None
    text: str | None = None
    moment: Any = None      # DATETIME 의 파싱 정규형 (datetime — 날짜만이면 그날 00:00 naive)


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
        text = str(value).strip()
        if not _NUMBER_TEXT.fullmatch(text):
            return None
        if text.endswith("%"):
            text = text[:-1].rstrip()
        text = text.replace(",", "")
        if _INTEGER_TEXT.fullmatch(text):
            return int(text)
        number = float(text)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def datetime_value(value: Any):
    """선언된 ISO 8601 표기(또는 datetime 객체)를 시각으로 읽는다. 아니면 None.

    날짜만(YYYY-MM-DD)은 그날 00:00 naive — "그날 이후" 필터의 자연 해석이다.
    표기 밖(슬래시·점 구분)과 달력 위반은 수선하지 않는다(선언 표기 계약).
    """
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not _DATETIME_TEXT.fullmatch(text):
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _moment_order(a: "ClassifiedValue", b: "ClassifiedValue"):
    """두 시각의 순서. naive 와 aware 가 섞이면 판정 불능(None) — 시간대를 지어내지 않는다."""
    left, right = a.moment, b.moment
    if (left.tzinfo is None) != (right.tzinfo is None):
        return None
    return OrderResult((left > right) - (left < right))


def is_nonfinite_number(value: Any) -> bool:
    """값이 NaN/Infinity 수치(또는 그 표기)인지 판정한다."""
    if isinstance(value, bool) or isinstance(value, int):
        return False
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, str):
        if numeric_value(value) is not None:
            return False
        try:
            return not math.isfinite(float(value.strip().replace(",", "").rstrip("%")))
        except (ValueError, OverflowError):
            return False
    return False


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
    moment = datetime_value(value)
    if moment is not None:
        return ClassifiedValue(ValueKind.DATETIME, value, moment=moment)
    if isinstance(value, str):
        # NFC 정규형 — 같은 글자의 결합형(NFD, macOS 파일명)과 조합형이 다른 실체가
        # 되지 않게 한다(46회차 B46-2). 호환 분해(NFKC — 전각·리가처)는 하지 않는다:
        # 전각 표기 침묵 수선 금지는 숫자 문법과 같은 판정이다.
        text = unicodedata.normalize("NFC", value).strip().casefold()
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
    if a.kind is ValueKind.DATETIME and b.kind is ValueKind.DATETIME:
        # 같은 순간은 표기가 달라도 같다(Z ↔ +00:00, 날짜만 ↔ 그날 00:00).
        # naive 와 aware 는 같은 순간임을 증명할 수 없다 — 다르다고 본다.
        if (a.moment.tzinfo is None) != (b.moment.tzinfo is None):
            return False
        return a.moment == b.moment
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


def _partial_text_form(value: Any) -> str | None:
    """부분일치 연산자(contains/startswith/endswith/in)의 텍스트 관점.

    스칼라만 텍스트가 된다 — 결측(null)·구조(list/dict)는 None(판정 대상 아님).
    결측을 str() 로 "None" 텍스트로 승격하면 contains 가 없는 값에 대해 참을
    주장하고(B46-3), 구조를 repr 로 읽으면 따옴표·괄호가 우연 판정을 만든다(B46-4).
    숫자는 표시 문자열 그대로(쉼표 표기는 접지 않는다 — 부분일치는 텍스트 공간 판정),
    bool 은 조건 언어의 기존 텍스트("true"/"false")를 쓴다.
    """
    classified = classify_value(value)
    if classified.kind in (ValueKind.NULL, ValueKind.STRUCTURE, ValueKind.OTHER):
        return None
    if classified.kind is ValueKind.BOOL:
        return classified.text
    if classified.kind in (ValueKind.NUMBER, ValueKind.DATETIME):
        # 숫자·날짜의 부분일치는 표시 문자열 관점 — "2026-08" contains 검색 지원
        return unicodedata.normalize("NFC", str(value).strip()).casefold()
    return classified.text


def text_match(op: str, left: Any, right: Any) -> bool:
    """부분일치 텍스트 연산자의 한 벌 판정 — 조건 표면 전부가 이것을 쓴다(B46-6).

    정규화는 eq 의 텍스트 계약(양끝 공백·casefold·NFC)을 그대로 승계한다(B46-1) —
    한 낱말이 표면·연산자마다 다른 판결을 내지 않는다. list 좌변의 contains 는
    원소 멤버십(values_equal)이다 — 목록이 값을 '담고 있다'의 자연 의미.
    """
    if op == "contains" and isinstance(left, _SEQUENCES):
        return any(values_equal(item, right) for item in left)
    left_text, right_text = _partial_text_form(left), _partial_text_form(right)
    if left_text is None or right_text is None:
        return False
    if op == "contains":
        return right_text in left_text
    if op == "startswith":
        return left_text.startswith(right_text)
    if op == "endswith":
        return left_text.endswith(right_text)
    if op == "in":
        return left_text in right_text
    raise ValueError(f"알 수 없는 텍스트 연산자: {op}")


def negative_text_match(op: str, left: Any, right: Any) -> bool:
    """부정 부분일치 — 결측·구조 좌변은 부정도 주장하지 않는다(ne 의 결측 계약과 동일)."""
    if isinstance(left, _SEQUENCES) and op == "contains":
        return not text_match(op, left, right)
    if _partial_text_form(left) is None:
        return False
    return not text_match(op, left, right)


def list_membership(left: Any, collection: Any) -> bool:
    """목록 멤버십(in)의 한 벌 판정 — 원소 동등성은 조건 언어의 values_equal 이다(B46-5).

    파이썬 원시 `in` 은 True∈[1] 을 참(bool==int), 1.5∈["1.5"] 를 거짓으로 읽어
    같은 몸의 eq 계약과 정반대 판결을 냈다. null∈[null] 은 참 — 결측 동등 검색
    ({op:"eq", value:null})과 같은 보존이다.
    """
    if not isinstance(collection, (*_SEQUENCES, set, frozenset)):
        return text_match("in", left, collection)
    return any(values_equal(left, item) for item in collection)


def regex_text(value: Any) -> str | None:
    """matches(정규식) 표면의 문자열 관점 — NFC 정규형, 대소문자는 정규식의 몫.

    결측·구조는 None(판정 대상 아님) — repr 누출 방지는 부분일치와 같은 계약.
    """
    if value is None or isinstance(value, (dict, *_SEQUENCES)):
        return None
    return unicodedata.normalize("NFC", str(value))


def compare_order(left: Any, right: Any) -> OrderResult | None:
    """공개 값의 크기 순서. 정의되지 않은 조합은 ``None``이다."""
    a, b = classify_value(left), classify_value(right)
    if a.kind is ValueKind.NUMBER and b.kind is ValueKind.NUMBER:
        return OrderResult((a.number > b.number) - (a.number < b.number))
    if a.kind is ValueKind.DATETIME and b.kind is ValueKind.DATETIME:
        return _moment_order(a, b)
    if a.kind is ValueKind.TEXT and b.kind is ValueKind.TEXT:
        return OrderResult((a.text > b.text) - (a.text < b.text))
    return None


def order_matches(result: OrderResult | None, op: str) -> bool:
    """공통 순서를 비교 연산자의 bool 로 번역한다. 판정 불능(None)은 항상 False.

    오류 봉투를 낼 수 없는 표면(goal case 분기·응답 변환 match)이 판정 불능을
    조용한 성공 오답 대신 불일치로 접기 위한 한 벌 번역기다. 오류를 낼 수 있는
    표면(where/블록 술어)은 None 을 자기 오류로 번역해야 한다 — 이 함수를 쓰지 말 것.
    """
    if result is None:
        return False
    return {
        "<": result < 0,
        "lt": result < 0,
        "<=": result <= 0,
        "lte": result <= 0,
        "le": result <= 0,
        ">": result > 0,
        "gt": result > 0,
        ">=": result >= 0,
        "gte": result >= 0,
        "ge": result >= 0,
    }.get(op, False)


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
    if isinstance(value, datetime):
        return "datetime", _canonical_moment_text(value)
    if isinstance(value, str):
        # 선언 표기(ISO 8601)의 날짜는 표기가 아니라 순간이 정체성이다(2026-08-27 판정)
        moment = datetime_value(value)
        if moment is not None:
            return "datetime", _canonical_moment_text(moment)
        # NFC — 결합형/조합형은 같은 글자다(B46-2). 대소문자·공백은 다른 JSON 값이라 보존.
        return "string", unicodedata.normalize("NFC", value)
    try:
        hash(value)
        return f"{type(value).__module__}.{type(value).__qualname__}", value
    except TypeError:
        return f"{type(value).__module__}.{type(value).__qualname__}", repr(value)


def group_identity(value):
    """그룹 키의 엄격한 타입·구조 식별자."""
    return freeze_structure(value, _group_scalar_identity)


def _canonical_moment_text(moment) -> str:
    """시각의 정본 키 표기 — aware 는 UTC 로 접고, naive 와는 접두로 영구 분리."""
    if moment.tzinfo is not None:
        from datetime import timezone
        return "aware:" + moment.astimezone(timezone.utc).replace(tzinfo=None).isoformat()
    return "naive:" + moment.isoformat()


def _relation_scalar_identity(value):
    # 숫자로 읽히는 표기는 수치 정규형이 키다(B46-7) — 1 과 1.0, "1,000" 과 1000,
    # "02" 와 2 는 조건 eq 가 같다고 판정하는 같은 실체다(43·44회차 숫자 계약).
    # 관계 키만 텍스트 표기로 갈라 두면 join/dedup 이 filter 와 다른 선고를 낸다.
    number = numeric_value(value)
    if number is not None:
        if isinstance(number, float) and number.is_integer():
            number = int(number)
        return str(number)
    # 선언 표기의 날짜도 같은 순간이면 같은 실체다(ISO 8601 판정, 2026-08-27) —
    # "2026-08-25T01:00Z" 와 "+00:00", 날짜만과 그날 00:00 이 join/dedup 에서 만난다.
    moment = datetime_value(value)
    if moment is not None:
        return _canonical_moment_text(moment)
    return re.sub(r"\s+", " ", unicodedata.normalize(
        "NFC", str("" if value is None else value)).strip().casefold())


def relation_identity(value):
    """join/merge/dedup의 느슨한 관계 키 식별자."""
    return freeze_structure(value, _relation_scalar_identity)


def require_finite_numbers(value: Any, *, path: str = "$") -> Any:
    """계산 결과 안의 NaN/Infinity 를 공개 JSON 경계 전에 정직하게 거절한다."""
    if isinstance(value, float) and not math.isfinite(value):
        label = "NaN" if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
        raise ValueError(f"계산 결과 {path}가 비유한 수 {label}입니다")
    if isinstance(value, _SEQUENCES):
        for index, item in enumerate(value):
            require_finite_numbers(item, path=f"{path}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            require_finite_numbers(key, path=f"{path}.<key>")
            require_finite_numbers(item, path=f"{path}.{key}")
    return value


_NONFINITE_RESULT = "NONFINITE_RESULT"
_NON_JSON_RESULT = "NON_JSON_RESULT"


class _PublicResultViolation(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _json_object(pairs):
    """JSON 문자열의 중복 객체 키를 파싱 단계에서 소실되기 전에 거절한다."""
    out = {}
    for key, value in pairs:
        if key in out:
            raise _PublicResultViolation(
                _NON_JSON_RESULT, f"JSON 문자열 객체에 중복 키 {key!r}가 있습니다")
        out[key] = value
    return out


def _normalize_public_value(value: Any, *, path: str = "$", active=None) -> Any:
    """공개 JSON 값을 재귀 정규화한다. 손실 없는 변환만 하고 나머지는 거절한다."""
    if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
        try:
            nested = json.loads(value, object_pairs_hook=_json_object)
        except _PublicResultViolation as error:
            raise _PublicResultViolation(error.code, f"{path}<json>: {error}") from error
        except (json.JSONDecodeError, TypeError):
            return value
        _normalize_public_value(nested, path=f"{path}<json>", active=active)
        return value
    if isinstance(value, float) and not math.isfinite(value):
        label = "NaN" if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
        raise _PublicResultViolation(
            _NONFINITE_RESULT, f"계산 결과 {path}가 비유한 수 {label}입니다")
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if not isinstance(value, (*_SEQUENCES, dict)):
        raise _PublicResultViolation(
            _NON_JSON_RESULT,
            f"공개 결과 {path}의 {type(value).__name__} 값은 JSON으로 표현할 수 없습니다")
    active = active if active is not None else set()
    marker = id(value)
    if marker in active:
        raise _PublicResultViolation(
            _NON_JSON_RESULT, f"공개 결과 {path}에 순환 참조가 있습니다")
    active.add(marker)
    try:
        if isinstance(value, _SEQUENCES):
            return [_normalize_public_value(item, path=f"{path}[{index}]", active=active)
                    for index, item in enumerate(value)]
        if all(isinstance(key, str) for key in value):
            return {key: _normalize_public_value(item, path=f"{path}.{key}", active=active)
                    for key, item in value.items()}
        # JSON 은 객체 키를 문자열로 강제해 1 과 "1" 을 충돌시킨다. 문자열화하지 않고
        # strict_json_value 와 같은 pair 표현으로 모든 키의 타입과 항목을 보존한다.
        return {"$object_pairs": [
            [_normalize_public_value(key, path=f"{path}.<key>", active=active),
             _normalize_public_value(item, path=f"{path}.{key}", active=active)]
            for key, item in value.items()
        ]}
    finally:
        active.remove(marker)


def public_result(value: Any, *, producer: str = "") -> Any:
    """공개 결과의 유한 JSON 수 계약을 적용하고 위반을 정직한 오류 봉투로 바꾼다.

    JSON 컨테이너 문자열도 검사한다. 평문 ``"NaN"`` 은 텍스트일 수 있으므로 문자열은
    ``{``/``[`` 로 시작할 때만 JSON 결과로 해석한다.
    """
    try:
        return _normalize_public_value(value)
    except _PublicResultViolation as error:
        envelope = {
            "success": False,
            "error_code": error.code,
            "error": f"공개 결과 계약 위반: {error}",
        }
        if producer:
            envelope["producer"] = producer
        return envelope


def dumps_public_result(value: Any, *, producer: str = "", ensure_ascii: bool = False,
                        indent=None, sort_keys: bool = False) -> str:
    """공개 결과를 오류 봉투 변환 뒤 엄격 JSON(``allow_nan=False``)으로 직렬화한다."""
    normalized = public_result(value, producer=producer)
    return json.dumps(normalized, ensure_ascii=ensure_ascii, indent=indent,
                      sort_keys=sort_keys, allow_nan=False)


def aggregate_numbers(op: str, numbers: list):
    """유한 수치 집합의 안정 집계 결과와 표현 오류를 반환한다. 반환값은 (value, error).

    관측/결측 정책은 호출자가 소유하지만 누산·타입 보존·공개 수 표현 가능성은 이
    한 벌만 소유한다. 순진한 float sum 은 부분합 오버플로(1e308+1e308-1e308→inf)와
    큰 정수 avg 의 정밀도 소실을 만들고, 고정 반올림은 서브노멀을 0 으로 접었다.
    """
    if not numbers:
        return None, None
    if op == "min":
        return min(numbers), None
    if op == "max":
        return max(numbers), None
    if op not in ("sum", "avg"):
        raise ValueError(f"알 수 없는 수치 집계: {op}")

    decimals = [Decimal(number) if isinstance(number, int) else Decimal.from_float(number)
                for number in numbers]
    max_digits = max(len(number.as_tuple().digits) for number in decimals)
    with localcontext() as context:
        context.prec = max(28, max_digits + len(str(len(decimals))) + 8)
        result = sum(decimals, Decimal(0))
        if op == "avg":
            result /= Decimal(len(decimals))

    integral = result == result.to_integral_value()
    has_float = any(isinstance(number, float) for number in numbers)
    if integral and not has_float:
        return int(result), None
    try:
        value = float(result)
    except (OverflowError, ValueError):
        value = math.inf
    if math.isfinite(value) and not (value == 0.0 and result != 0):
        return value, None
    if integral:
        return int(result), None
    return None, "집계 결과가 JSON 유한 수로 표현 가능한 범위를 벗어났습니다"


def value_sort_key(field: str, number_parser=numeric_value):
    """숫자(0)→날짜(1)→문자열(2)→결측(3) 버킷의 행 정렬 키.

    날짜 버킷은 파싱 순간으로 정렬한다(ISO 8601 판정, 2026-08-27) — 표기·시간대가
    섞여도 순서가 참이다. naive 는 aware 앞의 하위 버킷(둘의 순서는 판정 불능이라
    지어내지 않고 종류로 가른다 — 숫자→문자열 버킷과 같은 규율).
    number_parser=None(문자열 강제 정렬)이면 날짜 해석도 끈다 — 강제의 뜻을 지킨다.
    """
    def key(item):
        value = item.get(str(field)) if isinstance(item, dict) else None
        if value is None:
            return 3, 0.0, ""
        if number_parser:
            number = number_parser(value)
            if number is not None:
                return 0, number, ""
            moment = datetime_value(value)
            if moment is not None:
                prefix = "0|" if moment.tzinfo is None else "1|"
                return 1, 0.0, prefix + _canonical_moment_text(moment)
        classified = classify_value(value)
        text = (classified.text if classified.kind is ValueKind.TEXT
                else str(value).strip().casefold())
        return 2, 0.0, text
    return key


def sort_records(records, field: str, descending: bool = False,
                 number_parser=numeric_value):
    """버킷 순서는 고정하고 숫자·날짜·문자열 버킷 안에서만 방향을 적용한다."""
    key = value_sort_key(field, number_parser)
    buckets = {0: [], 1: [], 2: [], 3: []}
    for row in records:
        buckets[key(row)[0]].append(row)
    return (sorted(buckets[0], key=key, reverse=descending)
            + sorted(buckets[1], key=key, reverse=descending)
            + sorted(buckets[2], key=key, reverse=descending)
            + buckets[3])
