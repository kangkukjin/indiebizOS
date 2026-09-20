"""관리 기록의 제한된 선언 계약. 값·식의 뜻은 기존 common 모듈에 위임한다."""
import ast
import copy
import hashlib
import json
import re

from common.field_path import MISSING, walk_path
from common.ibl_vars import REF_RE, find_refs, split_ref, sub_refs
from common.safe_expr import compile_expr, eval_expr
from common.value_semantics import compare_order, require_finite_numbers, values_equal


class RecordError(ValueError):
    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind

    def result(self):
        return {'success': False, 'error_type': self.kind, 'error': str(self)}


def fail(kind, message):
    raise RecordError(kind, message)


def dump(value):
    require_finite_numbers(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(dump(value).encode()).hexdigest()


def name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[\w-]{1,80}', value):
        fail('validation', '이름은 1~80자의 문자·숫자·밑줄·하이픈이어야 합니다.')
    return value


def keys(obj, allowed, label):
    if not isinstance(obj, dict) or set(obj) - set(allowed):
        fail('validation', f'{label}: 객체 형식이나 선언되지 않은 키를 확인하세요.')


def expression(source, env=None):
    """IBL 참조를 공용 식의 값 슬롯으로 연결. 문자열 리터럴은 치환하지 않는다."""
    if not isinstance(source, str) or len(source) > 2048:
        fail('validation', '식은 2048자 이하여야 합니다.')
    refs = []

    def slot(root, path):
        refs.append((root, path.lstrip('.')))
        return f'v{len(refs)-1}'

    parts = re.split(r'("(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27)', source)
    rewritten = ''.join(p if i % 2 else sub_refs(p, [r for r, _ in find_refs(p)], slot)
                        for i, p in enumerate(parts))
    try:
        tree = ast.parse(rewritten, mode='eval')
        nodes = list(ast.walk(tree))
        if len(nodes) > 150 or any(isinstance(n, ast.Pow) for n in nodes):
            fail('validation', '식 복잡도 상한을 넘었습니다.')
        code, identifiers, cols = compile_expr(rewritten)
        if cols or set(identifiers) - {f'v{i}' for i in range(len(refs))}:
            fail('validation', '식의 값은 $input, $actor 또는 읽은 기록으로 참조하세요.')
        if env is None:
            return refs
        values = {}
        for i, (root, path) in enumerate(refs):
            value = env.get(root, MISSING)
            if path and value is not MISSING:
                value = walk_path(value, path)
            if value is MISSING:
                fail('validation', f'식의 참조가 없습니다: {root}.{path}')
            values[f'v{i}'] = value
        # 반복/초대형 정수 연산 차단. 공용 평가기의 숫자 의미론은 유지한다.
        for n in nodes:
            if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mult):
                for operand in (n.left, n.right):
                    subcode, _, _ = compile_expr(ast.unparse(operand))
                    number = eval_expr(subcode, values, preserve_values=True)
                    if type(number) not in (int, float) or abs(number) > 10 ** 18:
                        fail('validation', '곱셈은 숫자 값에만 적용합니다.')
        result = eval_expr(code, values, preserve_values=True)
        if len(dump(result)) > 262144:
            fail('validation', '계산 결과 상한 초과')
        return result
    except RecordError:
        raise
    except (ValueError, TypeError, SyntaxError, KeyError, ZeroDivisionError, OverflowError) as exc:
        fail('validation', f'업무 식 오류: {exc}')


def resolve(value, env):
    if isinstance(value, dict):
        if set(value) == {'expr'}:
            return expression(value['expr'], env)
        return {k: resolve(v, env) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, env) for v in value]
    if isinstance(value, str) and REF_RE.fullmatch(value):
        root, path = split_ref(REF_RE.fullmatch(value))
        result = env.get(root, MISSING)
        if path and result is not MISSING:
            result = walk_path(result, path.lstrip('.'))
        if result is MISSING:
            fail('validation', f'참조가 없습니다: {value}')
        return copy.deepcopy(result)
    return value


TYPES = {'string', 'integer', 'number', 'boolean', 'object', 'array', 'record_ref', 'artifact_ref'}
FIELD_KEYS = {'type', 'required', 'nullable', 'default', 'enum', 'min', 'max', 'max_length',
              'collection', 'items', 'fields', 'additional', 'label'}


