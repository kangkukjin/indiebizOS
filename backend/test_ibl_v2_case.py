"""First-match case interfaces and completion-sensitive repair boundaries."""
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
    ('return [case:$n]{[when:0]{7}[when:0]{8}[else]{9}}', 7),
    ('return [case:true]{[when:1]{7}[when:true]{8}[else]{9}}', 8),
    ('return [case:1.0]{[when:1]{7}[else]{9}}', 7),
    ('return [case:"é"]{[when:"é"]{7}[else]{9}}', 7),
    ('$v=[case:$n]{[when:0]{return {early:7}}[else]{[1,2]}};return len($v)', {'early': 7}),
    ('$v=[case:$n]{[when:1]{return {early:7}}[else]{[1,2]}};return len($v)', 2),
    ('$x=1;$v=[case:$x]{[when:1]{$x=2;7}[when:2]{99}[else]{88}};return {v:$v,x:$x}', {'v':7, 'x':2}),
    ('$v=[try]{[case:$n]{[when:0]{return 7}[else]{8}}}[finally]{};return 99', 7),
    ('$v=[case:$n]{[when:0]{return 7}[else]{8}} >> text();return $v', 7),
    ('$v=([case:$n]{[when:0]{return 7}[else]{8}}) ?? 9;return $v', 7),
    ('return [table:each]{items:[0,1]}{$v=[case:$it]{[when:0]{return 7}[else]{8}};return $v}', [7,8]),
    ('$v=[case:true]{[when:true]{return $n==0 ? 7 : 8}[else]{9}};return $v', 7),
    ('$v=[case:$n]{[when:0]{$x=7}[else]{$x=8}};return $x', 7),
    ('[if:true]{};[case:$n]{[when:0]{$x=7}[else]{$x=8}};return $x', 7),
])
def test_case_recomposes_without_lower_bodies(component_catalog, monkeypatch, body, expected):
    from test_ibl_v2_exits import test_value_returns_survive_storage_and_bodyless_composition
    test_value_returns_survive_storage_and_bodyless_composition(component_catalog, monkeypatch, body, expected)


@pytest.mark.parametrize('flag', [True, False])
def test_first_match_skips_later_callback_requirements(component_catalog, monkeypatch, flag):
    from function_library import register, definitions
    from ibl_v2_types import Type
    source = '[def:step]($flag,$later){return [case:$flag]{[when:true]{7}[when:$later{}]{8}[else]{9}}}'
    reg = {'t:write': Adapter({'version':1, 'params':{}, 'result':'Bool', 'effects':['write_external']}, lambda *a: True)}
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **k: reg)
    register('step', '#!ibl edition=2\n'+source, edition=2)
    query = 'return [fn:step]{flag:$flag,later:&[t:write]}'
    direct = compile_program(source+';'+query, reg, inputs={'flag':flag})
    with monkeypatch.context() as boundary:
        boundary.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body'))
        saved = compile_program(query, reg, inputs={'flag':flag}, definitions=definitions().interfaces_only())
    if flag:
        assert not direct.issues and not saved.issues, (direct.report(), saved.report())
        assert saved.result_type == Type('Number', literal=7)
        assert 'write_external' not in saved.effects
    else:
        assert any(i['code'] == 'PURE_EXPRESSION' for i in direct.issues), direct.report()
        assert any(i['code'] == 'PURE_EXPRESSION' for i in saved.issues), saved.report()


