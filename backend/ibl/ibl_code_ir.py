"""지연 실행문의 내부 표현: 소스는 한 번 파싱하고 값은 AST에 바인딩한다.

str 하위형은 기존 검사/로그 표면과 호환하는 뷰다. 실행은 source의 재파싱이
아닌 tree/parts를 사용한다. 바인딩된 데이터는 Literal이며 다시 참조로 읽지 않는다.
"""
import copy
import json
import re
import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from common.ibl_vars import REF_RE, split_ref

CAPTURE = ContextVar('ibl_typed_parameters', default=False)
STEP_RE = re.compile(r'\{\{_step_(\d+)_result((?:\.(?:\w+|\*))*\??)\}\}')


class Literal(str):
    """이미 값인 문자열. 데이터의 $나 슬롯 모양은 실행 참조가 아니다."""


class SourceText(str):
    def __new__(cls, text, quoted=False):
        obj = super().__new__(cls, text)
        obj.quoted = quoted
        return obj


@dataclass(frozen=True)
class Ref:
    namespace: str
    name: object
    path: str
    source: str


class Template(str):
    def __new__(cls, text, quoted=False, parts=None):
        obj = super().__new__(cls, text)
        obj.quoted = quoted
        obj.parts = tuple(parts) if parts is not None else tuple(_parts(text))
        return obj


class Code(str):
    def __new__(cls, source, tree=None, scope=None):
        obj = super().__new__(cls, source)
        obj.tree = tree
        obj.scope = scope
        return obj


def _parts(text, slots=True):
    matches = [(m.start(), m.end(), Ref('name', *split_ref(m), m.group()))
               for m in REF_RE.finditer(text)]
    if slots:
        matches += [(m.start(), m.end(), Ref('step', int(m[1]), m[2], m.group()))
                    for m in STEP_RE.finditer(text)]
    pos = 0
    for start, end, ref in sorted(matches):
        if start > pos:
            yield text[pos:start]
        yield ref
        pos = end
    if pos < len(text):
        yield text[pos:]


def source_slots(value):
    """소스에 직접 적힌 내부 슬롯 모양은 컴파일러가 만든 참조가 아니다."""
    if isinstance(value, str) and not isinstance(value, SourceText) and (
            STEP_RE.search(value) or '{{_prev_result}}' in value):
        return Template(value, parts=_parts(value, slots=False))
    if isinstance(value, list):
        return [source_slots(v) for v in value]
    if isinstance(value, dict):
        return {k: source_slots(v) for k, v in value.items()}
    return value


def link_template(template, variables):
    parts = []
    for part in template.parts:
        if isinstance(part, Ref) and part.namespace == 'name' and part.name in variables:
            index = variables[part.name]
            parts.append(Ref('step', index, part.path, '{{_step_%d_result%s}}' % (index, part.path)))
        else:
            parts.append(part)
    text = ''.join(p.source if isinstance(p, Ref) else p for p in parts)
    return Template(text, template.quoted, parts)


def literal(value):
    if isinstance(value, str):
        return Literal(value)
    if isinstance(value, list):
        return [literal(v) for v in value]
    if isinstance(value, dict):
        return {k: literal(v) for k, v in value.items()}
    return value


def _text(value):
    if value is None:
        return ''
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)


def bind_template(template, resolve, blocked=frozenset(), namespace='name', typed_paths=False):
    parts = []
    for part in template.parts:
        if not isinstance(part, Ref) or part.namespace != namespace or part.name in blocked:
            parts.append(part)
            continue
        found, value = resolve(part.name, part.path)
        if not found:
            parts.append(part)
            continue
        if len(template.parts) == 1 and (not template.quoted or (typed_paths and part.path)):
            return literal(value)
        parts.append(_text(value))
    if not any(isinstance(p, Ref) for p in parts):
        return Literal(''.join(parts))
    return Template(str(template), template.quoted, parts)


