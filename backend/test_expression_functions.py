"""Pure value conversion contracts, shared frontends and real pipeline composition."""
import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

from common.expression_ir import Fault, unpack
from common.expression_ops import pure_call
from common.safe_expr import compile_expr, eval_expr
from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Budget, Runtime
from ibl_v2_types import Type

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('pairs', [
    [], [['P01', 5], ['P02', None]],
    [['', False], ['nested', {'items': [1, {'x': 2}]}]],
    [['é', 1], ['e\u0301', 2], ['A', 3], ['a', 4]],
])
def test_from_entries_roundtrip_preserves_values_keys_and_order(pairs):
    record = pure_call('from_entries', [pairs])
    assert list(record.items()) == [tuple(pair) for pair in pairs]
    assert pure_call('entries', [record]) == pairs
    assert pure_call('from_entries', [pure_call('entries', [record])]) == record
    source = 'return from_entries($pairs)'
    result = Runtime(compile_program(source, {}, {'pairs': pairs}), {'pairs': pairs}).run()
    assert result['success'], result
    assert unpack(result['value_wire']['data']) == record
    assert eval_expr(compile_expr('from_entries(pairs)')[0], {'pairs': pairs}) == record


def test_from_entries_preserves_exact_decimal_and_source_input():
    pairs = [['x', Decimal('0.10000000000000001')], ['nested', [1, None]]]
    result = pure_call('from_entries', [pairs])
    assert result['x'] == Decimal('0.10000000000000001')
    assert pairs == [['x', Decimal('0.10000000000000001')], ['nested', [1, None]]]


@pytest.mark.parametrize('pairs,code', [
    (None, 'LIST_REQUIRED'), ({'a': 1}, 'LIST_REQUIRED'),
    ([[]], 'TYPE'), ([['a']], 'TYPE'), ([['a', 1, 2]], 'TYPE'),
    (['ab'], 'TYPE'), ([{'key': 'a', 'value': 1}], 'TYPE'),
    ([('a', 1)], 'TYPE'), ([[1, 2]], 'TEXT_REQUIRED'),
    ([[True, 2]], 'TEXT_REQUIRED'), ([[None, 2]], 'TEXT_REQUIRED'),
    ([['a', 1], ['a', 1]], 'DUPLICATE_KEY'),
    ([['a', None], ['a', 2]], 'DUPLICATE_KEY'),
])
def test_from_entries_rejects_invalid_input_without_coercion_or_overwrite(pairs, code):
    with pytest.raises(Fault) as raised:
        pure_call('from_entries', [pairs])
    assert raised.value.code == code
    if code == 'DUPLICATE_KEY':
        assert raised.value.details == {'list_index': 1, 'key': 'a'}


def test_from_entries_open_record_does_not_invent_observed_fields():
    plan = compile_program('return from_entries([["P01",5]])', {})
    assert not plan.issues
    assert plan.result_type == Type('Record')
    for access in ('$m.P01', '$m[$key]', 'get($m,"missing",0)',
                   'has($m,"P01")', '{**$m, fixed:7}'):
        plan = compile_program('$m=from_entries([["P01",5]]); return ' + access,
                               {}, {'key': 'P01'})
        assert not plan.issues, plan.issues
        assert not any(w['code'] == 'UNOBSERVED_FIELD' for w in plan.report()['warnings'])
        assert Runtime(plan, {'key': 'P01'}).run()['success']
    missing = Runtime(compile_program('return from_entries([]).missing', {})).run()
    assert not missing['success'] and 'MISSING_FIELD' in str(missing)


@pytest.mark.parametrize('source', [
    'return from_entries()', 'return from_entries([], [])', 'return from_entries({a:1})',
])
def test_from_entries_preflight_rejects_bad_arity_or_top_level_type(source):
    assert compile_program(source, {}).issues


def test_from_entries_duplicate_is_catchable_and_stops_before_later_effect():
    source = '''[try] {
      $m = from_entries([["a",1],["a",2]])
      assert false, "must not reach this"
    } [catch] { return $error }
    '''
    result = Runtime(compile_program(source, {})).run()
    assert result['success'], result
    assert result['value']['code'] == 'DUPLICATE_KEY'
    assert result['value']['details']['list_index'] == 1


def test_from_entries_obeys_shared_work_budget():
    inputs = {'pairs': [[str(i), i] for i in range(100)]}
    plan = compile_program('return from_entries($pairs)', {}, inputs)
    limited = Runtime(plan, inputs, budget=Budget(steps=15)).run()
    assert not limited['success'] and 'BUDGET' in str(limited)
    complete = Runtime(plan, inputs, budget=Budget(steps=1000)).run()
    assert complete['success'] and len(complete['value']) == 100


