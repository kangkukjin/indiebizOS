"""Conditional value types and exceptional/return continuation regressions."""
import boot_paths  # noqa: F401

import pytest

from ibl_v2_adapters import Adapter
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime
from ibl_v2_types import NUMBER, TEXT, BOOL, join


def run(code, inputs=None, registry=None):
    plan = compile_program(code, registry, inputs)
    return plan, Runtime(plan, inputs).run()


@pytest.mark.parametrize('value', [10, '20', True])
@pytest.mark.parametrize('context', ['if', 'case', 'each', 'function'])
def test_scalar_alternatives_interpolate_in_all_value_contexts(value, context):
    codes = {
        'if': '[if:$choose]{$x=$v}[else]{$x="대기"}; return f"값 ${x}"',
        'case': '[case:$choose]{[when:true]{$x=$v}[else]{$x="대기"}}; return f"값 ${x}"',
        'each': '[$v,"대기"] >> [table:each]{return f"값 ${it}"}',
        'function': '[def:f]($x){return f"값 ${x}"}; [$v,"대기"] >> [table:each]{[fn:f]{x:$it}}',
    }
    label = '값 ' + ('true' if value is True else str(value))
    expected = [label, '값 대기'] if context in ('each', 'function') else label
    plan, result = run(codes[context], {'v': value, 'choose': True})
    assert not plan.issues, plan.report()
    assert result['success'] and result['value'] == expected, result


@pytest.mark.parametrize('choose,expected', [(True, '가족'), (False, '소')])
def test_index_distributes_over_list_and_text(choose, expected):
    plan, result = run('[if:$choose]{$x=["가족"]}[else]{$x="소식"}; return $x[0]', {'choose': choose})
    assert not plan.issues, plan.report()
    assert result['success'] and result['value'] == expected, result


@pytest.mark.parametrize('key,expected', [('title', '가족'), ('count', 2)])
def test_dynamic_record_key_has_a_runtime_field_check(key, expected):
    plan, result = run('return {title:"가족",count:2}[$key]', {'key': key})
    assert not plan.issues and plan.guards, plan.report()
    assert result['success'] and result['value'] == expected, result


def test_dynamic_missing_record_key_preserves_runtime_failure():
    plan, result = run('return {title:"가족"}[$key]', {'key': 'absent'})
    assert not plan.issues and plan.guards, plan.report()
    assert not result['success'] and result['diagnostic']['code'] == 'MISSING_FIELD'


@pytest.mark.parametrize('code,error', [
    ('[if:true]{$x=[]}[else]{$x="제목"}; return f"${x}"', 'FORMAT_TYPE'),
    ('[if:true]{$x=null}[else]{$x=10}; return f"${x}"', 'FORMAT_TYPE'),
    ('[if:true]{$x=10}[else]{$x="제목"}; return $x[0]', 'FIELD_TYPE'),
    ('[if:true]{$x=[]}[else]{$x="제목"}; return $x.name', 'FIELD_TYPE'),
    ('[if:true]{$x=[1]}[else]{$x="제목"}; return $x[false]', 'TYPE'),
])
def test_unsupported_alternatives_are_still_rejected(code, error):
    plan, result = run(code)
    assert error in {i['code'] for i in plan.issues}, plan.report()
    assert not result['executed']


@pytest.mark.parametrize('left,right,expected', [
    ('[1]', '2', [1, 1]), ('"가"', '2', '가가'),
    ('2', '"3"', 4),
])
def test_dynamic_plus_can_use_supported_alternatives(left, right, expected):
    plan, result = run(f'[if:$choose]{{$x={left}}}[else]{{$x={right}}}; return $x+$x', {'choose': True})
    assert not plan.issues, plan.report()
    assert result['success'] and result['value'] == expected, result


def test_union_join_is_flat_idempotent_and_deterministic():
    joined = join(join(TEXT, NUMBER), BOOL)
    assert join(joined, TEXT) == joined
    assert join(TEXT, join(BOOL, NUMBER)) == joined
    assert 'Type(' not in str(joined)


