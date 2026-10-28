"""Stored repeat state and completion between effectful iterations."""
import boot_paths  # noqa: F401
import pytest

from ibl_v2_compile import Compiler, compile_program
from ibl_v2_runtime import Runtime
from ibl_v2_adapters import Adapter
from test_ibl_v2_component import component_catalog  # noqa: F401
from test_ibl_v2_repair import execute  # noqa: F401
from test_ibl_v2_repair_graph import repair
from test_ibl_v2_semantic import abilities  # noqa: F401


@pytest.mark.parametrize('body,expected', [
    ('$sum=0;[repeat:4]{$sum=$sum+$i};return $sum', 6),
    ('$x={total:0,tag:"kept"};[repeat:3]{$x={**$x,total:$x.total+1}};return $x', {'total': 3, 'tag': 'kept'}),
    ('$x=0;[repeat:until $x>=3]{$x=$x+1};return $x', 3),
    ('$x=0;[repeat:while $i<3]{$x=$x+1};return $x', 3),
    ('$x=7;[repeat:0]{$x="bad"};return $x', 7),
    ('[repeat:1]{$x={new:7}};return $x.new', 7),
    ('[repeat:until $x>0]{$x=7};return $x', 7),
    ('$sum=0;[repeat:2]{[repeat:2]{$sum=$sum+$i};$sum=$sum+$i};return $sum', 3),
    ('[repeat:3]{[if:$i==1]{return 7}};return 8', 7),
    ('[try]{[repeat:3]{return 7}}[finally]{};return 8', 7),
    ('[if:true]{};$x=0;[repeat:3]{$x=$x+1};return $x', 3),
    ('$x=0;[repeat:3]{[try]{1/$n}[catch]{$x=$x+1}};return $x', 3),
])
def test_repeat_state_survives_storage_and_two_promotions(component_catalog, monkeypatch, body, expected):
    from function_library import register, definitions
    source = '[def:step]($n){' + body + '}'
    direct = compile_program(source + ';return [fn:step]{n:$n}', {}, inputs={'n': 0})
    assert not direct.issues, direct.report()
    result = Runtime(direct, inputs={'n': 0}).run()
    assert result['success'] and result['value'] == expected, result
    register('step', '#!ibl edition=2\n' + source, edition=2)
    register('report', '#!ibl edition=2\n[def:report]($n){return {value:[fn:step]{n:$n}}}', edition=2)
    library = definitions()
    with monkeypatch.context() as boundary:
        boundary.setattr('ibl_v2_store.definitions', lambda: library.interfaces_only())
        review = register('review', '#!ibl edition=2\n[def:review]($n){return [fn:report]{n:$n}}', edition=2)
    library = definitions()
    assert set(library.interfaces) == {'step', 'report', 'review'}, library.interface_limits
    with monkeypatch.context() as boundary:
        boundary.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body read'))
        plan = compile_program('return [fn:review]{n:$n}', {}, inputs={'n': 0}, definitions=library.interfaces_only())
        assert not plan.issues, plan.report()
    plan.definitions = library
    result = Runtime(plan, inputs={'n': 0}).run()
    assert result['success'] and result['value'] == {'value': expected}, result


@pytest.mark.parametrize('mode', ['3', 'while $i<3', 'until $i>=2'])
def test_repeat_repair_preserves_completed_rounds_and_continues_original_rounds(execute, mode):
    run, calls, _ = execute
    code = ('[def:step]($n){$sum=0;[repeat:' + mode + ']{'
            '[t:send]{id:text($i)};$sum=$sum+10/(1-$i+$n)};return $sum};return [fn:step]{n:$n}')
    first = run(code)
    assert not first['success'] and calls == ['0', '1'], first
    out = repair(run, first, code.replace('1-$i+$n', '3-$i+$n'))
    assert out['success'] and calls == ['0', '1', '2'], out
    assert float(out['value']) == pytest.approx(10/3 + 5 + 10)
    revised = code.replace('1-$i+$n', '4-$i+$n')
    out = repair(run, out, revised)
    assert out['success'] and calls == ['0', '1', '2'], out
    again = run(revised, resume=first['resume'])
    assert again['success'] and again['value'] == out['value'] and calls == ['0', '1', '2'], again