def compile_code(code, _captures=None):
    if isinstance(code, Code):
        return code
    if isinstance(code, list):
        code = '\n'.join(code)
    source = str(code)
    scope = uuid.uuid4().hex
    captures = dict(_captures or {})
    # 바깥 슬롯과 이 몸을 파싱하며 생기는 지역 슬롯은 별도 이름 공간이다.
    # 재기록하는 것은 컴파일러 기호뿐이며 실행 데이터는 이 경로를 통과하지 않는다.
    def capture_slot(match):
        name = '_ibl_capture_' + scope + '_' + match[1]
        captures[name] = ('capture:' + scope, int(match[1]))
        return '${' + name + match[2] + '}'
    parse_source = STEP_RE.sub(capture_slot, source)
    from ibl_parser import parse_function_body
    token = CAPTURE.set(True)
    try:
        tree = parse_function_body(parse_source)
    finally:
        CAPTURE.reset(token)

    def expression(text, refs):
        def replace(match):
            name, path = split_ref(match)
            if name not in captures:
                return match.group()
            namespace, index = captures[name]
            symbol = '_ibl_expr_' + scope + '_' + str(len(refs))
            refs[symbol] = Ref(namespace, index, path, match.group())
            return '$' + symbol
        return REF_RE.sub(replace, text) if isinstance(text, str) else text

    def lower(obj):
        if isinstance(obj, SourceText):
            parts = []
            for part in _parts(obj):
                if isinstance(part, Ref) and part.namespace == 'name' and part.name in captures:
                    namespace, index = captures[part.name]
                    part = Ref(namespace, index, part.path, part.source)
                parts.append(part)
            return Template(obj, obj.quoted, parts)
        if isinstance(obj, list):
            return [lower(v) for v in obj]
        if isinstance(obj, dict):
            out = {k: lower(v) for k, v in obj.items()}
            if any(obj.get(k) for k in ('_assign', '_condition', '_repeat', '_case')):
                refs = {}
                for key in ('expr', 'condition', 'source'):
                    if key in out:
                        out[key] = expression(out[key], refs)
                if obj.get('_condition'):
                    for branch in out.get('branches', []):
                        branch['condition'] = expression(branch.get('condition'), refs)
                if refs:
                    out['_ir_expr_refs'] = refs
            if obj.get('_node') == 'table' and obj.get('action') == 'each':
                body = (obj.get('params') or {}).get('do')
                if body and not REF_RE.fullmatch(str(body)):
                    out['params']['do'] = compile_code(body, captures)
            return out
        return obj
    return Code(source, lower(tree), scope)


def pack(value):
    """전송/복구용 버전된 JSON 표현. 모든 컨테이너를 태그해 사용자 키와 충돌하지 않는다."""
    if isinstance(value, Code):
        return ['code', str(value), pack(value.tree), value.scope]
    if isinstance(value, Template):
        return ['template', str(value), value.quoted, [pack(p) for p in value.parts]]
    if isinstance(value, Ref):
        return ['ref', value.namespace, value.name, value.path, value.source]
    if isinstance(value, Literal):
        return ['literal', str(value)]
    if isinstance(value, dict):
        return ['dict', [[k, pack(v)] for k, v in value.items()]]
    if isinstance(value, list):
        return ['list', [pack(v) for v in value]]
    return ['value', value]


def unpack(data):
    tag, *args = data
    if tag == 'code':
        return Code(args[0], unpack(args[1]), args[2])
    if tag == 'template':
        return Template(args[0], args[1], [unpack(p) for p in args[2]])
    if tag == 'ref':
        return Ref(*args)
    if tag == 'literal':
        return Literal(args[0])
    if tag == 'dict':
        return {k: unpack(v) for k, v in args[0]}
    if tag == 'list':
        return [unpack(v) for v in args[0]]
    if tag == 'value':
        return args[0]
    raise ValueError(f'알 수 없는 IBL IR 태그: {tag}')


