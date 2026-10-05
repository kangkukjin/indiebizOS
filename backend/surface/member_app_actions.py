"""공개 앱 선언의 모든 실행 잎을 ID로 전달한다. 코드 치환은 서버 한 곳에서만 한다.

판본 2 블록(`edition: 2`, 2026-10-05 표면 바인딩 ①)은 치환하지 않는다 — 선언 원문 + `inputs`(제공 값,
타입 보존) + `declared_inputs`(템플릿이 참조하는 이름)를 그대로 실행기에 넘기고, 미지정 입력(빈 값)은
컴파일러가 호출 인자 생략으로 접는다. 행 레코드는 `$item` 한 입력이다. 구형 블록(edition 없음·1)은
종전 문자열 치환 경로를 유지한다(`@hub` 등 판본 1 전용 문법 블록).
"""
import copy
import json
import re

INPUT = re.compile(r'\$\{?([A-Za-z_][A-Za-z_0-9]*)')   # $name · f-문자열의 ${name}
ROW = re.compile(r'\{([\w.]+)\}')                        # 구형 행 치환 {field}
ROW_V2 = re.compile(r'\$\{?item\.([A-Za-z_][\w.]*)')     # 판본 2 행 레코드 필드 $item.a.b · f-문자열 ${item.a.b}
LITERAL = re.compile(r'"(?:\\.|[^"\\])*"')
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
        def walk(obj, path, inputs, edition):
            if isinstance(obj, list):
                for i, value in enumerate(obj):
                    walk(value, path + [str(i)], inputs, edition)
            elif isinstance(obj, dict):
                edition = obj.get('edition', edition)
                inputs = {**inputs, **{i['key']: i for i in obj.get('inputs', [])},
                          **{i['key']: i for i in obj.get('fields', []) if 'key' in i}}
                for key, value in list(obj.items()):
                    if ((key == 'action' or key.endswith('_action')) and isinstance(value, str)) or key == 'request':
                        identity = ':'.join(path + ([] if key in ('action', 'request') else [key]))
                        # 모드/버튼의 기존 ID를 유지하고 하위 동작은 선언 경로로 구별한다.
                        code = value if isinstance(value, str) else value.get('message', '')
                        v2 = edition == 2 and key != 'request'
                        names = sorted(set(INPUT.findall(code)) - ({'item'} | _bound_names(code) if v2 else set()))
                        if key == 'request':
                            rows = []
                        else:
                            rows = sorted(set(ROW_V2.findall(code))) if v2 else sorted(set(ROW.findall(code)))
                        spec = {'inputs': inputs, 'names': names, 'rows': rows, key: value,
                                'edition': 2 if v2 else None}
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
                                walk(mode, [app['id'], mode.get('id', str(i))], inputs, edition)
                        elif key == 'buttons':
                            for i, button in enumerate(value):
                                walk(button, path + ['button', str(i)], inputs, edition)
                        else:
                            walk(value, path + [key], inputs, edition)
        walk(app, [app['id']], {}, None)
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
    # 한 번의 치환으로 입력 문자열 속 $변수/{필드}를 다시 해석하지 않는다.
    def fill(text):
        return re.sub(r'\$([A-Za-z_][A-Za-z_0-9]*)|\{([\w.]+)\}',
                      lambda m: str(values.get(m[1], '')) if m[1] else str(row.get(m[2], '')), text)
    if 'request' in spec:
        request = spec['request']
        return {'message': fill(request['message']), 'workflow': request.get('workflow'), 'output': request.get('output')}
    code = next(v for k, v in spec.items() if k == 'action' or k.endswith('_action'))
    if spec.get('edition') == 2:
        # 판본 2: 치환 없음. 빈 값은 미지정(컴파일러가 인자 생략) — 구형 "빈 입력=인자 삭제"와 같은 뜻.
        inputs = {k: v for k, v in values.items() if k in spec['names'] and v not in ('', None)}
        declared = list(spec['names'])
        if spec['rows']:
            inputs['item'] = _nested(row)
            declared.append('item')
        return {'message': '앱 실행', 'code': code, 'edition': 2, 'inputs': inputs, 'declared_inputs': declared}
    # 문자열 밖 숫자 자리도 JSON 값으로만 삽입하며 IBL 코드는 받지 않는다.
    chunks, last = [], 0
    for match in LITERAL.finditer(code):
        chunks.append(_outside(code[last:match.start()], values, row))
        chunks.append(json.dumps(fill(json.loads(match[0])), ensure_ascii=False))
        last = match.end()
    chunks.append(_outside(code[last:], values, row))
    return {'message': '앱 실행', 'code': ''.join(chunks)}


def _outside(text, values, row):
    def replace(match):
        raw = values.get(match[1], '') if match[1] else row.get(match[2], '')
        try:
            value = json.loads(str(raw)) if isinstance(raw, str) else raw
        except ValueError:
            raise ValueError('숫자 입력을 확인하세요') from None
        if isinstance(value, (dict, list, str)) or value is None:
            raise ValueError('숫자 입력을 확인하세요')
        return json.dumps(value, allow_nan=False)
    return re.sub(r'\$([A-Za-z_][A-Za-z_0-9]*)|\{([\w.]+)\}', replace, text)