@pytest.mark.parametrize('parallel', [1, 2])
def test_each_completion_between_rounds_and_batches_is_not_result_identity(execute, parallel):
    run, calls, _ = execute
    code = ('[def:step]($id,$n){[t:send]{id:text($id)};return 10/(1-$id+$n)};'
            'return [table:each]{items:[0,1,2],parallel:' + str(parallel) + '}{return [fn:step]{id:$it,n:$n}}')
    first = run(code)
    assert not first['success'] and sorted(calls) == ['0', '1'], first
    out = repair(run, first, code.replace('1-$id+$n', '3-$id+$n'))
    assert out['success'] and sorted(calls) == ['0', '1', '2'], out
    assert [float(v) for v in out['value']] == pytest.approx([10/3, 5, 10])


@pytest.mark.parametrize('change', [
    ('[repeat:3]', '[repeat:4]'),
    ('text($state)', 'text($state+1)'),
    ('$state=$state+1', '$state=$state+2'),
    ('[if:$i==2]', '[if:$i==1]'),
])
def test_iteration_selection_and_loop_carried_effect_state_remain_fixed(execute, change):
    run, calls, _ = execute
    code = ('$state=0;[repeat:3]{[if:$i==2]{return 1/$n};'
            '[t:send]{id:text($state)};$unused=text($i);$state=$state+1};return 0')
    first = run(code)
    assert not first['success'] and calls == ['0', '1'], first
    changed = code.replace(*change).replace('1/$n', '1/($n+1)')
    out = run(changed, check=True, repair=first['resume'])
    assert not out.get('ok') and calls == ['0', '1'], out


def test_state_flow_across_multiple_rounds_cannot_change_later_effect(execute):
    run, calls, _ = execute
    code = ('$a="first";$b="second";[repeat:3]{[t:send]{id:$a};$a=$b;$b="third"};return 1/$n')
    first = run(code)
    assert calls == ['first', 'second', 'third'], first
    out = run(code.replace('$b="third"', '$b="changed"').replace('1/$n', '1'), check=True, repair=first['resume'])
    assert not out.get('ok') and calls == ['first', 'second', 'third'], out


def test_loop_completed_value_still_gates_effect_after_loop(execute):
    run, calls, _ = execute
    code = ('$x=0;[repeat:3]{[t:send]{id:text($i)};$x=$x+1};[t:send]{id:text($x)};return 1/$n')
    first = run(code)
    assert calls == ['0', '1', '2', '3'], first
    out = run(code.replace('$x=$x+1', '$x=$x+2').replace('1/$n', '1'), check=True, repair=first['resume'])
    assert not out.get('ok') and calls == ['0', '1', '2', '3'], out


