"""Common contract acceptance: promotion, invocation, failure and non-amplification."""
import boot_paths  # noqa: F401
import json
import pytest
from ibl_v2_adapters import Adapter, Adapted
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime
from ibl_v2_ir import Fault


def duty(action='t:read', predicate='$value > 0'):
    return {'id': 'verified', 'predicate': predicate,
            'sources': [{'action': action, 'targets': {'id': {'parameter': 'id'}}}]}


def definition(name='f', body='return [t:read]{id:$id}', obligation=None):
    return '[def:' + name + ']($id):' + json.dumps({'completion': [obligation or duty()]}) + '{' + body + '}'


def registry(calls=None, partial=False):
    calls = [] if calls is None else calls
    def read(rt, args):
        calls.append(args['id'])
        return Adapted(2 if args['id'] != 'bad' else 0, {'incomplete': partial})
    return {'t:read': Adapter({'version': 1, 'params': {'id': 'Text'}, 'result': 'Number',
                               'effects': ['read_external'], 'read_resources': {'object': 'id'}}, read)}


def run(source, reg=None, definitions=None):
    plan = compile_program(source, reg or {}, definitions=definitions)
    assert not plan.issues, plan.report()
    return Runtime(plan).run()


def test_definition_contract_is_inert_and_invocation_outcomes_are_distinct():
    calls = []
    source = definition() + '; [fn:f]{id:"bad"}; return [fn:f]{id:"good"}'
    plan = compile_program(source, registry(calls))
    assert not plan.issues, plan.report()
    assert calls == []
    assert all(c['protocol'] == 'ibl-component/1' for c in plan.components.values())
    assert all(c['evidence']['certified'] is False for c in plan.components.values())
    out = Runtime(plan).run()
    assert out['success'] and calls == ['bad', 'good'], out
    instances = out['component_completion']['instances']
    assert [o['status'] for o in instances] == ['unsatisfied', 'satisfied']
    assert len({o['instance'] for o in instances}) == 2
    # A discarded mandatory result is still an unmet obligation of this run.
    assert out['component_completion']['status'] == 'unsatisfied'


def test_never_called_or_optional_contract_is_not_certified():
    out = run(definition() + '; return 1', registry())
    assert 'component_completion' not in out
    optional = {**duty(), 'required': False}
    out = run(definition(obligation=optional) + '; return [fn:f]{id:"bad"}', registry())
    assert out['component_completion']['status'] == 'undetermined'


@pytest.mark.parametrize('depth', [1, 3, 6, 10, 14, 30])
def test_repeated_promotion_preserves_obligation_and_source(depth):
    definitions = {'f0': definition('f0')}
    for i in range(1, depth + 1):
        definitions[f'f{i}'] = f'[def:f{i}]($id){{return {{part:[fn:f{i-1}]{{id:$id}}}}}}'
    out = run(f'return [fn:f{depth}]{{id:"good"}}', registry(), definitions)
    assert out['success'] and out['component_completion']['status'] == 'satisfied', out
    result = out['value']
    for _ in range(depth):
        result = result['part']
    assert result == 2
    assert len(out['component_completion']['instances']) == 1


def test_real_store_f1_f2_f3_retains_definition_contract(tmp_path, monkeypatch):
    import function_store
    from function_library import register, definitions, validate_changes, reference_library
    saved = function_store._root_provider, function_store._validator, function_store._registrar
    calls, reg = [], registry()
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **k: reg)
    monkeypatch.setattr('function_consumers.stored_programs', lambda: [])
    try:
        function_store.wire(lambda **_: tmp_path / 'functions', validate_changes, None)
        register('f1', '#!ibl edition=2\n' + definition('f1'), edition=2)
        register('f2', '#!ibl edition=2\n[def:f2]($id){return {nested:[fn:f1]{id:$id}}}', edition=2)
        register('f3', '#!ibl edition=2\n[def:f3]($id){return [fn:f2]{id:$id}}', edition=2)
        plan = compile_program('return [fn:f3]{id:"good"}', reg, definitions=definitions())
        refs = plan.dependencies['function_refs']
        pinned = reference_library(refs)
        out = run('return [fn:f3]{id:"good"}', reg, pinned)
        assert out['value'] == {'nested': 2}, out
        assert out['component_completion']['status'] == 'satisfied'
    finally:
        function_store.wire(*saved)


