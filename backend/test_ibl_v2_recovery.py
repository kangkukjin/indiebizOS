"""Stored failure/recovery relations and their effect-preserving repair boundary."""
import boot_paths  # noqa: F401
import pytest

from ibl_v2_compile import Compiler, compile_program
from ibl_v2_runtime import Runtime
from ibl_v2_adapters import Adapter
from ibl_v2_ir import Fault
from test_ibl_v2_component import component_catalog  # noqa: F401
from test_ibl_v2_repair import execute  # noqa: F401
from test_ibl_v2_repair_graph import repair
from test_ibl_v2_semantic import abilities, save_layers  # noqa: F401


@pytest.mark.parametrize('body,expected', [
    ('return (10/$n) ?? {answer:7}', {'answer': 7}),
    ('[try]{return 10/$n}[catch]{return {answer:7}}', {'answer': 7}),
    ('[try]{10/$n}[catch]{$x={answer:7}};return $x', {'answer': 7}),
    ('$x=1;[try]{$x={answer:7};10/$n}[catch]{return $x}', {'answer': 7}),
    ('$x=1;[try]{$x=7}[finally]{$x=8};return $x', 8),
    ('[try]{[if:$n==0]{return {answer:7}};return 8}[catch]{return 9}', {'answer': 7}),
    ('$x=0;[try]{[try]{10/$n}[catch]{$x=7}}[catch]{$x=8};return $x', 7),
    ('return [try]{10/$n}[catch]{{answer:7}}', {'answer': 7}),
    ('return [try]{[table:each]{items:[1,2]}{return $it}}[catch]{[]}', [1, 2]),
    ('[if:$n==0]{};[try]{1/$n}[catch]{return $error.kind};return "normal"', 'runtime'),
    ('[if:$n==0]{};$v=[try]{$x=7}[catch]{$x=8};return $x', 7),
    ('[try]{[if:$n==0]{[try]{1/$n}[catch]{return $error.kind}};return $n}[catch]{return "outer"}', 'runtime'),
    ('[try]{[if:$n==0]{[try]{1/($n+1)}[catch]{return $error.kind}};return $n}[catch]{return "outer"}', 0),
    ('$x=1;$v=[try]{$x=7;10/$n}[catch]{$x=8;0};return $x', 8),
    ('[try]{10/$n}[catch]{$original=$error;[try]{10/$n}[catch]{$error};return $original==$error}', True),
])
def test_recovery_results_survive_storage_and_two_promotions(component_catalog, monkeypatch, body, expected):
    from function_library import register, definitions
    # The third case assigns in both possible normal paths.
    if body.startswith('[try]{10/$n}'):
        body = '$x={answer:0};' + body
    source = '[def:recover]($n){' + body + '}'
    direct = compile_program(source + ';return [fn:recover]{n:$n}', {}, inputs={'n': 0})
    assert not direct.issues, direct.report()
    original = Runtime(direct, inputs={'n': 0}).run()
    assert original['success'] and original['value'] == expected, original
    register('recover', '#!ibl edition=2\n' + source, edition=2)
    register('report', '#!ibl edition=2\n[def:report]($n){return {value:[fn:recover]{n:$n}}}', edition=2)
    register('review', '#!ibl edition=2\n[def:review]($n){return [fn:report]{n:$n}}', edition=2)
    library = definitions()
    assert set(library.interfaces) == {'recover', 'report', 'review'}, library.interface_limits
    with monkeypatch.context() as boundary:
        boundary.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body read'))
        checked = compile_program('return [fn:review]{n:$n}', {}, inputs={'n': 0},
                                  definitions=library.interfaces_only())
        assert not checked.issues, checked.report()
    checked.definitions = library
    out = Runtime(checked, inputs={'n': 0}).run()
    assert out['success'] and out['value'] == {'value': expected}, out