def test_saved_repeat_vertical_path_new_provider_and_internal_revision(abilities, monkeypatch, tmp_path):
    from function_library import register, definitions
    from ibl_v2_store import Library
    from ibl_v2_entry import handle_request
    from test_ibl_v2_semantic import NORMALIZE
    from ibl_v2_types import NUMBER
    reg, calls, scripts = abilities
    register('normalizer', '#!ibl edition=2\n' + NORMALIZE, edition=2)
    source = '''[def:rounds]($sources,$read,$normalize,$policy,$n){
$all=[];
[repeat:len($sources)]{
$raw=$read{source:$sources[$i]};
$rows=$normalize{data:$raw.items};
$selected=[table:filter]{items:$rows,where:$policy};
$sent=[probe:publish]{items:$selected};
$ratio=10/(1-$i+$n);
$all=$all+[{source:$raw.origin,rows:$selected,receipt:$sent,ratio:$ratio}]
};return $all}'''
    original = register('rounds', '#!ibl edition=2\n' + source, edition=2)
    raw_get = Library.__getitem__
    def no_body(lib, name):
        if name in lib.interfaces:
            pytest.fail('authoring read a lower body: ' + name)
        return raw_get(lib, name)
    with monkeypatch.context() as boundary:
        boundary.setattr(Library, '__getitem__', no_body)
        report = register('report', '#!ibl edition=2\n[def:report]($sources,$read,$normalize,$policy,$n){'
                 'return {rounds:[fn:rounds]{sources:$sources,read:$read,normalize:$normalize,policy:$policy,n:$n}}}', edition=2)
        review = register('review', '#!ibl edition=2\n[def:review]($sources,$read,$normalize,$policy,$n){'
                 'return [fn:report]{sources:$sources,read:$read,normalize:$normalize,policy:$policy,n:$n}}', edition=2)
    assert calls == []
    query = ('return [fn:review]{sources:["a","b","c"],read:&[probe:read],'
             'normalize:&[fn:normalizer],policy:($r)=>$r.score>3,n:$n}')
    library = definitions()
    assert 'rounds' in library.interfaces, library.interface_limits
    with monkeypatch.context() as boundary:
        boundary.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body read'))
        plan = compile_program(query, reg, inputs={'n': 0}, definitions=library.interfaces_only())
        assert not plan.issues, plan.report()
        rows = dict(dict(plan.result_type.fields)['rounds'].item.fields)['rows']
        assert dict(rows.item.fields)['score'] == NUMBER, rows
        assert plan.effects - {'pure'} == {'read_external', 'write_external'}
    assert calls == []
    request = {'edition': 2, 'code': query, 'inputs': {'n': 0}}
    first = handle_request(request, str(tmp_path))
    assert not first['success'] and [c[0] for c in calls].count('publish') == 2, first
    fixed_source = source.replace('1-$i+$n', '3-$i+$n')
    revised = register('rounds', '#!ibl edition=2\n' + fixed_source, edition=2,
                       function_id=original['function_id'], expected_revision=original['revision'])
    assert revised['revision'] != original['revision']
    plan = compile_program(query, reg, inputs={'n': 0}, definitions=definitions())
    update = {**request, 'function_refs': plan.dependencies['function_refs'], 'repair': first['resume']}
    checked = handle_request({**update, 'check': True}, str(tmp_path))
    assert checked['ok'], checked
    result = handle_request({**update, 'repair': {**first['resume'], 'plan_hash': checked['repair']['plan_hash']}}, str(tmp_path))
    assert result['success'] and [c[0] for c in calls].count('publish') == 3, result
    assert [c for c in calls if c[0] == 'read'] == [('read', 'a'), ('read', 'b'), ('read', 'c')]
    assert [r['source'] for r in result['value']['rounds']] == ['a', 'b', 'c']
    assert [r['rows'][0]['score'] for r in result['value']['rounds']] == [5, 5, 5]
    assert result['component_completion']['status'] == 'satisfied', result
    again = handle_request({**request, 'resume': first['resume']}, str(tmp_path))
    assert again['success'] and again['value'] == result['value'], again
    assert [c[0] for c in calls].count('publish') == 3

    # A changed immutable dependency invalidates the old certificate. Publish
    # the unchanged upper definitions again against the new lower interface.
    with monkeypatch.context() as boundary:
        boundary.setattr(Library, '__getitem__', no_body)
        for name, saved in [('report', report), ('review', review)]:
            register(name, '#!ibl edition=2\n' + raw_get(library, name), edition=2,
                     function_id=saved['function_id'], expected_revision=saved['revision'])

    # A requirement and two providers introduced after storing the composition.
    fields = {'id': 'Text', 'score': 'Number', 'source': 'Text', 'bytes': 'Number', '$closed': True}
    scripts['later'] = {**scripts['normalize'], 'callable_contract': {
        **scripts['normalize']['callable_contract'], 'params': {'data': {'$list': fields}},
        'result': {'$list': fields}, 'completion': []}}
    reg['files:scan'] = Adapter({'version': 1, 'params': {'source': 'Text'},
        'result': {'items': {'$list': fields}, 'origin': 'Text'}, 'effects': ['read_external']},
        lambda rt, a: {'items': [{'id': 'f', 'score': 9, 'source': a['source'], 'bytes': 20}], 'origin': a['source']})
    register('later_normalizer', '#!ibl edition=2\n[def:later_normalizer]($data){'
             'return [probe:python]{id:"later",args:{data:$data}}}', edition=2)
    new_query = query.replace('&[probe:read]', '&[files:scan]').replace('&[fn:normalizer]', '&[fn:later_normalizer]').replace('$r.score>3', '$r.bytes>10')
    library = definitions()
    with monkeypatch.context() as boundary:
        boundary.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body read'))
        new_plan = compile_program(new_query, reg, inputs={'n': 0}, definitions=library.interfaces_only())
        assert not new_plan.issues, new_plan.report()
        rows = dict(dict(new_plan.result_type.fields)['rounds'].item.fields)['rows']
        assert dict(rows.item.fields)['bytes'] == NUMBER
        bad = compile_program(new_query.replace('$r.bytes', '$r.absent'), reg, inputs={'n': 0}, definitions=library.interfaces_only())
        assert any(i['code'] == 'MISSING_FIELD' for i in bad.issues), bad.report()
    new_plan.definitions = library
    new_result = Runtime(new_plan, inputs={'n': 0}).run()
    assert new_result['success'], new_result
    assert [r['rows'][0]['bytes'] for r in new_result['value']['rounds']] == [20, 20, 20]
    assert ('script', 'later') in calls


