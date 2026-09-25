"""A ranking must not certify the input order when its key is absent."""
import boot_paths  # noqa: F401
import copy

import pytest

from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_ir import unpack
from ibl_v2_runtime import Runtime


@pytest.fixture(scope='module')
def registry():
    return load_registry()


def run(registry, code, inputs=None):
    plan = compile_program(code, registry, inputs)
    assert not plan.issues, plan.issues
    return Runtime(plan, inputs).run()


def output(result):
    assert result['success'], result
    return unpack(result['value_wire']['data'])


@pytest.mark.parametrize('descending', [False, True])
@pytest.mark.parametrize('rows', [
    [{'id': 'a', 'price': 300}, {'id': 'b', 'price': 100}],
    [{}, {}],
    [{'id': 'a'}, {'id': 'b', 'price': None}],
])
def test_missing_sort_field_never_returns_a_false_ranking(registry, descending, rows):
    inputs = {'rows': rows, 'descending': descending, 'key': 'cost'}
    original = copy.deepcopy(inputs)
    result = run(registry, '$rows >> [table:sort]{by:$key,descending:$descending} '
                 '>> [table:take]{n:1}', inputs)
    assert result['success'] is False, result
    assert result['diagnostic']['code'] == 'MISSING_FIELD'
    assert result['diagnostic']['kind'] == 'runtime'
    assert 'cost' in result['diagnostic']['message']
    assert inputs == original


def test_schema_rename_and_function_forwarding_keep_missing_field_check(registry):
    result = run(registry, '''
[def:추천]($rows,$key){$rows >> [table:sort]{by:$key} >> [table:take]{n:1}}
$r=[{price:300},{price:100}] >> [table:rename]{map:{price:"가격"}}
[fn:추천]{rows:$r.items,key:"price"}
''')
    assert result['success'] is False
    assert result['diagnostic']['code'] == 'MISSING_FIELD'
    assert '가격' in result['diagnostic']['message']


@pytest.mark.parametrize('recovery', ['catch', 'fallback'])
def test_missing_sort_field_reaches_recovery(registry, recovery):
    sort = '[{score:10}] >> [table:sort]{by:"total"}'
    code = ('[try]{' + sort + '; return "ranked"}[catch]{return "review"}'
            if recovery == 'catch' else '(' + sort + ') ?? "review"')
    assert output(run(registry, code)) == 'review'


def test_parallel_rankings_collect_the_invalid_source(registry):
    result = run(registry, '''
$r=[[{rank:2}],[{score:10}]] >> [table:each]{parallel:2,on_error:"collect"}{
 $it >> [table:sort]{by:"rank"}
}
return [is_ok($r[0]),is_ok($r[1])]
''')
    assert output(result) == [True, False]
    assert result['source_complete'] is False
    assert any(event['kind'] == 'collected_error' for event in result['evidence'])


@pytest.mark.parametrize('descending', [False, True])
@pytest.mark.parametrize('rows', [[], [{'cost': None}, {'cost': None}],
                                  [{'id': 'a'}, {'id': 'b', 'cost': None}]])
def test_empty_and_observed_null_keys_remain_normal(registry, descending, rows):
    result = run(registry, '$rows >> [table:sort]{by:"cost",descending:$descending}',
                 {'rows': rows, 'descending': descending})
    assert output(result) == rows
    assert result['source_complete'] is True


@pytest.mark.parametrize('descending', [False, True])
def test_sparse_ranking_keeps_missing_last_and_equal_keys_stable(registry, descending):
    rows = [{'id': 'unknown'}, {'id': 'a', 'cost': 20}, {'id': 'b', 'cost': 10},
            {'id': 'c', 'cost': 20}, {'id': 'null', 'cost': None}]
    original = copy.deepcopy(rows)
    result = run(registry, '$rows >> [table:sort]{by:"cost",descending:$descending}',
                 {'rows': rows, 'descending': descending})
    ids = ['a', 'c', 'b'] if descending else ['b', 'a', 'c']
    assert [row['id'] for row in output(result)] == ids + ['unknown', 'null']
    assert rows == original


def test_field_can_first_appear_after_diagnostic_sample(registry):
    rows = [{'id': i} for i in range(25)] + [{'cost': 1}]
    assert output(run(registry, '$rows >> [table:sort]{by:"cost"}',
                      {'rows': rows})) == [{'cost': 1}] + rows[:-1]


def test_record_keys_are_literal_not_implicit_nested_paths(registry):
    result = run(registry, '[{"price.value":20},{"price.value":10}] '
                 '>> [table:sort]{by:"price.value"}')
    assert output(result) == [{'price.value': 10}, {'price.value': 20}]
    missing = run(registry, '[{price:{value:10}}] >> [table:sort]{by:"price.value"}')
    assert missing['success'] is False
    assert missing['diagnostic']['code'] == 'MISSING_FIELD'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
