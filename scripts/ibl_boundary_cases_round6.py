"""IR 이후 조합 경계: 결과 기대값을 수리 전에 고정한 문장들."""
from ibl_boundary_cases import literal as q
from ibl_boundary_cases_round3 import each


def cases():
    out = []

    def add(name, code, expected=None, error=False):
        out.append(dict(id='r6_' + name, code=code, expected=expected,
                        error=error, contains=None))

    def take(value):
        return '[table:take]{items:[{v:' + value + '}],n:1}'

    # 부분 바인딩: 행 → 지역 파이프 통화. 데이터 속 참조는 보존한다.
    for i, value in enumerate(['plain', '$items', '${items.v}', '$it.v',
                               '한글 "quote"', '{{_step_0_result}}']):
        for shape in ['each', 'nested', 'function', 'repeat']:
            body = take('7') + ' >> [self:write]{path:"probe.txt",content:"${it.v} / $items.v"}'
            if shape == 'repeat':
                body = '[repeat:1]{' + body + '}'
            if shape == 'nested':
                body = each([{}], body, **{'as': 'child'})
            program = each([{'v': value}], body)
            if shape == 'function':
                program = '[def:f]{$return=' + each([{}],
                    take('7') + ' >> [self:write]{path:"probe.txt",content:"${prefix} / $items.v"}') + '}\n' + each(
                        [{'v': value}], '[fn:f]{prefix:$it.v}')
            add(f'mixed_{i}_{shape}', program + '\n[self:read]{path:"outputs/probe.txt"}', value + ' / [7]')

    # 같은 행/외부 입력이 조건·반복·지역 할당을 지나도 의미를 보존해야 한다.
    for i, value in enumerate([0, 1, 7, -2]):
        source = '$outer=' + take('10') + '\n'
        bodies = {
            'if': '[if:$it.v >= 1]{' + take('$it.v') + '}[else]{' + take('99') + '}',
            'capture_if': '[if:${outer.items.0.v} > $it.v]{' + take('$it.v') + '}[else]{' + take('99') + '}',
            'assign': '$n=$it.v + ${outer.items.0.v}\n' + take('$n'),
            'repeat': '[repeat:2,collect:true]{' + take('$it.v') + '}',
            'local_shadow': '$n=' + take('$it.v') + '\n' + take('${n.items.0.v}'),
        }
        expected = {'if': [{'v': value if value >= 1 else 99}],
                    'capture_if': [{'v': value}], 'assign': [{'v': str(value + 10)}],
                    'repeat': [{'v': value}] * 2, 'local_shadow': [{'v': value}]}
        for name, body in bodies.items():
            for parallel in [1, 4]:
                add(f'control_{i}_{name}_{parallel}', source + each([{'v': value}], body, parallel=parallel), expected[name])

    # $items 원형/열 추출이 각 행의 지역 파이프에 묶이는지 확인한다.
    for path, expected in [('$items', [{'v': {'x': 7}}]), ('$items.v', [{'x': 7}])]:
        for shape in ['direct', 'each', 'nested', 'function']:
            body = take('{x:7}') + ' >> [table:take]{items:' + path + ',n:1}'
            if shape == 'each':
                body = each([{}], body)
            elif shape == 'nested':
                body = each([{}], each([{}], body, **{'as': 'child'}))
            elif shape == 'function':
                body = '[def:f]{$return=' + each([{}], body) + '}\n[fn:f]{}'
            add(f'currency_{path}_{shape}', body, expected)

    for name, body in [('missing_row', take('$it.absent')),
                       ('missing_var', take('$unknown')),
                       ('missing_currency', '[self:write]{path:"probe.txt",content:"$items.v"}')]:
        add(name, each([{'v': 1}], body), error=True)
    return out
