"""Independent module-boundary acceptance, including post-publication changes."""
import boot_paths  # noqa: F401
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from ibl_v2_adapters import Adapter, load_registry
from ibl_v2_compile import compile_program, Compiler
from ibl_v2_ir import Fault
from ibl_v2_runtime import Runtime
from ibl_v2_types import Type, NUMBER, TEXT


@pytest.fixture
def abilities(tmp_path, monkeypatch):
    import function_store
    from function_library import validate_changes
    from ibl_dependencies import script_contract
    reg = {k: v for k, v in load_registry().items() if k in ('table:filter', 'table:select', 'table:sort')}
    calls = []
    row = {'id': 'Text', 'score': 'Number', 'source': 'Text', '$closed': True}
    raw_row = {**row, 'score': 'Text'}
    # External providers declare their boundary. Ordinary IBL authors only write functions.
    reg['probe:read'] = Adapter({'version': 1, 'params': {'source': 'Text'},
        'result': {'items': {'$list': raw_row}, 'origin': 'Text', '$closed': True},
        'effects': ['read_external'], 'read_resources': {'source': 'source'}},
        lambda rt, a: calls.append(('read', a['source'])) or {
            'items': [{'id': 'a', 'score': '2', 'source': a['source']},
                      {'id': 'b', 'score': '5', 'source': a['source']}], 'origin': a['source']})
    path = Path(__file__).resolve().parents[1] / 'data/packages/installed/tools/system_essentials/script_ops.py'
    spec = importlib.util.spec_from_file_location('semantic_script_test', path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    (tmp_path / 'normalize.py').write_text(
        'import json,sys\nr=json.load(sys.stdin)["args"]["data"]\n'
        'rows=[{**v,"score":int(v["score"])} for v in r]\n'
        'print(json.dumps({"protocol":"ibl-script/2","ok":True,"value":rows}))\n')
    contract = {'version': 1, 'params': {'data': {'$list': raw_row}}, 'result': {'$list': row},
                'effects': ['pure'], 'adapter': {'protocol': 'ibl-script/2'},
                'completion': [{'id': 'normalized', 'predicate': 'len($value)==2',
                    'sources': [{'action': 'probe:python', 'targets': {'id': 'normalize'}}]}]}
    scripts = {'normalize': {'file': 'normalize.py', 'interpreter': 'python', 'callable_contract': contract}}
    monkeypatch.setattr(runner, '_read_registry', lambda: scripts)
    monkeypatch.setattr(runner, '_SCRIPT_DIR', tmp_path)
    monkeypatch.setattr(runner, '_RUN_DIR', tmp_path / 'runs')
    monkeypatch.setattr(runner, '_update_state', lambda *a, **k: None)
    monkeypatch.setattr(runner, '_resolve_interpreter', lambda *a: (sys.executable, None))
    monkeypatch.setattr('ibl_dependencies._script_registry', lambda path: scripts)

    def normalize(rt, args):
        calls.append(('script', args['id']))
        result = runner.op_run({**args, '_ibl_edition': 2})
        assert result['success'], result
        return result['value']

    reg['probe:python'] = Adapter({'version': 1, 'params': {'id': 'Text', 'args': 'Record'},
        'result': 'Unknown', 'effects': ['unknown'], 'adapter': {'protocol': 'ibl-script/2'}},
        normalize, specialize=script_contract)
    reg['probe:publish'] = Adapter({'version': 1, 'params': {'items': 'List'},
        'result': 'Number', 'effects': ['write_external']},
        lambda rt, a: calls.append(('publish', a['items'])) or len(a['items']))
    original = function_store._root_provider, function_store._validator, function_store._registrar
    function_store.wire(lambda **_: tmp_path / 'functions', validate_changes, None)
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a, **k: reg)
    monkeypatch.setattr('function_consumers.stored_programs', lambda: [])
    monkeypatch.setattr('tool_batch.prepared_plan', lambda *a: None)
    try:
        yield reg, calls, scripts
    finally:
        function_store.wire(*original)


