"""IBL 값 의미론의 구조 순회·정렬 공통 코어.

연산마다 다른 것은 스칼라 정책뿐이다. JSON dict/list를 순회하는 법과 정렬 버킷은
여기 한 벌로 두어 삽입 순서·결측 위치가 표면마다 다시 갈리지 않게 한다.
"""

from collections.abc import Callable
from typing import Any


_SEQUENCES = (list, tuple)


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
    """bool을 제외하고 쉼표·표시 백분율을 포함한 숫자 문자열을 float로 읽는다."""
    if isinstance(value, bool):
        return None
    try:
        text = str(value).replace(",", "").strip()
        if text.endswith("%"):
            text = text[:-1].strip()
        return float(text)
    except (TypeError, ValueError):
        return None


def value_sort_key(field: str, number_parser=numeric_value):
    """숫자(0)→문자열(1)→결측(2) 버킷의 행 정렬 키."""
    def key(item):
        value = item.get(str(field)) if isinstance(item, dict) else None
        if value is None:
            return 2, 0.0, ""
        number = number_parser(value) if number_parser else None
        if number is not None:
            return 0, number, ""
        return 1, 0.0, str(value).lower()
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