@pytest.mark.parametrize('form', ['catch', 'fallback', 'no_catch', 'nested', 'callback', 'cleanup'])
def test_internal_recovery_tail_repair_reuses_completed_effect(execute, monkeypatch, form):
    run, calls, write = execute
    def read(rt, args):
        calls.append('read')
        raise Fault('SOURCE_DOWN', 'unavailable')
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **k: {
        't:send': write,
        't:read': Adapter({'version': 1, 'params': {}, 'result': 'Number',
                           'effects': ['read_external']}, read)})
    if form == 'fallback':
        source = ('[def:recover]($n){[t:send]{id:"recovery"};return 10/$n};'
                  '[def:step]($n){return [t:read]{} ?? [fn:recover]{n:$n}};')
    elif form == 'no_catch':
        source = '[def:step]($n){[try]{[t:send]{id:"recovery"};return 10/$n}[finally]{}};'
    elif form == 'cleanup':
        source = '[def:step]($n){[try]{return 10/$n}[finally]{[t:send]{id:"recovery"}}};'
    elif form == 'callback':
        source = ('[def:step]($read,$n){[try]{return $read{}}'
                  '[catch]{[t:send]{id:"recovery"};return 10/$n}};')
    else:
        protected = '[t:read]{}' if form == 'catch' else '[try]{[t:read]{}}[catch]{10/$n}'
        source = '[def:step]($n){[try]{' + protected + '}[catch]{[t:send]{id:"recovery"};return 10/$n}};'
    code = source + ('return [fn:step]{read:&[t:read],n:$n}' if form == 'callback' else 'return [fn:step]{n:$n}')
    first = run(code)
    expected = ['recovery'] if form in ('no_catch', 'cleanup') else ['read', 'recovery']
    assert not first['success'] and calls == expected, first
    # Change only the result of the outer recovery, not the failure selecting it.
    before, after = code.rsplit('return 10/$n', 1)
    fixed = before + 'return 10/($n+1)' + after
    out = repair(run, first, fixed)
    assert out['success'] and out['value'] == 10 and calls == expected, out
    resumed = run(fixed, resume=first['resume'])
    assert resumed['success'] and calls == expected, resumed


@pytest.mark.parametrize('change', [
    ('10/$n', '10/($n+1)'),
    ('id:"recovery"', 'id:"other"'),
    ('return "done"', 'return "different"'),
])
def test_recovery_effect_selection_inputs_and_caller_consumption_remain_fixed(execute, change):
    run, calls, _ = execute
    source = ('[def:step]($n){[try]{10/$n;return "normal"}[catch]{[t:send]{id:"recovery"};return "done"}};'
              '$result=[fn:step]{n:$n};[t:send]{id:$result};return 1/$n')
    first = run(source)
    assert not first['success'] and calls == ['recovery', 'done'], first
    out = run(source.replace(*change).replace('return 1/$n', 'return 1'),
              repair=first['resume'], check=True)
    assert not out.get('ok') and calls == ['recovery', 'done'], out


def test_following_failure_is_outside_catch_and_cleanup_tail_can_be_repaired(execute):
    run, calls, _ = execute
    source = ('[def:step]($n){[try]{[t:send]{id:"body"}}'
              '[catch]{[t:send]{id:"catch"}}[finally]{[t:send]{id:"cleanup"};10/$n};return 7};'
              'return [fn:step]{n:$n}')
    first = run(source)
    assert not first['success'] and first['diagnostic']['code'] == 'CLEANUP', first
    assert calls == ['body', 'cleanup']
    out = repair(run, first, source.replace('10/$n', '10/($n+1)'))
    assert out['success'] and out['value'] == 7 and calls == ['body', 'cleanup'], out


def test_cleanup_observing_partial_assignment_cannot_change_effect_input(execute):
    run, calls, _ = execute
    source = ('$id="before";[try]{$id="after";10/$n}[finally]{[t:send]{id:$id}}')
    first = run(source)
    assert not first['success'] and calls == ['after'], first
    out = run(source.replace('$id="after"', '$id="changed"'), check=True, repair=first['resume'])
    assert not out.get('ok') and calls == ['after'], out


@pytest.mark.parametrize('form', ['try', 'fallback'])
@pytest.mark.parametrize('kind', ['permission', 'budget', 'cancelled', 'protocol', 'runtime'])
def test_saved_recovery_preserves_fault_class_and_cleanup(component_catalog, monkeypatch, kind, form):
    from function_library import register, definitions
    calls = []
    def fail(rt, args):
        raise Fault('BLOCKED', 'original', kind=kind)
    reg = {'t:read': Adapter({'version': 1, 'params': {}, 'result': 'Number', 'effects': ['read_external']}, fail),
           't:cleanup': Adapter({'version': 1, 'params': {}, 'result': 'Number', 'effects': ['write_external']},
                                lambda *a: calls.append('cleanup') or 1)}
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **k: reg)
    source = '[def:recover](){[try]{return [t:read]{}}[catch]{return 7}[finally]{[t:cleanup]{}}}'
    if form == 'fallback':
        source = '[def:recover](){[try]{return [t:read]{} ?? 7}[finally]{[t:cleanup]{}}}'
    register('recover', '#!ibl edition=2\n' + source, edition=2)
    plan = compile_program('return [fn:recover]{}', reg, definitions=definitions())
    assert not plan.issues and calls == [], plan.report()
    out = Runtime(plan).run()
    assert calls == ['cleanup'], out
    if kind == 'runtime':
        assert out['success'] and out['value'] == 7, out
    else:
        assert not out['success'] and out['diagnostic']['kind'] == kind, out