GATHER = '''[def:gather]($sources,$read,$normalize,$policy){
return [table:each]{items:$sources,on_error:"collect"}{
$raw=$read{source:$it};
$rows=$normalize{data:$raw.items};
$selected=[table:filter]{items:$rows,where:$policy};
return {source:$raw.origin,rows:$selected}
}}'''
NORMALIZE = '[def:normalizer]($data){return [probe:python]{id:"normalize",args:{data:$data}}}'
DECIDE = '''[def:decide]($sources,$read,$normalize,$policy){
return {evidence:[fn:gather]{sources:$sources,read:$read,normalize:$normalize,policy:$policy}}
}'''
RECHECK = '''[def:recheck]($sources,$read,$normalize,$policy,$previous){
return {now:[fn:decide]{sources:$sources,read:$read,normalize:$normalize,policy:$policy},previous:$previous}
}'''


def save_layers():
    from function_library import register
    for name, source in [('normalizer', NORMALIZE), ('gather', GATHER), ('decide', DECIDE), ('recheck', RECHECK)]:
        register(name, '#!ibl edition=2\n' + source, edition=2)


def query(name='recheck', read='probe:read', policy='($r)=>$r.score>3'):
    extra = ',previous:{baseline:7}' if name == 'recheck' else ''
    return f'return [fn:{name}]{{sources:["catalog"],read:&[{read}],normalize:&[fn:normalizer],policy:{policy}{extra}}}'


def test_vertical_saved_interfaces_without_lower_body_analysis(abilities, monkeypatch):
    reg, calls, _ = abilities
    save_layers()
    from function_library import definitions
    library = definitions()
    assert set(library.interfaces) == {'normalizer', 'gather', 'decide', 'recheck'}, library.interface_limits
    assert calls == []
    original = Compiler._function
    monkeypatch.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body analysis'))
    plan = compile_program(query(), reg, definitions=library.interfaces_only())
    assert not plan.issues, plan.report()
    now = dict(plan.result_type.fields)['now']
    collected = dict(now.fields)['evidence'].item
    assert collected.kind == 'Result'
    row = dict(dict(collected.item.fields)['rows'].item.fields)
    assert row == {'id': TEXT, 'score': NUMBER, 'source': TEXT}, row
    assert plan.effects - {'pure'} == {'read_external'}
    assert calls == []
    monkeypatch.setattr(Compiler, '_function', original)
    plan.definitions = library
    result = Runtime(plan).run()
    assert result['success'], result
    assert calls == [('read', 'catalog'), ('script', 'normalize')]
    assert result['value']['previous'] == {'baseline': 7}
    assert result['component_completion']['status'] == 'satisfied'


def test_new_request_and_provider_after_storage_need_no_core_names(abilities, monkeypatch):
    reg, calls, scripts = abilities
    save_layers()
    from function_library import definitions
    # Created only after publication: unrelated name, additional row column.
    reg['files:inventory'] = Adapter({'version': 1, 'params': {'source': 'Text'},
        'result': {'items': {'$list': {
            'id': 'Text', 'score': 'Number', 'source': 'Text', 'bytes': 'Number'}}, 'origin': 'Text'},
        'effects': ['read_external']}, lambda rt, a: {'items': [], 'origin': a['source']})
    monkeypatch.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body analysis'))
    good = compile_program(query(read='files:inventory', policy='($r)=>$r.score>4'), reg, definitions=definitions())
    assert not good.issues, good.report()
    bad = compile_program(query(policy='($r)=>$r.missing>4'), reg, definitions=definitions())
    assert any(i['code'] == 'MISSING_FIELD' for i in bad.issues), bad.report()
    assert calls == []


def test_returned_capability_substitutes_captures(abilities, monkeypatch):
    from function_library import register, definitions
    reg, _, _ = abilities
    register('threshold', '#!ibl edition=2\n[def:threshold]($cut){return ($r)=>$r.score>$cut}', edition=2)
    monkeypatch.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body analysis'))
    plan = compile_program('$p=[fn:threshold]{cut:3};return filter([{score:4}],$p)', reg, definitions=definitions())
    assert not plan.issues, plan.report()
    assert dict(plan.result_type.item.fields)['score'].kind == 'Number'


