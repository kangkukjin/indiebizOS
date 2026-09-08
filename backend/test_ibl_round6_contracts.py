"""조합 경계 수리의 불변식: 부분 값·명시 통화·지연 함수 연결."""
import json
import sys
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ibl_boundary_probe import probe
from ibl_boundary_cases_round3 import each, take
from ibl_code_ir import bind_code, pack, unpack, Literal
from workflow_binding import _bind_items_params


@pytest.mark.parametrize('wire', [False, True])
@pytest.mark.parametrize('value', ['$items', '${items.v}', '$other', 'quote "\n한글'])
def test_partial_currency_binding_preserves_data_and_plan(value, wire):
    code = bind_code('[self:write]{content:"${prefix} / $items.v"}',
                     lambda n, p: (True, value) if n == 'prefix' else (False, None))
    if wire:
        code = unpack(json.loads(json.dumps(pack(code))))
    before = pack(code)
    for number in [7, 8]:
        out, error = _bind_items_params(code.tree[0], json.dumps({'items': [{'v': number}]}))
        assert error is None
        assert out['params']['content'] == value + ' / [' + str(number) + ']'
        assert isinstance(out['params']['content'], Literal)
        assert out['_list_in_text'] == [{'param': 'content', 'ref': '$items.v', 'rows': 1}]
    assert pack(code) == before


@pytest.mark.parametrize('body,expected', [
    ('[table:take]{items:[],n:1}', []),
    ('[table:take]{items:[4,5],n:1}', [4]),
    ('[table:dedup]{items:[{v:3},{v:3}],by:"v"}', [{'v': 3}]),
    ('[table:sort]{items:[{v:4},{v:2}],by:"v"}', [{'v': 2}, {'v': 4}]),
    ('[table:select]{items:[{a:4,b:5}],columns:["a"]}', [{'a': 4}]),
    ('[table:take]{items:$items.v,n:1}', [99]),
])
def test_explicit_currency_is_not_overwritten_by_pipeline_default(body, expected):
    row = probe(dict(id='explicit', code=take('99') + ' >> ' + body,
                     expected=expected, error=False, contains=None))
    assert row['ok'], row


@pytest.mark.parametrize('position', ['before', 'after'])
@pytest.mark.parametrize('parallel', [1, 4])
def test_delayed_function_uses_program_definition(position, parallel):
    definition = '[def:f]{$return=' + take('$x') + '}'
    body = each([{'v': 7}, {'v': 8}], '[fn:f]{x:$it.v}', parallel=parallel)
    code = definition + '\n' + body if position == 'before' else body + '\n' + definition
    row = probe(dict(id='lexical', code=code, expected=[{'v': 7}, {'v': 8}], error=False, contains=None))
    assert row['ok'], row


def test_delayed_local_function_shadows_outer_definition():
    body = '[def:f]{$return=' + take('8') + '}\n[fn:f]{}'
    code = '[def:f]{$return=' + take('7') + '}\n' + each([{}], body)
    row = probe(dict(id='shadow', code=code, expected=[{'v': 8}], error=False, contains=None))
    assert row['ok'], row


def test_delayed_function_cannot_capture_callers_row_variable():
    code = '[def:f]{$return=' + take('$it.v') + '}\n' + each([{'v': 7}], '[fn:f]{}')
    row = probe(dict(id='closed', code=code, expected=None, error=True, contains=None))
    assert row['ok'], row


def test_it_is_an_explicit_argument_outside_each():
    code = '[def:f]{$return=' + take('$it.v') + '}\n[fn:f]{it:{v:8}}'
    row = probe(dict(id='explicit_it', code=code, expected=[{'v': 8}], error=False, contains=None))
    assert row['ok'], row


def test_legacy_currency_binding_leaves_other_source_names_alone():
    out, error = _bind_items_params({'params': {'text': '$unknown / $items.v'}}, '{"items":[{"v":7}]}')
    assert error is None
    assert out['params']['text'] == '$unknown / [7]'


@pytest.mark.parametrize('source,expected', [('  $items.v  ', [7]), ('$items.0', [8])])
def test_currency_reference_keeps_legacy_whitespace_and_column_contract(source, expected):
    out, error = _bind_items_params({'params': {'text': source}}, '{"items":[{"v":7,"0":8}]}')
    assert error is None
    assert out['params']['text'] == expected


def test_empty_interpolation_does_not_turn_text_into_list():
    code = bind_code('[self:write]{content:"${prefix}$items.v"}', lambda n, p: (n == 'prefix', ''))
    out, error = _bind_items_params(code.tree[0], '{"items":[{"v":7}]}')
    assert error is None
    assert out['params']['content'] == '[7]'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
