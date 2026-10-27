import boot_paths  # noqa: F401
import pytest
from ibl_v2_adapters import Adapter, Adapted
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime
from ibl_v2_ir import Fault


@pytest.mark.parametrize('partial,expected', [(False, 'satisfied'), (True, 'undetermined')])
def test_validated_fallback_preserves_audit_and_scoped_commit(partial, expected):
    committed = []
    def primary(rt, a):
        raise Fault('UNAVAILABLE', 'unavailable')
    def mirror(rt, a):
        rt.commit_scope.actions['observation'] = lambda: committed.append(1)
        return Adapted([1, 2], {'incomplete': partial})
    contract = {'version': 1, 'params': {'revision': 'Text'}, 'result': 'List<Number>', 'effects': ['read_external']}
    registry = {'t:primary': Adapter(contract, primary), 't:mirror': Adapter(contract, mirror)}
    source = 'return [t:primary]{revision:"r1"} ?? [t:mirror]{revision:"r1"}'
    completion = [{'id': 'rows', 'predicate': '$value == [1,2]',
                   'sources': [{'action': 't:mirror', 'targets': {'revision': 'r1'}}]}]
    out = Runtime(compile_program(source, registry), completion=completion).run()
    assert out['success'] and not out['source_complete']
    assert any(e['kind'] == 'tool_failure' for e in out['evidence'])
    assert out['completion']['status'] == expected, out
    assert bool(committed) is (expected == 'satisfied')


def test_business_json_cannot_certify_completion():
    spec = [{'id': 'rows', 'predicate': '$value.complete', 'sources': [{'action': 't:source', 'targets': {}}]}]
    out = Runtime(compile_program('return {complete:true}'), completion=spec).run()
    assert out['completion']['status'] == 'undetermined'


def test_effectful_completion_predicate_rejected():
    with pytest.raises(Fault):
        Runtime(compile_program('return 1'), completion=[{'id': 'x', 'predicate': '[t:write]{}',
                                                        'sources': [{'action': 't:source', 'targets': {}}]}])


def test_discarded_source_cannot_certify_literal_result():
    contract = {'version': 1, 'params': {}, 'result': 'Number', 'effects': ['read_external']}
    registry = {'t:source': Adapter(contract, lambda rt, a: 2)}
    spec = [{'id': 'x', 'predicate': '$value == 2', 'sources': [{'action': 't:source', 'targets': {}}]}]
    out = Runtime(compile_program('[t:source]{}; return 2', registry), completion=spec).run()
    assert out['completion']['status'] == 'undetermined'
    assert any(e['kind'] == 'invoke' for e in out['evidence'])



def test_completion_cannot_reset_shared_execution_budget():
    from ibl_v2_runtime import Budget
    spec = [{'id': 'x', 'predicate': 'len(map($value,($x)=>$x+1)) == 80',
             'sources': [{'action': 't:source', 'targets': {}}]}]
    registry = {'t:source': Adapter({'version': 1, 'params': {}, 'result': 'List<Number>',
                                    'effects': ['read_external']}, lambda rt, a: list(range(80)))}
    budget = Budget(steps=60)
    out = Runtime(compile_program('return [t:source]{}', registry), completion=spec, budget=budget).run()
    assert out['completion']['status'] == 'undetermined'
    assert budget.used_steps > 60


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__]))


def scoped_registry(committed):
    def good(rt, a):
        rt.commit_scope.actions['good'] = lambda: committed.append('good')
        return 2
    def partial(rt, a):
        rt.commit_scope.actions['partial'] = lambda: committed.append('partial')
        return Adapted(7, {'incomplete': True})
    contract = {'version': 1, 'params': {}, 'result': 'Number', 'effects': ['read_external']}
    return {'t:good': Adapter(contract, good), 't:partial': Adapter(contract, partial)}


def duty(name, predicate, action, **kwargs):
    return {'id': name, 'predicate': predicate, 'sources': [{'action': action, 'targets': {}}], **kwargs}


@pytest.mark.parametrize('prefix,expression,path', [
    ('', '{good:[t:good]{},other:[t:partial]{}}', '.good'),
    ('[def:f]($x){return $x};', '[fn:f]{x:{good:[t:good]{},other:[t:partial]{}}}', '.good'),
    ('', '(($x)=>$x)({good:[t:good]{},other:[t:partial]{}})', '.good'),
    ('', '[{good:[t:good]{},other:[t:partial]{}}]', '[0].good'),
    ('', 'get({box:{good:[t:good]{},other:[t:partial]{}}},"box")', '.good'),
    ('', 'unwrap(([table:each]{items:[1],on_error:"collect"}{return {good:[t:good]{},other:[t:partial]{}}})[0])', '.good'),
])
def test_independent_obligations_survive_component_boundaries(prefix, expression, path):
    committed = []
    registry = scoped_registry(committed)
    spec = [duty('good', '$value' + path + '==2', 't:good'),
            duty('other', 'true', 't:partial', required=False)]
    out = Runtime(compile_program(prefix + 'return ' + expression, registry), completion=spec).run()
    assert out['success'] and out['source_complete'] is False, out
    assert [o['status'] for o in out['completion']['obligations']] == ['satisfied', 'undetermined'], out
    assert out['completion']['status'] == 'satisfied'
    assert committed == ['good']
    assert any(e.get('incomplete') for e in out['evidence'])