def test_callback_record_selection_and_scoped_commit_survive_fanout():
    committed = []
    reg = registry()
    def read(rt, args):
        rt.commit_scope.actions[args['id']] = lambda: committed.append(args['id'])
        return 2 if args['id'] == 'good' else 0
    reg['t:read'] = Adapter(reg['t:read'].contract, read)
    out = run(definition() + '; $r=[table:each]{items:["good","bad"],parallel:2}{return [fn:f]{id:$it}}; return $r', reg)
    assert out['success'], out
    assert out['component_completion']['status'] == 'unsatisfied'
    assert committed == ['good']


def test_adapter_and_function_own_the_same_completion_schema():
    reg = registry()
    contract = {**reg['t:read'].contract, 'completion': [duty()]}
    reg['t:read'] = Adapter(contract, reg['t:read'].run)
    out = run('return [t:read]{id:"good"}', reg)
    assert out['component_completion']['status'] == 'satisfied', out


@pytest.mark.parametrize('source', [
    '[def:f]($x){return abs($x.payload.count)}',
    '[def:f]($x){return abs(get($x,"payload").count)}',
])
def test_symbolic_projection_retains_input_relation(source):
    plan = compile_program(source)
    assert not plan.issues, plan.report()
    req = next(iter(plan.components.values()))['inputs']['relations']['x']
    assert any(r.get('path') == ['payload', 'count'] and r['expected']['type'] == 'Number' for r in req), req


def test_same_callback_result_conflicts_but_distinct_applications_do_not():
    bad = compile_program('[def:f]($cb){$r=$cb(1); $n=abs($r); return not $r}')
    assert any(i['code'] == 'REQUIREMENT_CONFLICT' for i in bad.issues), bad.report()
    good = compile_program('[def:f]($cb){$n=abs($cb(1)); return not $cb("flag")}')
    assert not good.issues, good.report()


@pytest.mark.parametrize('depth', [1, 6, 14, 30])
def test_repropagation_keeps_original_failure_across_composition(depth):
    def fail(rt, args):
        raise Fault('ORIGINAL', 'original failure', partial={'kept': 7}, details={'origin': 'leaf'})
    reg = {'t:fail': Adapter({'version': 1, 'params': {}, 'result': 'Number', 'effects': ['read_external']}, fail)}
    definitions = {'f0': '[def:f0](){[try]{return [t:fail]{}}[catch]{return propagate($error)}}'}
    for i in range(1, depth + 1):
        definitions[f'f{i}'] = f'[def:f{i}](){{return [fn:f{i-1}]{{}}}}'
    out = run(f'return [fn:f{depth}]{{}}', reg, definitions)
    assert not out['success'] and out['diagnostic']['code'] == 'ORIGINAL', out
    assert out['diagnostic']['partial'] == {'kept': 7}
    assert out['diagnostic']['details']['origin'] == 'leaf'
    assert len(out['diagnostic']['frames']) == depth + 1


def test_collected_failure_preserves_capability_but_wire_cannot_mint_it():
    from common.expression_ir import ResultValue, pack, unpack
    from common.expression_ops import pure_call
    failure = Fault('ORIGINAL', 'failed', partial=[1])
    value = ResultValue(False, error={'code': 'FORGED'}, failure=failure)
    with pytest.raises(Fault) as caught:
        pure_call('propagate', [value])
    assert caught.value.code == 'ORIGINAL' and caught.value.partial == [1]
    with pytest.raises(Fault) as caught:
        pure_call('propagate', [unpack(pack(value))])
    assert caught.value.code == 'FAILURE_CAPABILITY'
    with pytest.raises(Fault) as caught:
        pure_call('unwrap', [value])
    assert caught.value.code == 'UNWRAP_ERR'


