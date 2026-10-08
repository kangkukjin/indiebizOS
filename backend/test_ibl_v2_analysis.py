"""Actionable compiler diagnostics preserve the existing rejection boundary."""
import boot_paths  # noqa: F401
import pytest

from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime


@pytest.fixture
def registry():
    from ibl_v2_adapters import load_registry
    return load_registry()


@pytest.mark.parametrize('source', [
    '[table:ai]{items:[{text:"source"}],instruction:"extract",schema:"n(숫자), label(문자열)"}',
    '[self:struct]{text:"source",schema:"n(Number), label(Text)"}',
])
def test_schema_nullable_number_fails_before_model_and_guarded_version_passes(source, registry):
    unsafe = '$r=' + source + '; return number($r.items[0].n)'
    plan = compile_program(unsafe, registry=registry)
    assert any(i['code'] == 'ARITHMETIC' and i['actual'] == 'Null' for i in plan.issues)
    assert not Runtime(plan).run()['executed']
    safe = '$r=' + source + '; $n=$r.items[0].n; return $n == null ? null : number($n)'
    plan = compile_program(safe, registry=registry)
    assert not plan.issues, plan.issues
    assert 'Number' in str(plan.result_type) and 'Null' in str(plan.result_type)


def test_schema_types_flow_through_functions_each_and_projection(registry):
    source = '''
    [def:convert]($row){return number($row.n)}
    $r=[table:ai]{items:[{id:"a"}],instruction:"extract",
        schema:"n(숫자), yes(불리언)", fields:["n","yes"]}
    return $r.items >> [table:each]{return [fn:convert]{row:$it}}
    '''
    plan = compile_program(source, registry=registry)
    assert any(i['code'] == 'ARITHMETIC' and i['call_path'] for i in plan.issues)
    safe = source.replace('return number($row.n)',
                          'return $row.n == null ? null : number($row.n)')
    assert not compile_program(safe, registry=registry).issues


def test_schema_inspection_preserves_input_and_prose_stays_unknown(registry):
    source = '''$r=[table:ai]{items:[{n:1}],instruction:"extract",
        schema:"n(숫자), label(문자열)",inspect:"batch"}; return $r.items[0].n'''
    plan = compile_program(source, registry=registry)
    assert not plan.issues and str(plan.result_type) == 'Number'
    source = source.replace(',inspect:"batch"', '').replace('n(숫자)', 'n(금액 원)')
    plan = compile_program(source, registry=registry)
    assert not plan.issues and str(plan.result_type) == 'Unknown'


def test_nullable_arithmetic_diagnostic_explains_direct_guard():
    source = '''$rows >> [table:each]{
      $status=$it.price==null ? "unknown" : "ok"
      return $status=="ok" ? $it.price*2 : null
    }'''
    plan = compile_program(source, inputs={'rows': [{'price': None}, {'price': 3}]})
    issue = next(i for i in plan.issues if i['code'] == 'ARITHMETIC')
    assert issue['actual'] == 'Null'
    assert 'null' in issue['hint'] and '직접' in issue['hint']
    assert '상태 변수' in issue['hint']
    assert not Runtime(plan, {'rows': [{'price': None}, {'price': 3}]}).run()['executed']


@pytest.mark.parametrize('rows', [[], [{'price': None}], [{'price': 3}, {'price': None}]])
def test_direct_nullable_guard_runs_without_coercing_missing_to_zero(rows):
    source = '$rows >> [table:each]{return $it.price==null ? null : $it.price*2}'
    plan = compile_program(source, inputs={'rows': rows})
    result = Runtime(plan, {'rows': rows}).run()
    assert result['success'], result
    assert result['value'] == [None if row['price'] is None else row['price']*2 for row in rows]


def test_other_arithmetic_type_errors_keep_their_own_advice():
    plan = compile_program('return $x*2', inputs={'x': []})
    issue = next(i for i in plan.issues if i['code'] == 'ARITHMETIC')
    assert '상태 변수' not in issue['hint']
    assert not Runtime(plan, {'x': []}).run()['executed']


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
