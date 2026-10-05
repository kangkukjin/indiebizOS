"""Actionable compiler diagnostics preserve the existing rejection boundary."""
import boot_paths  # noqa: F401
import pytest

from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime


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