def test_unknown_write_parallel_is_rejected_without_opt_in():
    calls = []
    reg = {'t:write': Adapter({'version': 1, 'params': {}, 'result': 'Number', 'effects': ['unknown']},
                              lambda rt, a: calls.append(1) or 1)}
    out = run('return [t:write]{} & [t:write]{}', reg)
    assert not out['success'] and not calls, out
    assert out['diagnostic']['code'] == 'PARALLEL_RESOURCE_CONFLICT'


@pytest.mark.parametrize('selection,expected', [('good', 'satisfied'), ('other', 'undetermined')])
def test_promoted_certificate_survives_transport_relocation_and_not_equal_substitution(selection, expected):
    from model_result_view import input_ref_evidence
    first = run(definition() + ';return {good:[fn:f]{id:"good"},other:2}', registry())
    assert first['component_certificates']['obligations'][0]['scope'] == ['good']
    current = first
    # Three actual execution/receipt boundaries, without redeclaring the duty.
    for _ in range(3):
        inputs = {'x': current['value']}
        note = {'path': ['value'], 'evidence': input_ref_evidence(current)}
        plan = compile_program('return $x', inputs=inputs)
        current = Runtime(plan, inputs, input_evidence={'x': note}).run()
        assert current['component_certificates']['obligations'][0]['scope'] == ['good']
    inputs = {'x': current['value']}
    final_duty = {**duty(), 'scope': ['moved'], 'sources': [{'action': 't:read', 'targets': {'id': 'good'}}]}
    out = Runtime(compile_program('return {moved:$x.' + selection + '}', inputs=inputs), inputs,
                  input_evidence={'x': {'path': ['value'], 'evidence': input_ref_evidence(current)}},
                  completion=[final_duty]).run()
    assert out['completion']['status'] == expected, out


@pytest.mark.parametrize('depth', [6, 10, 14, 30])
def test_shared_dag_contracts_and_effects_stay_bounded(depth):
    source = '[def:g0]($x){return abs($x.payload.n)};'
    source += ';'.join(f'[def:g{i}]($x){{return [fn:g{i-1}]{{x:$x}}+[fn:g{i-1}]{{x:$x}}}}' for i in range(1, depth+1))
    plan = compile_program(source)
    assert not plan.issues, plan.report()
    assert len(plan.components) == depth + 1
    assert sum(len(c['dependencies']) for c in plan.components.values()) <= depth
    assert plan.preflight['analysis']['function_bodies'] <= (depth + 1) * (depth + 2)
    top = next(c for c in plan.components.values() if c['identity']['name'] == f'g{depth}')
    assert any(r.get('path') == ['payload', 'n'] for r in top['inputs']['relations']['x'])


def test_cached_and_uncached_contracts_agree(monkeypatch):
    from ibl_v2_compile import Compiler
    source = '[def:f]($x){return abs($x.a.n)};[def:g]($x){return [fn:f]{x:$x}+[fn:f]{x:$x}}'
    cached = compile_program(source)
    init = Compiler.init_call_analysis
    def disable(self):
        init(self)
        self.analysis_cache_enabled = False
    monkeypatch.setattr(Compiler, 'init_call_analysis', disable)
    direct = compile_program(source)
    assert direct.components == cached.components
    assert direct.effects == cached.effects
    assert direct.node_effects == cached.node_effects


