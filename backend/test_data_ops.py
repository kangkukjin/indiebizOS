"""Data transform contracts through the public IBL execution boundary."""
import boot_paths  # noqa: F401
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('key', ['author', ['title', 'author']])
def test_dedup_documented_alias_selects_the_same_keys(key):
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    from thread_context import actor_context
    inputs = {'rows': [{'title': 'Shared', 'author': 'A'},
                       {'title': 'Shared', 'author': 'B'},
                       {'title': 'Shared', 'author': 'a'}], 'key': key}
    results = []
    for argument in ('by', 'key'):
        plan = compile_program('$rows >> [table:dedup]{' + argument + ':$key}',
                               load_registry(str(ROOT)), inputs)
        assert not plan.issues, plan.issues
        with actor_context(origin='training'):
            result = Runtime(plan, inputs).run()
        assert result['success'], result.get('diagnostic')
        results.append(result['value']['items'])
    assert results[0] == results[1] == inputs['rows'][:2]


@pytest.fixture(scope='module')
def data_ops():
    import importlib.util
    path = ROOT / 'data/packages/installed/tools/data-ops/handler.py'
    spec = importlib.util.spec_from_file_location('data_ops_contract', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('reverse', [False, True])
@pytest.mark.parametrize('reserved', [False, True])
def test_flatten_parent_columns_are_stable_for_sparse_children(data_ops, reverse, reserved):
    import copy
    rows = [{'shipment': 'S1', 'lines': [{'sku': 'A', 'shipment': 'vendor', 'qty': 2},
                                       {'sku': 'B', 'qty': 3}]},
            {'shipment': 'S2', 'lines': [{'sku': 'C', 'qty': 4}]}]
    if reserved:
        rows[1]['lines'][0]['shipment_2'] = 'original'
    if reverse:
        rows.reverse()
    original = copy.deepcopy(rows)
    result = data_ops._op_flatten({'items': rows}, {'field': 'lines', 'keep': ['shipment']})
    assert result['success']
    parent = 'shipment_3' if reserved else 'shipment_2'
    expected = [{**child, parent: row['shipment']} for row in rows for child in row['lines']]
    assert result['items'] == expected
    assert rows == original


def test_flatten_sparse_nested_keep_and_scalar_children(data_ops):
    rows = [{'meta': {'id': 'A'}, 'lines': [{'meta.id': 'child'}, 7]},
            {'meta': {}, 'lines': [{'other': 2}]}]
    result = data_ops._op_flatten({'items': rows}, {'field': 'lines', 'keep': ['meta.id']})
    assert result['items'] == [{'meta.id': 'child', 'meta.id_2': 'A'},
                               {'value': 7, 'meta.id_2': 'A'}, {'other': 2}]


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
