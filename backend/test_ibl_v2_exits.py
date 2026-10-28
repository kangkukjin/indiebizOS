"""Nonlocal return in a value block is not its normal value or a caught fault."""
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
    ('$v=[if:$n==0]{return {early:7}}[else]{{normal:8}};return $v.normal', {'early': 7}),
    ('$v=[if:$n!=0]{return {early:7}}[else]{{normal:8}};return $v.normal', 8),
    ('$v=[try]{return {early:7}}[catch]{{normal:8}};return $v.normal', {'early': 7}),
    ('$v=[try]{1/$n;{normal:8}}[catch]{return {early:7}};return $v.normal', {'early': 7}),
    ('$x=1;$v=[try]{return $x}[finally]{$x=9};return 99', 1),
    ('$v=[repeat:3]{[if:$i==1]{return 7}};return 99', 7),
    ('$v=([try]{return 7}[finally]{}) ?? 8;return 99', 7),
    ('$v=(1/$n) ?? [try]{return 7}[finally]{};return 99', 7),
    ('return [try]{return 7}[finally]{}', 7),
    ('$v=[try]{$w=[if:$n==0]{return 7}[else]{8};99}[finally]{};return $v', 7),
    ('$x=0;$v=([try]{$x=7;1/$n}[finally]{}) ?? [if:$n==0]{$x=8;9}[else]{return 1};return $x', 8),
    ('$v=[if:$n==0]{return 7}[else]{8} >> text();return $v', 7),
    ('$v=[if:$n!=0]{return 7}[else]{8} >> text();return $v', '8'),
    ('$v=(([try]{return 7}[finally]{}) ?? (($x)=>$x+1)){x:8};return 99', 7),
    ('$v=(([try]{($x)=>$x+1}[finally]{}) ?? (($x)=>$x+1)){x:8};return $v', 9),
    ('$v=8 >> (([try]{return 7}[finally]{}) ?? (($x)=>$x+1)){};return 99', 7),
    ('$v=8 >> (([try]{($x)=>$x+1}[finally]{}) ?? (($x)=>$x+1)){};return $v', 9),
    ('$v=[if:$n==0]{return $n==0 ? {early:7} : {late:8}}[else]{0};return $v', {'early': 7}),
    ('$v=[try]{return $n==0 and true}[finally]{};return false', True),
    ('$v=[repeat:1]{return false or $n==0};return false', True),
    ('$v=(1/$n) ?? ($n==0 ? 7 : 8);return $v', 7),
    ('$items=[];$present=len($items)>0;$prev=[if:len($items)==0]{null}[else]{{value:7}};return $present ? $prev.value : 8', 8),
    ('return [table:each]{items:[1,2]}{$v=[if:$it==1]{return 7}[else]{8};return $v}', [7, 8]),
    ('return ([try]{return 7}[finally]{}) & ([if:$n==0]{return 8}[else]{9})', [7, 8]),
])
def test_value_returns_survive_storage_and_bodyless_composition(component_catalog, monkeypatch, body, expected):
    from function_library import register, definitions
    from ibl_v2_store import Library
    source = '[def:step]($n){' + body + '}'
    direct = compile_program(source + ';return [fn:step]{n:$n}', {}, inputs={'n': 0})
    assert not direct.issues, direct.report()
    out = Runtime(direct, inputs={'n': 0}).run()
    assert out['success'] and out['value'] == expected, out
    register('step', '#!ibl edition=2\n' + source, edition=2)
    original = Library.__getitem__
    def no_body(lib, name):
        if name in lib.interfaces:
            pytest.fail('lower body read: ' + name)
        return original(lib, name)
    with monkeypatch.context() as boundary:
        boundary.setattr(Library, '__getitem__', no_body)
        register('report', '#!ibl edition=2\n[def:report]($n){return {result:[fn:step]{n:$n}}}', edition=2)
        register('review', '#!ibl edition=2\n[def:review]($n){return [fn:report]{n:$n}}', edition=2)
    library = definitions()
    assert set(library.interfaces) == {'step', 'report', 'review'}, library.interface_limits
    with monkeypatch.context() as boundary:
        boundary.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body analysis'))
        plan = compile_program('return [fn:review]{n:$n}', {}, inputs={'n': 0}, definitions=library.interfaces_only())
        assert not plan.issues, plan.report()
    plan.definitions = library
    out = Runtime(plan, inputs={'n': 0}).run()
    assert out['success'] and out['value'] == {'result': expected}, out