def test_computed_key_diagnostic_teaches_from_entries():
    from ibl_v2_entry import handle_request
    result = handle_request({'code': '#!ibl edition=2\n$k="P01"; return {[$k]:5}', 'check': True})
    assert not result['ok'] and 'from_entries' in result['issues'][0]['message']


@pytest.mark.parametrize('variant', ['base', 'cycle', 'changed'])
def test_from_entries_round33_original_program_against_independent_oracle(tmp_path, variant):
    """Keep the failed v0 program intact except for its dynamic-key construction."""
    fixture = ROOT / 'docs/experiments/long_sentence_imagination/round_33'
    spec = importlib.util.spec_from_file_location('_from_entries_bom', fixture / 'harness/prepare.py')
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    data = generator.build_base()
    if variant == 'cycle':
        data = generator.build_cycle(*data)
    elif variant == 'changed':
        for order in data[2]:
            if order['order_id'] == 'O007':
                order['qty'] *= 2
    expected = generator.oracle(*data)
    folder, output = tmp_path / 'source', tmp_path / 'out'
    folder.mkdir()
    output.mkdir()
    for name, rows in zip(('parts', 'bom', 'orders', 'stock'), data):
        (folder / f'{name}.json').write_text(json.dumps(rows, ensure_ascii=False))
    source = (fixture / 'drafts/main_v0.ibl').read_text()
    old = 'reduce($depths.items,{},($acc,$r)=>{**$acc,[$r.product]:$r.depth})'
    assert source.count(old) == 1
    source = source.replace(old, 'from_entries(map($depths.items,($r)=>[$r.product,$r.depth]))')
    inputs = {'source': str(folder), 'out': str(output)}
    plan = compile_program(source, load_registry(str(tmp_path)), inputs)
    assert not plan.issues, plan.issues
    result = Runtime(plan, inputs, budget=Budget(steps=1000000, rows=100000)).run()
    assert result['success'], result.get('error', result)
    actual = json.loads((output / 'result.json').read_text())
    for key in ('requirements', 'depth_by_product', 'max_depth', 'events'):
        assert actual[key] == expected[key], key
    assert len(actual['orders']) == len(expected['orders']) == 20
    edges = {(row['parent'], row['child']) for row in data[1]}
    for got, wanted in zip(actual['orders'], expected['orders']):
        assert {k: v for k, v in got.items() if k != 'cycle_path'} == {
            k: v for k, v in wanted.items() if k != 'cycle_path'}
        path = got['cycle_path']
        if wanted['status'] == '순환':
            assert path and path[-1] in path[:-1]
            assert all(edge in edges for edge in zip(path, path[1:]))
        else:
            assert path is None
    report = (output / 'report.md').read_text()
    assert all(row['order_id'] in report for row in expected['orders'])
    assert all(section in report for section in ('주문별 상태', '부족 상위', '재고 미상', '순환'))


@pytest.mark.parametrize('expression,expected', [
    ('replace($s,"zzz","y")', '앞 e\u0301 음악 뒤'),
    ('replace($s,"é","NEW")', '앞 NEW 음악 뒤'),
    ('join("",split($s,"\\n"))', '앞 e\u0301 음악 뒤'),
    ('$s[:3]', '앞 e\u0301'),
    ('$s[2]', 'e\u0301'),
    ('$s[-1]', '뒤'),
    ('f"${s}"', '앞 e\u0301 음악 뒤'),
    ('text($s)+"!"', '앞 e\u0301 음악 뒤!'),
    ('strip("  "+$s+"  ")', '앞 e\u0301 음악 뒤'),
    ('replace($s,"음악","새 é")', '앞 e\u0301 새 é 뒤'),
])
def test_text_edit_preserves_unmatched_mixed_normalization(expression, expected):
    inputs = {'s': '앞 e\u0301 음악 뒤'}
    result = Runtime(compile_program('return ' + expression, {}, inputs), inputs).run()
    assert result['success'], result
    assert result['value'] == expected
    legacy = expression.replace('$s', 's')
    if not expression.startswith('f"'):
        assert eval_expr(compile_expr(legacy)[0], inputs) == expected


@pytest.mark.parametrize('limit', [-1, 0, 1, 2, 30])
def test_canonical_text_split_and_empty_replace_limits(limit):
    text = 'e\u0301-é-e\u0301'
    assert pure_call('replace', [text, 'é', 'X', limit]) == (
        text if limit == 0 else 'X-é-e\u0301' if limit == 1 else
        'X-X-e\u0301' if limit == 2 else 'X-X-X')
    pieces = pure_call('split', [text, '-', limit])
    assert '-'.join(pieces) == text
    assert pure_call('replace', ['abc', '', '!', limit]) == 'abc'.replace('', '!', limit)
    assert pure_call('split', ['  e\u0301  음악  ', None, limit]) == '  e\u0301  음악  '.split(None, limit)


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
