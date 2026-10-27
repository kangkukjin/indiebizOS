import boot_paths  # noqa: F401
import pytest
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime
from ibl_v2_adapters import Adapter
from ibl_v2_requirements import require_wire


CHOOSE = '[def:choose]($x,$pred){[if:$pred($x)]{return $x}[else]{return null}}'


def test_independent_requirements_and_stored_use():
    plan = compile_program(CHOOSE)
    assert not plan.issues
    requirements = next(iter(plan.function_contracts.values()))['requirements']['pred']
    assert requirements[0]['effects'] == ['pure']
    assert requirements[1]['expected']['type'] == 'Bool'
    assert requirements[0]['arguments'][0]['variable'] == 'x'
    applied = compile_program('return [fn:choose]{x:2,pred:($v)=>$v>0}', definitions={'choose': CHOOSE})
    assert Runtime(applied).run()['value'] == 2
    numeric = compile_program('[def:f]($x){return abs($x)}')
    assert next(iter(numeric.function_contracts.values()))['requirements']['x'][0]['expected']['type'] == 'Number'


def test_impure_predicate_is_still_rejected():
    reg = {'t:write': Adapter({'version': 1, 'params': {}, 'result': 'Bool', 'effects': ['write_external']}, lambda rt, a: True)}
    plan = compile_program(CHOOSE + '; return [fn:choose]{x:2,pred:($v)=>[t:write]{}}', reg)
    assert any(i['code'] == 'PURE_EXPRESSION' for i in plan.issues)


@pytest.mark.parametrize('expr,path', [('abs', '$'), ('{callback:abs}', '$.callback'), ('[1,{f:abs}]', '$[1].f')])
def test_wire_before_effect(expr, path):
    calls = []
    reg = {'t:write': Adapter({'version': 1, 'params': {}, 'result': 'Number', 'effects': ['write_external']}, lambda rt, a: calls.append(1) or 1)}
    plan = require_wire(compile_program('[t:write]{}; return ' + expr, reg))
    assert path in [i.get('path') for i in plan.issues]
    assert not Runtime(plan).run()['executed']
    assert not calls


def test_internal_callable_return_is_valid():
    plan = compile_program('[def:f](){return abs}; return [fn:f]{}(-3)')
    assert not require_wire(plan).issues
    assert Runtime(plan).run()['value'] == 3


@pytest.mark.parametrize('callback,valid', [('($v)=>$v>0', True), ('abs', False)])
def test_explicit_callback_contract(callback, valid):
    source = ('[def:f]($x:"Number",$p:{"$callable":{params:["Number"],result:"Bool",effects:["pure"]}})'
              '{return $p($x)}; return [fn:f]{x:2,p:' + callback + '}')
    plan = compile_program(source)
    assert bool(plan.issues) is not valid, plan.report()
    if valid:
        assert Runtime(plan).run()['value'] is True


def test_conditional_requirement_is_not_global_input_restriction():
    code = '[def:f]($flag,$x){[if:$flag]{return abs($x)}[else]{return $x}}'
    plan = compile_program(code)
    requirement = next(iter(plan.function_contracts.values()))['requirements']['x'][0]
    assert requirement['conditional'] is True
    assert Runtime(compile_program(code + '; return [fn:f]{flag:false,x:null}')).run()['value'] is None


def test_function_registration_accepts_conditional_pure_callback(tmp_path, monkeypatch):
    import function_store
    from function_library import register, validate_changes
    saved = function_store._root_provider, function_store._validator, function_store._registrar
    try:
        function_store.wire(lambda **_: tmp_path / 'functions', validate_changes, None)
        monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **k: {})
        monkeypatch.setattr('function_consumers.stored_programs', lambda: [])
        ref = register('choose', '#!ibl edition=2\n' + CHOOSE, edition=2)
        assert ref['revision']
    finally:
        function_store.wire(*saved)



def test_wire_consumer_policy_does_not_mutate_reusable_analysis():
    plan = compile_program('return {f:abs}')
    refused = require_wire(plan)
    assert refused.issues and not plan.issues
    assert Runtime(plan).run()['executed'] is False
    assert not plan.issues



def test_declared_callback_check_has_no_execution_accesses():
    calls = []
    reg = {'t:w': Adapter({'version': 1, 'params': {'key': 'Text'}, 'result': 'Number',
                          'effects': ['write_external'], 'write_resources': {'record': 'key'}},
                         lambda rt, a: calls.append(a) or 1)}
    code = '[def:f]($p:{"$callable":{params:[],result:"Number",effects:["write_external"]}}){return 1}; '
    code += '$p=()=>[t:w]{key:"same"}; return [fn:f]{p:$p} & [fn:f]{p:$p}'
    plan = compile_program(code, reg)
    assert not plan.issues and not plan.effects and not plan.accesses, plan.report()
    assert Runtime(plan).run()['value'] == [1, 1] and not calls



def test_public_boundary_keeps_requested_wire_on_preflight_rejection(monkeypatch, tmp_path):
    from ibl_v2_entry import handle_request
    calls = []
    reg = {'t:ref': Adapter({'version': 1, 'params': {}, 'result': 'ForeignRef',
                            'effects': ['write_external']}, lambda rt, a: calls.append(1))}
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **kw: reg)
    monkeypatch.setattr('ibl_v2_store.definitions', lambda: {})
    monkeypatch.setattr('tool_batch.prepared_plan', lambda *a: None)
    out = handle_request({'edition': 2, 'code': 'return [t:ref]{}',
                          'value_protocols': ['ibl-value/1']}, str(tmp_path))
    assert out['executed'] is False and out['diagnostic']['code'] == 'VALUE_PROTOCOL', out
    assert not calls


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__]))