@pytest.mark.parametrize('value', [
    '[if:$n==0]{[t:send]{id:"sent"};return 10/$n}[else]{1}',
    '[try]{[t:send]{id:"sent"};return 10/$n}[finally]{}',
    '[try]{1/$n}[catch]{[t:send]{id:"sent"};return 10/$n}',
    '[repeat:3]{[t:send]{id:"sent"};return 10/$n}',
    '(1/$n) ?? [try]{[t:send]{id:"sent"};return 10/$n}[finally]{}',
    '[try]{[t:send]{id:"sent"};return 10/$n}[finally]{} >> text()',
    '8 >> (([try]{1/$n;($x)=>$x+1}[finally]{}) ?? [try]{[t:send]{id:"sent"};return 10/$n}[finally]{}){}',
])
def test_internal_value_return_tail_repairs_without_repeating_effect(execute, value):
    run, calls, _ = execute
    code = '[def:step]($n){$v=' + value + ';return 99};return [fn:step]{n:$n}'
    first = run(code)
    assert not first['success'] and calls == ['sent'], first
    fixed = code.replace('return 10/$n', 'return 10/($n+1)')
    out = repair(run, first, fixed)
    assert out['success'] and out['value'] == 10 and calls == ['sent'], out
    out = run(fixed, resume=first['resume'])
    assert out['success'] and out['value'] == 10 and calls == ['sent'], out


@pytest.mark.parametrize('kind', ['if', 'try', 'repeat'])
def test_unconditional_value_return_does_not_assign_or_reach_later_effect(execute, kind):
    run, calls, _ = execute
    block = {'if': '[if:true]{return 7}[else]{return 8}',
             'try': '[try]{return 7}[finally]{[t:send]{id:"cleanup"}}',
             'repeat': '[repeat:1]{return 7}'}[kind]
    code = '$v=' + block + ';[t:send]{id:"after"};return $v'
    checked = run(code, check=True)
    assert checked['ok'] and not calls, checked
    out = run(code)
    assert out['success'] and out['value'] == 7, out
    assert calls == (['cleanup'] if kind == 'try' else [])
    # Changing the nonlocal return into a block value would activate a new effect.
    bad = run(code.replace('return 7', '7').replace('return 8', '8'), check=True, repair=out['resume'])
    assert not bad.get('ok'), bad


@pytest.mark.parametrize('form', ['caught', 'fallback', 'cleanup_failure'])
def test_return_bypasses_recovery_but_cleanup_failure_overrides_it(execute, form):
    run, calls, _ = execute
    cleanup = '[t:send]{id:"cleanup"}' + (';1/$n' if form == 'cleanup_failure' else '')
    protected = '[try]{return 7}[catch]{[t:send]{id:"caught"};return 8}[finally]{' + cleanup + '}'
    if form == 'fallback':
        protected += ' ?? [t:send]{id:"fallback"}'
    out = run('$v=' + protected + ';[t:send]{id:"after"};return $v')
    assert calls == ['cleanup'], out
    if form == 'cleanup_failure':
        assert not out['success'] and out['diagnostic']['code'] == 'CLEANUP', out
    else:
        assert out['success'] and out['value'] == 7, out


def test_changed_return_value_consumed_by_caller_effect_is_fixed(execute):
    run, calls, _ = execute
    code = ('[def:step]($n){$v=[try]{[t:send]{id:"sent"};return "first"}[finally]{};return "unused"};'
            '$v=[fn:step]{n:$n};[t:send]{id:$v};return 1/$n')
    first = run(code)
    assert calls == ['sent', 'first'], first
    bad = run(code.replace('return "first"', 'return "other"').replace('1/$n', '1'), check=True, repair=first['resume'])
    assert not bad.get('ok') and calls == ['sent', 'first'], bad


