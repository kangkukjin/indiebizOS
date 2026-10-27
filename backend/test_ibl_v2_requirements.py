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
