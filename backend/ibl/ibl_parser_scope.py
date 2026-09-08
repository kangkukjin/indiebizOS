"""블록의 어휘 범위와 소스 몸통. 바깥 슬롯 번호는 안쪽 파이프에 복사하지 않는다."""
from contextvars import ContextVar

BODY_NAMES = ContextVar('ibl_body_names', default=frozenset())


def merge_layout_lines(entries):
    """괄호 안과 연산자 앞뒤 개행은 같은 문장이다. 문자열 내용은 보존한다."""
    result, current, stack = [], [], []
    quote = None
    operators = ('>>', '??', '&', '|')
    pairs = {'}': '{', ']': '[', ')': '('}
    for line, was_in_string in entries:
        continued = current and (stack or quote or was_in_string
            or line.startswith(operators)
            or current[-1].rstrip().endswith(operators))
        if current and not continued:
            result.append('\n'.join(current))
            current = []
        current.append(line)
        i = 0
        while i < len(line):
            ch = line[i]
            if quote:
                if ch == '\\':
                    i += 2
                    continue
                if ch == quote:
                    quote = None
            elif ch in ('"', "'"):
                quote = ch
            elif ch in '{[(':
                stack.append(ch)
            elif ch in pairs and stack and stack[-1] == pairs[ch]:
                stack.pop()
            i += 1
    if current:
        result.append('\n'.join(current))
    return result


def scoped_block(parse_block, text, variables, free_ok):
    names = True if free_ok is True else frozenset(variables or ()) | frozenset(free_ok or ())
    token = BODY_NAMES.set(names)
    try:
        return parse_block(text)
    finally:
        BODY_NAMES.reset(token)


def emitted_names(obj):
    """문자열에 $를 남기지 않는 변수 방출 AST도 바깥 값 바인딩에 참여한다."""
    if isinstance(obj, dict):
        if obj.get('_def'):
            return set()
        names = {obj['name']} if obj.get('_var_emit') else set()
        return names | set().union(*(emitted_names(v) for v in obj.values()))
    if isinstance(obj, list):
        return set().union(*(emitted_names(v) for v in obj))
    return set()


def take_do_body(params, tail):
    from ibl_parser_blocks import _extract_bracket_raw
    from ibl_parser_values import IBLSyntaxError
    from ibl_code_ir import SourceText
    if not tail.startswith('{'):
        return tail
    if 'do' in params:
        raise IBLSyntaxError('each: do와 코드 블록을 동시에 지정할 수 없습니다.')
    body, end = _extract_bracket_raw(tail, 0, '{', '}')
    if body is None or not body.strip():
        raise IBLSyntaxError('each: 닫힌 비어 있지 않은 코드 블록이 필요합니다.')
    params['do'] = SourceText(body, quoted=True)
    return tail[end + 1:].strip()