def test_new_upper_definition_uses_bodyless_lower_interfaces(abilities, monkeypatch):
    from function_library import register, definitions
    from ibl_v2_store import Library
    reg, calls, _ = abilities
    save_layers()
    original = Library.__getitem__

    def no_lower_source(library, name):
        if name in library.interfaces:
            pytest.fail('authoring requested a lower implementation: ' + name)
        return original(library, name)

    monkeypatch.setattr(Library, '__getitem__', no_lower_source)
    register('audit', '#!ibl edition=2\n[def:audit]($sources,$read,$normalize,$policy){'
             'return {decision:[fn:decide]{sources:$sources,read:$read,normalize:$normalize,policy:$policy}}}', edition=2)
    assert 'audit' in definitions().interfaces
    assert calls == []


def test_post_publication_script_replacement_preserves_new_columns(abilities, monkeypatch):
    from function_library import register, definitions
    reg, calls, scripts = abilities
    save_layers()
    fields = {'id': 'Text', 'score': 'Number', 'source': 'Text', 'bytes': 'Number', '$closed': True}
    scripts['later'] = {**scripts['normalize'], 'callable_contract': {
        **scripts['normalize']['callable_contract'], 'params': {'data': {'$list': fields}},
        'result': {'$list': fields}, 'completion': []}}
    reg['files:scan'] = Adapter({'version': 1, 'params': {'source': 'Text'},
        'result': {'items': {'$list': fields}, 'origin': 'Text'}, 'effects': ['read_external']},
        lambda rt, a: {'items': [{'id': 'f', 'score': 9, 'source': a['source'], 'bytes': 20}], 'origin': a['source']})
    register('later_normalizer', '#!ibl edition=2\n[def:later_normalizer]($data){'
             'return [probe:python]{id:"later",args:{data:$data}}}', edition=2)
    source = query(read='files:scan', policy='($r)=>$r.bytes>10').replace('&[fn:normalizer]', '&[fn:later_normalizer]')
    library = definitions()
    with monkeypatch.context() as blocked:
        blocked.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body analysis'))
        plan = compile_program(source, reg, definitions=library.interfaces_only())
    assert not plan.issues, plan.report()
    now = dict(plan.result_type.fields)['now']
    evidence = dict(now.fields)['evidence'].item.item
    assert dict(dict(evidence.fields)['rows'].item.fields)['bytes'] == NUMBER
    plan.definitions = library
    result = Runtime(plan).run()
    assert result['success'], result
    assert calls == [('script', 'later')]


def test_effect_parameter_completion_partial_failure_and_repair(abilities, tmp_path):
    from function_library import register, definitions
    from ibl_v2_entry import handle_request
    from ibl_v2_ir import unpack
    reg, calls, scripts = abilities
    save_layers()
    register('deliver', '#!ibl edition=2\n[def:deliver]($writer,$items){return $writer{items:$items}}', edition=2)
    interface = definitions().interfaces['deliver']
    assert interface['effects'] and 'probe:publish' not in json.dumps(interface)
    code = '$r=[fn:gather]{sources:["catalog"],read:&[probe:read],normalize:&[fn:normalizer],policy:($r)=>$r.score>3};'
    code += '$sent=[fn:deliver]{writer:&[probe:publish],items:$r};return 10/$n'
    checked = compile_program(code, reg, inputs={'n': 0}, definitions=definitions().interfaces_only())
    assert not checked.issues and 'write_external' in checked.effects, checked.report()
    assert calls == []
    first = handle_request({'edition': 2, 'code': code, 'inputs': {'n': 0}}, str(tmp_path))
    assert not first['success'], first
    assert first['component_completion']['status'] == 'satisfied', first
    assert sum(c[0] == 'publish' for c in calls) == 1
    fixed = {'edition': 2, 'code': code.replace('10/$n', '10/($n+1)'), 'inputs': {'n': 0},
             'repair': {'run_id': first['resume']['run_id']}}
    check = handle_request({**fixed, 'check': True}, str(tmp_path))
    assert check.get('ok'), check
    fixed['repair']['plan_hash'] = check['repair']['plan_hash']
    repaired = handle_request(fixed, str(tmp_path))
    assert repaired['success'] and repaired['value'] == 10, repaired
    assert sum(c[0] == 'publish' for c in calls) == 1

    def failed_read(rt, args):
        raise Fault('SOURCE_UNAVAILABLE', 'source unavailable')

    reg['other:missing'] = Adapter(reg['probe:read'].contract, failed_read)
    failed = Runtime(compile_program(query('gather', read='other:missing'), reg, definitions=definitions())).run()
    values = unpack(failed['value_wire']['data'])
    assert failed['success'] and len(values) == 1 and not values[0].ok


