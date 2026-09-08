"""네 번째 경계 실험: 주석·반복 바인딩·복구를 교차한 고정 100문장."""
from ibl_boundary_cases import literal as q
from ibl_boundary_cases_round3 import each, take

VALUES = ['서울', '007', '따옴표"\n경로\\', '$child.id', 0, False, None, {'k': [1, 2]}]


def cases():
    rows = []

    def add(name, code, expected=None, error=False):
        rows.append(dict(id=name, code=code, expected=expected, error=error, contains=None))

    for i, value in enumerate(VALUES):
        repeat = '[repeat:2,as:"x"]{' + take('$x') + '}'
        call = '}\n[fn:f]{x:' + q(value) + '}'
        add(f'r4_each_repeat_{i}', each([value], repeat, **{'as': 'x'}), [{'v': '1'}])
        add(f'r4_fn_repeat_{i}', '[def:f]{$return=' + repeat + call, [{'v': '1'}])
        add(f'r4_fn_delayed_repeat_{i}', '[def:f]{$return=' + each([{'id': 1}], repeat)
            + call, [{'v': '1'}])
        add(f'r4_fn_after_repeat_{i}', '[def:f]{$r=' + repeat
            + '\n$return=[table:take]{items:[{outer:"$x",inner:"$r.items.0.v"}],n:1}'
            + call, [{'outer': value, 'inner': '1'}])
        inner = '[repeat:2]{[table:take]{items:[{v:$outer.v,n:$i}],n:1}}'
        add(f'r4_nested_list_repeat_{i}', each([{'v': value}],
            each([{'id': 2}], [inner]), **{'as': 'outer'}), [{'v': value, 'n': '1'}])
        add(f'r4_each_comment_{i}', each([{'v': value}], '# $it.missing\n' + take('$it.v')),
            [{'v': value}])
        # do 원문의 따옴표 안 치환은 문자열 보간이다(값 자리의 원시 타입과 구별).
        text = ['서울', '007', '따옴표"\n경로\\', '$child.id', '0', 'False', '', '{"k": [1, 2]}'][i]
        add(f'r4_fn_comment_{i}', '[def:f]{$return=' + each([{'id': 1}],
            '# $x.missing\n' + take('"$x"')) + call, [{'v': text}])
        add(f'r4_fake_comment_{i}', each([{'v': value}],
            '# [repeat:2,as:"it"]{ $it.missing\n' + take('$it.v')), [{'v': value}])

    failure = '[try]{[self:read]{path:"missing-fixture.txt"}}[catch]{'
    for field in ['absent', 'detail.absent', 'traceback.absent', 'summary.absent']:
        add('r4_catch_optional_' + field, failure + take('"${error.' + field + '?}"') + '}', [{'v': None}])
        add('r4_catch_embedded_' + field, failure + take('"x=${error.' + field + '?}"') + '}', [{'v': 'x='}])
        add('r4_catch_required_' + field, failure + take('"$error.' + field + '"') + '}', error=True)
    for field, value in [('action', 'read'), ('node', 'self')]:
        for shape, body, expected in [
            ('param', take('"$error.' + field + '"'), [{'v': value}]),
            ('each', each([{'id': 1}], take('"$error.' + field + '"')), [{'v': value}]),
            ('assign', '$return=$error.' + field, value),
            ('condition', '[if:$error.' + field + ' == ' + q(value) + ']{' + take('1')
             + '}[else]{' + take('0') + '}', [{'v': 1}]),
        ]:
            add('r4_catch_present_' + shape + '_' + field, failure + body + '}', expected)
    for i, value in enumerate(VALUES):
        # 입력은 데이터로 전달하고, 앞 행의 실패가 뒤 행의 실제 값을 바꾸지 않는지 비교.
        body = '[if:$it.id == 1]{[self:read]{path:"absent"}}[else]{' + take('$it.v') + '}'
        add(f'r4_partial_recovery_{i}', each([{'id': 1, 'v': 'bad'}, {'id': 2, 'v': value}], body),
            [{'v': value}])
        count = i % 3 + 1
        body = '[repeat:' + str(count) + ',as:"x",collect:true]{' + take('$x') + '}'
        add(f'r4_collect_shadow_{i}', each([value], body, **{'as': 'x'}),
            [{'v': str(n)} for n in range(count)])
    assert len(rows) == 100
    return rows