CALLBACK = '{"$callable":{params:["Number"],result:"Bool",effects:["pure"]}}'


@pytest.mark.parametrize('container,argument,application', [
    ('{p:CONTRACT}', '{p:CALLBACK}', '$cfg.p(1)'),
    ('{"$list":CONTRACT}', '[CALLBACK]', '$cfg[0](1)'),
    ('{"$result":CONTRACT}', '([table:each]{items:[1],on_error:"collect"}{return CALLBACK})[0]', 'unwrap($cfg)(1)'),
    ('{"$callable":{params:[],result:CONTRACT,effects:["pure"]}}', '()=>CALLBACK', '$cfg()(1)'),
])
@pytest.mark.parametrize('impure', [False, True])
def test_structural_callback_contract(container, argument, application, impure):
    calls = []
    registry = {'t:write': Adapter({'version': 1, 'params': {}, 'result': 'Bool',
                                   'effects': ['write_external']}, lambda rt, a: calls.append(1) or True)}
    callback = '($x)=>[t:write]{}' if impure else '($x)=>$x>0'
    code = ('[def:f]($cfg:' + container.replace('CONTRACT', CALLBACK) + '){return ' + application + '};'
            'return [fn:f]{cfg:' + argument.replace('CALLBACK', callback) + '}')
    plan = compile_program(code, registry)
    out = Runtime(plan).run()
    assert out['success'] is not impure, out
    assert calls == []
    if impure:
        assert out['executed'] is False


def test_requirements_summary_replay_matches_uncached(monkeypatch):
    from ibl_v2_compile import Compiler
    source = ('[def:g]($x){return abs($x)};[def:f]($flag,$x){'
              '[if:$flag]{[fn:g]{x:$x}};return [fn:g]{x:$x}}')
    cached = compile_program(source)
    initialize = Compiler.init_call_analysis
    def disable(self):
        initialize(self)
        self.analysis_cache_enabled = False
    monkeypatch.setattr(Compiler, 'init_call_analysis', disable)
    uncached = compile_program(source)
    def requirements(plan):
        return {c['name']: c['requirements'] for c in plan.function_contracts.values()}
    assert requirements(cached) == requirements(uncached)
    assert any(not r['conditional'] for r in requirements(cached)['f']['x'])


@pytest.mark.parametrize('source,conflict', [
    ('[def:f]($x){abs($x);return not $x}', True),
    ('[def:f]($flag,$x){[if:$flag]{return abs($x)}[else]{return not $x}}', False),
    ('[def:g]($x){return abs($x)};[def:f]($x){[fn:g]{x:$x};return not $x}', True),
])
def test_independent_requirement_satisfiability(source, conflict):
    plan = compile_program(source)
    assert any(i['code'] == 'REQUIREMENT_CONFLICT' for i in plan.issues) is conflict


@pytest.mark.parametrize('flag', [True, False])
def test_mixed_wire_is_runtime_obligation(flag):
    calls = []
    reg = {'t:w': Adapter({'version': 1, 'params': {}, 'result': 'Number',
                           'effects': ['write_external']}, lambda rt, a: calls.append(1) or 1)}
    plan = require_wire(compile_program('[t:w]{};return {x:($flag ? abs : 1)}', reg, {'flag': flag}))
    assert not plan.issues
    assert plan.guards
    out = Runtime(plan, {'flag': flag}).run()
    assert out['executed'] and len(calls) == 1
    assert out['success'] is not flag
    if flag:
        assert out['diagnostic']['code'] == 'VALUE_PROTOCOL'
    else:
        assert out['value'] == {'x': 1}


def test_unsatisfiable_function_registration_rejected(tmp_path, monkeypatch):
    import function_store
    from function_library import register, validate_changes
    saved = function_store._root_provider, function_store._validator, function_store._registrar
    try:
        function_store.wire(lambda **_: tmp_path / 'functions', validate_changes, None)
        monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **k: {})
        monkeypatch.setattr('function_consumers.stored_programs', lambda: [])
        with pytest.raises(ValueError, match='요구'):
            register('impossible', '#!ibl edition=2\n[def:impossible]($x){abs($x);return not $x}', edition=2)
    finally:
        function_store.wire(*saved)


@pytest.mark.parametrize('body', [
    'return $flag ? abs($x) : not $x',
    '$n=$flag and (abs($x)>0);return not $x',
    'return abs($x) ?? (not $x)',
])
def test_conditional_and_recovery_requirements_do_not_create_false_contradictions(body):
    plan = compile_program('[def:f]($flag,$x){' + body + '}')
    assert not plan.issues, plan.issues


def test_symbolic_shared_dag_has_bounded_requirement_summary():
    source = '[def:g0]($x){return abs($x)};'
    source += ';'.join('[def:g' + str(i) + ']($x){return [fn:g' + str(i-1) +
                       ']{x:$x} + [fn:g' + str(i-1) + ']{x:$x}}' for i in range(1, 31))
    plan = compile_program(source)
    assert not plan.issues, plan.issues
    top = next(c for c in plan.function_contracts.values() if c['name'] == 'g30')
    assert len(top['requirements']['x']) == 1
    assert top['requirements']['x'][0]['expected']['type'] == 'Number'
    assert top['requirements']['x'][0]['conditional'] is False
    assert sum(len(rows) for c in plan.function_contracts.values()
               for rows in c['requirements'].values()) <= 31
    assert plan.preflight['analysis']['function_reuses'] >= 30


def test_unconstrained_container_does_not_require_deep_shape_proof():
    values = {'rows': [{'x': i} for i in range(5000)]}
    plan = compile_program('[def:f]($xs:"List"){return len($xs)};return [fn:f]{xs:$rows}', inputs=values)
    out = Runtime(plan, values).run()
    assert out['success'] and out['value'] == 5000, out
