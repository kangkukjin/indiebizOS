"""실행 없는 계획 분석: 누락·증폭 탐지와 동적 값에 대한 기권 회귀."""
import json

import pytest

import boot_paths  # noqa: F401 — 직접 실행도 같은 backend 경로를 쓴다.
import ibl_typecheck as tc
from ibl_parser import parse_with_vars
from ibl_preflight import analyze


ROWS = '[{x:1},{x:2},{x:3}]'
AI = '[table:ai]{instruction:"분류"}'


def checked(code):
    result = tc.typecheck_code(code)
    assert not result.get('abstained'), result
    assert 'preflight' in result, result
    assert result['preflight']['status'] != 'abstained', result
    return result


def rules(result):
    return {i.get('rule'): i for i in result['issues'] if i.get('rule')}


def test_known_truncation_and_repeated_batch_are_nonblocking():
    result = checked(f'$a={ROWS}\n$a >> [table:each]{{limit:2}}'
                     '{[table:ai]{items:$a,instruction:"분류"}}')
    assert result['ok']
    found = rules(result)
    assert set(found) == {'each_input_limit', 'repeated_ai_batch'}
    assert found['each_input_limit']['facts']['omitted_rows'] == 1
    assert found['repeated_ai_batch']['facts']['row_transmissions_upper_bound'] == 6
    assert all(i['severity'] == 'warning' for i in found.values())
    assert result['preflight']['declared_ai_visits_upper_bound'] == 2


def test_default_limit_matches_executor():
    from ibl_exec_each import _EACH_DEFAULT_LIMIT
    n = _EACH_DEFAULT_LIMIT + 1
    result = checked(f'[table:each]{{items:{json.dumps(list(range(n)))}}}'
                     '{[$it] >> ' + AI + '}')
    assert rules(result)['each_input_limit']['facts'] == {
        'input_rows': n, 'limit': _EACH_DEFAULT_LIMIT, 'omitted_rows': 1}


@pytest.mark.parametrize('limit', ['$a.count', '3', '30'])
def test_full_count_and_current_row_have_no_new_warnings(limit):
    result = checked(f'$a={ROWS}\n$a >> [table:each]{{limit:{limit}}}'
                     '{[$it] >> ' + AI + '}')
    assert not rules(result)
    assert result['preflight']['declared_ai_visits_upper_bound'] == 3


@pytest.mark.parametrize('items,limit', [('[]', 20), (ROWS, 0)])
def test_zero_iterations_do_not_visit_ai(items, limit):
    result = checked(f'[table:each]{{items:{items},limit:{limit}}}{{{AI}}}')
    assert result['preflight']['declared_ai_visits_upper_bound'] == 0
    assert result['preflight']['ai_sites'] == []


def test_pipeline_input_takes_precedence_over_explicit_items():
    result = checked('[{x:1}] >> [table:each]{items:' + ROWS + ',limit:1}'
                     '{[$it] >> ' + AI + '}')
    assert not rules(result)
    assert result['preflight']['declared_ai_visits_upper_bound'] == 1


def test_unknown_pipeline_is_not_replaced_by_literal_parameter():
    result = checked('[sense:search]{query:"x"} >> [table:each]{items:' + ROWS
                     + ',limit:2}{[$it] >> ' + AI + '}')
    assert not rules(result)
    assert result['preflight']['status'] == 'partial'
    assert result['preflight']['declared_ai_visits_upper_bound'] == 2


def test_dynamic_bound_is_unknown_not_zero_or_error():
    result = checked('$a=[sense:search]{query:"x"}\n'
                     '$a >> [table:each]{limit:$a.count}{[$it] >> ' + AI + '}')
    assert result['ok'] and not rules(result)
    assert result['preflight']['declared_ai_visits_upper_bound'] is None
    assert result['preflight']['status'] == 'partial'


def test_filter_output_count_is_not_inferred_from_preserved_columns():
    result = checked(ROWS + ' >> [table:filter]{where:"x > 2"}'
                     ' >> [table:each]{limit:1}{[$it] >> ' + AI + '}')
    assert 'each_input_limit' not in rules(result)


@pytest.mark.parametrize('consumer', [
    '$a >> [table:each]{limit:1}{[$it] >> ' + AI + '}',
    '[table:each]{items:$a,limit:1}{[$it] >> ' + AI + '}',
])
def test_branch_assignment_invalidates_old_named_and_slot_counts(consumer):
    result = checked(f'$a={ROWS}\n[if:true]{{$a=[{{x:1}}]}}\n' + consumer)
    assert 'each_input_limit' not in rules(result)