def test_foreign_value_lifetime_and_unknown_effect_are_not_erased(abilities):
    from function_library import register, definitions
    reg, calls, _ = abilities
    register('box', '#!ibl edition=2\n[def:box]($value){return {inside:$value}}', edition=2)
    plan = compile_program('return [fn:box]{value:$ref}', reg, definitions=definitions().interfaces_only(),
                           input_types={'ref': Type('ForeignRef')}, value_protocols=['ibl-value/1'])
    assert any(i['code'] == 'VALUE_PROTOCOL' for i in plan.issues), plan.report()
    register('apply_unknown', '#!ibl edition=2\n[def:apply_unknown]($f){return $f{}}', edition=2)
    plan = compile_program('return [fn:apply_unknown]{f:$f}', reg, definitions=definitions().interfaces_only(),
                           input_types={'f': Type('Callable')})
    assert 'unknown' in plan.effects and plan.guards
    assert calls == []


def test_discarded_computation_keeps_input_obligations(abilities):
    from function_library import register, definitions
    reg, calls, _ = abilities
    register('validate', '#!ibl edition=2\n[def:validate]($x){$unused=$x.required+1;return "ok"}', edition=2)
    bad = compile_program('return [fn:validate]{x:{other:3}}', reg, definitions=definitions().interfaces_only())
    assert any(i['code'] == 'MISSING_FIELD' for i in bad.issues), bad.report()
    assert calls == []


def test_direct_and_two_promotions_match_independent_value_oracle(abilities):
    from function_library import definitions
    from ibl_v2_ir import unpack
    reg, calls, _ = abilities
    save_layers()
    expected = {'source': 'catalog', 'rows': [{'id': 'b', 'score': 5, 'source': 'catalog'}]}
    for name in ('gather', 'decide', 'recheck'):
        plan = compile_program(query(name), reg, definitions=definitions())
        output = Runtime(plan).run()
        assert output['success'], output
        result = unpack(output['value_wire']['data'])
        if name == 'recheck':
            assert result['previous'] == {'baseline': 7}
            result = result['now']
        if name != 'gather':
            result = result['evidence']
        assert len(result) == 1 and result[0].ok and result[0].value == expected
    direct = Runtime(compile_program(NORMALIZE + ';' + GATHER + ';' + query('gather'), reg)).run()
    result = unpack(direct['value_wire']['data'])
    assert direct['success'] and result[0].value == expected
    assert calls == [('read', 'catalog'), ('script', 'normalize')] * 4


def test_execution_lowering_preserves_snapshot_before_any_effect(abilities):
    from function_library import register, definitions
    reg, calls, _ = abilities
    asset = {'revision': 1}
    reg['probe:versioned'] = Adapter({'version': 1, 'params': {}, 'result': 'Number',
        'effects': ['read_external']}, lambda rt, a: calls.append(('versioned', 1)) or 1,
        dependency=lambda args: dict(asset))
    register('versioned', '#!ibl edition=2\n[def:versioned](){return [probe:versioned]{}}', edition=2)
    source = '[probe:publish]{items:[]};return [fn:versioned]{}'
    checked = compile_program(source, reg, definitions=definitions())
    assert Runtime(checked).plan.fingerprint == checked.fingerprint
    assert calls == []
    asset['revision'] = 2
    with pytest.raises(Fault, match='의존 판본') as rejected:
        Runtime(checked)
    assert rejected.value.code == 'DEFINITION_CHANGED' and calls == []