def test_nested_repeat_function_tail_uses_iteration_coordinates(execute):
    run, calls, _ = execute
    code = ('[def:step]($round,$n){[t:send]{id:"same"};$value=10/(2-$round+$n);return $value};'
            '$round=0;$sum=0;[repeat:2]{[repeat:2]{'
            '$sum=$sum+[fn:step]{round:$round,n:$n};$round=$round+1}};return $sum')
    first = run(code)
    assert not first['success'] and len(calls) == 3, first
    # Here result completion also precedes the counter used by the next call;
    # the counter update itself must remain unchanged.
    out = repair(run, first, code.replace('2-$round+$n', '4-$round+$n'))
    assert out['success'] and len(calls) == 4, out
    assert float(out['value']) == pytest.approx(2.5 + 10/3 + 5 + 10)


def test_fixed_tail_must_really_complete_before_new_round(execute):
    run, calls, _ = execute
    code = '[repeat:3]{[t:send]{id:text($i)};10/($n+$i)}'
    first = run(code)
    assert not first['success'] and calls == ['0'], first
    still_failed = repair(run, first, code.replace('10/', '20/'))
    assert not still_failed['success'] and calls == ['0'], still_failed
    out = repair(run, still_failed, code.replace('$n+$i', '$n+$i+1'))
    assert out['success'] and calls == ['0', '1', '2'], out


@pytest.mark.parametrize('mode', ['while $state<3', 'until $state>=3'])
def test_state_selecting_later_rounds_is_not_a_result_only_edit(execute, mode):
    run, calls, _ = execute
    code = '$state=0;[repeat:' + mode + ']{[t:send]{id:text($i)};$state=$state+1};return 1/$n'
    first = run(code)
    assert calls == ['0', '1', '2'], first
    out = run(code.replace('$state=$state+1', '$state=$state+2').replace('1/$n', '1'), check=True, repair=first['resume'])
    assert not out.get('ok') and calls == ['0', '1', '2'], out