def transport_params(params):
    """기존 code HTTP 통로에 IR 부속을 싣는다. 일반 액션 요청은 바꾸지 않는다."""
    def contains(obj):
        if isinstance(obj, (Code, Template, Literal)):
            return True
        if isinstance(obj, dict):
            return any(contains(v) for v in obj.values())
        return isinstance(obj, list) and any(contains(v) for v in obj)
    return {**params, '_ibl_ir': {'version': 1, 'params': pack(params)}} if contains(params) else params


def receive_params(params):
    envelope = params.get('_ibl_ir')
    if envelope is None:
        return params
    if not isinstance(envelope, dict) or envelope.get('version') != 1:
        raise ValueError('지원하지 않는 IBL IR 전송 버전입니다.')
    restored = unpack(envelope['params'])
    if not isinstance(restored, dict):
        raise ValueError('IBL IR params는 객체여야 합니다.')
    return restored


def bind_code(code, resolve, blocked=frozenset(), *, namespace='name', typed_paths=False):
    plan = compile_code(code)
    if namespace == 'capture':
        namespace = 'capture:' + plan.scope
    return Code(str(plan), bind_tree(plan.tree, resolve, blocked,
                                    namespace=namespace, typed_paths=typed_paths), plan.scope)


def bind_tree(tree, resolve, blocked=frozenset(), *, namespace='name', typed_paths=False):
    """같은 AST에서 참조만 해소한다. 닫힌 정의·행/회차/오류 이름 범위는 여기서 소유."""
    def walk(obj, bound=blocked):
        if isinstance(obj, Code):
            return bind_code(obj, resolve, bound, namespace=namespace, typed_paths=typed_paths)
        if isinstance(obj, Template):
            return bind_template(obj, resolve, bound, namespace, typed_paths)
        if isinstance(obj, list):
            return [walk(v, bound) for v in obj]
        if not isinstance(obj, dict) or obj.get('_def'):
            return copy.deepcopy(obj)
        if obj.get('_node') == 'table' and obj.get('action') == 'each':
            params = obj.get('params') or {}
            alias = str(params.get('as') or 'it').lstrip('$').strip() or 'it'
            out = {k: walk(v, bound) for k, v in obj.items() if k != 'params'}
            out['params'] = {k: walk(v, bound | {alias} if k == 'do' else bound)
                             for k, v in params.items()}
            return out
        expr_keys = {'expr', 'condition', 'source'} if any(
            obj.get(k) for k in ('_assign', '_condition', '_repeat', '_case')) else set()
        out = {}
        for key, value in obj.items():
            local = bound
            if obj.get('_repeat') and key in ('body', 'condition'):
                local = bound | {obj.get('var') or 'i'}
            if obj.get('_try') and key in ('catch', 'finally'):
                local = bound | {'error'}
            out[key] = copy.deepcopy(value) if key in expr_keys or key.startswith(('_var', '_ir_')) else walk(value, local)
        remaining = {}
        captured_values = {}
        for symbol, ref in obj.get('_ir_expr_refs', {}).items():
            found, value = resolve(ref.name, ref.path) if ref.namespace == namespace else (False, None)
            if found:
                captured_values[symbol] = literal(value)
            else:
                remaining[symbol] = ref
        if captured_values:
            out['_var_values'] = {**(out.get('_var_values') or {}), **captured_values}
        if remaining:
            out['_ir_expr_refs'] = remaining
        else:
            out.pop('_ir_expr_refs', None)
        if namespace == 'name':
            expressions = [obj.get(k) for k in expr_keys]
            if obj.get('_condition'):
                expressions += [b.get('condition') for b in obj.get('branches', [])]
            if obj.get('_var_emit') and obj.get('_free'):
                expressions.append('$' + obj['name'])
            values = {}
            for expr in expressions:
                for match in REF_RE.finditer(str(expr or '')):
                    name, _ = split_ref(match)
                    if name in bound or (obj.get('_repeat') and name == (obj.get('var') or 'i')):
                        continue
                    found, value = resolve(name, '')
                    if found:
                        values[name] = literal(value)
            if values:
                out['_var_values'] = {**(out.get('_var_values') or {}), **values}
        return out
    return walk(tree)