def test_explicit_scope_has_scoped_value_and_hash():
    committed = []
    reg = scoped_registry(committed)
    spec = [duty('good', '$value==2', 't:good', scope=['good'])]
    out = Runtime(compile_program('return {good:[t:good]{},other:[t:partial]{}}', reg), completion=spec).run()
    from ibl_v2_ir import digest, pack
    assert out['completion']['status'] == 'satisfied', out
    assert out['completion']['obligations'][0]['value_hash'] == digest(pack(2))
    assert committed == ['good']


@pytest.mark.parametrize('source', [
    '$good=[t:good]{};$condition=[t:partial]{};return $condition>0 ? {good:$good} : {good:0}',
    'return {good:[t:partial]{},other:[t:good]{}}',
])
def test_scoped_completion_cannot_drop_control_or_substitute_wrong_source(source):
    committed = []
    out = Runtime(compile_program(source, scoped_registry(committed)),
                  completion=[duty('good', '$value>0', 't:good', scope=['good'])]).run()
    assert out['completion']['status'] == 'undetermined', out
    assert committed == []


def test_public_post_effect_wire_failure_preserves_receipt_and_resume(tmp_path, monkeypatch):
    from ibl_v2_entry import handle_request
    calls = []
    reg = {'t:send': Adapter({'version': 1, 'params': {}, 'result': 'Number', 'effects': ['write_external']},
                             lambda rt, a: calls.append(1) or 1)}
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **kw: reg)
    monkeypatch.setattr('ibl_v2_store.definitions', lambda: {})
    monkeypatch.setattr('tool_batch.prepared_plan', lambda *a: None)
    monkeypatch.setattr('ibl_run_journal.journal_root', lambda *a: tmp_path / 'runs')
    request = {'edition': 2, 'code': '[t:send]{};return [table:each]{items:[1]}{return abs}',
               'completion': [duty('sent', 'true', 't:send')]}
    out = handle_request(request, str(tmp_path))
    assert out['executed'] and not out['success'], out
    assert out['diagnostic']['code'] == 'VALUE_PROTOCOL'
    assert out['completion']['status'] == 'undetermined' and out['resume']
    assert any(e.get('action') == 't:send' for e in out['evidence'])
    resumed = handle_request({**request, 'resume': out['resume']}, str(tmp_path))
    assert resumed['executed'] and calls == [1], resumed


def test_completion_infrastructure_fault_preserves_execution(monkeypatch):
    def fail(*args):
        raise RuntimeError('synthetic evaluator fault')
    monkeypatch.setattr('ibl_v2_completion.evaluate', fail)
    calls = []
    reg = {'t:send': Adapter({'version': 1, 'params': {}, 'result': 'Number', 'effects': ['write_external']},
                             lambda rt, a: calls.append(1) or 1)}
    out = Runtime(compile_program('return [t:send]{}', reg), completion=[duty('sent', 'true', 't:send')]).run()
    assert out['executed'] and out['success'] and out['value'] == 1
    assert out['completion']['status'] == 'undetermined'
    assert out['completion']['diagnostic']['code'] == 'COMPLETION_EVALUATION'
    assert calls == [1] and out['evidence']


def test_stored_function_preserves_selected_completion_evidence():
    committed = []
    source = '[def:bundle]($x){return {box:$x}}'
    code = 'return [fn:bundle]{x:{good:[t:good]{},other:[t:partial]{}}}'
    out = Runtime(compile_program(code, scoped_registry(committed), definitions={'bundle': source}),
                  completion=[duty('good', '$value==2', 't:good', scope=['box', 'good'])]).run()
    assert out['completion']['status'] == 'satisfied', out
    assert committed == ['good']


@pytest.mark.parametrize('selection,expected', [('good', 'satisfied'), ('other', 'undetermined')])
def test_certified_reference_relocation_is_bound_to_original_scope(selection, expected):
    from model_result_view import input_ref_evidence
    contract = {'version': 1, 'params': {}, 'result': 'Number', 'effects': ['read_external']}
    # Identical values from different sources must not launder the certificate.
    reg = {'t:good': Adapter(contract, lambda rt, a: 2),
           't:other': Adapter(contract, lambda rt, a: Adapted(2, {'incomplete': True}))}
    original = Runtime(compile_program('return {good:[t:good]{},other:[t:other]{}}', reg),
                       completion=[duty('good', '$value==2', 't:good', scope=['good'])]).run()
    assert original['completion']['status'] == 'satisfied'
    evidence = {'name': 'x', 'path': ['value'], 'evidence': input_ref_evidence(original)}
    inputs = {'x': original['value']}
    out = Runtime(compile_program('return {moved:$x.' + selection + '}', inputs=inputs), inputs,
                  input_evidence={'x': evidence},
                  completion=[duty('new-id', '$value==2', 't:good', scope=['moved'])]).run()
    assert out['completion']['status'] == expected, out
    assert out['source_complete'] is False


