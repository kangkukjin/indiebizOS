"""관계 연산 내부 키 정체성 — 공개 값은 바꾸지 않고 해시 가능한 식별자만 만든다."""

import re


def group_identity(value):
    """IBL JSON 값의 타입·구조 동등성을 해시 가능한 재귀 튜플로 보존한다."""
    if value is None:
        return "null", None
    if isinstance(value, bool):
        return "bool", value
    if isinstance(value, (int, float)):
        # bool은 위에서 분리. int/float는 IBL의 같은 number 부류로 묶는다.
        if isinstance(value, float) and value != value:  # NaN은 자기 자신과도 다르다.
            return "number", "nan"
        return "number", value
    if isinstance(value, str):
        return "string", value
    if isinstance(value, (list, tuple)):
        return "list", tuple(group_identity(item) for item in value)
    if isinstance(value, dict):
        pairs = [(group_identity(key), group_identity(item))
                 for key, item in value.items()]
        pairs.sort(key=lambda pair: repr(pair[0]))
        return "dict", tuple(pairs)
    try:
        hash(value)
        return f"{type(value).__module__}.{type(value).__qualname__}", value
    except TypeError:
        return f"{type(value).__module__}.{type(value).__qualname__}", repr(value)


def relation_identity(value):
    """기존 스칼라 비교 규칙을 유지하며 JSON 구조를 재귀적으로 정규화한다."""
    if isinstance(value, (list, tuple)):
        return "list", tuple(relation_identity(item) for item in value)
    if isinstance(value, dict):
        pairs = [(relation_identity(key), relation_identity(item))
                 for key, item in value.items()]
        pairs.sort(key=repr)
        return "dict", tuple(pairs)
    return re.sub(r"\s+", " ", str("" if value is None else value).strip().lower())
