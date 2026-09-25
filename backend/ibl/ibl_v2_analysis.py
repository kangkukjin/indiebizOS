"""Compiler diagnostics and bounded, non-executing expression observations."""
from urllib.parse import quote

from ibl_v2_ir import Fault, Node, digest, span
from ibl_v2_types import Type, UNKNOWN, NUMBER, TEXT, BOOL, join, alternatives
from ibl_v2_expr import number


HINTS = {
    "UNBOUND": "이 위치 전에 값을 정의하거나 함수의 명시 인자로 전달하세요.",
    "MISSING_FIELD": "입력·반환 필드를 확인하세요. 선택 필드는 has/get으로 처리하세요.",
    "TYPE": "기대 타입과 실제 타입을 비교하고 값을 만드는 호출부터 확인하세요.",
    "NUMBER_REQUIRED": "숫자로 관측할 수 있는 값인지 확인하세요. 구조·산문은 숫자가 아닙니다.",
    "MISSING_ARGUMENT": "함수·도구 서명의 필수 인자를 명시하세요.",
    "UNKNOWN_ARGUMENT": "현재 판본의 서명에 선언된 인자 이름을 사용하세요.",
    "PIPE_COLLISION": "파이프 입력 자리와 같은 명시 인자를 함께 주지 마세요.",
    "REPEAT_COUNT": "반복 횟수에는 0 이상의 정수를 사용하세요.",
    "SYNTAX": "표시된 구문 경계를 수정한 뒤 프로그램 전체를 다시 검사하세요.",
}


def location(source, source_map, node):
    """Local coordinates in the submitted source or the linked definition.

    Keep source_span's combined offsets for existing consumers. location is the
    human/AI-facing source identity; offsets are Unicode code points, not UTF-16.
    """
    entry = next((s for s in reversed(source_map)
                  if s['start'] <= node.start <= s['end']), source_map[0])
    text = source[entry['start']:entry['end']]
    start = max(0, node.start - entry['start'])
    end = min(len(text), max(start, node.end - entry['start']))
    pos = span(text, Node('location', start, end))
    name = entry['name']
    return {**pos, 'source': name,
            'uri': 'ibl://program' if name == '<program>' else 'ibl://function/' + quote(name, safe=''),
            'end_line': text.count('\n', 0, end) + 1,
            'end_column': end - text.rfind('\n', 0, end),
            'offset_encoding': 'unicode-codepoints'}


def finish_diagnostics(compiler):
    for entries, severity in ((compiler.issues, 'error'), (compiler.guards, 'information')):
        for entry in entries:
            old = entry['source_span']
            node = Node('diagnostic', old['start'], old['end'])
            entry['source_span'] = span(compiler.source, node)
            entry['location'] = location(compiler.source, compiler.source_map, node)
            entry.setdefault('code', 'RUNTIME_GUARD')
            entry.setdefault('rule', entry['code'])
            entry.setdefault('severity', severity)
            entry.setdefault('message', entry.get('expected', '실행 중 계약 확인이 필요합니다.'))
            entry.setdefault('hint', HINTS.get(entry['code'], '해당 위치의 계약과 호출 인자를 확인하세요.'))
            for frame in entry.get('call_path', []):
                for key in ('call', 'definition'):
                    if frame.get(key):
                        p = frame[key]
                        frame[key] = location(compiler.source, compiler.source_map,
                                              Node('frame', p['start'], p['end']))


def syntax_report(exc, source):
    diagnostic = exc.view(source)
    diagnostic.update(rule=exc.code, severity='error', hint=HINTS.get(exc.code, HINTS['SYNTAX']))
    if exc.node:
        diagnostic['location'] = location(source, [{'name': '<program>', 'start': 0, 'end': len(source)}], exc.node)
    return {'edition': 2, 'ok': False, 'success': False, 'executed': False,
            'status': 'invalid' if exc.kind == 'compile' else 'failed',
            'error': str(exc), 'diagnostic': diagnostic,
            'issues': [diagnostic] if exc.kind == 'compile' else [],
            'guards': [], 'source_hash': digest(source)}


