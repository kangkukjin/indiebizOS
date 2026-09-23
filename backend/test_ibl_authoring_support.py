"""Authoring regressions: generated values, independent oracles, inert effects."""
import boot_paths  # noqa: F401
import json

import pytest
from hypothesis import given, settings, strategies as st
from ibl_v2_adapters import Adapter
from ibl_v2_compile import compile_program
from ibl_v2_ir import unpack
from ibl_v2_runtime import Runtime


def compile_and_run(code, inputs=None, registry=None):
    plan = compile_program(code, registry, inputs)
    assert not plan.issues, plan.report()
    result = Runtime(plan, inputs).run()
    assert result['success'], result
    return unpack(result['value_wire']['data'])


@pytest.mark.parametrize('code,expected', [
    ('return len(4)', 'TYPE'),
    ('return has([], "x")', 'TYPE'),
    ('return get({}, 1, null)', 'TYPE'),
    ('return unwrap(1)', 'TYPE'),
    ('return text([])', 'TYPE'),
    ('return 1 + "hello"', 'NUMBER_REQUIRED'),
    ('return number("hello")', 'NUMBER_REQUIRED'),
    ('$x={n:1}\n[repeat:1]{$x={m:2}}\nreturn $x.n', 'MISSING_FIELD'),
    ('[repeat:1.5]{return 1}', 'REPEAT_COUNT'),
])
def test_known_errors_are_reported_before_effects(code, expected):
    plan = compile_program(code)
    assert expected in [e['code'] for e in plan.issues]
    assert Runtime(plan).run()['executed'] is False


def test_many_errors_one_report_and_function_local_source_locations():
    source = '$a=len(4)\n$b=[fn:outer]{x:{wrong:1}}\nreturn $missing'
    definitions = {'outer': '[def:outer]($x){return [fn:inner]{x:$x}}',
                   'inner': '[def:inner]($x){return $x.score}'}
    report = compile_program(source, definitions=definitions).report()
    assert {'TYPE', 'MISSING_FIELD', 'UNBOUND'} <= {e['code'] for e in report['issues']}
    field = next(e for e in report['issues'] if e['code'] == 'MISSING_FIELD')
    assert field['location']['uri'] == 'ibl://function/inner'
    assert field['location']['line'] == 1
    assert [f['function'] for f in field['call_path']] == ['outer', 'inner']
    assert field['call_path'][0]['call']['uri'] == 'ibl://program'
    assert field['call_path'][1]['call']['uri'] == 'ibl://function/outer'
    assert field['hint'] and field['severity'] == 'error'
    corrected = '$a=len([])\n$b=[fn:outer]{x:{score:1}}\nreturn $b'
    repaired = compile_program(corrected, definitions=definitions)
    assert not repaired.issues
    assert repaired.report()['source_hash'] != report['source_hash']
    assert repaired.fingerprint != report['plan_hash']
    assert Runtime(repaired).run()['value'] == 1


def test_function_observed_signatures_do_not_discard_previous_calls():
    p = compile_program('[def:f]($x){return $x}\n$a=[fn:f]{x:1}\n$b=[fn:f]{x:"a"}')
    contract = next(iter(p.report()['functions'].values()))
    assert contract['params']['x'] == 'Unknown'
    assert {v['result'] for v in contract['specializations']} == {'Number', 'Text'}
    assert contract['definition']['uri'] == 'ibl://program'


@pytest.mark.parametrize('choose', [True, False])
def test_builtin_union_accepts_every_valid_branch(choose):
    code = '$x=[if:$choose]{"abc"}[else]{[1,2]}\nreturn len($x)'
    assert compile_and_run(code, {'choose': choose}) == (3 if choose else 2)


@given(st.integers(min_value=-10000, max_value=10000))
@settings(max_examples=60, deadline=None, derandomize=True)
def test_numeric_text_observation_matches_independent_integer_sum(n):
    code = 'return 3 + ' + json.dumps(str(n))
    assert compile_and_run(code) == n + 3