def test_nested_reference_keeps_part_coordinates():
    from model_result_view import input_ref_evidence
    reg = scoped_registry([])
    first = Runtime(compile_program('return {good:[t:good]{},other:[t:partial]{}}', reg),
                    completion=[duty('good', '$value==2', 't:good', scope=['good'])]).run()
    inputs = {'x': {'wrapped': first['value']}}
    evidence = {'refs': [{'name': 'x', 'at': ['wrapped'], 'path': ['value'],
                         'evidence': input_ref_evidence(first)}]}
    out = Runtime(compile_program('return $x', inputs=inputs), inputs, input_evidence={'x': evidence},
                  completion=[duty('moved', '$value==2', 't:good', scope=['wrapped', 'good'])]).run()
    assert out['completion']['status'] == 'satisfied', out


@pytest.mark.parametrize('tail', [
    'return map([$bundle],($x)=>{good:$x.good})',
    'return [$bundle][0:1]',
    '$pick=()=>{good:$bundle.good};return [$pick()]',
])
def test_value_transformations_keep_component_provenance(tail):
    committed = []
    code = '$bundle={good:[t:good]{},other:[t:partial]{}};' + tail
    out = Runtime(compile_program(code, scoped_registry(committed)),
                  completion=[duty('good', '$value==2', 't:good', scope=[0, 'good'])]).run()
    assert out['completion']['status'] == 'satisfied', out
    assert committed == ['good']


def test_public_late_journal_error_never_becomes_not_executed(tmp_path, monkeypatch):
    from ibl_v2_entry import handle_request
    from ibl_run_journal import Journal
    calls = []
    reg = {'t:send': Adapter({'version': 1, 'params': {}, 'result': 'Number', 'effects': ['write_external']},
                             lambda rt, a: calls.append(1) or 1)}
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **kw: reg)
    monkeypatch.setattr('ibl_v2_store.definitions', lambda: {})
    monkeypatch.setattr('tool_batch.prepared_plan', lambda *a: None)
    monkeypatch.setattr('ibl_run_journal.journal_root', lambda *a: tmp_path / 'runs')
    def broken(*args):
        raise OSError('synthetic journal finalization failure')
    monkeypatch.setattr(Journal, 'complete', broken)
    out = handle_request({'edition': 2, 'code': 'return [t:send]{}'}, str(tmp_path))
    assert out['executed'] and not out['success'] and calls == [1], out
    assert out['resume'] and out['evidence'] and out['value'] == 1
    assert out['diagnostic']['code'] == 'EXECUTION_FINALIZATION'


@pytest.mark.parametrize('tail', [
    'return [table:each]{items:$rows}{return $good}',
    'return map($rows,($x)=>$good)',
    'return map($rows[0:1],($x)=>$good)',
    'return filter(map($rows,($x)=>$good),($x)=>true)',
])
def test_partial_iteration_coverage_is_not_erased_by_constant_callback(tail):
    contract = {'version': 1, 'params': {}, 'result': 'Number', 'effects': ['read_external']}
    reg = {'t:good': Adapter(contract, lambda rt, a: 2),
           't:rows': Adapter({**contract, 'result': 'List<Number>'},
                             lambda rt, a: Adapted([1], {'incomplete': True}))}
    source = '$good=[t:good]{};$rows=[t:rows]{};' + tail
    out = Runtime(compile_program(source, reg), completion=[duty('x', 'len($value)==1', 't:good', scope=[])]).run()
    assert out['success'] and out['completion']['status'] == 'undetermined', out


def test_missing_key_fallback_keeps_structural_source_dependency():
    contract = {'version': 1, 'params': {}, 'result': 'Number', 'effects': ['read_external']}
    reg = {'t:good': Adapter(contract, lambda rt, a: 2),
           't:record': Adapter({**contract, 'result': 'Record'},
                               lambda rt, a: Adapted({}, {'incomplete': True}))}
    source = '$good=[t:good]{};$record=[t:record]{};return get($record,"missing",$good)'
    out = Runtime(compile_program(source, reg), completion=[duty('x', '$value==2', 't:good')]).run()
    assert out['completion']['status'] == 'undetermined', out


@pytest.mark.parametrize('rows', [[], [1]])
def test_reduce_retains_iteration_coverage_when_callback_ignores_rows(rows):
    contract = {'version': 1, 'params': {}, 'result': 'Number', 'effects': ['read_external']}
    reg = {'t:good': Adapter(contract, lambda rt, a: 2),
           't:rows': Adapter({**contract, 'result': 'List<Number>'},
                             lambda rt, a: Adapted(rows, {'incomplete': True}))}
    code = '$good=[t:good]{};$rows=[t:rows]{};return reduce($rows,$good,($a,$x)=>$a)'
    out = Runtime(compile_program(code, reg), completion=[duty('x', '$value==2', 't:good')]).run()
    assert out['success'] and out['completion']['status'] == 'undetermined', out