@pytest.mark.parametrize('domain', ['publication', 'device'])
def test_whole_workflow_promoted_completion_and_repair(tmp_path, monkeypatch, domain, component_catalog):
    from ibl_v2_entry import handle_request
    calls, state = [], {'device': 0}
    path = tmp_path / 'report.txt'
    def read(rt, args):
        calls.append('read')
        return len(path.read_text()) if path.exists() and domain == 'publication' else state['device']
    def write(rt, args):
        calls.append('write')
        if domain == 'publication':
            path.write_text('published')
        else:
            state['device'] = 9
        return 9
    reg = {
        't:read': Adapter({'version': 1, 'params': {'id': 'Text'}, 'result': 'Number',
                          'effects': ['read_external'], 'read_resources': {'object': 'id'}}, read),
        't:write': Adapter({'version': 1, 'params': {'id': 'Text'}, 'result': 'Number',
                           'effects': ['write_external'], 'write_resources': {'object': 'id'}}, write)}
    defs = {'f1': definition('f1', '$before=[t:read]{id:$id};[if:$before==0]{[t:write]{id:$id}};return [t:read]{id:$id}'),
            'f2': '[def:f2]($id){return {checked:[fn:f1]{id:$id}}}',
            'f3': '[def:f3]($id){return [fn:f2]{id:$id}}'}
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **k: reg)
    from function_library import register
    for name, body in defs.items():
        register(name, '#!ibl edition=2\n' + body, edition=2)
    monkeypatch.setattr('tool_batch.prepared_plan', lambda *a: None)
    source = '$done=[fn:f3]{id:"' + domain + '"};$report=10/$n;return {result:$done,score:$report}'
    request = {'edition': 2, 'code': source, 'inputs': {'n': 0}}
    first = handle_request(request, str(tmp_path))
    assert not first['success'] and calls == ['read', 'write', 'read'], first
    fixed = {**request, 'code': source.replace('10/$n', '10/($n+1)')}
    handle = {'run_id': first['resume']['run_id']}
    checked = handle_request({**fixed, 'check': True, 'repair': handle}, str(tmp_path))
    assert checked['ok'], json.dumps(checked, ensure_ascii=False)
    final = handle_request({**fixed, 'repair': {**handle, 'plan_hash': checked['repair']['plan_hash']}}, str(tmp_path))
    assert final['success'] and final['value'] == {'result': {'checked': 9}, 'score': 10}, final
    assert final['component_completion']['status'] == 'satisfied'
    assert calls == ['read', 'write', 'read']


@pytest.fixture
def component_catalog(tmp_path, monkeypatch):
    import function_store
    from function_library import validate_changes
    saved = function_store._root_provider, function_store._validator, function_store._registrar
    function_store.wire(lambda **_: tmp_path / 'functions', validate_changes, None)
    monkeypatch.setattr('function_consumers.stored_programs', lambda: [])
    try:
        yield
    finally:
        function_store.wire(*saved)


@pytest.fixture
def real_script_registry(tmp_path, monkeypatch):
    import sys
    import importlib.util
    from pathlib import Path
    from ibl_dependencies import script_contract
    from function_library import register, definitions
    runner_path = Path(__file__).resolve().parents[1] / 'data/packages/installed/tools/system_essentials/script_ops.py'
    spec = importlib.util.spec_from_file_location('component_script_test', runner_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    script = tmp_path / 'double.py'
    script.write_text('import json,sys\nr=json.load(sys.stdin)\nprint(json.dumps({"protocol":"ibl-script/2","ok":True,"value":r["args"]["x"]*2}))\n')
    script_declaration = {'version': 1, 'params': {'x': 'Number'}, 'result': 'Number', 'effects': ['pure'],
                          'adapter': {'protocol': 'ibl-script/2'},
                          'completion': [{'id': 'double', 'predicate': '$value==4',
                                          'sources': [{'action': 't:script', 'targets': {'id': 'double'}}]}]}
    catalog = {'double': {'file': 'double.py', 'interpreter': 'python', 'callable_contract': script_declaration}}
    monkeypatch.setattr(module, '_read_registry', lambda: catalog)
    monkeypatch.setattr(module, '_SCRIPT_DIR', tmp_path)
    monkeypatch.setattr(module, '_RUN_DIR', tmp_path / 'runs')
    monkeypatch.setattr(module, '_update_state', lambda *a, **k: None)
    monkeypatch.setattr(module, '_resolve_interpreter', lambda *a: (sys.executable, None))
    monkeypatch.setattr('ibl_dependencies._script_registry', lambda path: catalog)
    calls = []
    reg = registry(calls)
    def invoke(rt, args):
        calls.append('script')
        result = module.op_run({**args, '_ibl_edition': 2})
        assert result['success'], result
        return result['value']
    reg['t:script'] = Adapter({'version': 1, 'params': {'id': 'Text', 'args': 'Record'}, 'result': 'Unknown',
                                'effects': ['unknown'], 'adapter': {'protocol': 'ibl-script/2'}},
                               invoke, specialize=script_contract)
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **k: reg)
    return reg, calls


