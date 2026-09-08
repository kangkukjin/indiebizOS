"""일반적인 데이터 변환을 짧은 IBL로: 결과·타입·조합·실패 의미론 검증."""
import copy
import importlib.util
import json
import sys
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from ibl_boundary_probe import probe
from ibl_parser import parse, IBLSyntaxError
from common.safe_expr import compile_expr, eval_expr


def run(code, expected):
    result = probe(dict(id='expression_revision', code=code, expected=expected,
                        error=False, contains=None))
    assert result['ok'], (result.get('actual'), result.get('error_text'), code)


@pytest.fixture
def ops():
    spec = importlib.util.spec_from_file_location('_expression_dataops', ROOT / 'data/packages/installed/tools/data-ops/handler.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize('shape', ['plain', 'if', 'repeat', 'try', 'function', 'nested', 'parallel'])
def test_raw_body_composes_and_preserves_source_values(shape):
    rows = [{'id': '007', 'text': '$5 "quote"\n{}', 'n': 3}]
    body = '[table:select]{items:[$v],columns:{source:{id:"id",text:"text"},n:"n*2",xs:["id",false,null]}}'
    code = '[table:each]{items:' + json.dumps(rows) + ',as:v,parallel:2} {' + body + '}'
    expected = [{'source': {'id': '007', 'text': rows[0]['text']}, 'n': 6, 'xs': ['007', False, None]}]
    if shape == 'if':
        code = '[if: 1 == 1]{' + code + '}'
    elif shape == 'repeat':
        code = '[repeat: 1,collect:true]{' + code + '}'
    elif shape == 'try':
        code = '[try]{' + code + '}[catch]{[table:take]{items:[],n:1}}'
    elif shape == 'function':
        code = '[def:f]{' + code + '}; [fn:f]{}'
    elif shape == 'nested':
        code = '[table:each]{items:[{}],as:outer} {' + code + '}'
    elif shape == 'parallel':
        code = '(' + code + ') & (' + code + ') >> [table:union]'
        expected *= 2
    run(code, expected)


@pytest.mark.parametrize('body', [
    '[if: 1 == 1]{$x >> [table:take]{n:1}}',
    '[repeat: 1,collect:true]{$x >> [table:take]{n:1}}',
    '[try]{$x >> [table:take]{n:1}}[catch]{[table:take]{items:[],n:1}}',
    '[if: 1 == 1]{[if: 2 == 2]{$x >> [table:take]{n:1}}}',
    '[if: 1 == 1]{$a=$x >> [table:take]{n:1};$a >> [table:take]{n:1}}',
    '[table:each]{items:[{}]} {$x >> [table:take]{n:1}}',
])
def test_outer_pipeline_in_every_body(body):
    run('$x=[table:take]{items:[{id:7}],n:1};' + body, [{'id': 7}])


def test_raw_and_quoted_body_are_equivalent():
    body = '$a=[table:take]{items:[$it],n:1}; $a >> [table:compute]{set:{n:"id+1"}}'
    for do in ['do:' + json.dumps(body), None]:
        code = '[table:each]{items:[{id:1},{id:2}]' + (',' + do if do else '') + '}'
        if do is None:
            code += ' {' + body + '}'
        run(code, [{'id': 1, 'n': 2}, {'id': 2, 'n': 3}])


@pytest.mark.parametrize('code', [
    '[table:each]{items:[],do:"[table:take]"}{[table:take]}',
    '[table:each]{items:[]}{}',
    '[table:each]{items:[]}{[table:take]',
    '[if:1==1]{$typo >> [table:take]}',
    '$x=[table:take]{items:[],n:1};[if:1==1]{$typo >> [table:take]}',
])
def test_malformed_or_unknown_body_is_rejected(code):
    with pytest.raises(IBLSyntaxError):
        parse(code)


def test_structure_literals_in_assignment_compute_and_reduce():
    run('$x=[1,2]; $return={"xs":$x,"ok":True}', {'xs': [1, 2], 'ok': True})
    run('[table:compute]{items:[{id:2}],set:{obj:"{\'id\':id,\'xs\':[id,False]}"}}',
        [{'id': 2, 'obj': {'id': 2, 'xs': [2, False]}}])
    from ibl_control_blocks import _execute_table_reduce
    result = _execute_table_reduce({'items': [{'id': 2}, {'id': 3}], 'init': [], 'step': 'acc + [id]'}, str(ROOT))
    assert result['value'] == [2, 3]


@pytest.mark.parametrize('expr', ['[x for x in xs]', '{**x}', "{x:1}", "{'a':1,'a':2}",
                                  'x.__class__', '__import__("os")', '[*xs]'])
def test_structure_expressions_do_not_enable_arbitrary_execution(expr):
    with pytest.raises((ValueError, SyntaxError)):
        compile_expr(expr)


def test_projection_rejects_incomplete_rows_and_keeps_input(ops):
    rows = [{'id': '001', 'n': 2}, {'id': '002'}]
    original = copy.deepcopy(rows)
    result = ops._op_select({'items': rows}, {'columns': {'id': 'id', 'obj': {'n': 'n'}}})
    assert result['success'] is False and '2행' in result['error']
    assert rows == original
    assert ops._op_select({'items': []}, {'columns': {'x': 'n'}})['items'] == []


@pytest.mark.parametrize('how,expected', [
    ('inner', [{'id': 'a', 'x': 1, 'n': 2}, {'id': 'a', 'x': 1, 'n': 3}]),
    ('left', [{'id': 'a', 'x': 1, 'n': 2}, {'id': 'a', 'x': 1, 'n': 3}, {'id': 'b', 'x': 2, 'n': None}, {'id': None, 'x': 3, 'n': None}]),
    ('right', [{'id': 'a', 'x': 1, 'n': 2}, {'id': 'a', 'x': 1, 'n': 3}, {'id': 'c', 'x': None, 'n': 4}, {'id': None, 'x': None, 'n': 5}]),
    ('full', [{'id': 'a', 'x': 1, 'n': 2}, {'id': 'a', 'x': 1, 'n': 3}, {'id': 'b', 'x': 2, 'n': None}, {'id': None, 'x': 3, 'n': None}, {'id': 'c', 'x': None, 'n': 4}, {'id': None, 'x': None, 'n': 5}]),
    ('semi', [{'id': 'a', 'x': 1}]),
    ('anti', [{'id': 'b', 'x': 2}, {'id': None, 'x': 3}]),
])
@pytest.mark.parametrize('table', [False, True])
def test_relations_with_duplicates_null_keys_and_both_currency_forms(ops, how, expected, table):
    a = [{'id': 'a', 'x': 1}, {'id': 'b', 'x': 2}, {'id': None, 'x': 3}]
    b = [{'id': 'a', 'n': 2}, {'id': 'a', 'n': 3}, {'id': 'c', 'n': 4}, {'id': None, 'n': 5}]
    def envelope(rows):
        if table:
            return {'table': {'columns': list(rows[0]), 'rows': [list(r.values()) for r in rows]}}
        return {'items': rows}
    prev = [envelope(a), envelope(b)]
    before = copy.deepcopy(prev)
    result = ops._op_join(prev, {'on': 'id', 'how': how})
    actual = ops._row_dicts(result['table']) if table else result['items']
    assert actual == expected
    assert prev == before


def test_defaults_empty_input_collisions_and_real_null(ops):
    a = {'items': [{'id': 'a', 'n': 8}, {'id': 'b', 'n': 9}]}
    b = {'items': [{'id': 'a', 'n': None}]}
    result = ops._op_join([a, b], {'on': 'id', 'how': 'left', 'defaults': {'n_2': 0}})
    assert result['items'] == [{'id': 'a', 'n': 8, 'n_2': None}, {'id': 'b', 'n': 9, 'n_2': 0}]
    result = ops._op_join([a, {'items': []}], {'on': 'id', 'how': 'left', 'defaults': {'count': 0}})
    assert [r['count'] for r in result['items']] == [0, 0]


def test_composite_keys_and_relation_value_semantics(ops):
    a = {'items': [{'id': 'A', 'kind': 0}, {'id': 'b', 'kind': False}, {'id': 'c', 'kind': ''}]}
    b = {'items': [{'id': ' a ', 'kind': 0}, {'id': 'b', 'kind': False}, {'id': 'c', 'kind': ''}]}
    result = ops._op_join([a, b], {'on': ['id', 'kind'], 'how': 'anti'})
    assert result['items'] == [{'id': 'c', 'kind': ''}]


@pytest.mark.parametrize('params', [{'how': 'outer'}, {'how': 'left', 'defaults': []},
                                   {'how': 'semi', 'defaults': {'n': 0}}, {'how': 'left', 'on': []}])
def test_invalid_relation_options_fail(ops, params):
    result = ops._op_join([{'items': [{'id': 1}]}, {'items': [{'id': 1}]}], {'on': 'id', **params})
    assert result['success'] is False


def test_preflight_checks_nested_projection_and_raw_body():
    from ibl_typecheck import typecheck_code
    good = '[table:select]{items:[{id:1}],columns:{source:{id:"id"}}} >> [table:select]{columns:["source"]}'
    assert typecheck_code(good)['ok']
    assert not typecheck_code(good.replace('id:"id"', 'id:"missing"'))['ok']
    assert not typecheck_code('[table:each]{items:[]} { 문장이아님 }')['ok']
    assert not typecheck_code('[table:each]{items:[]} { [table:select]{columns:{x:"[x for x in xs]"}} }')['ok']


def test_raw_nested_code_transmission_and_capture():
    from ibl_code_ir import compile_code, bind_code, pack, unpack
    plan = compile_code('[table:each]{items:[$rows],as:v} { $input >> [table:select]{columns:{id:"id"}} }')
    restored = unpack(json.loads(json.dumps(pack(plan))))
    bound = bind_code(restored, lambda name, path: (True, [{'id': '007'}]) if name == 'input' else (False, None))
    assert bound.tree[0]['params']['do'].tree[0]['_var_values']['input'] == [{'id': '007'}]


def test_block_scope_is_reset_and_functions_remain_closed():
    parse('$x=[table:take]{items:[],n:1};[if:1==1]{$x >> [table:take]}')
    with pytest.raises(IBLSyntaxError):
        parse('[if:1==1]{$x >> [table:take]}')
    steps = parse('$x=[table:take]{items:[],n:1};[def:f]{[if:1==1]{$x >> [table:take]}}')
    assert 'x' in steps[0]['signature']


@pytest.mark.parametrize('header', ['if:1 == 1', 'case: self:time'])
def test_branch_pipeline_keeps_currency_inside_each(header):
    branch = '$x >> [table:compute]{set:{n:"id+1"}}'
    body = ('[if:1 == 1]{' + branch + '}' if header.startswith('if') else
            '[case: $x.items.0.id]{"1": ' + branch + ', default: [table:take]{items:[],n:1}}')
    run('[table:each]{items:[{id:1}]} {$x=[table:take]{items:[$it],n:1};' + body + '}',
        [{'id': 1, 'n': 2}])


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