def test_returned_value_type_never_becomes_the_assignment_type(component_catalog, monkeypatch):
    from function_library import register, definitions
    source = '[def:step]($flag){$v=[if:$flag]{return {early:7}}[else]{[1,2]};return len($v)}'
    register('step', '#!ibl edition=2\n' + source, edition=2)
    with monkeypatch.context() as boundary:
        boundary.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body read'))
        from ibl_v2_types import BOOL, alternatives
        plan = compile_program('return [fn:step]{flag:$flag}', {}, input_types={'flag': BOOL},
                               definitions=definitions().interfaces_only())
        assert not plan.issues, plan.report()
        assert {v.kind for v in alternatives(plan.result_type)} == {'Record', 'Number'}


def test_nonlocal_return_keeps_reference_lifetime_and_completion(component_catalog, monkeypatch):
    from function_library import register, definitions
    from ibl_v2_types import Type
    from test_ibl_v2_component import definition
    register('identity', '#!ibl edition=2\n[def:identity]($ref){$v=[try]{return $ref}[finally]{};return $v}', edition=2)
    with monkeypatch.context() as boundary:
        boundary.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body read'))
        plan = compile_program('return [fn:identity]{ref:$ref}', {}, input_types={'ref': Type('ForeignRef')},
                               definitions=definitions().interfaces_only(), value_protocols=['ibl-value/1'])
        assert plan.result_type.kind == 'ForeignRef'
        assert any(i['code'] == 'VALUE_PROTOCOL' for i in plan.issues), plan.report()
    calls = []
    reg = {'t:read': Adapter({'version': 1, 'params': {'id': 'Text'}, 'result': 'Number', 'effects': ['read_external']},
                            lambda *a: calls.append('read') or 0)}
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **k: reg)
    register('checked', '#!ibl edition=2\n' + definition('checked'), edition=2)
    register('exit', '#!ibl edition=2\n[def:exit]($id){$v=[try]{[fn:checked]{id:$id};return 7}[finally]{};return 8}', edition=2)
    library = definitions()
    with monkeypatch.context() as boundary:
        boundary.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body read'))
        plan = compile_program('return [fn:exit]{id:"document"}', reg, definitions=library.interfaces_only())
        assert not plan.issues, plan.report()
    assert calls == []
    plan.definitions = library
    out = Runtime(plan).run()
    assert out['success'] and out['value'] == 7 and calls == ['read'], out
    assert out['component_completion']['status'] != 'satisfied', out


@pytest.mark.parametrize('position', ['record', 'list', 'condition'])
def test_exit_transfer_does_not_widen_existing_expression_grammar(position):
    forms = {'record': 'return {x:[try]{return 7}[finally]{}}',
             'list': 'return [[if:true]{return 7}[else]{8}]',
             'condition': '[if:[try]{return true}[finally]{}]{return 7}'}
    plan = compile_program(forms[position], {})
    assert any(i['code'] in ('VALUE_EXPRESSION', 'PURE_EXPRESSION') for i in plan.issues), plan.report()