@pytest.mark.parametrize('guard', ['$x', 'has($x,"value")'])
def test_case_refines_null_and_shape_in_source_and_interface(component_catalog, monkeypatch, guard):
    from function_library import register, definitions
    from ibl_v2_types import Type, NUMBER, NULL, join
    test = 'null' if guard == '$x' else 'false'
    source = '[def:step]($x){return [case:'+guard+']{[when:'+test+']{7}[else]{$x.value}}}'
    typ = join(NULL if guard == '$x' else Type('Record', open=False), Type('Record', (('value',NUMBER),), open=False))
    register('step', '#!ibl edition=2\n'+source, edition=2)
    query = 'return [fn:step]{x:$x}'
    direct = compile_program(source+';'+query, {}, input_types={'x':typ})
    with monkeypatch.context() as boundary:
        boundary.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body'))
        saved = compile_program(query, {}, input_types={'x':typ}, definitions=definitions().interfaces_only())
    assert not direct.issues and not saved.issues, (direct.report(), saved.report())
    assert direct.result_type == saved.result_type == NUMBER


@pytest.mark.parametrize('block', [
    '[case:$n]{[when:0]{[t:send]{id:"sent"};return 10/$n}[else]{8}}',
    '[case:$n]{[when:1]{8}[else]{[t:send]{id:"sent"};10/$n}}',
    '[try]{[case:$n]{[when:0]{[t:send]{id:"sent"};return 10/$n}}}[finally]{[t:send]{id:"cleanup"}}',
    '[case:$n]{[when:0]{[t:send]{id:"sent"};return 10/$n}[else]{8}} >> text()',
    '[case:$n]{[when:0]{[t:send]{id:"sent"};return 10/$n}[else]{[t:send]{id:"other"};8}}',
    '[repeat:3]{[case:$i]{[when:0]{[t:send]{id:"sent"};10/$n}[else]{[t:send]{id:"later"};20}}}',
])
def test_case_internal_tail_repairs_and_reuses_completed_effects(execute, block):
    run, calls, _ = execute
    code = '[def:step]($n){$v='+block+';return $v};return [fn:step]{n:$n}'
    first = run(code)
    assert not first['success'] and calls[0] == 'sent', first
    fixed = code.replace('10/$n', '10/($n+1)')
    out = repair(run, first, fixed)
    assert out['success'] and calls.count('sent') == 1, out
    if 'cleanup' in code:
        assert calls == ['sent','cleanup']
    if 'repeat' in code:
        assert calls == ['sent','later','later']
    previous = calls.copy()
    again = run(fixed, resume=first['resume'])
    assert again['success'] and again['value'] == out['value'] and calls == previous, again


@pytest.mark.parametrize('original,changed', [
    ('[case:$n]{[when:0]{[t:send]{id:"sent"};10/$n}[else]{8}}', '[case:$n+1]{[when:0]{[t:send]{id:"sent"};10}[else]{8}}'),
    ('[case:$n]{[when:1]{8}[when:0]{[t:send]{id:"sent"};10/$n}}', '[case:$n]{[when:0]{8}[when:0]{[t:send]{id:"sent"};10}}'),
    ('[case:$n]{[when:0]{[t:send]{id:"sent"};return 10/$n}[else]{8}};[t:send]{id:"after"}', '[case:$n]{[when:0]{[t:send]{id:"sent"};10}[else]{8}};[t:send]{id:"after"}'),
    ('$v=[case:$n]{[when:0]{"sent"}[else]{"other"}};[t:send]{id:$v};10/$n', '$v=[case:$n]{[when:0]{"changed"}[else]{"other"}};[t:send]{id:$v};10'),
    ('[case:$n]{[when:0]{[t:send]{id:"sent"};7}[else]{8}};[t:send]{id:"after"};10/$n', '[case:$n]{[when:0]{[t:send]{id:"sent"};9}[else]{8}};[t:send]{id:"after"};10'),
])
def test_case_effect_selection_input_and_completion_changes_are_rejected(execute, original, changed):
    run, calls, _ = execute
    code = '[def:step]($n){'+original+'};return [fn:step]{n:$n}'
    first = run(code)
    before = calls.copy()
    assert not first['success'] and 'sent' in before, first
    checked = run('[def:step]($n){'+changed+'};return [fn:step]{n:$n}', check=True, repair=first['resume'])
    assert not checked.get('ok') and calls == before, checked


