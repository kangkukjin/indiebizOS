"""Join column identity and alignment across sparse business data."""
import boot_paths  # noqa: F401
import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def ops():
    spec = importlib.util.spec_from_file_location(
        'round65_dataops', ROOT / 'data/packages/installed/tools/data-ops/handler.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('how', ['inner', 'left', 'right', 'full'])
@pytest.mark.parametrize('reverse', [False, True])
def test_sparse_columns_keep_source_identity_for_every_join_mode(ops, how, reverse):
    left = [{'id': 'a', 'score': 10, 'score_2': 9}, {'id': 'b'}]
    right = [{'id': 'a', 'score': 20}, {'id': 'b', 'score': 30}]
    if reverse:
        left.reverse()
        right.reverse()
    inputs = [{'items': left}, {'items': right}]
    before = copy.deepcopy(inputs)
    out = ops._op_join(inputs, {'on': 'id', 'how': how})
    assert out['success'], out
    assert {row['id']: row['score_3'] for row in out['items']} == {'a': 20, 'b': 30}
    assert next(row for row in out['items'] if row['id'] == 'b').get('score') is None
    assert inputs == before


@pytest.mark.parametrize('reverse', [False, True])
def test_sparse_right_columns_get_one_mapping_even_with_suffix_collisions(ops, reverse):
    left = [{'id': 'a', 'score': 10}, {'id': 'b', 'score': 11}]
    right = [{'id': 'a', 'score': 20, 'score_2': 90}, {'id': 'b', 'score_2': 91}]
    if reverse:
        left.reverse()
        right.reverse()
    out = ops._op_join([left, right], {'on': 'id'})
    # Mapping must not be recalculated per matched pair: each right source
    # column occupies the same destination in all output rows.
    first = next(row for row in out['items'] if row['id'] == 'a')
    second = next(row for row in out['items'] if row['id'] == 'b')
    destination = next(key for key, value in first.items() if value == 90)
    assert second[destination] == 91
    assert first['score'] == 10 and second['score'] == 11


@pytest.mark.parametrize('how', ['inner', 'left', 'right', 'full'])
@pytest.mark.parametrize('left_width,right_width', [(1, 1), (1, 3), (2, 2), (3, 1), (3, 3)])
def test_ragged_table_rows_keep_declared_cell_positions(ops, how, left_width, right_width):
    left_row = ['a', 'left', 'memo'][:left_width]
    right_row = ['a', 20, 'note'][:right_width]
    inputs = [
        {'table': {'columns': ['id', 'name', 'memo'], 'rows': [left_row]}},
        {'table': {'columns': ['id', 'score', 'note'], 'rows': [right_row]}},
    ]
    before = copy.deepcopy(inputs)
    out = ops._op_join(inputs, {'on': 'id', 'how': how})
    expected = (left_row + [None] * (3 - left_width)
                + right_row[1:] + [None] * (3 - right_width))
    assert out['table'] == {'columns': ['id', 'name', 'memo', 'score', 'note'],
                            'rows': [expected]}, out
    assert inputs == before


def test_inner_join_keeps_sparse_absence_and_many_to_many_multiplicity(ops):
    left = [{'id': 'a', 'score': 10}, {'id': 'a'}]
    right = [{'id': 'a', 'score': 20}, {'id': 'a', 'note': 'late'}]
    out = ops._op_join([left, right], {'on': 'id'})
    assert out['items'] == [
        {'id': 'a', 'score': 10, 'score_2': 20},
        {'id': 'a', 'score': 10, 'note': 'late'},
        {'id': 'a', 'score_2': 20}, {'id': 'a', 'note': 'late'},
    ]


@pytest.mark.parametrize('how', ['semi', 'anti'])
def test_existence_joins_never_copy_right_columns(ops, how):
    left = [{'id': 'a', 'score': 10}, {'id': 'b'}]
    right = [{'id': 'a', 'score': 20}, {'id': 'a', 'score': 30}]
    out = ops._op_join([left, right], {'on': 'id', 'how': how})
    assert out['items'] == [left[0 if how == 'semi' else 1]]


@pytest.fixture(scope='module')
def registry(tmp_path_factory):
    from ibl_v2_adapters import load_registry
    return load_registry(str(tmp_path_factory.mktemp('round65')))


@pytest.mark.parametrize('case_number', [0, 1, 2, 3, 4, 5, 6, 7, 13, 14, 15, 16, 17])
def test_real_vocabulary_compositions(registry, case_number):
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    spec = importlib.util.spec_from_file_location(
        'round65_probe', ROOT / 'docs/experiments/imagination_round65_2026_09_25/probe.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _, _, code, _, expected = module.CASES[case_number]
    plan = compile_program(code, registry)
    assert not plan.issues, plan.report()
    out = Runtime(plan).run()
    assert out['success'] and out['value'] == expected, out
    assert out['source_complete']


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