def test_nested_repeat_multiplies_upper_bound():
    result = checked('[repeat:4]{[repeat:3]{' + ROWS + ' >> ' + AI + '}}')
    assert result['preflight']['declared_ai_visits_upper_bound'] == 12
    assert 'repeated_ai_batch' in rules(result)


@pytest.mark.parametrize('value', ['$it.x', '"row $it.x"'])
def test_loop_dependent_constructed_input_is_not_called_invariant(value):
    result = checked('[table:each]{items:' + ROWS + '}{'
                     '[{x:' + value + '},{x:0}] >> ' + AI + '}')
    assert 'repeated_ai_batch' not in rules(result)


def test_current_row_envelope_keeps_loop_dependency():
    result = checked('[table:each]{items:[{items:[1,2]},{items:[3,4]}]}'
                     '{$it >> ' + AI + '}')
    assert 'repeated_ai_batch' not in rules(result)


def test_changed_outer_variable_is_not_assumed_constant_in_repeat():
    result = checked(f'$a={ROWS}\n[repeat:3]{{'
                     '$a >> ' + AI + '\n$a=[{x:1}]\n}')
    assert 'repeated_ai_batch' not in rules(result)


def test_local_function_parameters_forward_def_and_unused_body():
    result = checked('[fn:f]{목록:' + ROWS + '}\n'
                     '[def:f]{$목록 >> [table:each]{limit:2}{[$it] >> ' + AI + '}}\n'
                     '[def:unused]{[repeat:99]{' + ROWS + ' >> ' + AI + '}}')
    assert result['preflight']['declared_ai_visits_upper_bound'] == 2
    assert rules(result)['each_input_limit']['facts']['input_rows'] == 3


def test_function_implicit_pipe():
    result = checked('[def:f]{$목록 >> [table:each]{limit:1}{[$it] >> ' + AI + '}}\n'
                     + ROWS + ' >> [fn:f]')
    assert rules(result)['each_input_limit']['facts']['input_rows'] == 3
    assert result['preflight']['declared_ai_visits_upper_bound'] == 1


def test_function_return_count():
    result = checked('[def:f]{$return=$목록}\n[fn:f]{목록:' + ROWS + '}'
                     ' >> [table:each]{limit:1}{[$it] >> ' + AI + '}')
    assert rules(result)['each_input_limit']['facts']['input_rows'] == 3
    assert result['preflight']['declared_ai_visits_upper_bound'] == 1


def test_conditional_return_overwrite_invalidates_previous_count():
    result = checked('[def:f]{$return=' + ROWS + '\n'
                     '[if:true]{$return=[{x:1}]}}\n'
                     '[fn:f] >> [table:each]{limit:1}{[$it] >> ' + AI + '}')
    assert 'each_input_limit' not in rules(result)


def test_bad_nested_body_preserves_other_plan_sites():
    result = checked(AI + '\n[table:each]{items:' + ROWS + ',do:"broken source"}')
    assert result['preflight']['status'] == 'partial'
    assert len(result['preflight']['ai_sites']) == 1
    assert any(u['reason'] == 'unparsed_body' for u in result['preflight']['unknowns'])


def test_external_function_body_is_only_read(monkeypatch):
    monkeypatch.setattr(tc, '_external_fn_code', lambda name: '[repeat:3]{' + AI + '}')
    result = checked('[fn:외부]')
    assert result['preflight']['declared_ai_visits_upper_bound'] == 3


def test_recursive_function_stops_with_unknown_bound():
    result = checked('[def:f]{[fn:f]}\n[fn:f]')
    assert result['preflight']['status'] == 'partial'
    assert result['preflight']['declared_ai_visits_upper_bound'] is None
    assert any(u['reason'] == 'analysis_depth_limit' for u in result['preflight']['unknowns'])


def test_exclusive_branches_are_conservatively_summed():
    result = checked('[if:true]{[repeat:2]{' + AI + '}}'
                     '[else]{[repeat:3]{' + AI + '}}')
    assert result['preflight']['declared_ai_visits_upper_bound'] == 5


