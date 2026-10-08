"""자연어 schema에서 명시된 필드만 읽는다. 자유 주제 라벨은 추측하지 않는다."""
import re


def hidden_schema_fields(schema, input_fields, row_fields):
    """Detect declared writes to hidden columns, including an unambiguous single name.

    A single free-form schema stays backward compatible; only a name matching
    an existing hidden column is actionable here.
    """
    if not isinstance(input_fields, list) or not input_fields:
        return []
    names = schema_fields(schema)
    if not names and isinstance(schema, str):
        match = re.fullmatch(r'\s*([\w]+)\s*\([^()]*\)\s*', schema)
        names = [match[1]] if match else []
    return sorted(set(names or []) & (set(row_fields) - set(input_fields)))


def hidden_schema_message(fields):
    return (f"schema가 input_fields 밖의 원본 필드를 덮어씁니다: {fields}. "
            "앞에서 select로 해당 열을 제거하거나, 출력 필드를 다른 이름으로 지정하거나, "
            "수정할 원본 열을 input_fields에 포함하세요.")


def _schema_descriptions(schema):
    """Parse names and descriptions once; free-form labels remain opaque."""
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
    fields = {}
    for part in parts:
        match = re.fullmatch(r'([\w]+)\s*(?:\(([\s\S]*)\))?', part)
        if not match:
            return None
        field = match[1]
        if field in fields:
            raise ValueError(f'schema에 필드 {field!r}가 두 번 선언되었습니다.')
        fields[field] = (match[2] or '').strip()
    return fields


def schema_fields(schema):
    """`name(설명), other(설명)` → 필드 목록. 모호한 자유 라벨은 None."""
    fields = _schema_descriptions(schema)
    return list(fields) if fields else None


def schema_types(schema):
    """Only explicit scalar type labels constrain values; all permit unknown/null.

    Descriptive prose, units and examples are not a type language. Recognize
    exact labels (optionally followed by '또는 null' / '|Null') only.
    """
    labels = {'숫자': 'Number', 'number': 'Number',
              '문자열': 'Text', 'text': 'Text', 'string': 'Text',
              '불리언': 'Bool', 'bool': 'Bool', 'boolean': 'Bool'}
    result = {}
    for field, description in (_schema_descriptions(schema) or {}).items():
        label = re.sub(r'\s*(?:또는|\|)\s*null\s*$', '', description,
                       flags=re.IGNORECASE).strip().lower()
        if label in labels:
            result[field] = labels[label]
    return result


def records_schema_error(records, schema):
    """Check declared names and explicit scalar types, never factual truth."""
    fields = schema_fields(schema)
    if not fields:
        return None
    types = schema_types(schema)
    from common.value_semantics import numeric_value
    for index, row in enumerate(records):
        missing = [name for name in fields if name not in row]
        if missing:
            return f'schema 불일치: {index + 1}행에 선언한 필드 {missing}가 없습니다.'
        for name, kind in types.items():
            value = row[name]
            if value is None:
                continue
            valid = (isinstance(value, str) if kind == 'Text' else
                     type(value) is bool if kind == 'Bool' else
                     type(value) in (int, float) and numeric_value(value) is not None)
            if not valid:
                return (f'schema 불일치: {index + 1}행 필드 {name!r}는 '
                        f'{kind}|Null이어야 합니다(실제 {type(value).__name__}).')
    return None


def schema_instruction(schema, *, merged=False):
    fields = schema_fields(schema)
    if not fields:
        return ''
    subject = '원 행과 병합한 최종 행' if merged else '결과 행'
    types = schema_types(schema)
    typed = (f' 명시한 필드 타입 {types}을 지킨다(Number=JSON 숫자, Text=문자열, Bool=불리언).'
             if types else '')
    return (f'\n선언된 필드 {fields}의 이름을 모든 {subject}에 유지한다. '
            '알 수 없는 값은 원문 밖에서 채우지 않고 null로 둔다. '
            '설명이 빈 문자열 등 다른 결측 표기를 지정하면 그 표기를 따른다.' + typed)