def test_lowering_keeps_unspecified_input_and_exact_decimal_defaults(abilities):
    from decimal import Decimal
    from function_library import register, definitions
    from ibl_v2_ir import unpack
    reg, _, _ = abilities
    register('discount', '#!ibl edition=2\n[def:discount]($rate=0.9){return $rate}', edition=2)
    plan = compile_program('return [fn:discount]{rate:$rate}', reg, definitions=definitions(),
                           declared_inputs=['rate'])
    result = Runtime(plan).run()
    assert result['success'] and unpack(result['value_wire']['data']) == Decimal('0.9'), result


def test_pinned_dependency_interfaces_survive_current_revision_change(abilities, monkeypatch):
    from function_library import register, definitions, reference_library
    reg, _, _ = abilities
    old = register('leaf', '#!ibl edition=2\n[def:leaf]($x){return $x+1}', edition=2)
    register('wrapper', '#!ibl edition=2\n[def:wrapper]($x){return [fn:leaf]{x:$x}}', edition=2)
    plan = compile_program('return [fn:wrapper]{x:1}', reg, definitions=definitions())
    register('leaf', '#!ibl edition=2\n[def:leaf]($x){return $x+2}', edition=2, expected_revision=old['revision'])
    pinned = reference_library(plan.dependencies['function_refs'])
    assert set(pinned.interfaces) == {'wrapper', 'leaf'}
    with monkeypatch.context() as blocked:
        blocked.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('pinned body analysis'))
        checked = compile_program('return [fn:wrapper]{x:1}', reg, definitions=pinned.interfaces_only())
    checked.definitions = pinned
    assert Runtime(checked).run()['value'] == 2


def test_publication_replaces_supplied_semantic_json(abilities):
    import function_store
    from function_library import definitions
    from ibl_v2_semantic import derive
    from uuid import uuid4
    reg, calls, _ = abilities
    source = '#!ibl edition=2\n[def:honest](){return 41}'
    forged = derive(source.replace('41', '42'))
    result = function_store.publish([{'record': {
        'schema': 1, 'function_id': uuid4().hex, 'name': 'honest', 'edition': 2,
        'source': source, 'description': '', 'origin': 'user', 'semantic_interface': forged},
        'expected_revision': None}])
    ref = result['functions'][0]
    stored = function_store.revision(ref['function_id'], ref['revision'])
    assert stored['semantic_interface'] != forged
    assert Runtime(compile_program('return [fn:honest]{}', reg, definitions=definitions())).run()['value'] == 41
    assert calls == []


def test_resource_relation_survives_stored_string_composition(abilities):
    from function_library import register, definitions
    reg, calls, _ = abilities
    reg['archive:write'] = Adapter({'version': 1, 'params': {'path': 'Text'}, 'result': 'Number',
        'effects': ['write_external'], 'write_resources': {'file': 'path'}}, lambda rt, a: 1)
    register('archive', '#!ibl edition=2\n[def:archive]($folder){return [archive:write]{path:$folder+"/result"}}', edition=2)
    library = definitions().interfaces_only()
    safe = compile_program('[fn:archive]{folder:"a"} & [fn:archive]{folder:"b"}', reg, definitions=library)
    assert not safe.issues and all(a.resources for a in safe.accesses), safe.report()
    conflict = compile_program('[fn:archive]{folder:"a"} & [fn:archive]{folder:"a"}', reg, definitions=library)
    assert any(i['code'] == 'PARALLEL_WRITE_CONFLICT' for i in conflict.issues), conflict.report()
    assert calls == []


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
