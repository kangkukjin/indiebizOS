"""Composition audit regressions plus branch/cleanup safety boundaries."""
import boot_paths  # noqa: F401
import importlib.util
from pathlib import Path

import pytest

from ibl_v2_adapters import Adapter
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime


path = Path(__file__).resolve().parents[1] / 'scripts/probe_ibl_composition_2026_09_25.py'
spec = importlib.util.spec_from_file_location('composition_audit_fixture', path)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


@pytest.mark.parametrize('case', audit.cases(), ids=lambda c: c['name'])
def test_audited_compositions(case):
    result = audit.evaluate(case)
    assert result['passed'], result


def execute(code, inputs=None, registry=None):
    plan = compile_program(code, registry, inputs)
    assert not plan.issues, plan.report()
    result = Runtime(plan, inputs).run()
    assert result['success'], result
    return result['value']


@pytest.mark.parametrize('branches', [
    '({n:1} & {n:2}) & {n:3}',
    '{n:1} & ({n:2} & {n:3})',
    '({n:1} & {n:2}) & ({n:3} & {n:4})',
])
def test_parenthesized_parallel_types_match_runtime(branches):
    assert execute('$rows=' + branches + '\nreturn $rows[2].n') == 3


def test_function_returning_parallel_value_stays_a_single_branch():
    code = '''[def:pair](){return {n:1} & {n:2}}
    $rows=[fn:pair]{} & [fn:pair]{} & [fn:pair]{}
    return $rows[2][1].n'''
    assert execute(code) == 2


def write_registry(calls):
    return {'fixture:write': Adapter({
        'version': 1, 'params': {'path': 'Text'}, 'result': 'Text',
        'effects': ['write_external'], 'write_resources': {'file': 'path'},
    }, lambda rt, args: calls.append(args['path']) or args['path'])}


@pytest.mark.parametrize('paths', [('a', 'a', 'b'), ('a', 'b', 'a'), ('a', 'b', 'b')])
def test_parallel_write_conflicts_between_any_two_branches(paths):
    calls = []
    code = ' & '.join(f'[fixture:write]{{path:"{p}"}}' for p in paths)
    plan = compile_program(code, write_registry(calls))
    assert 'PARALLEL_WRITE_CONFLICT' in {i['code'] for i in plan.issues}
    assert Runtime(plan).run()['executed'] is False
    assert calls == []


def test_parallel_independent_writes_execute_once_and_keep_order():
    calls = []
    code = ' & '.join(f'[fixture:write]{{path:"{p}"}}' for p in ('a', 'b', 'c'))
    assert execute(code, registry=write_registry(calls)) == ['a', 'b', 'c']
    assert sorted(calls) == ['a', 'b', 'c']


@pytest.mark.parametrize('code', [
    '[case:2]{[when:1]{return 0}[when:2]{$x=1}[else]{2}}\nreturn $x',
    '[case:2]{[when:1]{return 0}[when:2]{$x=1}}\nreturn $x',
    '[case:1]{[when:1]{[table:each]{items:[1]}{return 0}}[else]{$x=1}}\nreturn $x',
    '[try]{$x=1}[catch]{0}\nreturn $x',
    '[try]{1/0}[catch]{$x=1}\nreturn $x',
    '[try]{$x=1}[catch]{return 0}[finally]{$y=$x}\nreturn 1',
])
def test_missing_bindings_are_still_rejected(code):
    plan = compile_program(code)
    assert 'UNBOUND' in {i['code'] for i in plan.issues}
    assert Runtime(plan).run()['executed'] is False


@pytest.mark.parametrize('choice', [1, 2, 3])
def test_nested_returns_do_not_remove_the_surviving_case_environment(choice):
    code = '''[def:f]($choice){
      [case:$choice]{
        [when:1]{[if:true]{return 1}[else]{return 10}}
        [when:2]{return 2}
        [else]{$x=3}
      }
      return $x
    }
    [fn:f]{choice:$choice}'''
    assert execute(code, {'choice': choice}) == choice


@pytest.mark.parametrize('divisor', [0, 1])
def test_catch_return_still_runs_finally_and_preserves_its_assignments(divisor):
    calls = []
    code = '''[def:f]($divisor){
      [try]{$x=8/$divisor}[catch]{return 0}
      [finally]{[fixture:write]{path:"cleanup"}; $suffix=2}
      return $x+$suffix
    }
    [fn:f]{divisor:$divisor}'''
    assert execute(code, {'divisor': divisor}, write_registry(calls)) == (10 if divisor else 0)
    assert calls == ['cleanup']


@pytest.mark.parametrize('divisor', [0, 1])
def test_try_return_leaves_catch_binding_on_the_continuing_path(divisor):
    code = '''[def:f]($divisor){
      [try]{return 8/$divisor}[catch]{$x=3}
      [finally]{$suffix=2}
      return $x+$suffix
    }
    [fn:f]{divisor:$divisor}'''
    assert execute(code, {'divisor': divisor}) == (8 if divisor else 5)


def test_finally_rebinding_does_not_leave_a_stale_continuation_type():
    code = '''[try]{$x={old:1}}[catch]{return 0}
    [finally]{$x={new:2}}
    return $x.new'''
    assert execute(code) == 2
    plan = compile_program(code.replace('$x.new', '$x.old'))
    assert 'MISSING_FIELD' in {i['code'] for i in plan.issues}


def test_inner_catch_restores_the_outer_error_binding():
    code = '''[try]{1/0}[catch]{
      $outer=$error.message
      [try]{1/0}[catch]{0}
      return $error.message==$outer
    }'''
    assert execute(code) is True


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