def test_dynamic_each_items_and_callback_completion(execute):
    run, calls, _ = execute
    code = ('[def:step]($id,$n){[t:send]{id:text($id)};$x=10/(1-$id+$n);return $x};'
            'return [table:each]{items:$rows}{return [fn:step]{id:$it,n:$n}}')
    inputs = {'n': 0, 'rows': [0, 1, 2]}
    first = run(code, inputs=inputs)
    assert not first['success'] and calls == ['0', '1'], first
    fixed = code.replace('1-$id+$n', '3-$id+$n')
    checked = run(fixed, inputs=inputs, check=True, repair=first['resume'])
    assert checked['ok'], checked
    out = run(fixed, inputs=inputs, repair={**first['resume'], 'plan_hash': checked['repair']['plan_hash']})
    assert out['success'] and calls == ['0', '1', '2'], out


def test_bodyless_repeat_preserves_reference_and_callback_effects(component_catalog, monkeypatch):
    from function_library import register, definitions
    from ibl_v2_types import Type
    register('step', '#!ibl edition=2\n[def:step]($ref,$f){$state=$ref;[repeat:2]{$state=$f($state)};return $state}', edition=2)
    library = definitions().interfaces_only()
    monkeypatch.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body read'))
    plan = compile_program('return [fn:step]{ref:$ref,f:($v)=>$v}', {}, definitions=library,
                           input_types={'ref': Type('ForeignRef')}, value_protocols=['ibl-value/1'])
    assert plan.result_type.kind == 'ForeignRef'
    assert any(i['code'] == 'VALUE_PROTOCOL' for i in plan.issues), plan.report()
    reg = {'opaque:step': Adapter({'version': 1, 'params': {'x': 'Number'}, 'result': 'Number', 'effects': ['unknown']},
                                  lambda *a: pytest.fail('check executed a leaf'))}
    plan = compile_program('return [fn:step]{ref:1,f:($x)=>[opaque:step]{x:$x}}', reg, definitions=library)
    assert not plan.issues and 'unknown' in plan.effects, plan.report()


def test_repeat_return_and_recovery_do_not_fulfill_lower_completion(component_catalog, monkeypatch):
    from function_library import register, definitions
    from test_ibl_v2_component import definition
    reg = {'t:read': Adapter({'version': 1, 'params': {'id': 'Text'}, 'result': 'Number', 'effects': ['read_external']},
                            lambda *a: 0)}
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **k: reg)
    register('checked', '#!ibl edition=2\n' + definition('checked'), edition=2)
    register('rounds', '#!ibl edition=2\n[def:rounds]($id){[repeat:2]{[fn:checked]{id:$id}};return 7}', edition=2)
    library = definitions()
    with monkeypatch.context() as boundary:
        boundary.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body read'))
        plan = compile_program('return [fn:rounds]{id:"document"}', reg, definitions=library.interfaces_only())
        assert not plan.issues, plan.report()
    plan.definitions = library
    out = Runtime(plan).run()
    assert out['success'] and out['value'] == 7, out
    assert out['component_completion']['status'] != 'satisfied' and out['component_completion']['instances'], out


@pytest.mark.parametrize('count', [0, 1, 3])
def test_repeat_source_and_interface_agree_on_effects_and_empty_state(component_catalog, monkeypatch, count):
    from function_library import register, definitions
    calls = []
    reg = {'t:write': Adapter({'version': 1, 'params': {}, 'result': 'Number', 'effects': ['write_external']},
                             lambda *a: calls.append('write') or 1)}
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **k: reg)
    source = '[def:step](){[repeat:' + str(count) + ']{[t:write]{}};return 7}'
    direct = compile_program(source + ';return [fn:step]{}', reg)
    register('step', '#!ibl edition=2\n' + source, edition=2)
    with monkeypatch.context() as boundary:
        boundary.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body read'))
        stored = compile_program('return [fn:step]{}', reg, definitions=definitions().interfaces_only())
    assert not direct.issues and not stored.issues, (direct.report(), stored.report())
    expected = {'write_external'} if count else set()
    assert direct.effects - {'pure'} == stored.effects - {'pure'} == expected
    assert calls == []
    stored.definitions = definitions()
    out = Runtime(stored).run()
    assert out['success'] and out['value'] == 7 and len(calls) == count, out


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
