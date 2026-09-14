"""공개 앱 선언의 모든 실행 잎을 ID로 전달한다. 코드 치환은 서버 한 곳에서만 한다."""
import copy
import json
import re

INPUT = re.compile(r'\$([A-Za-z_][A-Za-z_0-9]*)')
ROW = re.compile(r'\{([\w.]+)\}')
LITERAL = re.compile(r'"(?:\\.|[^"\\])*"')


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
                        names = sorted(set(INPUT.findall(code)))
                        rows = sorted(set(ROW.findall(code))) if key != 'request' else []
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
