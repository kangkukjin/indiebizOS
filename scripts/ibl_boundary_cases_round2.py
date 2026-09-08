"""두 번째 경계 실험: 중첩 스코프와 구조 값, 선택 경로의 독립 기대값."""
from ibl_boundary_cases import literal as q


def cases():
    rows = []

    def add(name, code, expected=None, error=False):
        rows.append(dict(id=name, code=code, expected=expected,
                         error=error, contains=None))

    def each(items, body, alias='it', parallel=1):
        return ('[table:each]{items:' + q(items) + ',as:' + q(alias)
                + ',parallel:' + str(parallel) + ',do:' + q(body) + '}')

    for parallel in (1, 2):
        for alias in ('it', '행'):
            prefix = f'each_{parallel}_{alias}'
            for name, field, expected in (
                ('missing', 'missing', None), ('null', 'nil', None),
                ('false', 'flag', False), ('zero', 'zero', 0),
            ):
                body = '[table:take]{items:[{v:${' + alias + '.' + field + '?}}],n:1}'
                add(prefix + '_optional_' + name,
                    each([{'nil': None, 'flag': False, 'zero': 0}], body, alias, parallel),
                    [{'v': expected}])
            add(prefix + '_whole_object',
                each([{'id': 1, 'text': '따옴표"와\n줄'}],
                     '[table:take]{items:[$' + alias + '],n:1}', alias, parallel),
                [{'id': 1, 'text': '따옴표"와\n줄'}])
            add(prefix + '_nested_same',
                each([{'id': 1}], each([{'id': 2}],
                     '[table:take]{items:[{v:$' + alias + '.id}],n:1}', alias), alias, parallel),
                [{'v': 2}])
            add(prefix + '_nested_distinct',
                each([{'id': 1}], each([{'id': 2}],
                     '[table:take]{items:[{v:$child.id,outer:$' + alias + '.id}],n:1}', 'child'), alias, parallel),
                [{'v': 2, 'outer': 1}])

    add('each_nested_input', each([{'children': [{'id': 4}]}],
        '[table:each]{items:$it.children,do:' + q('[table:take]{items:[{v:$it.id}],n:1}') + '}'), [{'v': 4}])
    add('each_wildcard', each([{'children': [{'id': 1}, {'id': 2}]}],
        '[table:take]{items:[{v:${it.children.*.id}}],n:1}'), [{'v': [1, 2]}])
    add('each_missing_required', each([{'id': 1}],
        '[table:take]{items:[{v:$it.missing}],n:1}'), error=True)
    add('each_inner_alias_outside', each([{'id': 1}],
        each([{'id': 2}], '[table:take]{items:[{v:$child.id}],n:1}', 'child')
        + '\n[table:take]{items:[{v:$child.id}],n:1}'), error=True)
    add('repeat_shadow', '[repeat:2]{[repeat:3]{[table:take]{items:[{v:$i}],n:1}}}', [{'v': '2'}])
    add('repeat_distinct', '[repeat:2,as:"outer"]{[repeat:3]{[table:take]{items:[{v:$i,outer:$outer}],n:1}}}', [{'v': '2', 'outer': '1'}])
    add('repeat_shadow_in_condition', '[repeat:2]{[repeat:3]{[if:$i == 2]{[table:take]{items:[{v:"last"}],n:1}}[else]{[table:take]{items:[{v:"early"}],n:1}}}}', [{'v': 'last'}])
    add('fn_nested_argument', '[def:outer]{[def:inner]{$return=$x}\n$return=[fn:inner]{x:7}}\n[fn:outer]{}', 7)
    add('fn_nested_same_name', '[def:outer]{[def:inner]{$return=$x}\n$return=[fn:inner]{x:$x}}\n[fn:outer]{x:9}', 9)
    add('fn_nested_missing_inner_arg', '[def:outer]{[def:inner]{$return=$x}\n$return=[fn:inner]{}}\n[fn:outer]{}', error=True)
    add('fn_sibling_call', '[def:inner]{$return=$x}\n[def:outer]{$return=[fn:inner]{x:$y}}\n[fn:outer]{y:8}', 8)
    return rows


def additional_cases():
    """고정 39건 수리 후 발견한 서명 경계와 인접 회귀. 앞 성적과 별도 집계."""
    nested = '[table:each]{items:[{id:2}],as:"child",do:' + q(
        '[table:take]{items:[{v:$child.id,outer:$it.id}],n:1}') + '}'
    text = '따옴표"와\'작은따옴표\n줄\\경로'
    quoted = '[table:each]{items:[{id:2}],as:"child",do:' + q(
        '[table:take]{items:[{text:"$it.text",v:$child.id}],n:1}') + '}'
    specs = [
        ('nested_catch_scope', '[try]{[table:take]{items:[],n:"bad"}}[catch]{[try]{[self:read]{path:"inner-missing.txt"}}[catch]{[table:take]{items:[{action:"$error.action"}],n:1}}}', [{'action': 'read'}]),
        ('fn_nested_each_signature', '[def:outer]{[table:each]{items:$rows,do:' + q(nested) + '}}\n[fn:outer]{rows:[{id:1}]}', [{'v': 2, 'outer': 1}]),
        ('nested_each_quoted_data', '[table:each]{items:' + q([{'text': text}]) + ',do:' + q(quoted) + '}', [{'text': text, 'v': 2}]),
        ('each_quoted_object_is_text', '[table:each]{items:[{id:1}],do:' + q('[table:take]{items:[{text:"$it"}],n:1}') + '}', [{'text': q({'id': 1})}]),
        ('each_scalar_optional', '[table:each]{items:[0,false],do:' + q('[table:take]{items:[{v:${it.missing?}}],n:1}') + '}', [{'v': None}, {'v': None}]),
        ('each_closed_definition', '[table:each]{items:[{id:1}],as:"x",do:' + q('[def:inner]{$return=[table:take]{items:[{v:$x.id}],n:1}}\n[fn:inner]{x:{id:2}}') + '}', [{'v': 2}]),
        ('fn_nested_binding_does_not_hide_argument', '[def:outer]{[def:inner]{$x=1\n$return=$x}\n$return=$x}\n[fn:outer]{x:9}', 9),
    ]
    return [dict(id=name, code=code, expected=value, error=False, contains=None)
            for name, code, value in specs]