def test_stored_recovery_keeps_reference_lifetime_and_following_fault_outside_catch(component_catalog, monkeypatch):
    from function_library import register, definitions
    from ibl_v2_types import Type
    source = '[def:recover]($ref,$n){[try]{1/$n}[catch]{0};return $ref}'
    register('recover', '#!ibl edition=2\n' + source, edition=2)
    with monkeypatch.context() as blocked:
        blocked.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body analysis'))
        plan = compile_program('return [fn:recover]{ref:$ref,n:0}', {},
                               definitions=definitions().interfaces_only(),
                               input_types={'ref': Type('ForeignRef')}, value_protocols=['ibl-value/1'])
        assert plan.result_type.kind == 'ForeignRef'
        assert any(issue['code'] == 'VALUE_PROTOCOL' for issue in plan.issues), plan.report()
    register('tail', '#!ibl edition=2\n[def:tail]($n){[try]{1}[catch]{return 7};return 10/$n}', edition=2)
    plan = compile_program('return [fn:tail]{n:$n}', {}, inputs={'n': 0}, definitions=definitions())
    out = Runtime(plan, inputs={'n': 0}).run()
    assert not out['success'] and out['diagnostic']['code'] == 'VALUE', out


def test_stored_catch_propagates_partial_failure_capability(component_catalog, monkeypatch):
    from function_library import register, definitions
    def fail(rt, args):
        raise Fault('PARTIAL_SOURCE', 'original', kind='partial', partial={'saved': 3})
    reg = {'t:read': Adapter({'version': 1, 'params': {}, 'result': 'Number', 'effects': ['read_external']}, fail)}
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **k: reg)
    register('recover', '#!ibl edition=2\n[def:recover](){[try]{return [t:read]{}}'
             '[catch]{return propagate($error)}}', edition=2)
    plan = compile_program('return [fn:recover]{}', reg, definitions=definitions())
    assert not plan.issues, plan.report()
    out = Runtime(plan).run()
    assert not out['success'] and out['diagnostic']['code'] == 'PARTIAL_SOURCE', out
    assert out['diagnostic']['kind'] == 'partial' and out['diagnostic']['partial'] == {'saved': 3}, out


def test_recovery_success_does_not_certify_failed_lower_completion(component_catalog, monkeypatch):
    from function_library import register, definitions
    from test_ibl_v2_component import definition
    def fail(rt, args):
        raise Fault('OFFLINE', 'unavailable')
    reg = {'t:read': Adapter({'version': 1, 'params': {'id': 'Text'}, 'result': 'Number',
                              'effects': ['read_external']}, fail)}
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **k: reg)
    register('checked', '#!ibl edition=2\n' + definition('checked'), edition=2)
    register('recover', '#!ibl edition=2\n[def:recover]($id){[try]{return [fn:checked]{id:$id}}'
             '[catch]{return 7}}', edition=2)
    plan = compile_program('return [fn:recover]{id:"document"}', reg, definitions=definitions())
    assert not plan.issues, plan.report()
    out = Runtime(plan).run()
    assert out['success'] and out['value'] == 7, out
    assert out['component_completion']['status'] != 'satisfied', out
    assert out['component_completion']['instances'], out