@pytest.mark.parametrize('operator', ['&', '??'])
def test_parallel_and_fallback_visit_both_branches(operator):
    branch = '[table:ai]{items:[{x:1}],instruction:"분류"}'
    result = checked(branch + ' ' + operator + ' ' + branch)
    assert result['preflight']['declared_ai_visits_upper_bound'] == 2


def test_try_finally_does_not_use_old_outer_limit():
    result = checked('$n=1\n[try]{$n=3}[finally]{'
                     '[table:each]{items:' + ROWS + ',limit:$n}{[$it] >> ' + AI + '}}')
    assert result['preflight']['declared_ai_visits_upper_bound'] is None
    assert 'each_input_limit' not in rules(result)


def test_ai_detection_reads_dictionary_not_content_action_names():
    steps, _ = parse_with_vars('[repeat:3]{[custom:judge]{items:' + ROWS + '}}')
    result = analyze(steps, lambda n, a: {'ai_call': True, 'flow': {'accepts': 'items'}}, lambda a: None)
    assert result['declared_ai_visits_upper_bound'] == 3
    assert result['issues'][0]['rule'] == 'repeated_ai_batch'


def test_missing_function_and_action_are_not_free():
    steps, _ = parse_with_vars('[fn:missing]\n[custom:missing]')
    result = analyze(steps, lambda n, a: None, lambda a: None)
    assert result['status'] == 'partial'
    assert result['declared_ai_visits_upper_bound'] is None


def test_analysis_budget_and_bounded_diagnostics(monkeypatch):
    import ibl_preflight
    monkeypatch.setattr(ibl_preflight, 'MAX_STEPS', 5)
    steps, _ = parse_with_vars('\n'.join([AI] * 10))
    result = analyze(steps, tc._action_def, lambda a: None)
    assert result['declared_ai_visits_upper_bound'] is None
    assert len(result['ai_sites']) == 5


def test_runtime_envelope_items_count_is_known():
    result = checked('$a={items:' + ROWS + '}\n$a >> [table:each]{limit:1}'
                     '{[$it] >> ' + AI + '}')
    assert rules(result)['each_input_limit']['facts']['input_rows'] == 3


def test_literal_dollar_data_does_not_bind_a_variable():
    from ibl_code_ir import Literal
    from ibl_preflight import _Plan
    plan = _Plan(tc._action_def, lambda a: None)
    fact = plan.value([{'x': Literal('$it.x')}, {'x': Literal('$a')}], {}, {})
    assert fact.rows == 2 and not fact.dependencies


def test_analysis_failure_keeps_existing_type_errors(monkeypatch):
    import ibl_preflight
    monkeypatch.setattr(ibl_preflight._Plan, 'run', lambda *a, **k: 1 / 0)
    result = tc.typecheck_code('[self:write]{path:"a",content:"b"} >> [table:select]{columns:["x"]}')
    assert result['ok'] is False
    assert result['preflight']['status'] == 'abstained'
    assert any(i['severity'] == 'error' for i in result['issues'])


def test_check_true_exposes_plan_without_execution(monkeypatch, tmp_path):
    import ibl_engine
    import system_tools_ibl as unified
    import thread_context
    import workflow_engine

    def forbidden(*args, **kwargs):
        pytest.fail('정적 검사에서 실행기를 호출했습니다')

    monkeypatch.setattr(ibl_engine, 'execute_ibl', forbidden)
    monkeypatch.setattr(workflow_engine, 'execute_pipeline', forbidden)
    monkeypatch.setattr(unified, '_ibl_debug_log', lambda *args: None)
    snapshot = thread_context.snapshot()
    thread_context.clear_all_context()
    try:
        result = json.loads(unified._execute_ibl_unified_impl(
            {'code': ROWS + ' >> [table:each]{limit:2}{[$it] >> ' + AI + '}', 'check': True},
            str(tmp_path)))
    finally:
        thread_context.restore(snapshot)
    assert result['preflight']['declared_ai_visits_upper_bound'] == 2
    assert 'each_input_limit' in rules(result)


def test_execution_warning_summary_preserves_rule_and_evidence():
    from system_tools_ibl import _attach_precheck
    result = checked(ROWS + ' >> [table:each]{limit:1}{[$it] >> ' + AI + '}')
    output = {'success': True}
    _attach_precheck(output, result)
    warning = output['precheck_warnings'][0]
    assert warning['rule'] == 'each_input_limit'
    assert warning['facts']['omitted_rows'] == 2


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-v']))