def test_saved_value_exit_vertical_path_and_revised_internal_tail(abilities, monkeypatch, tmp_path):
    from function_library import register, definitions
    from ibl_v2_store import Library
    from ibl_v2_entry import handle_request
    from test_ibl_v2_semantic import NORMALIZE
    from ibl_v2_types import NUMBER
    reg, calls, scripts = abilities
    reg['probe:cleanup'] = Adapter({'version': 1, 'params': {}, 'result': 'Number', 'effects': ['write_external']},
                                   lambda *a: calls.append(('cleanup', None)) or 1)
    register('normalizer', '#!ibl edition=2\n' + NORMALIZE, edition=2)
    source = '''[def:prepare]($source,$read,$normalize,$policy,$stop,$n){
$raw=$read{source:$source};$rows=$normalize{data:$raw.items};
$selected=[table:filter]{items:$rows,where:$policy};
$v=[try]{
$receipt=[probe:publish]{items:$selected};
$gate=[if:$stop]{return {rows:$selected,receipt:$receipt,ratio:10/$n}}[else]{0};
{rows:$selected,receipt:$receipt,ratio:20}
}[finally]{[probe:cleanup]{}};
return $v}'''
    original = register('prepare', '#!ibl edition=2\n' + source, edition=2)
    raw_get = Library.__getitem__
    def no_body(lib, name):
        if name in lib.interfaces:
            pytest.fail('lower body read: ' + name)
        return raw_get(lib, name)
    sources = {
        'report': '[def:report]($source,$read,$normalize,$policy,$stop,$n){return {report:[fn:prepare]{source:$source,read:$read,normalize:$normalize,policy:$policy,stop:$stop,n:$n}}}',
        'review': '[def:review]($source,$read,$normalize,$policy,$stop,$n){return [fn:report]{source:$source,read:$read,normalize:$normalize,policy:$policy,stop:$stop,n:$n}}'}
    published = {}
    with monkeypatch.context() as boundary:
        boundary.setattr(Library, '__getitem__', no_body)
        for name, text in sources.items():
            published[name] = register(name, '#!ibl edition=2\n' + text, edition=2)
    query = ('return [fn:review]{source:"catalog",read:&[probe:read],normalize:&[fn:normalizer],'
             'policy:($r)=>$r.score>3,stop:true,n:$n}')
    library = definitions()
    assert 'prepare' in library.interfaces, library.interface_limits
    with monkeypatch.context() as boundary:
        boundary.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body read'))
        plan = compile_program(query, reg, inputs={'n': 0}, definitions=library.interfaces_only())
        assert not plan.issues, plan.report()
        assert dict(dict(dict(plan.result_type.fields)['report'].fields)['rows'].item.fields)['score'] == NUMBER
    assert calls == []
    request = {'edition': 2, 'code': query, 'inputs': {'n': 0}}
    first = handle_request(request, str(tmp_path))
    assert not first['success'] and [c[0] for c in calls] == ['read', 'script', 'publish', 'cleanup'], first
    revised = register('prepare', '#!ibl edition=2\n' + source.replace('10/$n', '10/($n+1)'), edition=2,
                       function_id=original['function_id'], expected_revision=original['revision'])
    assert revised['revision'] != original['revision']
    plan = compile_program(query, reg, inputs={'n': 0}, definitions=definitions())
    update = {**request, 'function_refs': plan.dependencies['function_refs'], 'repair': first['resume']}
    checked = handle_request({**update, 'check': True}, str(tmp_path))
    assert checked['ok'], checked
    out = handle_request({**update, 'repair': {**first['resume'], 'plan_hash': checked['repair']['plan_hash']}}, str(tmp_path))
    assert out['success'] and out['value']['report']['ratio'] == 10, out
    assert out['value']['report']['rows'] == [{'id': 'b', 'score': 5, 'source': 'catalog'}]
    again = handle_request({**request, 'resume': first['resume']}, str(tmp_path))
    assert again['success'] and again['value'] == out['value'], again
    assert out['component_completion']['status'] == 'satisfied', out
    assert [c for c in calls if c[0] in ('read', 'publish', 'cleanup')] == [
        ('read', 'catalog'), ('publish', [{'id': 'b', 'score': 5, 'source': 'catalog'}]), ('cleanup', None)]

    with monkeypatch.context() as boundary:
        boundary.setattr(Library, '__getitem__', no_body)
        for name, text in sources.items():
            old = published[name]
            register(name, '#!ibl edition=2\n' + text, edition=2,
                     function_id=old['function_id'], expected_revision=old['revision'])
    # Post-publication input shape, script and policy replacement.
    fields = {'id': 'Text', 'score': 'Number', 'source': 'Text', 'bytes': 'Number', '$closed': True}
    scripts['later'] = {**scripts['normalize'], 'callable_contract': {
        **scripts['normalize']['callable_contract'], 'params': {'data': {'$list': fields}},
        'result': {'$list': fields}, 'completion': []}}
    reg['files:scan'] = Adapter({'version': 1, 'params': {'source': 'Text'},
        'result': {'items': {'$list': fields}, 'origin': 'Text'}, 'effects': ['read_external']},
        lambda rt, a: {'items': [{'id': 'f', 'score': 9, 'source': a['source'], 'bytes': 20}], 'origin': a['source']})
    register('later_normalizer', '#!ibl edition=2\n[def:later_normalizer]($data){return [probe:python]{id:"later",args:{data:$data}}}', edition=2)
    query = query.replace('&[probe:read]', '&[files:scan]').replace('&[fn:normalizer]', '&[fn:later_normalizer]').replace('$r.score>3', '$r.bytes>10')
    library = definitions()
    before = len(calls)
    with monkeypatch.context() as boundary:
        boundary.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body read'))
        plan = compile_program(query, reg, inputs={'n': 0}, definitions=library.interfaces_only())
        assert not plan.issues, plan.report()
        assert dict(dict(dict(plan.result_type.fields)['report'].fields)['rows'].item.fields)['bytes'] == NUMBER
    assert len(calls) == before
    plan.definitions = library
    out = Runtime(plan, inputs={'n': 0}).run()
    assert out['success'] and out['value']['report']['rows'][0]['bytes'] == 20, out
    assert ('script', 'later') in calls