def numeric_operand(compiler, node, typ):
    """Use exactly the runtime number observation for literal operands."""
    if node.kind == 'literal':
        try:
            number(node.data['value'])
        except Fault as exc:
            compiler.issue(node, exc.code, str(exc), expected='Number', actual=str(typ))
        return
    if typ.kind == 'Union':
        for member in alternatives(typ):
            numeric_operand(compiler, node, member)
    elif typ.kind in ('Text', 'Unknown'):
        compiler.need(node, UNKNOWN, NUMBER)
    elif typ.kind != 'Number':
        compiler.issue(node, 'ARITHMETIC', f'산술로 관측할 수 없는 타입: {typ}',
                       expected='Number', actual=str(typ))


def access_type(compiler, node, base, key, key_type=None):
    """Check each possible receiver shape, retaining its projected type."""
    if base.kind == 'Union':
        values = [access_type(compiler, node, member, key, key_type)
                  for member in alternatives(base)]
        result = values[0]
        for value in values[1:]:
            result = join(result, value)
        return result
    if base.kind == 'Record' and isinstance(key, str):
        fields = dict(base.fields)
        if key in fields:
            return fields[key]
        if not base.open:
            compiler.issue(node, 'MISSING_FIELD',
                           f'선언된 필드가 없습니다: {key}. 선택 필드는 has/get을 쓰세요.')
        else:
            compiler.need(node, UNKNOWN, UNKNOWN)
        return UNKNOWN
    if base.kind == 'Record' and key is None and node.kind == 'index':
        compiler.need(node, key_type, TEXT)
        compiler.need(node, UNKNOWN, UNKNOWN)
        return UNKNOWN
    if base.kind in ('List', 'Text') and node.kind == 'index':
        compiler.need(node, key_type, NUMBER)
        return base.item if base.kind == 'List' else TEXT
    if base.kind == 'Unknown':
        compiler.need(node, UNKNOWN, Type('Record') if node.kind == 'field' else UNKNOWN)
    else:
        compiler.issue(node, 'FIELD_TYPE', f'{base}에 해당 필드 접근을 할 수 없습니다.')
    return UNKNOWN


def builtin_type(compiler, node, name, types):
    """Structural obligations only; never invoke a callback or external tool."""
    nodes = node.data['args']
    def need(i, typ):
        if i < len(types):
            compiler.need(nodes[i], types[i], typ)
    if name == 'len':
        need(0, join(join(TEXT, Type('List', item=UNKNOWN)), Type('Record')))
        return NUMBER
    if name in ('has', 'get'):
        need(0, Type('Record'))
        need(1, TEXT)
        # has/get are deliberately the dynamic/optional-field escape hatch.
        return BOOL if name == 'has' else UNKNOWN
    if name in ('number', 'abs', 'round'):
        if types:
            numeric_operand(compiler, nodes[0], types[0])
        if name == 'round':
            need(1, NUMBER)
        return NUMBER
    if name in ('is_ok', 'unwrap', 'error_of'):
        need(0, Type('Result', item=UNKNOWN))
        return BOOL if name == 'is_ok' else (types[0].item or UNKNOWN) if name == 'unwrap' and types else UNKNOWN
    if name == 'reduce':
        need(0, Type('List', item=UNKNOWN))
        need(2, Type('Callable'))
        return UNKNOWN  # callback may change accumulator shape
    if name == 'text':
        need(0, join(join(TEXT, NUMBER), BOOL))
        return TEXT
    if name == 'json':
        return TEXT
    if name == 'evidence':
        return Type('Record')
    return UNKNOWN


def assigned_names(node):
    """Potential mutations in a repeat frame, excluding nested value frames."""
    result = set()
    def visit(value):
        if isinstance(value, Node):
            if value.kind in ('def', 'lambda', 'parallel', 'fallback'):
                return
            if value.kind == 'call':
                return
            if value.kind == 'bind':
                result.add(value.data['name'])
            for child in value.data.values():
                visit(child)
        elif isinstance(value, dict):
            for child in value.values():
                visit(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child)
    visit(node)
    return result