@given(st.lists(st.integers(-100, 100), max_size=20), st.integers(-10, 10))
@settings(max_examples=60, deadline=None, derandomize=True)
def test_nested_map_and_function_extraction_preserve_values(rows, factor):
    code = '''[def:scale]($rows,$factor){
      return $rows >> [table:each]{} {return $it*$factor}
    }
    [def:twice]($rows,$factor){
      $first=[fn:scale]{rows:$rows,factor:$factor}
      return [fn:scale]{rows:$first,factor:2}
    }
    return [fn:twice]{rows:$rows,factor:$factor}'''
    assert compile_and_run(code, {'rows': rows, 'factor': factor}) == [n * factor * 2 for n in rows]


@given(st.integers(0, 8), st.integers(-100, 100))
@settings(max_examples=40, deadline=None, derandomize=True)
def test_repeat_mutations_never_certify_stale_shape(count, n):
    code = '$x={old:0}\n[repeat:$count]{$x={new:$n}}\nreturn $x.old'
    report = compile_program(code, inputs={'count': count, 'n': n}).report()
    assert report['status'] != 'valid'
    safe = '$x=0\n[repeat:$count]{$x=$x+$n}\nreturn $x'
    assert compile_and_run(safe, {'count': count, 'n': n}) == count * n


def model_registry(calls):
    return {'fixture:judge': Adapter({'version': 1, 'params': {'items': 'List'},
             'required': ['items'], 'result': 'Number', 'effects': ['model'],
             'pipe_input': 'items'}, lambda rt, args: calls.append(args) or len(args['items']))}


@pytest.mark.parametrize('argument,warning', [('$rows', True), ('[$it]', False)])
def test_repeated_model_batch_warnings_are_nonblocking_and_effect_free(argument, warning):
    calls = []
    source = f'$rows=[1,2,3]\nreturn $rows >> [table:each]{{}}{{[fixture:judge]{{items:{argument}}}}}'
    plan = compile_program(source, model_registry(calls))
    report = plan.report()
    assert calls == []
    assert bool(report['warnings']) is warning
    assert report['preflight']['declared_ai_visits_upper_bound'] == 3
    assert not plan.issues
    assert Runtime(plan).run()['success']
    assert len(calls) == 3


def test_preflight_tracks_functions_and_never_calls_unknown_cost_zero():
    reg = model_registry([])
    source = '''[def:judge]($batch){return [fixture:judge]{items:$batch}}
    $rows=[1,2,3]
    return $rows >> [table:each]{} {return [fn:judge]{batch:$rows}}'''
    p = compile_program(source, reg)
    assert p.report()['warnings'][0]['rule'] == 'repeated_ai_batch'
    assert p.preflight['declared_ai_visits_upper_bound'] == 3
    unknown = compile_program('[def:f]($rows){return $rows >> [table:each]{}{[fixture:judge]{items:[$it]}}}', reg)
    # Uncalled definitions cost no visits.
    assert unknown.preflight['declared_ai_visits_upper_bound'] == 0
    reg['fixture:opaque'] = Adapter({'version': 1, 'params': {}, 'result': 'Record',
                                    'effects': ['unknown']}, lambda *_: pytest.fail('must not execute'))
    assert compile_program('[fixture:opaque]{}', reg).preflight['declared_ai_visits_upper_bound'] is None


def test_declared_inspection_is_not_a_model_visit_and_analysis_has_a_budget():
    reg = model_registry([])
    contract = {**reg['fixture:judge'].contract, 'params': {'items': 'List', 'inspect': 'Text'},
                'analysis': {'ai_call': True, 'ai_inspect_param': 'inspect'}}
    reg['fixture:judge'] = Adapter(contract, lambda *_: pytest.fail('must not execute'))
    source = '$rows=[1,2,3]\nreturn $rows >> [table:each]{}{[fixture:judge]{items:$rows,inspect:"each"}}'
    p = compile_program(source, reg)
    assert not p.preflight['warnings']
    assert p.preflight['declared_ai_visits_upper_bound'] == 0
    p = compile_program('\n'.join('$x=1' for _ in range(2100)))
    assert p.preflight['status'] == 'partial'
    assert p.preflight['declared_ai_visits_upper_bound'] is None


FAMILIES = ('report', 'files', 'records', 'branch', 'aggregate', 'partial')