def test_earlier_comparison_failure_selects_recovery_effect(execute):
    run, calls, _ = execute
    code = '[def:step]($n){[try]{[case:0]{[when:1/$n]{8}[when:0]{9}}}[catch]{[t:send]{id:"recovery"};return 10/$n}};return [fn:step]{n:$n}'
    first = run(code)
    assert calls == ['recovery'] and not first['success'], first
    fixed = code.replace('return 10/$n', 'return 10/($n+1)')
    out = repair(run, first, fixed)
    assert out['success'] and out['value'] == 10 and calls == ['recovery'], out
    bad = run(fixed.replace('when:1/$n','when:1/($n+1)'), check=True, repair=first['resume'])
    assert not bad.get('ok') and calls == ['recovery'], bad


def test_unmatched_unit_and_dead_stored_case(component_catalog, monkeypatch):
    from function_library import register, definitions
    from ibl_v2_types import BOOL, alternatives
    source = '[def:step]($flag){$v=[case:$flag]{[when:true]{return 7}}}'
    register('step', '#!ibl edition=2\n'+source, edition=2)
    library = definitions().interfaces_only()
    with monkeypatch.context() as boundary:
        boundary.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body'))
        plan = compile_program('return [fn:step]{flag:$flag}', {}, input_types={'flag':BOOL}, definitions=library)
        assert not plan.issues and {t.kind for t in alternatives(plan.result_type)} == {'Number','Unit'}, plan.report()
        dead = compile_program('return 9;return [fn:step]{flag:$flag}', {}, input_types={'flag':BOOL}, definitions=library)
        assert not dead.issues and dead.result_type.literal == 9, dead.report()


def test_saved_case_vertical_path_and_revised_internal_tail(abilities, monkeypatch, tmp_path):
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
$gate=[case:$stop]{[when:true]{return {rows:$selected,receipt:$receipt,ratio:10/$n}}[when:false]{0}[else]{1}};
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
        bad = compile_program(query.replace('$r.bytes>10', '$r.absent>10'), reg, inputs={'n': 0},
                              definitions=library.interfaces_only())
        assert bad.issues, bad.report()
    assert len(calls) == before
    plan.definitions = library
    out = Runtime(plan, inputs={'n': 0}).run()
    assert out['success'] and out['value']['report']['rows'][0]['bytes'] == 20, out
    assert ('script', 'later') in calls


def test_selector_once_and_comparisons_only_until_first_match(component_catalog, monkeypatch):
    from function_library import register, definitions
    calls = []
    def adapter(name, value):
        return Adapter({'version':1, 'params':{}, 'result':'Bool', 'effects':['pure']},
                       lambda *a: calls.append(name) or value)
    reg = {'t:pick':adapter('selector',True), 't:miss':adapter('miss',False),
           't:match':adapter('match',True), 't:later':adapter('later',True)}
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **k: reg)
    source = '[def:step]($pick,$miss,$match,$later){return [case:$pick{}]{[when:$miss{}]{7}[when:$match{}]{8}[when:$later{}]{9}[else]{10}}}'
    register('step', '#!ibl edition=2\n'+source, edition=2)
    library = definitions()
    query = 'return [fn:step]{pick:&[t:pick],miss:&[t:miss],match:&[t:match],later:&[t:later]}'
    with monkeypatch.context() as boundary:
        boundary.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body'))
        plan = compile_program(query, reg, definitions=library.interfaces_only())
        assert not plan.issues, plan.report()
    assert calls == []
    plan.definitions = library
    out = Runtime(plan).run()
    assert out['success'] and out['value'] == 8 and calls == ['selector','miss','match'], out