@pytest.mark.parametrize('body', [
    'return {id:"a"}',
    '[if:$choose]{return {id:"a"}}[else]{return {id:"b"}}',
    '[case:$choose]{[when:true]{return {id:"a"}}[else]{return {id:"b"}}}',
    '[try]{return {id:"a"}}[catch]{return {id:"b"}}[finally]{1}',
    '[repeat:1]{return {id:"a"}}',
    '[repeat:until true]{return {id:"a"}}',
])
def test_unreachable_tail_does_not_contaminate_function_result(body):
    code = '[def:f]($choose){'+body+'; return "종료"}; $r=[fn:f]{choose:true}; return $r.id'
    plan, result = run(code)
    assert not plan.issues, plan.report()
    assert result['success'] and result['value'] == 'a', result
    assert plan.result_type.kind == 'Text'


@pytest.mark.parametrize('wrapper', [
    '[def:f](){{BODY}}; [fn:f]{}',
    '[1] >> [table:each]{{BODY}}',
    '[if:true]{{BODY}} & 2',
    '{BODY}',
])
def test_dead_tail_return_types_do_not_leak_across_frames(wrapper):
    code = wrapper.replace('{BODY}', 'return 7; return "dead"')
    plan, result = run(code)
    assert not plan.issues, plan.report()
    assert 'Text' not in str(plan.result_type), plan.report()
    assert result['success'], result


@pytest.mark.parametrize('tail,error', [
    ('return $missing', 'UNBOUND'),
    ('[try]{1}[finally]{return 2}', 'FINALLY_RETURN'),
    ('$i=2', 'READONLY'),
])
def test_unreachable_source_still_gets_static_safety_checks(tail, error):
    plan, result = run('return 7; '+tail)
    assert error in {i['code'] for i in plan.issues}, plan.report()
    assert not result['executed']


@pytest.mark.parametrize('body', [
    '$x={score:70}; 1/0',
    '[if:true]{$x={score:70}}; 1/0',
    '[case:1]{[when:1]{$x={score:70}}}; 1/0',
    '[repeat:1]{$x={score:70}}; 1/0',
    '[try]{$x={score:70}}[finally]{1/0}',
])
def test_catch_reads_current_shared_binding_not_entry_type(body):
    plan, result = run('$x=0; [try]{'+body+'}[catch]{return $x.score}')
    assert not plan.issues, plan.report()
    assert plan.guards
    assert result['success'] and result['value'] == 70, result


@pytest.mark.parametrize('fail_first', [True, False])
def test_catch_state_covers_both_sides_of_assignment(fail_first):
    code = '$x={score:1}; [try]{[if:$early]{1/0}; $x={score:2}; 1/0}[catch]{return $x.score}'
    plan, result = run(code, {'early': fail_first})
    assert not plan.issues, plan.report()
    assert result['success'] and result['value'] == (1 if fail_first else 2), result


def test_invalid_rebound_value_fails_at_runtime_not_as_a_false_success():
    plan, result = run('$x={score:1}; [try]{$x=0; 1/0}[catch]{return $x.score}')
    assert not plan.issues and plan.guards, plan.report()
    assert not result['success'] and result['diagnostic']['code'] == 'FIELD_TYPE'


def test_catch_cannot_claim_a_new_binding_was_definitely_assigned():
    plan, result = run('[try]{1/0; $new=2}[catch]{return $new}')
    assert 'UNBOUND' in {i['code'] for i in plan.issues}
    assert not result['executed']


@pytest.mark.parametrize('body', [
    '$x=0; [try]{$x={score:70}; 1/0}',
    '$x={score:70}; [try]{1/0; $x=0}',
    '$x={score:70}; [try]{1/0}[catch]{1/0; $x=0}',
])
def test_finally_checks_partial_progress_of_rebound_values(body):
    code = body + '[finally]{[fixture:save]{value:$x.score}}'
    seen = []
    registry = {'fixture:save': Adapter({'version': 1, 'params': {'value': 'Number'},
                 'result': 'Number', 'effects': ['write_external']},
                 lambda rt, args: seen.append(args['value']) or args['value'])}
    plan, result = run(code, registry=registry)
    assert not plan.issues, plan.report()
    assert seen == [70]
    assert not result['success'] and result['diagnostic']['code'] != 'CLEANUP'


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
