"""Independent effect/result dependency and repair-lineage counterexamples."""
import boot_paths  # noqa: F401
import pytest

from test_ibl_v2_repair import execute  # noqa: F401 -- isolated effect fixture
from test_ibl_v2_component import component_catalog  # noqa: F401


def repair(run, first, code):
    handle = {'run_id': first['resume']['run_id']}
    checked = run(code, check=True, repair=handle)
    assert checked['ok'], checked
    return run(code, repair={**handle, 'plan_hash': checked['repair']['plan_hash']})


@pytest.mark.parametrize('depth', [0, 2, 5])
def test_internal_result_edit_preserves_completed_call_and_multiple_repairs(execute, depth):
    run, calls, _ = execute
    def code(tail):
        definitions = '[def:step]($n){$sent=[t:send]{id:"delivery"};' + tail + '};'
        previous = 'step'
        for i in range(depth):
            name = 'wrapper' + str(i)
            definitions += f'[def:{name}]($n){{return [fn:{previous}]{{n:$n}}}};'
            previous = name
        return definitions + f'return [fn:{previous}]{{n:$n}}'
    first = run(code('return 10/$n'))
    assert not first['success'] and calls == ['delivery'], first
    fixed = code('$denominator=$n+1; return {answer:10/$denominator,receipt:$sent}')
    out = repair(run, first, fixed)
    assert out['success'] and out['value'] == {'answer': 10, 'receipt': 1}, out
    next_code = code('$denominator=$n+2; return {answer:10/$denominator,receipt:$sent}')
    out = repair(run, out, next_code)
    assert out['success'] and out['value'] == {'answer': 5, 'receipt': 1}, out
    assert calls == ['delivery']


@pytest.mark.parametrize('use', [
    '$sent=[t:send]{id:$result};return 1/$n',
    '[if:$result=="delivery"]{[t:send]{id:"second"}};return 1/$n',
    '$sent=[t:send]{id:"second"};return 1/$n',
])
def test_internal_return_used_by_later_effect_or_its_reachability_stays_fixed(execute, use):
    run, calls, _ = execute
    code = ('[def:step](){[t:send]{id:"first"};return "delivery"};'
            '$result=[fn:step]{};' + use)
    first = run(code)
    assert not first['success'] and len(calls) == 2, first
    changed = code.replace('return "delivery"', 'return "other"').replace('1/$n', '1')
    out = run(changed, check=True, repair=first['resume'])
    assert not out.get('ok') and out['diagnostic']['code'] == 'REPAIR_UNSUPPORTED', out
    assert len(calls) == 2


def test_higher_order_callback_result_used_by_effect_stays_fixed(execute):
    run, calls, _ = execute
    code = ('[def:target](){return "delivery"};'
            '[def:publish]($choose){return [t:send]{id:$choose{}}};'
            '$done=[fn:publish]{choose:&[fn:target]};return 1/$n')
    first = run(code)
    changed = code.replace('return "delivery"', 'return "other"').replace('1/$n', '1')
    out = run(changed, check=True, repair=first['resume'])
    assert not out.get('ok') and calls == ['delivery'], out


def test_lexical_callback_result_only_tail_can_change(execute):
    run, calls, _ = execute
    code = ('[def:step]($x){[t:send]{id:"delivery"};return 10/$x};'
            '$worker=($x)=>[fn:step]{x:$x};'
            '[def:apply]($work,$x){return $work{x:$x}};return [fn:apply]{work:$worker,x:$n}')
    first = run(code)
    assert not first['success'] and calls == ['delivery'], first
    out = repair(run, first, code.replace('10/$x', '10/($x+1)'))
    assert out['success'] and out['value'] == 10 and calls == ['delivery'], out


@pytest.mark.parametrize('change', [
    ('id:"delivery"', 'id:"other"'),
    ('return 10/$n', '[t:send]{id:"delivery"};return 1'),
    ('[t:send]{id:"delivery"};', ''),
])
def test_internal_effect_argument_insertion_and_removal_are_not_repaired(execute, change):
    run, calls, _ = execute
    code = '[def:step]($n){[t:send]{id:"delivery"};return 10/$n};return [fn:step]{n:$n}'
    first = run(code)
    out = run(code.replace(*change), check=True, repair=first['resume'])
    assert not out.get('ok') and calls == ['delivery'], out


def test_callback_from_record_preserves_captures_and_effect_dependency(execute):
    run, calls, _ = execute
    code = ('[def:step]($id,$x){[t:send]{id:$id};return 10/$x};'
            '$id="delivery";$box={run:($x)=>[fn:step]{id:$id,x:$x}};'
            'return $box.run{x:0}')
    first = run(code)
    assert not first['success'] and calls == ['delivery'], first
    bad = run(code.replace('$id="delivery"', '$id="other"').replace('10/$x', '10/($x+1)'),
              check=True, repair=first['resume'])
    assert not bad.get('ok') and calls == ['delivery'], bad
    out = repair(run, first, code.replace('10/$x', '10/($x+1)'))
    assert out['success'] and out['value'] == 10 and calls == ['delivery'], out


def test_sequential_iteration_keeps_previous_tail_as_next_effect_condition(execute):
    run, calls, _ = execute
    code = ('[def:step]($x){[t:send]{id:"delivery"};return 10/$x};'
            'return [table:each]{items:[0,1]}{return [fn:step]{x:$it}}')
    first = run(code)
    assert not first['success'] and calls == ['delivery'], first
    out = run(code.replace('10/$x', '10/($x+1)'), check=True, repair=first['resume'])
    assert not out.get('ok') and calls == ['delivery'], out