def fields_valid(fields):
    if not isinstance(fields, dict) or len(fields) > 100:
        fail('validation', '필드는 100개 이하의 객체여야 합니다.')
    for key, spec in fields.items():
        name(key)
        if key.startswith('_'):
            fail('validation', '밑줄로 시작하는 필드는 시스템 예약입니다.')
        keys(spec, FIELD_KEYS, key)
        if spec.get('type') not in TYPES:
            fail('validation', f'{key}: 지원하지 않는 타입')
        if spec['type'] == 'record_ref':
            name(spec.get('collection'))
        if spec['type'] == 'object':
            fields_valid(spec.get('fields', {}))
        if spec['type'] == 'array':
            fields_valid({'item': spec.get('items', {})})


def policy_valid(policy):
    keys(policy, {'roles', 'subjects', 'where', 'fields', 'deny_self'}, '접근 정책')
    for key in ('roles', 'subjects', 'fields', 'deny_self'):
        if key in policy and (not isinstance(policy[key], list) or any(not isinstance(v, str) for v in policy[key])):
            fail('validation', '정책의 역할·주체·필드는 문자열 목록입니다.')
    if 'where' in policy:
        expression(policy['where'])


def validate_values(value, fields, *, additional=False, defaults=False):
    if not isinstance(value, dict) or (not additional and set(value) - set(fields)):
        fail('validation', '객체 입력이나 선언되지 않은 필드를 확인하세요.')
    value = copy.deepcopy(value)
    for field, spec in fields.items():
        if field not in value and defaults and 'default' in spec:
            value[field] = copy.deepcopy(spec['default'])
        if field not in value:
            if spec.get('required'):
                fail('validation', f'{field}: 필수값입니다.')
            continue
        v = value[field]
        if v is None:
            if not spec.get('nullable'):
                fail('validation', f'{field}: null을 허용하지 않습니다.')
            continue
        typ = spec['type']
        ok = {'string': isinstance(v, str), 'integer': type(v) is int,
              'number': type(v) in (int, float), 'boolean': type(v) is bool,
              'object': isinstance(v, dict), 'array': isinstance(v, list),
              'record_ref': isinstance(v, str), 'artifact_ref': isinstance(v, str)}[typ]
        if not ok:
            fail('validation', f'{field}: {typ} 값이 필요합니다.')
        if 'enum' in spec and not any(values_equal(v, x) for x in spec['enum']):
            fail('validation', f'{field}: 허용값 밖입니다.')
        for bound, sign in [('min', -1), ('max', 1)]:
            if bound in spec:
                order = compare_order(v, spec[bound])
                if order is None or order == sign:
                    fail('validation', f'{field}: {bound} 범위를 벗어났습니다.')
        if isinstance(v, (str, list, dict)) and len(v) > spec.get('max_length', 1000 if typ == 'array' else 65536):
            fail('validation', f'{field}: 길이 상한 초과')
        if typ == 'object':
            value[field] = validate_values(v, spec.get('fields', {}), additional=spec.get('additional', False), defaults=defaults)
        if typ == 'array':
            value[field] = [validate_values({'v': x}, {'v': spec['items']}, defaults=defaults)['v'] for x in v]
    dump(value)
    return value


def validate_definition(definition):
    try:
        return _validate_definition(definition)
    except RecordError:
        raise
    except (ValueError, TypeError, KeyError, RecursionError) as exc:
        fail('validation', f'업무 정의의 형식과 복잡도를 확인하세요: {type(exc).__name__}')


