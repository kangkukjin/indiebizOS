"""세 번째 경계 실험: 100개 고정 문장. 값/스코프/복구/표 조합을 교차한다."""
from ibl_boundary_cases import literal as q

VALUES = ['서울', '007', '큰"따옴표와\'작은따옴표', '첫줄\n다음줄\\경로',
          '$child.id', '${child.id}', 0, False, None, {'k': [1, 2]}]


def each(items, body, **params):
    return '[table:each]' + q(dict(items=items, do=body, **params))


def take(value):
    return '[table:take]{items:[{v:' + value + '}],n:1}'


def cases():
    rows = []

    def add(name, code, expected=None, error=False):
        rows.append(dict(id=name, code=code, expected=expected, error=error, contains=None))

    for i, value in enumerate(VALUES):
        add(f'array_row_{i}', each([[value, 'tail']], take('$it.0')), [{'v': value}])
        # do 원문에 직접 적은 $child는 미할당 참조다. 데이터로 전달하는
        # nested_data와 구별하며, 두 달러 문자열의 기대값은 검토 후 거절로 정정.
        add(f'nested_do_list_{i}', each([{'v': 'outer'}],
            each([{'v': value}], [take('$it.v')])), [{'v': value}], error=i in (4, 5))
        add(f'optional_present_expr_{i}', '[def:f]{$return=${x.v?}}\n[fn:f]{x:' + q({'v': value}) + '}', value)
        add(f'optional_missing_expr_{i}', '[def:f]{$return=${x.missing?}}\n[fn:f]{x:' + q({'v': value}) + '}', None)
        add(f'nested_data_{i}', each([{'v': value}], each([{'id': 2}],
            take('$it.v'), **{'as': 'child'})), [{'v': value}])
        body = each([{'id': 1}], take('$x.id'), **{'as': 'x'})
        add(f'fn_alias_shadow_{i}', '[def:f]{' + body + '\n$return=' + take('"$x"')
            + '}\n[fn:f]{x:' + q(value) + '}', [{'v': value}])
        nested = '[def:g]{$return=' + take('"$x"') + '}\n[fn:g]{x:7}'
        body = '[table:each]{items:[{seed:"$x"}],do:' + q(nested) + '}'
        add(f'fn_nested_code_{i}', '[def:f]{$return=' + body + '}\n[fn:f]{x:' + q(value) + '}', [{'v': 7}])
        items = [{'id': 2, 'v': value}, {'id': 1, 'v': value}, {'id': 2, 'v': 'duplicate'}]
        add(f'table_chain_{i}', '[table:dedup]{items:' + q(items)
            + ',by:"id"} >> [table:sort]{by:"id"} >> [table:take]{n:1} >> [table:select]{columns:["v"]}', [{'v': value}])

    failure = '[try]{[self:read]{path:"missing-fixture.txt"}}[catch]{'
    for field, value in [('action', 'read'), ('node', 'self'), ('step', 1)]:
        add('catch_assign_' + field, failure + '$return=$error.' + field + '}', value)
        add('catch_condition_' + field, failure + '[if:$error.' + field + ' == ' + q(value)
            + ']{' + take('1') + '}[else]{' + take('0') + '}}', [{'v': 1}])
    for field, value in [('action', 'read'), ('node', 'self')]:
        add('catch_quoted_' + field, failure + '$return="오류=${error.' + field + '}"}', '오류=' + value)
        add('catch_each_' + field, failure + each([{'id': 1}],
            take('"$error.' + field + '"')) + '}', [{'v': value}])
    add('repeat_each_shadow', '[repeat:2]{' + each([{'id': 7}], take('$i.id'), **{'as': 'i'}) + '}', [{'v': 7}])
    add('fn_optional_condition', '[def:f]{[if:${x.missing?} == null]{$return=1}[else]{$return=0}}\n[fn:f]{x:{v:2}}', 1)

    negatives = [
        ('array_required_missing', each([[1]], take('$it.9'))),
        ('fn_required_missing', '[def:f]{$return=$x.missing}\n[fn:f]{x:{v:1}}'),
        ('fn_arg_missing', '[def:f]{$return=$x}\n[fn:f]{}'),
        ('catch_outside', each([{'id': 1}], take('"$error.action"'))),
        ('each_wrong_alias', each([{'id': 1}], take('$it.id'), **{'as': 'x'})),
        ('compute_missing_column', '[table:compute]{items:[{v:1}],set:{x:"missing+1"}}'),
        ('catch_rethrow', '[try]{[self:read]{path:"missing"}}[catch]{[self:read]{path:"still-missing"}}'),
    ]
    for name, code in negatives:
        add(name, code, error=True)
    add('compute_dict', '[table:compute]{items:[{v:1}],set:{x:"{\'v\':v}"}}', [{'v':1,'x':{'v':1}}])
    assert len(rows) == 100
    return rows