def test_real_script_and_vocabulary_compose_through_saved_f1_f2_f3(real_script_registry, component_catalog):
    from function_library import register, definitions
    reg, calls = real_script_registry
    register('f1', '#!ibl edition=2\n[def:f1]($id){$n=[t:read]{id:$id};return [t:script]{id:"double",args:{x:$n}}}', edition=2)
    register('f2', '#!ibl edition=2\n[def:f2]($id){return {part:[fn:f1]{id:$id}}}', edition=2)
    register('f3', '#!ibl edition=2\n[def:f3]($id){return [fn:f2]{id:$id}}', edition=2)
    assert calls == []
    plan = compile_program('return [fn:f3]{id:"good"}', reg, definitions=definitions())
    assert any(c['completion'] for c in plan.components.values())
    out = Runtime(plan).run()
    assert out['success'] and out['value'] == {'part': 4} and calls == ['good', 'script'], out
    assert out['component_completion']['status'] == 'satisfied', out


def test_stored_pure_f3_revision_repair_preserves_completed_effects(tmp_path, monkeypatch, component_catalog):
    from ibl_v2_entry import handle_request
    from function_library import register, definitions
    calls = []
    reg = {'t:write': Adapter({'version': 1, 'params': {}, 'result': 'Number',
                              'effects': ['write_external']}, lambda rt, args: calls.append(1) or 1)}
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **k: reg)
    monkeypatch.setattr('tool_batch.prepared_plan', lambda *a: None)
    leaf = register('p1', '#!ibl edition=2\n[def:p1]($n){return 10/$n}', edition=2)
    register('p2', '#!ibl edition=2\n[def:p2]($n){return [fn:p1]{n:$n}}', edition=2)
    register('p3', '#!ibl edition=2\n[def:p3]($n){return [fn:p2]{n:$n}}', edition=2)
    request = {'edition': 2, 'code': '$done=[t:write]{};return [fn:p3]{n:$n}', 'inputs': {'n': 0}}
    first = handle_request(request, str(tmp_path))
    assert not first['success'] and calls == [1], first
    register('p1', '#!ibl edition=2\n[def:p1]($n){return 10/($n+1)}', edition=2,
             function_id=leaf['function_id'], expected_revision=leaf['revision'])
    current = compile_program(request['code'], reg, inputs=request['inputs'], definitions=definitions())
    updated = {**request, 'function_refs': current.dependencies['function_refs']}
    handle = {'run_id': first['resume']['run_id']}
    checked = handle_request({**updated, 'check': True, 'repair': handle}, str(tmp_path))
    assert checked.get('ok'), json.dumps(checked, ensure_ascii=False)
    final = handle_request({**updated, 'repair': {**handle, 'plan_hash': checked['repair']['plan_hash']}}, str(tmp_path))
    assert final['success'] and final['value'] == 10 and calls == [1], final
    resumed = handle_request({**request, 'resume': handle}, str(tmp_path))
    assert resumed['success'] and resumed['value'] == 10 and calls == [1], resumed