def test_old_frontier_cannot_silently_gain_new_repair_authority():
    from ibl_v2_repair_graph import mapping
    from ibl_v2_ir import Fault
    with pytest.raises(Fault, match='효과'):
        mapping({'protocol': 'ibl-repair-frontier/1'}, {'protocol': 'ibl-repair-frontier/2'})


def test_stored_effectful_revision_repairs_inside_three_composed_abilities(
        tmp_path, monkeypatch, component_catalog):
    from function_library import register, definitions
    from ibl_v2_adapters import Adapter
    from ibl_v2_compile import compile_program
    from ibl_v2_entry import handle_request
    calls = []
    registry = {'delivery:publish': Adapter(
        {'version': 1, 'params': {'id': 'Text'}, 'result': 'Number', 'effects': ['write_external']},
        lambda rt, args: calls.append(args['id']) or 7)}
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **kw: registry)
    monkeypatch.setattr('tool_batch.prepared_plan', lambda *a: None)
    source = '[def:publish]($id,$n){$receipt=[delivery:publish]{id:$id};return {receipt:$receipt,ratio:10/$n}}'
    original = register('publish', '#!ibl edition=2\n' + source, edition=2)
    register('report', '#!ibl edition=2\n[def:report]($id,$n){return [fn:publish]{id:$id,n:$n}}', edition=2)
    register('review', '#!ibl edition=2\n[def:review]($id,$n){return {report:[fn:report]{id:$id,n:$n}}}', edition=2)
    assert calls == []
    request = {'edition': 2, 'code': 'return [fn:review]{id:"document",n:$n}', 'inputs': {'n': 0}}
    first = handle_request(request, str(tmp_path))
    assert not first['success'] and calls == ['document'], first
    changed = register('publish', '#!ibl edition=2\n' + source.replace('10/$n', '10/($n+1)'),
                       edition=2, function_id=original['function_id'], expected_revision=original['revision'])
    assert changed['revision'] != original['revision'] and calls == ['document']
    plan = compile_program(request['code'], registry, inputs=request['inputs'], definitions=definitions())
    updated = {**request, 'function_refs': plan.dependencies['function_refs'], 'repair': first['resume']}
    checked = handle_request({**updated, 'check': True}, str(tmp_path))
    assert checked['ok'] and calls == ['document'], checked
    final = handle_request({**updated, 'repair': {**first['resume'], 'plan_hash': checked['repair']['plan_hash']}}, str(tmp_path))
    assert final['success'] and final['value'] == {'report': {'receipt': 7, 'ratio': 10}}, final
    resumed = handle_request({**request, 'resume': first['resume']}, str(tmp_path))
    assert resumed['success'] and resumed['value'] == final['value'] and calls == ['document'], resumed


def test_failed_read_observation_replays_through_fixed_recovery_before_inner_tail(
        execute, monkeypatch):
    from ibl_v2_adapters import Adapter
    from ibl_v2_ir import Fault
    run, calls, write = execute
    def read(rt, args):
        calls.append('read')
        raise Fault('SOURCE_UNAVAILABLE', 'temporarily unavailable')
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **kw: {
        't:send': write,
        't:read': Adapter({'version': 1, 'params': {}, 'result': 'Number',
                           'effects': ['read_external']}, read)})
    code = ('[def:step]($n){[try]{[t:read]{}}[catch]{[t:send]{id:"fallback"}};'
            'return 10/$n};return [fn:step]{n:$n}')
    first = run(code)
    assert not first['success'] and calls == ['read', 'fallback'], first
    out = repair(run, first, code.replace('10/$n', '10/($n+1)'))
    assert out['success'] and out['value'] == 10 and calls == ['read', 'fallback'], out


def test_same_definition_cannot_be_edited_when_one_use_feeds_an_effect(execute):
    run, calls, _ = execute
    code = ('[def:step]($id){[t:send]{id:$id};return "delivery"};'
            '$first=[fn:step]{id:"one"};[t:send]{id:$first};'
            '$last=[fn:step]{id:"two"};return 1/$n')
    first = run(code)
    assert calls == ['one', 'delivery', 'two'], first
    out = run(code.replace('return "delivery"', 'return "other"').replace('1/$n', '1'),
              check=True, repair=first['resume'])
    assert not out.get('ok') and calls == ['one', 'delivery', 'two'], out


def test_default_evaluation_before_effect_stays_fixed_even_when_unused(execute):
    run, calls, _ = execute
    code = '[def:step]($n,$unused=1){[t:send]{id:"delivery"};return 10/$n};return [fn:step]{n:$n}'
    first = run(code)
    assert not first['success'] and calls == ['delivery'], first
    out = run(code.replace('$unused=1', '$unused=2').replace('10/$n', '10/($n+1)'),
              check=True, repair=first['resume'])
    assert not out.get('ok') and calls == ['delivery'], out


@pytest.mark.parametrize('container', ['index', 'each'])
def test_unresolved_callable_container_retains_body_effect_intent(execute, container):
    run, calls, _ = execute
    workers = '$workers=[($id)=>[t:send]{id:$id}];'
    use = ('$sent=$workers[$n]{id:"delivery"};' if container == 'index' else
           '$sent=[table:each]{items:$workers}{return $it{id:"delivery"}};')
    code = workers + use + 'return 1/$n'
    first = run(code)
    assert not first['success'] and calls == ['delivery'], first
    changed = code.replace('[t:send]{id:$id}', '[t:send]{id:"other"}').replace('return 1/$n', 'return 1')
    out = run(changed, check=True, repair=first['resume'])
    assert not out.get('ok') and calls == ['delivery'], out


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