@pytest.mark.parametrize('target', ['[t:send]{}', '(([try]{&[t:send]}[finally]{}) ?? &[t:send]){}'])
def test_piped_effect_argument_remains_fixed(execute, target):
    run, calls, adapter = execute
    adapter.contract['pipe_input'] = 'id'
    code = '"sent" >> ' + target + ';return 1/$n'
    first = run(code)
    assert not first['success'] and calls == ['sent'], first
    bad = run(code.replace('"sent"', '"other"').replace('1/$n', '1'), check=True, repair=first['resume'])
    assert not bad.get('ok') and calls == ['sent'], bad


def test_early_return_does_not_assign_before_cleanup(execute):
    run, calls, _ = execute
    code = '$v="before";[try]{$v=[if:true]{return 7}[else]{"after"}}[finally]{[t:send]{id:$v}}'
    out = run(code)
    assert out['success'] and out['value'] == 7 and calls == ['before'], out
    bad = run(code.replace('before', 'changed'), check=True, repair=out['resume'])
    assert not bad.get('ok') and calls == ['before'], bad


def test_normal_unit_fallthrough_is_not_erased_at_a_stored_frame(component_catalog, monkeypatch):
    from function_library import register, definitions
    from ibl_v2_types import BOOL, alternatives
    source = '[def:step]($flag){$v=[if:$flag]{return 7}}'
    direct = compile_program(source + ';return [fn:step]{flag:$flag}', {}, input_types={'flag': BOOL})
    assert not direct.issues, direct.report()
    assert {t.kind for t in alternatives(direct.result_type)} == {'Unit', 'Number'}
    register('step', '#!ibl edition=2\n' + source, edition=2)
    with monkeypatch.context() as boundary:
        boundary.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body read'))
        plan = compile_program('return [fn:step]{flag:$flag}', {}, input_types={'flag': BOOL},
                               definitions=definitions().interfaces_only())
        assert not plan.issues, plan.report()
        assert plan.result_type == direct.result_type


@pytest.mark.parametrize('body', [
    '$v=[if:$flag]{return 7}[else]{8};return $v',
    '[try]{$v=[if:$flag]{return 7}[else]{8};return $v}[finally]{}',
    '$v=[repeat:1]{[if:$flag]{return 7}[else]{return 8}};return $v',
    '$v=([if:$flag]{return 7}[else]{8}) ?? 9;return $v',
    '$v=[if:$flag]{return 7}[else]{8} >> text();return $v',
])
def test_unreachable_stored_call_has_no_continuing_exit(component_catalog, monkeypatch, body):
    from function_library import register, definitions
    from ibl_v2_types import BOOL
    register('step', '#!ibl edition=2\n[def:step]($flag){' + body + '}', edition=2)
    with monkeypatch.context() as boundary:
        boundary.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body read'))
        plan = compile_program('return 9;return [fn:step]{flag:$flag}', {},
                               input_types={'flag': BOOL}, definitions=definitions().interfaces_only())
        assert not plan.issues, plan.report()
        assert plan.result_type.kind == 'Number' and plan.result_type.literal == 9


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
