"""공개 앱 선언의 모든 실행 잎을 ID로 전달한다. 코드 치환은 하지 않는다.

표면 바인딩(2026-10-05 ①): 회원 표면은 동작 ID 와 입력값만 보내고, 서버가 선언 원문 + `inputs`(제공 값, 타입 보존)
+ `declared_inputs`(템플릿이 참조하는 이름)를 그대로 실행기에 넘긴다. 미지정 입력(빈 값)은 컴파일러가 호출 인자
생략으로 접는다. 행 레코드는 `$item` 한 입력이다. 구형 `$key`/`{field}` 문자열 치환은 모든 앱 블록이 판본 2 로
넘어간 뒤 은퇴했다(같은 날) — 입력값은 어떤 모양이어도 코드가 되지 않는다.
"""
import copy
import json
import re

INPUT = re.compile(r'\$\{?([A-Za-z_][A-Za-z_0-9]*)')   # $name · f-문자열의 ${name}
ROW = re.compile(r'\$\{?item\.([A-Za-z_][\w.]*)')        # 행 레코드 필드 $item.a.b · f-문자열 ${item.a.b}
BOUND_ASSIGN = re.compile(r'\$(\w+)\s*=(?!=)')          # 템플릿 안 대입 — 입력이 아니다
BOUND_LAMBDA = re.compile(r'\(([^()]*)\)\s*=>')          # 람다 인자 — 입력이 아니다


def _bound_names(code: str) -> set:
    names = set(BOUND_ASSIGN.findall(code))
    for params in BOUND_LAMBDA.findall(code):
        names.update(re.findall(r'\$(\w+)', params))
    return names


def compile_apps(instruments):
    apps, registry = copy.deepcopy(instruments), {}
    for app in apps:
        declarations = {}
        def walk(obj, path, inputs):
            if isinstance(obj, list):
                for i, value in enumerate(obj):
                    walk(value, path + [str(i)], inputs)
            elif isinstance(obj, dict):
                inputs = {**inputs, **{i['key']: i for i in obj.get('inputs', [])},
                          **{i['key']: i for i in obj.get('fields', []) if 'key' in i}}
                for key, value in list(obj.items()):
                    if ((key == 'action' or key.endswith('_action')) and isinstance(value, str)) or key == 'request':
                        identity = ':'.join(path + ([] if key in ('action', 'request') else [key]))
                        # 모드/버튼의 기존 ID를 유지하고 하위 동작은 선언 경로로 구별한다.
                        code = value if isinstance(value, str) else value.get('message', '')
                        if key == 'request':
                            names, rows = sorted(set(INPUT.findall(code))), []
                        else:
                            names = sorted(set(INPUT.findall(code)) - {'item'} - _bound_names(code))
                            rows = sorted(set(ROW.findall(code)))
                        spec = {'inputs': inputs, 'names': names, 'rows': rows, key: value}
                        registry[identity] = spec
                        declarations[identity] = {'inputs': names, 'rows': rows,
                            'defaults': {k: v.get('default', '') for k, v in inputs.items()}}
                        if key == 'request':
                            obj[key] = {'output': bool(value.get('output'))}
                        else:
                            obj[key] = 'client-action:' + identity
                        obj['client_action_id' if key in ('action', 'request') else key + '_id'] = identity
                    elif isinstance(value, (dict, list)):
                        if key == 'modes':
                            for i, mode in enumerate(value):
                                walk(mode, [app['id'], mode.get('id', str(i))], inputs)
                        elif key == 'buttons':
                            for i, button in enumerate(value):
                                walk(button, path + ['button', str(i)], inputs)
                        else:
                            walk(value, path + [key], inputs)
        walk(app, [app['id']], {})
        app['client_actions'] = declarations
    return apps, registry


def _nested(flat: dict) -> dict:
    """{'board.id': v} → {'board': {'id': v}} — 행 필드 경로를 $item 레코드로(점 경로 해석은 common.field_path 한 벌)."""
    from common.field_path import parse_path
    out = {}
    for key, value in flat.items():
        cursor = out
        parts = [str(x) for x in parse_path(str(key))]
        for part in parts[:-1]:
            nxt = cursor.get(part)
            if not isinstance(nxt, dict):
                nxt = cursor[part] = {}
            cursor = nxt
        cursor[parts[-1]] = value
    return out


def resolve(registry, action_id, args):
    spec = registry.get(action_id)
    if not spec:
        raise ValueError('현재 공개되지 않은 앱 동작입니다')
    if not isinstance(args, dict) or len(json.dumps(args, ensure_ascii=False)) > 64000:
        raise ValueError('앱 입력 제한 초과')
    row = args.get('_row', {})
    if not isinstance(row, dict) or set(row) - set(spec['rows']):
        raise ValueError('선언되지 않은 행 입력')
    allowed = set(spec['inputs']) | set(spec['names'])
    if set(args) - allowed - {'_row'}:
        raise ValueError('선언되지 않은 앱 입력')
    values = {k: args.get(k, spec['inputs'].get(k, {}).get('default', '')) for k in allowed}
    if any(not isinstance(v, (str, int, float, bool)) for v in [*values.values(), *row.values()]):
        raise ValueError('앱 입력은 단일 값이어야 합니다')
    for key, item in spec['inputs'].items():
        if key in spec['names'] and item.get('required') and not str(values.get(key, '')).strip():
            raise ValueError((item.get('placeholder') or key) + '을 입력하세요')
    if 'request' in spec:
        # 자연어 요청문의 $이름은 본문 치환이다(코드가 아니라 메시지) — 한 번만 치환하고 다시 해석하지 않는다.
        request = spec['request']
        message = re.sub(r'\$([A-Za-z_][A-Za-z_0-9]*)', lambda m: str(values.get(m[1], '')), request['message'])
        return {'message': message, 'workflow': request.get('workflow'), 'output': request.get('output')}
    code = next(v for k, v in spec.items() if k == 'action' or k.endswith('_action'))
    # 치환 없음. 빈 값은 미지정(컴파일러가 인자 생략). 입력값은 어떤 문자열이어도 코드가 아니라 값이다.
    inputs = {k: v for k, v in values.items() if k in spec['names'] and v not in ('', None)}
    declared = list(spec['names'])
    if spec['rows']:
        inputs['item'] = _nested(row)
        declared.append('item')
    return {'message': '앱 실행', 'code': code, 'edition': 2, 'inputs': inputs, 'declared_inputs': declared}