def _validate_definition(definition):
    keys(definition, {'contract_version', 'name', 'collections', 'commands', 'processes', 'effects',
                      'views', 'subscriptions', 'notice', 'roles'}, '업무 정의')
    if definition.get('contract_version') != 1 or len(dump(definition)) > 524288:
        fail('validation', 'contract_version: 1 및 정의 512KiB 상한을 확인하세요.')
    collections = definition.get('collections', {})
    commands = definition.get('commands', {})
    if not isinstance(collections, dict) or not collections or not isinstance(commands, dict) or len(collections) > 100 or len(commands) > 100:
        fail('validation', 'collections와 commands가 필요합니다.')
    for collection, spec in collections.items():
        name(collection)
        keys(spec, {'fields', 'additional', 'unique', 'invariants', 'access', 'process', 'label'}, collection)
        fields_valid(spec.get('fields', {}))
        keys(spec.get('access', {}), {'read'}, 'access')
        policy_valid(spec.get('access', {}).get('read', {}))
        for invariant in spec.get('invariants', []):
            expression(invariant)
        for unique in spec.get('unique', []):
            if not unique or not isinstance(unique, list) or set(unique) - set(spec['fields']):
                fail('validation', '고유 키의 필드를 확인하세요.')
        if spec.get('process') and spec['process'] not in definition.get('processes', {}):
            fail('validation', '존재하지 않는 process')
    for command, spec in commands.items():
        name(command)
        keys(spec, {'input', 'allow', 'read', 'require', 'change', 'emit', 'confirmation',
                    'reason_required', 'label', 'internal_access'}, command)
        fields_valid(spec.get('input', {}))
        policy_valid(spec.get('allow', {}))
        if not spec.get('allow') or len(spec.get('change', [])) > 100:
            fail('validation', '명령의 allow와 변경 상한을 확인하세요.')
        for alias, read in spec.get('read', {}).items():
            name(alias)
            keys(read, {'collection', 'id', 'version'}, 'read')
            if alias.startswith('_') or alias in {'input', 'actor', 'now'} or read.get('collection') not in collections or read.get('version') not in {'observed', 'current'} or 'id' not in read:
                fail('validation', 'read의 별칭·묶음·버전 정책 오류')
        for step in spec.get('change', []):
            if not isinstance(step, dict) or len(step) != 1 or next(iter(step)) not in {'create', 'patch', 'archive', 'transition', 'task'}:
                fail('validation', '지원하지 않는 변경 원자')
        if spec.get('confirmation') not in (None, 'human'):
            fail('validation', 'confirmation은 human 또는 생략입니다.')
        if not isinstance(spec.get('internal_access', []), list) or set(spec.get('internal_access', [])) - set(collections):
            fail('validation', '내부 접근 묶음을 확인하세요.')
    for proc, spec in definition.get('processes', {}).items():
        name(proc)
        keys(spec, {'field', 'initial', 'transitions'}, 'process')
        if not isinstance(spec.get('initial'), str) or not isinstance(spec.get('transitions'), dict):
            fail('validation', 'process initial/transitions가 필요합니다.')
        for command, edge in spec['transitions'].items():
            keys(edge, {'from', 'to', 'task'}, 'transition')
            if command not in commands or not isinstance(edge.get('from'), str) or not isinstance(edge.get('to'), str):
                fail('validation', '전이 명령·상태를 확인하세요.')
            if edge.get('task', {}).get('command') and edge['task']['command'] not in commands:
                fail('validation', '작업 항목의 명령이 없습니다.')
    for effect, spec in definition.get('effects', {}).items():
        name(effect)
        keys(spec, {'adapter', 'url', 'credential_env', 'idempotency_header', 'timeout',
                    'lookup_url', 'success_command', 'success_input', 'failure_command', 'failure_input'}, 'effect')
        if not isinstance(spec.get('adapter'), str):
            fail('validation', 'effect adapter가 필요합니다.')
        for field in ('success_command', 'failure_command'):
            if spec.get(field) and spec[field] not in commands:
                fail('validation', 'effect 후속 명령이 없습니다.')
    graph = {c: set() for c in commands}
    for cmd, spec in commands.items():
        for step in spec.get('change', []):
            task = step.get('task', {})
            if task.get('op') == 'create' and task.get('timeout_command'):
                graph[cmd].add(task['timeout_command'])
        for process in definition.get('processes', {}).values():
            task = process['transitions'].get(cmd, {}).get('task', {})
            if task.get('timeout_command'):
                graph[cmd].add(task['timeout_command'])
        for event in spec.get('emit', []):
            if event.get('effect') and event['effect'] not in definition.get('effects', {}):
                fail('validation', '정의되지 않은 effect')
            effect = definition.get('effects', {}).get(event.get('effect'), {})
            graph[cmd].update(effect[k] for k in ('success_command', 'failure_command') if effect.get(k))
            for sub in definition.get('subscriptions', {}).get(event.get('event'), []):
                keys(sub, {'command', 'input', 'expected'}, 'subscription')
                if sub.get('command') not in commands:
                    fail('validation', '구독 명령이 없습니다.')
                graph[cmd].add(sub['command'])
    visited = set()
    def acyclic(current, stack):
        if current not in graph:
            fail('validation', '자동 후속 명령이 없습니다.')
        if current in stack:
            fail('validation', '자동 사건 구독에 순환이 있습니다.')
        if current in visited:
            return
        for following in graph[current]:
            acyclic(following, stack | {current})
        visited.add(current)
    for command in graph:
        acyclic(command, set())
    def visit(value):
        if isinstance(value, dict):
            if set(value) == {'expr'}:
                expression(value['expr'])
            for v in value.values():
                visit(v)
        elif isinstance(value, list):
            for v in value:
                visit(v)
    visit(definition)
    return copy.deepcopy(definition)