@pytest.mark.parametrize('form', ['catch','fallback','cleanup_failure'])
def test_case_return_and_cleanup_precedence(execute, form):
    run, calls, _ = execute
    code = '[try]{[case:$n]{[when:0]{return 7}[else]{8}}}[catch]{[t:send]{id:"caught"}}[finally]{[t:send]{id:"cleanup"}'
    code += ';1/$n}' if form == 'cleanup_failure' else '}'
    if form == 'fallback':
        code += ' ?? [t:send]{id:"fallback"}'
    out = run('$v='+code+';[t:send]{id:"after"};return $v')
    assert calls == ['cleanup'], out
    if form == 'cleanup_failure':
        assert not out['success'] and out['diagnostic']['code'] == 'CLEANUP', out
    else:
        assert out['success'] and out['value'] == 7, out


def test_case_reference_lifetime_and_lower_completion_are_not_erased(component_catalog, monkeypatch):
    from function_library import register, definitions
    from test_ibl_v2_component import definition
    from ibl_v2_types import Type
    register('identity', '#!ibl edition=2\n[def:identity]($ref){$v=[case:true]{[when:true]{return $ref}};return 9}', edition=2)
    with monkeypatch.context() as boundary:
        boundary.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body'))
        plan = compile_program('return [fn:identity]{ref:$ref}', {}, input_types={'ref':Type('ForeignRef')},
                               definitions=definitions().interfaces_only(), value_protocols=['ibl-value/1'])
        assert plan.result_type.kind == 'ForeignRef'
        assert any(i['code'] == 'VALUE_PROTOCOL' for i in plan.issues), plan.report()
    calls = []
    reg = {'t:read':Adapter({'version':1, 'params':{'id':'Text'}, 'result':'Number', 'effects':['read_external']},
                           lambda *a: calls.append('read') or 0)}
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **k: reg)
    register('checked', '#!ibl edition=2\n'+definition('checked'), edition=2)
    register('step', '#!ibl edition=2\n[def:step]($id){$v=[case:true]{[when:true]{[fn:checked]{id:$id};return 7}};return 8}', edition=2)
    library = definitions()
    with monkeypatch.context() as boundary:
        boundary.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body'))
        plan = compile_program('return [fn:step]{id:"document"}', reg, definitions=library.interfaces_only())
        assert not plan.issues and not calls, plan.report()
    plan.definitions = library
    out = Runtime(plan).run()
    assert out['success'] and out['value'] == 7 and calls == ['read'], out
    assert out['component_completion']['status'] != 'satisfied', out


def test_case_binding_join_used_by_effect_stays_fixed(execute):
    run, calls, _ = execute
    code = '[def:step]($n){[case:$n]{[when:0]{$id="sent"}[else]{$id="other"}};[t:send]{id:$id};return 10/$n};return [fn:step]{n:$n}'
    first = run(code)
    assert not first['success'] and calls == ['sent'], first
    bad = run(code.replace('"sent"','"changed"').replace('10/$n','10'), check=True, repair=first['resume'])
    assert not bad.get('ok') and calls == ['sent'], bad


@pytest.mark.parametrize('body', [
    '[case:true]{[when:true]{7}[else]{$missing}}',
    '[case:true]{[when:true]{7}[when:$missing]{8}}',
    '[case:true]{[when:true]{$x=7}[else]{8}};return $x',
])
def test_case_dead_syntax_and_lexical_assignment_remain_checked(body):
    plan = compile_program(body, {})
    assert plan.issues, plan.report()


def test_returning_case_path_does_not_constrain_other_paths_following_effect(execute):
    run, calls, _ = execute
    code = '[def:step]($n){[case:$n]{[when:0]{[t:send]{id:"sent"};return 10/$n}[else]{8}};[t:send]{id:"after"};return 9};return [fn:step]{n:$n}'
    first = run(code)
    assert not first['success'] and calls == ['sent'], first
    out = repair(run, first, code.replace('10/$n', '10/($n+1)'))
    assert out['success'] and out['value'] == 10 and calls == ['sent'], out


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
