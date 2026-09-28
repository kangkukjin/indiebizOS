"""Value-library contracts shared by both expression frontends.

No effects and no private equality policy. Iteration reports work to the host's
budget; stable list set operations retain the first representative value.
"""
from functools import cmp_to_key
from common.expression_ir import Fault
from common.value_semantics import (values_equal, compare_order, text_match,
                                    equality_bucket, normalized_text, sort_records)

# name -> (minimum arity, maximum arity, positional types, result type)
CONTRACTS = {
    'split': (1, 3, ('Text', 'Text|Null', 'Number'), 'List<Text>'),
    'replace': (3, 4, ('Text', 'Text', 'Text', 'Number'), 'Text'),
    'strip': (1, 2, ('Text', 'Text|Null'), 'Text'),
    'upper': (1, 1, ('Text',), 'Text'),
    'lower': (1, 1, ('Text',), 'Text'),
    'contains': (2, 2, ('Text', 'Text'), 'Bool'),
    'join': (2, 2, ('Text', 'List<Text>'), 'Text'),
    'unique': (1, 1, ('List',), 'List'),
    'union': (2, 1000, ('List',), 'List'),
    'intersection': (2, 2, ('List', 'List'), 'List'),
    'difference': (2, 2, ('List', 'List'), 'List'),
    'zip': (1, 1000, ('List',), 'List<List>'),
    'enumerate': (1, 2, ('List', 'Number'), 'List<List>'),
    'any': (1, 1, ('List<Bool>',), 'Bool'),
    'all': (1, 1, ('List<Bool>',), 'Bool'),
    'sorted': (1, 3, ('List', 'Text|Callable|Null', 'Bool'), 'List'),
    'keys': (1, 1, ('Record',), 'List<Text>'),
    'values': (1, 1, ('Record',), 'List'),
    'entries': (1, 1, ('Record',), 'List<List>'),
}


def text(value):
    if not isinstance(value, str):
        raise Fault('TEXT_REQUIRED', '문자열 연산에는 Text가 필요합니다. 변환은 text()/json()으로 명시하세요.')
    return normalized_text(value)


def integer(value):
    if type(value) is not int:
        raise Fault('INTEGER_REQUIRED', '정수가 필요합니다.')
    return value


def listing(value):
    if not isinstance(value, list):
        raise Fault('LIST_REQUIRED', '목록 연산에는 List가 필요합니다.')
    return value


def call(name, args, tick, callback=None):
    first = args[0]
    if name in ('split', 'replace', 'strip', 'upper', 'lower', 'contains', 'join'):
        s = text(first)
        if name == 'split':
            sep = None if len(args) < 2 or args[1] is None else text(args[1])
            limit = -1 if len(args) < 3 else integer(args[2])
            result = s.split(sep, limit)
            for _ in result:
                tick()
            return result
        if name == 'replace':
            return normalized_text(s.replace(text(args[1]), text(args[2]), -1 if len(args) < 4 else integer(args[3])))
        if name == 'strip':
            return s.strip(None if len(args) < 2 or args[1] is None else text(args[1]))
        if name in ('upper', 'lower'):
            return normalized_text(getattr(s, name)())
        if name == 'contains':
            return text_match('contains', s, text(args[1]))
        parts = listing(args[1])
        for part in parts:
            tick()
            text(part)
        return normalized_text(s.join(text(part) for part in parts))
    if name in ('keys', 'values', 'entries'):
        if not isinstance(first, dict):
            raise Fault('RECORD_REQUIRED', 'Record가 필요합니다.')
        for _ in first:
            tick()
        return list(first) if name == 'keys' else list(first.values()) if name == 'values' else [list(x) for x in first.items()]
    rows = listing(first)
    if name in ('any', 'all'):
        # Validate the complete input even when the boolean result is known.
        for row in rows:
            tick()
            if type(row) is not bool:
                raise Fault('BOOL_REQUIRED', 'any/all은 List<Bool>을 받습니다.')
        return any(rows) if name == 'any' else all(rows)
    if name == 'enumerate':
        start = 0 if len(args) < 2 else integer(args[1])
        out = []
        for i, row in enumerate(rows, start):
            tick()
            out.append([i, row])
        return out
    if name == 'zip':
        lists = [listing(a) for a in args]
        out = []
        for row in zip(*lists):
            tick()
            out.append(list(row))
        return out
    if name == 'sorted':
        key = args[1] if len(args) > 1 else None
        reverse = args[2] if len(args) > 2 else False
        if type(reverse) is not bool:
            raise Fault('BOOL_REQUIRED', 'sorted의 reverse는 Bool입니다.')
        if isinstance(key, str):
            if any(not isinstance(row, dict) for row in rows):
                raise Fault('RECORD_REQUIRED', '필드 정렬에는 List<Record>가 필요합니다.')
            for _ in rows:
                tick()
            if rows and not any(key in row for row in rows):
                raise Fault('MISSING_FIELD', f'sorted 키가 입력 행에 없습니다: {key}')
            return sort_records(rows, key, descending=reverse)
        decorated = []
        for row in rows:
            tick()
            if key is None:
                k = row
            elif callback is not None:
                k = callback(key, row)
            else:
                raise Fault('CALLABLE', 'sorted의 key는 Text, Callable 또는 null입니다.')
            decorated.append((k, row))
        def compare(a, b):
            tick()
            order = compare_order(a[0], b[0])
            if order is None:
                raise Fault('UNORDERED', 'sorted의 키를 서로 비교할 수 없습니다.')
            return order
        return [row for _, row in sorted(decorated, key=cmp_to_key(compare), reverse=reverse)]
    if name in ('unique', 'union', 'intersection', 'difference'):
        lists = [listing(a) for a in args]
        def add(index, value):
            tick()
            index.setdefault(equality_bucket(value), []).append(value)
        def member(value, index):
            tick()
            for item in index.get(equality_bucket(value), ()):
                tick()
                if values_equal(value, item):
                    return True
            return False
        right, selected, out = {}, {}, []
        if name in ('intersection', 'difference'):
            for row in lists[1]:
                add(right, row)
        sources = lists if name == 'union' else [rows]
        for source in sources:
            for row in source:
                tick()
                if name == 'intersection' and not member(row, right):
                    continue
                if name == 'difference' and member(row, right):
                    continue
                if not member(row, selected):
                    out.append(row)
                    add(selected, row)
        return out
    raise Fault('BUILTIN', f'알 수 없는 값 함수: {name}')
