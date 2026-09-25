"""Real data composition must retain row failures and positional value types."""
import boot_paths  # noqa: F401
import copy
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from ibl_v2_adapters import Adapter, load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime
from ibl_v2_types import infer, join, compatible, declared


def run(code, registry=None, inputs=None):
    plan = compile_program(code, registry, inputs)
    assert not plan.issues, plan.report()
    return Runtime(plan, inputs).run()


@pytest.fixture(scope='module')
def registry(tmp_path_factory):
    return load_registry(str(tmp_path_factory.mktemp('round63')))


@pytest.mark.parametrize('source', [
    '[{title:"강의"},"2026-09-25"]',
    '({title:"강의"} & "2026-09-25")',
    '([{title:"강의"}]+["2026-09-25"])',
    '$input',
])
def test_fixed_order_values_preserve_each_position(source):
    result = run(f'$r={source}; return [$r[0].title,len($r[1])]',
                 inputs={'input': [{'title': '강의'}, '2026-09-25']})
    assert result['success'] and result['value'] == ['강의', 10], result


@pytest.mark.parametrize('wrapper', [
    '$r={expr}; return $r[0].title',
    '[def:f]($r){return $r[0].title}; $x={expr}; [fn:f]{r:$x}',
    '[def:f](){return {expr}}; $r=[fn:f]{}; return $r[0].title',
    '$r={value:{expr}}; return $r.value[0].title',
])
def test_positional_types_flow_through_existing_value_containers(wrapper):
    # Only the expression marker is substituted; IBL braces remain literal.
    code = wrapper.replace('{expr}', '[{title:"강의"},"날짜"]')
    result = run(code)
    assert result['success'] and result['value'] == '강의', result


def test_parallel_tool_outputs_with_different_declared_types():
    registry = {
        'fixture:read': Adapter({'version': 1, 'params': {}, 'result': {'text': 'Text'},
                                 'effects': ['pure']}, lambda rt, args: {'text': '강의'}),
        'fixture:date': Adapter({'version': 1, 'params': {}, 'result': 'Text',
                                 'effects': ['pure']}, lambda rt, args: '2026-09-25'),
        'fixture:count': Adapter({'version': 1, 'params': {}, 'result': 'Number',
                                  'effects': ['pure']}, lambda rt, args: 3),
    }
    result = run('$r=[fixture:read]{} & [fixture:date]{} & [fixture:count]{}; '
                 'return [$r[0].text,len($r[1]),$r[2]+1]', registry)
    assert result['success'] and result['value'] == ['강의', 10, 4], result


@pytest.mark.parametrize('flag', [True, False])
def test_alternative_lists_join_corresponding_positions(flag):
    code = '$r=[if:$flag]{[{title:"A"},1]}[else]{[{title:"B"},"date"]}; return $r[0].title'
    result = run(code, inputs={'flag': flag})
    assert result['success'] and result['value'] == ('A' if flag else 'B'), result


@pytest.mark.parametrize('code', [
    '$r=[{title:"A"},"date"]; return $r[1].title',
    '$r=[{title:"A"},"date"]+[{title:"B"},"later"]; return $r[1].title',
    '$r=[if:true]{[{title:"A"},1]}[else]{["date",1]}; return $r[0].title',
    '$r=[if:true]{[{title:"A"},1]}[else]{[1]}; return $r[0].title',
    '$r=[{title:"A"},"date"]; $i=1; return $r[$i].title',
])
def test_positions_do_not_erase_real_type_errors(code):
    assert compile_program(code).issues


def test_concat_does_not_merge_positions_as_control_flow_alternatives():
    result = run('$r=[{title:"A"}]+["date"]+[{score:7}]; '
                 'return [$r[0].title,$r[1],$r[2].score]')
    assert result['success'] and result['value'] == ['A', 'date', 7], result


def test_concat_keeps_empty_operand_and_rebinding_precision():
    result = run('$r=[]+[{title:"A"},"date"]+[]; $r=[7]+$r; return $r[1].title')
    assert result['success'] and result['value'] == 'A', result