def long_fixture(family, size):
    """30 synthetic cases, six structural families; never called historical successes."""
    lines = ['#!ibl edition=2', '[def:stage0]($row,$delta){',
             '  return {id:$row.id,score:$row.score+$delta}', '}']
    for i in range(1, 7):
        lines += [f'[def:stage{i}]($row,$delta){{',
                  f'  $next=[fn:stage{i-1}]{{row:$row,delta:$delta}}',
                  '  $adjusted={id:$next.id,score:$next.score+1}',
                  '  return $adjusted', '}']
    lines += ['$loaded=[fixture:read]{items:$rows}',
              '$processed=$loaded >> [table:each]{parallel:2}{',
              '  return [fn:stage6]{row:$it,delta:$delta}', '}']
    tails = {
        'report': 'return {rows:$processed,count:len($processed)}',
        'files': 'return $processed >> [table:each]{}{return f"${it.id}: ${it.score}"}',
        'records': 'return $processed >> [table:each]{}{return [fixture:write]{record:$it}}',
        'branch': '$out=[if:len($processed)>0]{return $processed}[else]{return []}\nreturn $out',
        'aggregate': '$total=0\n[repeat:len($processed)]{$total=$total+$processed[$i].score}\nreturn $total',
        'partial': 'return $processed >> [table:each]{on_error:"collect"}{return 12/$it.score}',
    }
    lines.append(tails[family])
    inputs = {'rows': [{'id': f'{i:03}', 'score': i - 7} for i in range(size)], 'delta': 1}
    calls = []
    reg = {
        'fixture:read': Adapter({'version': 1, 'params': {'items': 'List'},
                                'result': {'$list': {'id': 'Text', 'score': 'Number'}},
                                'effects': ['read_external']}, lambda rt, a: a['items']),
        'fixture:write': Adapter({'version': 1, 'params': {'record': {'id': 'Text', 'score': 'Number'}},
                                 'result': {'id': 'Text', 'score': 'Number'},
                                 'effects': ['write_external']}, lambda rt, a: calls.append(a) or a['record']),
    }
    return '\n'.join(lines), inputs, reg, calls


@pytest.mark.parametrize('family', FAMILIES)
@pytest.mark.parametrize('size', [0, 1, 3, 10, 50])
def test_long_programs_have_independent_expected_results(family, size):
    code, inputs, reg, calls = long_fixture(family, size)
    actual = compile_and_run(code, inputs, reg)
    rows = [{'id': f'{i:03}', 'score': i} for i in range(size)]
    expected = {'report': {'rows': rows, 'count': size}, 'files': [f'{i:03}: {i}' for i in range(size)],
                'records': rows, 'branch': rows, 'aggregate': sum(range(size))}
    if family == 'partial':
        assert [r.ok for r in actual] == [i != 0 for i in range(size)]
        assert [r.value for r in actual if r.ok] == [12 / i for i in range(1, size)]
    else:
        assert actual == expected[family]
    assert len(calls) == (size if family == 'records' else 0)
    mutation = code.replace('score:$row.score+$delta', 'score:$row.missing+$delta')
    # Declared Records are open: an undeclared field is unknown, not proven absent.
    partial = compile_program(mutation, reg, inputs).report()
    assert partial['status'] == 'incomplete'
    assert partial['guards']
    unbound = code.replace('score:$row.score+$delta', 'score:$missing+$delta')
    errors = compile_program(unbound, reg, inputs).issues
    assert any(e['code'] == 'UNBOUND' for e in errors)


def test_public_check_consumers_use_the_same_compiler(monkeypatch):
    import ibl_v2_adapters
    import ibl_v2_store
    import api_ibl
    from ibl_v2_entry import handle_request
    monkeypatch.setattr(ibl_v2_adapters, 'load_registry', lambda *a: {})
    monkeypatch.setattr(ibl_v2_store, 'definitions', lambda: {})
    code = 'return len(1)'
    direct = compile_program(code).report()
    tool = handle_request({'edition': 2, 'code': code, 'check': True})
    http = api_ibl.validate_request_code(code, edition=2)
    assert direct['issues'] == tool['issues'] == http['issues']
    syntax = handle_request({'edition': 2, 'code': 'return [', 'check': True})
    assert syntax['issues'][0]['severity'] == 'error'
    assert syntax['executed'] is False


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