def test_saved_recovery_substitutes_new_reader_script_and_policy_without_bodies(abilities, monkeypatch):
    from function_library import register, definitions
    from ibl_v2_store import Library
    from ibl_v2_types import NUMBER
    reg, calls, scripts = abilities
    save_layers()
    register('resilient', '#!ibl edition=2\n[def:resilient]($sources,$read,$backup,$normalize,$policy){'
             'return [fn:gather]{sources:$sources,read:($source)=>($read{source:$source} ?? $backup{source:$source}),'
             'normalize:$normalize,policy:$policy}}', edition=2)
    original = Library.__getitem__
    with monkeypatch.context() as blocked:
        def no_lower(library, name):
            if name in library.interfaces:
                pytest.fail('upper authoring expanded lower body')
            return original(library, name)
        blocked.setattr(Library, '__getitem__', no_lower)
        register('audit', '#!ibl edition=2\n[def:audit]($read,$backup,$normalize,$policy){'
                 'return {evidence:[fn:resilient]{sources:["new"],read:$read,backup:$backup,'
                 'normalize:$normalize,policy:$policy}}}', edition=2)
    fields = {'id': 'Text', 'score': 'Number', 'source': 'Text', 'bytes': 'Number', '$closed': True}
    scripts['later'] = {**scripts['normalize'], 'callable_contract': {
        **scripts['normalize']['callable_contract'], 'params': {'data': {'$list': fields}},
        'result': {'$list': fields}, 'completion': []}}
    register('later_normalizer', '#!ibl edition=2\n[def:later_normalizer]($data){'
             'return [probe:python]{id:"later",args:{data:$data}}}', edition=2)
    contract = {'version': 1, 'params': {'source': 'Text'},
                'result': {'items': {'$list': fields}, 'origin': 'Text'}, 'effects': ['read_external']}
    def missing(rt, args):
        calls.append(('missing', args['source']))
        raise Fault('OFFLINE', 'source unavailable')
    def backup(rt, args):
        calls.append(('backup', args['source']))
        return {'items': [{'id': 'f', 'score': 9, 'source': args['source'], 'bytes': 20}], 'origin': args['source']}
    reg['new:primary'] = Adapter(contract, missing)
    reg['new:backup'] = Adapter(contract, backup)
    code = ('return [fn:audit]{read:&[new:primary],backup:&[new:backup],'
            'normalize:&[fn:later_normalizer],policy:($r)=>$r.bytes>10}')
    library = definitions()
    with monkeypatch.context() as blocked:
        blocked.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body analysis'))
        plan = compile_program(code, reg, definitions=library.interfaces_only())
        assert not plan.issues, plan.report()
        row = dict(dict(plan.result_type.fields)['evidence'].item.item.fields)['rows'].item
        assert dict(row.fields)['bytes'] == NUMBER
        bad = compile_program(code.replace('$r.bytes', '$r.missing'), reg, definitions=library.interfaces_only())
        assert any(i['code'] == 'MISSING_FIELD' for i in bad.issues), bad.report()
    assert calls == []
    plan.definitions = library
    out = Runtime(plan).run()
    assert out['success'], out
    assert calls == [('missing', 'new'), ('backup', 'new'), ('script', 'later')]
    assert out['value']['evidence'][0]['value']['rows'][0]['bytes'] == 20, out


def test_saved_recovery_revision_repairs_inside_bodyless_upper_composition(
        component_catalog, monkeypatch, tmp_path):
    from function_library import register, definitions
    from ibl_v2_entry import handle_request
    calls = []
    def missing(rt, args):
        calls.append('read')
        raise Fault('OFFLINE', 'unavailable')
    reg = {
        'archive:read': Adapter({'version': 1, 'params': {}, 'result': 'Number',
                                 'effects': ['read_external']}, missing),
        'archive:send': Adapter({'version': 1, 'params': {}, 'result': 'Number',
                                 'effects': ['write_external']}, lambda *a: calls.append('write') or 7)}
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **k: reg)
    monkeypatch.setattr('tool_batch.prepared_plan', lambda *a: None)
    source = ('[def:recover]($n){[try]{return [archive:read]{}}[catch]{'
              '$receipt=[archive:send]{};return {receipt:$receipt,answer:10/$n}}}')
    old = register('recover', '#!ibl edition=2\n' + source, edition=2)
    for name, lower in [('report', 'recover'), ('review', 'report')]:
        register(name, '#!ibl edition=2\n[def:' + name + ']($n){return [fn:' + lower + ']{n:$n}}', edition=2)
    request = {'edition': 2, 'code': 'return [fn:review]{n:$n}', 'inputs': {'n': 0}}
    with monkeypatch.context() as blocked:
        blocked.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body analysis'))
        plan = compile_program(request['code'], reg, inputs=request['inputs'], definitions=definitions().interfaces_only())
        assert not plan.issues and calls == [], plan.report()
    first = handle_request(request, str(tmp_path))
    assert not first['success'] and calls == ['read', 'write'], first
    register('recover', '#!ibl edition=2\n' + source.replace('10/$n', '10/($n+1)'), edition=2,
             function_id=old['function_id'], expected_revision=old['revision'])
    plan = compile_program(request['code'], reg, inputs=request['inputs'], definitions=definitions())
    updated = {**request, 'function_refs': plan.dependencies['function_refs'], 'repair': first['resume']}
    check = handle_request({**updated, 'check': True}, str(tmp_path))
    assert check['ok'] and calls == ['read', 'write'], check
    out = handle_request({**updated, 'repair': {**first['resume'], 'plan_hash': check['repair']['plan_hash']}}, str(tmp_path))
    assert out['success'] and out['value'] == {'receipt': 7, 'answer': 10}, out
    repeated = handle_request({**request, 'resume': first['resume']}, str(tmp_path))
    assert repeated['success'] and repeated['value'] == out['value'] and calls == ['read', 'write'], repeated


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