def test_position_refinement_does_not_change_list_contracts():
    a = infer([{'title': 'A'}, 'date'])
    b = infer([{'title': 'B'}, 1])
    assert compatible(a, declared('List'))
    assert not compatible(a, declared('List<Record>'))
    assert join(a, b) == join(b, a)
    assert join(a, a) == a
    assert join(a, join(b, declared('List'))) == join(join(a, b), declared('List'))


@pytest.mark.parametrize('bad', [None, True, 7, '읽기 실패', ['nested']])
@pytest.mark.parametrize('placement', ['mixed', 'all'])
@pytest.mark.parametrize('carrier', ['list', 'envelope', 'json'])
def test_reduce_refuses_nonrecord_rows_before_aggregation(registry, bad, placement, carrier):
    rows = [{'cost': 10}, bad, {'cost': 20}] if placement == 'mixed' else [bad]
    source = rows if carrier == 'list' else {'items': rows}
    if carrier == 'json':
        source = json.dumps(source, ensure_ascii=False)
    result = run('$source >> [table:reduce]{init:0,step:"acc+1"}', registry, {'source': source})
    assert result['executed'] and not result['success'], result
    assert result['source_complete'] is False
    assert '객체' in result['error'] and '행' in result['error']


@pytest.mark.parametrize('how', ['inner', 'left', 'right', 'full', 'semi', 'anti'])
@pytest.mark.parametrize('side', ['left', 'right'])
@pytest.mark.parametrize('carrier', ['envelope', 'json'])
def test_all_join_modes_reject_bad_rows_on_either_side(registry, how, side, carrier):
    values = {'left': {'items': [{'id': 'a'}]}, 'right': {'items': [{'id': 'a'}]}}
    values[side]['items'].insert(0, 'broken')
    if carrier == 'json':
        values = {key: json.dumps(value) for key, value in values.items()}
    result = run(f'[table:join]{{left:$left,right:$right,on:"id",how:"{how}"}}', registry, values)
    assert result['executed'] and not result['success'], result


def test_reduce_reports_original_invalid_indices_and_performs_no_fold(monkeypatch):
    from ibl_control_blocks import _execute_table_reduce
    import common.safe_expr
    monkeypatch.setattr(common.safe_expr, 'eval_expr', lambda *a, **k: pytest.fail('fold ran on invalid rows'))
    rows = [None, {'cost': 10}, 'bad', {'cost': 20}]
    before = copy.deepcopy(rows)
    result = _execute_table_reduce({'items': rows, 'init': 0, 'step': 'acc+cost'}, '.')
    assert result['success'] is False and result['invalid_row_indices'] == [0, 2]
    assert result['rows_done'] == 0
    assert rows == before


def test_table_transform_row_policy_census():
    """Each operation either preserves rows, explicitly selects, or rejects them."""
    path = Path(__file__).resolve().parents[1] / 'data/packages/installed/tools/data-ops'
    sys.path.insert(0, str(path))
    try:
        spec = importlib.util.spec_from_file_location('round63_dataops', path / 'handler.py')
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(path))
    rows = [{'id': 'a', 'n': 1}, 'bad', {'id': 'b', 'n': 2}]
    configurations = {
        'filter': {'where': {'field': 'n', 'op': 'gte', 'value': 0}},
        'sort': {'by': 'id'}, 'select': {'columns': ['id']},
        'compute': {'set': {'n': 'n+1'}}, 'groupby': {'by': 'id'},
        'dedup': {'by': 'id'},
    }
    for operation, args in configurations.items():
        valid = getattr(mod, '_op_'+operation)({'items': [rows[0], rows[2]]}, args)
        assert valid.get('success') is not False, (operation, valid)
        result = getattr(mod, '_op_'+operation)({'items': copy.deepcopy(rows)}, args)
        assert result.get('success') is False, (operation, result)
    # These verbs preserve uninterpreted payload rows instead of deleting them.
    assert mod._op_rename({'items': rows}, {'map': {'id': 'name'}})['items'][1] == 'bad'
    assert mod._op_take({'items': rows}, {'n': 3})['items'] == rows
    for operation in ['merge', 'union']:
        result = getattr(mod, '_op_'+operation)([{'items': rows}, {'items': []}], {})
        assert result['items'] == rows


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