@pytest.mark.parametrize('domain', ['publication', 'device'])
def test_distinct_mixed_workflows_preserve_completion_and_repair(
        tmp_path, monkeypatch, component_catalog, real_script_registry, domain):
    from function_library import register
    from ibl_v2_entry import handle_request
    reg, calls = real_script_registry
    path = tmp_path / 'published.json'
    state = {'current': 2, 'pending': None}

    def action(name, params, result, effects, operation):
        def invoke(rt, args):
            calls.append(name)
            return operation(args)
        reg['t:' + name] = Adapter({'version': 1, 'params': params, 'result': result,
                                   'effects': [effects]}, invoke)

    def unavailable(args):
        raise Fault('SOURCE_MISSING', 'primary unavailable')

    def publish(args):
        path.write_text(json.dumps({'required': args['n'], 'optional': []}))
        return 'published'

    def submit(args):
        state['pending'] = args['n']
        return {'task_ref': 'pending-1', 'status': 'accepted'}

    def wait(args):
        assert args['task'] == 'pending-1' and state['current'] == 2
        state['current'], state['pending'] = state['pending'], None
        return {'status': 'completed'}

    if domain == 'publication':
        action('primary', {}, 'Number', 'read_external', unavailable)
        action('fallback', {}, 'Number', 'read_external', lambda args: 2)
        action('publish', {'n': 'Number'}, 'Text', 'write_external', publish)
        action('verify', {'id': 'Text'}, 'Number', 'read_external',
               lambda args: json.loads(path.read_text())['required'])
        first = '[def:f1](){ $n=[t:primary]{} ?? [t:fallback]{};return [t:script]{id:"double",args:{x:$n}}}'
        second = definition('f2', '$n=[fn:f1]{};$ok=(($v)=>$v==4)($n);'
                            '[if:$ok]{[t:publish]{n:$n}};return [t:verify]{id:$id}',
                            duty('t:verify', '$value==4'))
        expected_calls = ['primary', 'fallback', 'script', 'publish', 'verify']
    else:
        action('state', {}, 'Number', 'read_external', lambda args: state['current'])
        action('submit', {'n': 'Number'}, 'Record', 'write_external', submit)
        action('wait', {'task': 'Text'}, 'Record', 'read_external', wait)
        action('observe', {'id': 'Text'}, 'Number', 'read_external', lambda args: state['current'])
        first = '[def:f1](){ $n=[t:state]{};return [t:script]{id:"double",args:{x:$n}}}'
        second = definition('f2', '$n=[fn:f1]{};$ok=(($v)=>$v>2)($n);'
                            '[if:$ok]{$receipt=[t:submit]{n:$n};[t:wait]{task:$receipt.task_ref}};'
                            'return [t:observe]{id:$id}', duty('t:observe', '$value==4'))
        expected_calls = ['state', 'script', 'submit', 'wait', 'observe']
    register('f1', '#!ibl edition=2\n' + first, edition=2)
    register('f2', '#!ibl edition=2\n' + second, edition=2)
    register('f3', '#!ibl edition=2\n[def:f3]($id){return {verified:[fn:f2]{id:$id}}}', edition=2)
    assert calls == []
    monkeypatch.setattr('tool_batch.prepared_plan', lambda *a: None)
    source = '$r=[fn:f3]{id:"target"};return {data:$r,score:10/$n}'
    request = {'edition': 2, 'code': source, 'inputs': {'n': 0}}
    failed = handle_request(request, str(tmp_path))
    assert not failed['success'] and calls == expected_calls, failed
    assert failed['component_completion']['status'] == 'satisfied', failed
    fixed = {**request, 'code': source.replace('10/$n', '10/($n+1)')}
    repair = {'run_id': failed['resume']['run_id']}
    check = handle_request({**fixed, 'repair': repair, 'check': True}, str(tmp_path))
    assert check.get('ok'), json.dumps(check, ensure_ascii=False)
    final = handle_request({**fixed, 'repair': {**repair, 'plan_hash': check['repair']['plan_hash']}}, str(tmp_path))
    assert final['success'] and final['value'] == {'data': {'verified': 4}, 'score': 10}, final
    assert final['component_completion']['status'] == 'satisfied'
    # Pure scripts recompute; external reads/writes and failed source receipts do not.
    assert calls == expected_calls + ['script']
    if domain == 'publication':
        assert json.loads(path.read_text()) == {'required': 4, 'optional': []}
    else:
        assert state == {'current': 4, 'pending': None}


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
