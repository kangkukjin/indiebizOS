"""자연어 schema에서 명시된 필드만 읽는다. 자유 주제 라벨은 추측하지 않는다."""
import re


def schema_fields(schema):
    """`name(설명), other(설명)` → 필드 목록. 모호한 자유 라벨은 None."""
    if not isinstance(schema, str) or not schema.strip():
        return None
    parts, start, depth = [], 0, 0
    for i, char in enumerate(schema):
        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if depth < 0:
                return None
        elif char == ',' and depth == 0:
            parts.append(schema[start:i].strip())
            start = i + 1
    if depth:
        return None
    parts.append(schema[start:].strip())
    if len(parts) < 2:
        return None  # finance · 팁(tip) 등 기존 자유 라벨은 필드 선언으로 오인하지 않는다.
    fields = []
    for part in parts:
        match = re.fullmatch(r'([\w]+)\s*(?:\([\s\S]*\))?', part)
        if not match:
            return None
        field = match[1]
        if field in fields:
            raise ValueError(f'schema에 필드 {field!r}가 두 번 선언되었습니다.')
        fields.append(field)
    return fields


def records_schema_error(records, schema):
    """값의 진실은 판단하지 않는다. 선언된 이름의 누락만 모델 호출 없이 검사한다."""
    fields = schema_fields(schema)
    if not fields:
        return None
    for index, row in enumerate(records):
        missing = [name for name in fields if name not in row]
        if missing:
            return f'schema 불일치: {index + 1}행에 선언한 필드 {missing}가 없습니다.'
    return None


def schema_instruction(schema, *, merged=False):
    fields = schema_fields(schema)
    if not fields:
        return ''
    subject = '원 행과 병합한 최종 행' if merged else '결과 행'
    return (f'\n선언된 필드 {fields}의 이름을 모든 {subject}에 유지한다. '
            '알 수 없는 값은 원문 밖에서 채우지 않고 null로 둔다. '
            '설명이 빈 문자열 등 다른 결측 표기를 지정하면 그 표기를 따른다.')
