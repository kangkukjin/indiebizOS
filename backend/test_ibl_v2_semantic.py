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



@pytest.mark.parametrize('row,expected', [({}, 0), ({'score': None}, 0), ({'score': 7}, 14)])
def test_conditional_policy_survives_two_stored_promotions(abilities, monkeypatch, row, expected):
    from function_library import register, definitions
    reg, calls, _ = abilities
    policy = '[def:safe]($row,$policy){return has($row,"score") && $row.score != null ? $policy($row.score) : 0}'
    upper = '[def:report]($row,$policy){return {row:$row,value:[fn:safe]{row:$row,policy:$policy}}}'
    again = '[def:review]($row,$policy){return {now:[fn:report]{row:$row,policy:$policy},before:$row}}'
    for name, source in [('safe', policy), ('report', upper), ('review', again)]:
        register(name, '#!ibl edition=2\n' + source, edition=2)
    library = definitions()
    assert set(library.interfaces) == {'safe', 'report', 'review'}, library.interface_limits
    code = 'return [fn:review]{row:$row,policy:($v)=>$v*2}'
    with monkeypatch.context() as blocked:
        blocked.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body analysis'))
        plan = compile_program(code, reg, inputs={'row': row}, definitions=library.interfaces_only())
    assert not plan.issues, plan.report()
    assert calls == []
    plan.definitions = library
    result = Runtime(plan, inputs={'row': row}).run()
    assert result['success'], result
    oracle = {'now': {'row': row, 'value': expected}, 'before': row}
    assert result['value'] == oracle
    # Direct construction and one saved promotion use the same independent oracle.
    direct = policy + upper + again + code
    first = policy + upper + 'return {now:[fn:report]{row:$row,policy:($v)=>$v*2},before:$row}'
    for candidate in (direct, first):
        checked = compile_program(candidate, reg, inputs={'row': row})
        assert not checked.issues, checked.report()
        executed = Runtime(checked, {'row': row}).run()
        assert executed['success'] and executed['value'] == oracle, executed


def test_statement_branches_preserve_returns_bindings_and_effect_choice(abilities, monkeypatch):
    from function_library import register, definitions
    from ibl_v2_types import BOOL, UNKNOWN
    reg, calls, _ = abilities
    source = '[def:dispatch]($enabled,$items,$send){[if:$enabled]{$n=$send{items:$items};return {sent:$n}};return {skipped:$items}}'
    register('dispatch', '#!ibl edition=2\n' + source, edition=2)
    lib = definitions()
    assert 'dispatch' in lib.interfaces, lib.interface_limits
    for enabled, effects in [(False, set()), (True, {'write_external'})]:
        code = 'return [fn:dispatch]{enabled:$enabled,items:[1],send:&[probe:publish]}'
        with monkeypatch.context() as blocked:
            blocked.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body analysis'))
            plan = compile_program(code, reg, inputs={'enabled': enabled}, definitions=lib.interfaces_only())
        assert not plan.issues, plan.report()
        assert plan.effects - {'pure'} == effects
        assert set(dict(plan.result_type.fields)) == ({'sent'} if enabled else {'skipped'})
        plan.definitions = lib
        result = Runtime(plan, inputs={'enabled': enabled}).run()
        assert result['success'], result
        assert result['value'] == ({'sent': 1} if enabled else {'skipped': [1]})
    assert len(calls) == 1
    uncertain = compile_program('return [fn:dispatch]{enabled:$enabled,items:[1],send:$send}', reg,
        input_types={'enabled': BOOL, 'send': UNKNOWN}, definitions=lib.interfaces_only())
    assert 'unknown' in uncertain.effects

    branching = '[def:assigned]($enabled,$r){[if:$enabled]{$v=$r.left}[else]{$v=$r.right};return {v:$v,original:$r}}'
    register('assigned', '#!ibl edition=2\n' + branching, edition=2)
    plan = compile_program('return [fn:assigned]{enabled:true,r:{left:7,right:"other"}}', reg,
                           definitions=definitions().interfaces_only())
    assert not plan.issues, plan.report()
    assert dict(plan.result_type.fields)['v'].kind == 'Number'


@pytest.mark.parametrize('wrapped', [False, True])
def test_conditional_call_requirements_stay_conditional_and_pure(abilities, wrapped):
    from function_library import register, definitions
    reg, calls, _ = abilities
    expr = 'has($r,"score") ? $f{items:$r.score} : 0'
    source = '[def:optional]($r,$f){return ' + ('{value:' + expr + '}' if wrapped else expr) + '}'
    register('optional', '#!ibl edition=2\n' + source, edition=2)
    lib = definitions().interfaces_only()
    good = compile_program('return [fn:optional]{r:{},f:&[probe:publish]}', reg, definitions=lib)
    assert not good.issues and not (good.effects - {'pure'}), good.report()
    good.definitions = definitions()
    out = Runtime(good).run()
    assert out['success'] and out['value'] == ({'value': 0} if wrapped else 0), out
    bad = compile_program('return [fn:optional]{r:{score:[1]},f:&[probe:publish]}', reg, definitions=lib)
    assert any(i['code'] == 'PURE_EXPRESSION' for i in bad.issues), bad.report()
    assert calls == []


def test_conditional_numeric_and_projection_requirements_survive_storage(abilities):
    from function_library import register, definitions
    reg, _, _ = abilities
    source = '[def:head]($rows){return len($rows)==0 ? null : $rows[0].score*2}'
    register('head', '#!ibl edition=2\n' + source, edition=2)
    lib = definitions().interfaces_only()
    good = compile_program('return [fn:head]{rows:[{score:3}]}', reg, definitions=lib)
    assert not good.issues, good.report()
    empty = compile_program('return [fn:head]{rows:[]}', reg, definitions=lib)
    assert not empty.issues and empty.result_type.kind == 'Null', empty.report()
    bad = compile_program('return [fn:head]{rows:[{other:3}]}', reg, definitions=lib)
    assert any(i['code'] == 'MISSING_FIELD' for i in bad.issues), bad.report()


def test_conditional_saved_effect_repairs_without_repeating_publication(abilities, tmp_path):
    from function_library import register, definitions
    from ibl_v2_entry import handle_request
    reg, calls, _ = abilities
    save_layers()
    source = '[def:maybe_send]($enabled,$writer,$items){[if:$enabled]{return $writer{items:$items}};return 0}'
    register('maybe_send', '#!ibl edition=2\n' + source, edition=2)
    source2 = '[def:publish_report]($enabled,$writer,$items){return {sent:[fn:maybe_send]{enabled:$enabled,writer:$writer,items:$items},items:$items}}'
    register('publish_report', '#!ibl edition=2\n' + source2, edition=2)
    code = '$rows=[fn:gather]{sources:["catalog"],read:&[probe:read],normalize:&[fn:normalizer],policy:($r)=>$r.score>3};'
    code += '$report=[fn:publish_report]{enabled:true,writer:&[probe:publish],items:$rows};return 10/$n'
    plan = compile_program(code, reg, inputs={'n': 0}, definitions=definitions().interfaces_only())
    assert not plan.issues and 'write_external' in plan.effects, plan.report()
    assert calls == []
    failed = handle_request({'edition': 2, 'code': code, 'inputs': {'n': 0}}, str(tmp_path))
    assert not failed['success'] and failed['component_completion']['status'] == 'satisfied', failed
    before = list(calls)
    assert [c[0] for c in before] == ['read', 'script', 'publish']
    fixed = {'edition': 2, 'code': code.replace('10/$n', '10/($n+1)'), 'inputs': {'n': 0},
             'repair': {'run_id': failed['resume']['run_id']}}
    checked = handle_request({**fixed, 'check': True}, str(tmp_path))
    assert checked.get('ok'), checked
    assert calls == before
    fixed['repair']['plan_hash'] = checked['repair']['plan_hash']
    done = handle_request(fixed, str(tmp_path))
    assert done['success'] and done['value'] == 10, done
    # Pure normalization may be recomputed; completed external effects may not.
    assert [c for c in calls if c[0] != 'script'] == [c for c in before if c[0] != 'script']



def test_sequential_policies_share_continuations_without_expanding_paths(abilities, monkeypatch):
    from function_library import register, definitions
    from ibl_v2_semantic import derive
    from ibl_v2_types import BOOL
    reg, calls, _ = abilities

    def source(count):
        params = ','.join(['$x', *('$f' + str(i) for i in range(count))])
        steps = ''.join('[if:$f' + str(i) + ']{$x=$x+1}[else]{$x=$x-1};' for i in range(count))
        return '[def:policy](' + params + '){' + steps + 'return $x}'

    # The observed counterexample was exponential growth at nine sequential
    # decisions. A shared continuation makes definition growth linear.
    small, large = derive(source(6)), derive(source(12))
    assert len(json.dumps(large)) < 3 * len(json.dumps(small))
    register('policy', '#!ibl edition=2\n' + source(12), edition=2)
    lib = definitions()
    code = 'return [fn:policy]{x:10,' + ','.join('f'+str(i)+':$f'+str(i) for i in range(12)) + '}'
    with monkeypatch.context() as blocked:
        blocked.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body analysis'))
        plan = compile_program(code, reg, definitions=lib.interfaces_only(),
                               input_types={'f'+str(i): BOOL for i in range(12)})
    assert not plan.issues, plan.report()
    assert plan.result_type.kind == 'Number'
    assert plan.preflight['analysis']['lambda_bodies'] < 50
    assert not calls
    plan.definitions = lib
    inputs = {'f'+str(i): i % 3 == 0 for i in range(12)}
    out = Runtime(plan, inputs).run()
    assert out['success'] and out['value'] == 10 + 4 - 8, out


ENRICH = r'''[def:enrich]($rows,$field,$policy){
return [table:each]{items:$rows}{
return {**$it,measured:$it[$field],accepted:$policy($it[$field]),label:f"${$it.id}:${$it[$field]}"}
}}'''
PREPARE = '''[def:prepare]($source,$read,$normalize,$field,$policy){
$raw=$read{source:$source};
$rows=$normalize{data:$raw.items};
$enriched=[fn:enrich]{rows:$rows,field:$field,policy:$policy};
return {**$raw,items:$enriched}
}'''
REVIEW = '''[def:review]($source,$read,$normalize,$field,$policy){
$report=[fn:prepare]{source:$source,read:$read,normalize:$normalize,field:$field,policy:$policy};
$chosen=[table:filter]{items:$report.items,where:($r)=>$r.accepted};
return {**$report,items:$chosen,count:len($chosen)}
}'''


def test_shape_relationships_recombine_after_publication_and_provider_change(abilities, monkeypatch):
    from function_library import register, definitions
    from ibl_v2_store import Library
    reg, calls, scripts = abilities
    for name, source in [('normalizer', NORMALIZE), ('enrich', ENRICH), ('prepare', PREPARE)]:
        register(name, '#!ibl edition=2\n' + source, edition=2)
    original = Library.__getitem__

    def no_lower_body(library, name):
        if name in library.interfaces:
            pytest.fail('lower body requested while composing: ' + name)
        return original(library, name)

    with monkeypatch.context() as blocked:
        blocked.setattr(Library, '__getitem__', no_lower_body)
        register('review', '#!ibl edition=2\n' + REVIEW, edition=2)
    library = definitions()
    assert set(library.interfaces) == {'normalizer', 'enrich', 'prepare', 'review'}, library.interface_limits
    code = 'return [fn:review]{source:"catalog",read:&[probe:read],normalize:&[fn:normalizer],field:"score",policy:($n)=>$n>3}'
    expected = {'origin': 'catalog', 'count': 1, 'items': [
        {'id': 'b', 'score': 5, 'source': 'catalog', 'measured': 5, 'accepted': True, 'label': 'b:5'}]}
    # Direct, one saved level and two saved levels use one independent oracle.
    for prefix, lib in [(NORMALIZE + ENRICH + PREPARE + REVIEW, None),
                        (PREPARE + REVIEW, library), ('', library)]:
        checked = compile_program(prefix + code, reg, definitions=lib)
        assert not checked.issues, checked.report()
        assert Runtime(checked).run()['value'] == expected
    calls.clear()
    # A later provider adds business metadata and a different measured field.
    fields = {'id': 'Text', 'score': 'Number', 'source': 'Text', 'bytes': 'Number', '$closed': True}
    scripts['files_normalize'] = {**scripts['normalize'], 'callable_contract': {
        **scripts['normalize']['callable_contract'], 'params': {'data': {'$list': fields}},
        'result': {'$list': fields}, 'completion': [{'id': 'normalized', 'predicate': 'len($value)==2',
            'sources': [{'action': 'probe:python', 'targets': {'id': 'files_normalize'}}]}]}}
    reg['files:snapshot'] = Adapter({'version': 1, 'params': {'source': 'Text'},
        'result': {'items': {'$list': fields}, 'origin': 'Text',
                   'revision': 'Text', 'metadata': {'owner': 'Text', '$closed': True}, '$closed': True},
        'effects': ['read_external']}, lambda rt, a: calls.append(('snapshot', a['source'])) or {
            'items': [{'id': 'a', 'score': 1, 'source': a['source'], 'bytes': 4},
                      {'id': 'b', 'score': 2, 'source': a['source'], 'bytes': 20}],
            'origin': a['source'], 'revision': 'r2', 'metadata': {'owner': 'operator'}})
    register('files_normalizer', '#!ibl edition=2\n[def:files_normalizer]($data){'
             'return [probe:python]{id:"files_normalize",args:{data:$data}}}', edition=2)
    library = definitions()
    later = code.replace('probe:read', 'files:snapshot').replace('fn:normalizer', 'fn:files_normalizer')
    later = later.replace('field:"score"', 'field:"bytes"').replace('$n>3', '$n>10')
    with monkeypatch.context() as blocked:
        blocked.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body analysis'))
        plan = compile_program(later, reg, definitions=library.interfaces_only())
        bad = compile_program(later.replace('field:"bytes"', 'field:"absent"'), reg,
                              definitions=library.interfaces_only())
    assert not plan.issues, plan.report()
    assert any(i['code'] == 'MISSING_FIELD' for i in bad.issues), bad.report()
    shape = dict(plan.result_type.fields)
    assert shape['revision'] == TEXT and dict(shape['metadata'].fields)['owner'] == TEXT
    assert dict(shape['items'].item.fields)['bytes'] == NUMBER
    assert calls == []  # storage and both suitability checks never invoke a leaf
    plan.definitions = library
    result = Runtime(plan).run()
    assert result['success'] and result['component_completion']['status'] == 'satisfied', result
    assert result['value'] == {'origin': 'catalog', 'revision': 'r2', 'metadata': {'owner': 'operator'},
        'count': 1, 'items': [{'id': 'b', 'score': 2, 'source': 'catalog', 'bytes': 20,
                              'measured': 20, 'accepted': True, 'label': 'b:20'}]}
    assert calls == [('snapshot', 'catalog'), ('script', 'files_normalize')]


@pytest.mark.parametrize('expression,arguments,code', [
    ('{**$x}', 'x:4', 'TYPE'),
    ('f"${$x}"', 'x:{n:1}', 'FORMAT_TYPE'),
    ('$x[$key]', 'x:{n:1},key:"missing"', 'MISSING_FIELD'),
    ('$x[$key]', 'x:[1],key:"not-a-number"', 'TYPE'),
])
def test_shape_requirements_remain_when_result_is_discarded(abilities, expression, arguments, code):
    from function_library import register, definitions
    reg, calls, _ = abilities
    definition = '[def:check_shape]($x,$key="n"){$unused=' + expression + ';return 1}'
    register('check_shape', '#!ibl edition=2\n' + definition, edition=2)
    source = 'return [fn:check_shape]{' + arguments + '}'
    for prefix, library in [(definition, None), ('', definitions().interfaces_only())]:
        plan = compile_program(prefix + source, reg, definitions=library)
        assert any(i['code'] == code for i in plan.issues), plan.report()
    assert calls == []


def test_record_overlay_order_and_foreign_lifetime_are_preserved(abilities):
    from function_library import register, definitions
    from ibl_v2_types import UNKNOWN
    reg, calls, _ = abilities
    source = '[def:overlay]($row,$patch){return {fixed:1,**$row,after:2,**$patch,last:3}}'
    register('overlay', '#!ibl edition=2\n' + source, edition=2)
    code = 'return [fn:overlay]{row:$row,patch:$patch}'
    actuals = {'row': Type('Record', (('fixed', TEXT), ('ref', Type('ForeignRef'))), open=False),
               'patch': Type('Record', (('after', TEXT),), open=True)}
    for prefix, library in [(source, None), ('', definitions().interfaces_only())]:
        plan = compile_program(prefix + code, reg, definitions=library, input_types=actuals)
        shape = dict(plan.result_type.fields)
        assert not plan.issues and plan.result_type.open, plan.report()
        assert shape['fixed'] == UNKNOWN and shape['after'] == TEXT and shape['last'].literal == 3
        # A closed empty patch cannot overwrite the ForeignRef carried by the spread.
        actuals_closed = {**actuals, 'patch': Type('Record', open=False)}
        wire = compile_program(prefix + code, reg, definitions=library, input_types=actuals_closed,
                               value_protocols=['ibl-value/1'])
        assert any(i['code'] == 'VALUE_PROTOCOL' for i in wire.issues), wire.report()
    assert calls == []


def test_dynamic_projection_keeps_callable_effect_and_argument_contract(abilities):
    from function_library import register, definitions
    reg, calls, _ = abilities
    source = '[def:invoke]($providers,$name,$items){$selected=$providers[$name];return $selected{items:$items}}'
    register('invoke', '#!ibl edition=2\n' + source, edition=2)
    lib = definitions().interfaces_only()
    code = 'return [fn:invoke]{providers:{send:&[probe:publish]},name:"send",items:[1]}'
    plan = compile_program(code, reg, definitions=lib)
    assert not plan.issues and plan.effects - {'pure'} == {'write_external'}, plan.report()
    bad = compile_program(code.replace('items:[1]', 'items:1'), reg, definitions=lib)
    assert any(i['code'] == 'TYPE' for i in bad.issues), bad.report()
    unknown = compile_program('return [fn:invoke]{providers:{send:$f},name:"send",items:[1]}', reg,
                              definitions=lib, input_types={'f': Type('Callable')})
    assert 'unknown' in unknown.effects and unknown.guards
    assert calls == []


def test_interpolated_resource_identity_survives_storage_and_repair(abilities, tmp_path):
    from function_library import register, definitions
    from ibl_v2_entry import handle_request
    reg, calls, _ = abilities
    reg['archive:write'] = Adapter({'version': 1, 'params': {'path': 'Text'}, 'result': 'Number',
        'effects': ['write_external'], 'write_resources': {'file': 'path'}},
        lambda rt, a: calls.append(('write', a['path'])) or 1)
    source = '[def:archive]($record,$field,$folder){return [archive:write]{path:f"${$folder}/${$record[$field]}.txt"}}'
    register('archive', '#!ibl edition=2\n' + source, edition=2)
    library = definitions().interfaces_only()
    call = '[fn:archive]{record:{id:7},field:"id",folder:"folder"}'
    safe = compile_program(call + ' & ' + call.replace('id:7', 'id:8'), reg, definitions=library)
    assert not safe.issues and all(a.resources for a in safe.accesses), safe.report()
    conflict = compile_program(call + ' & ' + call, reg, definitions=library)
    assert any(i['code'] == 'PARALLEL_WRITE_CONFLICT' for i in conflict.issues), conflict.report()
    assert calls == []
    code = call + ';return 10/$n'
    failed = handle_request({'edition': 2, 'code': code, 'inputs': {'n': 0}}, str(tmp_path))
    assert not failed['success'] and calls == [('write', 'folder/7.txt')], failed
    fixed = {'edition': 2, 'code': code.replace('10/$n', '10/($n+1)'), 'inputs': {'n': 0},
             'repair': {'run_id': failed['resume']['run_id']}}
    checked = handle_request({**fixed, 'check': True}, str(tmp_path))
    assert checked.get('ok'), checked
    fixed['repair']['plan_hash'] = checked['repair']['plan_hash']
    done = handle_request(fixed, str(tmp_path))
    assert done['success'] and done['value'] == 10, done
    assert calls == [('write', 'folder/7.txt')]


@pytest.mark.parametrize('flag', [False, True, None])
def test_overlay_retains_finite_branch_fields_and_dynamic_selector(abilities, flag):
    from function_library import register, definitions
    from ibl_v2_types import BOOL, alternatives
    reg, calls, _ = abilities
    definition = '[def:overlay]($flag,$key){$row=$flag ? {id:1,left:2} : {id:3,right:4};return {**$row,selected:$row[$key]}}'
    register('overlay', '#!ibl edition=2\n' + definition, edition=2)
    for prefix, library in [(definition, None), ('', definitions().interfaces_only())]:
        plan = compile_program(prefix + 'return [fn:overlay]{flag:$flag,key:"id"}', reg,
            definitions=library, input_types={'flag': BOOL} if flag is None else None,
            inputs={} if flag is None else {'flag': flag})
        assert not plan.issues, plan.report()
        candidates = list(alternatives(plan.result_type))
        assert len(candidates) == (2 if flag is None else 1)
        for candidate in candidates:
            fields = dict(candidate.fields)
            assert fields['id'].kind == fields['selected'].kind == 'Number'
            assert ('left' in fields) != ('right' in fields)
    assert calls == []



def test_record_relation_limit_keeps_common_guarantees_and_reports_uncertainty(abilities):
    from function_library import register, definitions
    reg, calls, _ = abilities
    source = '[def:overlay]($row){return {**$row,last:3}}'
    register('overlay', '#!ibl edition=2\n' + source, edition=2)
    variants = Type('Union', item=tuple(Type('Record', (('id', NUMBER), ('field'+str(i), TEXT)), open=False)
                                        for i in range(65)))
    for prefix, library in [(source, None), ('', definitions().interfaces_only())]:
        plan = compile_program(prefix + 'return [fn:overlay]{row:$row}', reg,
                               definitions=library, input_types={'row': variants})
        assert not plan.issues and plan.result_type.open, plan.report()
        assert dict(plan.result_type.fields) == {'id': NUMBER, 'last': Type('Number', literal=3)}
        assert any(w['code'] == 'RECORD_RELATION_LIMIT' for w in plan.preflight.get('warnings', [])), plan.report()
    assert calls == []



@pytest.mark.parametrize('invocation', ['[fn:label]{**$args}', '$f{**$args}'])
def test_record_alternatives_remain_applicable_as_named_arguments(abilities, invocation):
    from function_library import register, definitions
    from ibl_v2_types import BOOL
    reg, calls, _ = abilities
    label = '[def:label]($id,$suffix="default"){return f"${$id}:${$suffix}"}'
    caller = '[def:dispatch]($flag,$f){$args=$flag ? {id:1} : {id:2,suffix:"second"};return ' + invocation + '}'
    for name, definition in [('label', label), ('dispatch', caller)]:
        register(name, '#!ibl edition=2\n' + definition, edition=2)
    source = 'return [fn:dispatch]{flag:$flag,f:&[fn:label]}'
    library = definitions()
    for prefix, lib in [(label + caller, None), ('', library.interfaces_only())]:
        plan = compile_program(prefix + source, reg, definitions=lib, input_types={'flag': BOOL})
        assert not plan.issues and plan.result_type.kind == 'Text', plan.report()
        if lib is not None:
            plan.definitions = library
        for flag, expected in [(True, '1:default'), (False, '2:second')]:
            result = Runtime(plan, {'flag': flag}).run()
            assert result['success'] and result['value'] == expected, result
    assert calls == []


def test_named_record_alternatives_check_every_callback_candidate(abilities):
    from function_library import register, definitions
    from ibl_v2_types import BOOL
    reg, calls, _ = abilities
    # Different field sets must not erase the known bad `items` argument.
    source = '[def:dispatch]($flag,$send){$args=$flag ? {items:[1]} : {items:7,extra:1};return $send{**$args}}'
    register('dispatch', '#!ibl edition=2\n' + source, edition=2)
    for prefix, lib in [(source, None), ('', definitions().interfaces_only())]:
        plan = compile_program(prefix + 'return [fn:dispatch]{flag:$flag,send:&[probe:publish]}', reg,
                               definitions=lib, input_types={'flag': BOOL})
        assert {'TYPE', 'UNKNOWN_ARGUMENT'} <= {i['code'] for i in plan.issues}, plan.report()
        assert 'write_external' in plan.effects
    direct = compile_program('$args=$flag ? {items:[1]} : {items:7,extra:1};'
                             'return [probe:publish]{**$args}', reg, input_types={'flag': BOOL})
    assert {'TYPE', 'UNKNOWN_ARGUMENT'} <= {i['code'] for i in direct.issues}, direct.report()
    assert calls == []


PARALLEL_GATHER = GATHER.replace('on_error:"collect"', 'on_error:"collect",parallel:2')


@pytest.mark.parametrize('second_source', ['other', 'unavailable'])
def test_parallel_collection_is_a_bodyless_reusable_ability(abilities, monkeypatch, tmp_path, second_source):
    import threading
    from function_library import register, definitions
    from ibl_v2_ir import unpack
    from ibl_v2_store import Library
    reg, calls, scripts = abilities
    for name, source in [('normalizer', NORMALIZE), ('gather', PARALLEL_GATHER),
                         ('decide', DECIDE), ('recheck', RECHECK)]:
        register(name, '#!ibl edition=2\n' + source, edition=2)
    library = definitions()
    assert set(library.interfaces) == {'normalizer', 'gather', 'decide', 'recheck'}, library.interface_limits
    assert calls == []
    # A later source keeps the old boundary but introduces a new row column.
    fields = {'id': 'Text', 'score': 'Number', 'source': 'Text', 'bytes': 'Number', '$closed': True}
    scripts['file_normalize'] = {**scripts['normalize'], 'callable_contract': {
        **scripts['normalize']['callable_contract'], 'params': {'data': {'$list': fields}},
        'result': {'$list': fields}, 'completion': []}}
    register('file_normalizer', '#!ibl edition=2\n[def:file_normalizer]($data){'
             'return [probe:python]{id:"file_normalize",args:{data:$data}}}', edition=2)
    rendezvous = threading.Barrier(2)

    def read(rt, args):
        source = args['source']
        calls.append(('file_read', source))
        rendezvous.wait(timeout=10)  # Both independent rows really start together.
        if source == 'unavailable':
            raise Fault('SOURCE_OFFLINE', 'source unavailable')
        return {'items': [{'id': 'a', 'score': 2, 'source': source, 'bytes': 4},
                          {'id': 'b', 'score': 5, 'source': source, 'bytes': 20}], 'origin': source}

    reg['files:batch_read'] = Adapter({'version': 1, 'params': {'source': 'Text'},
        'result': {'items': {'$list': fields}, 'origin': 'Text', '$closed': True},
        'effects': ['read_external'], 'read_resources': {'source': 'source'}}, read)
    audit = '[def:audit]($sources,$read,$normalize,$policy){return {review:[fn:decide]{sources:$sources,read:$read,normalize:$normalize,policy:$policy}}}'
    original = Library.__getitem__
    with monkeypatch.context() as blocked:
        blocked.setattr(Library, '__getitem__', lambda lib, name: pytest.fail('lower source requested')
                        if name in lib.interfaces else original(lib, name))
        register('audit', '#!ibl edition=2\n' + audit, edition=2)
    library = definitions()
    source = ('return [fn:audit]{sources:' + json.dumps(['catalog', second_source]) + ',read:&[files:batch_read],'
              'normalize:&[fn:file_normalizer],policy:($r)=>$r.bytes>10}')
    with monkeypatch.context() as blocked:
        blocked.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body analysis'))
        checked = compile_program(source, reg, definitions=library.interfaces_only())
    assert not checked.issues and checked.effects - {'pure'} == {'read_external'}, checked.report()
    collected = dict(dict(checked.result_type.fields)['review'].fields)['evidence'].item
    assert collected.kind == 'Result'
    assert dict(dict(collected.item.fields)['rows'].item.fields)['bytes'] == NUMBER
    assert calls == []
    # Direct, one stored level, and two stored levels share an independent oracle.
    normalizer = '[def:file_normalizer]($data){return [probe:python]{id:"file_normalize",args:{data:$data}}}'
    for prefix, lib in [(normalizer + PARALLEL_GATHER + DECIDE + audit, None),
                        (DECIDE + audit, library), ('', library)]:
        plan = compile_program(prefix + source, reg, definitions=lib)
        result = Runtime(plan).run()
        assert result['success'], result
        values = unpack(result['value_wire']['data'])['review']['evidence']
        assert len(values) == 2 and values[0].ok
        assert values[1].ok == (second_source != 'unavailable')
        assert values[0].value == {'source': 'catalog', 'rows': [
            {'id': 'b', 'score': 5, 'source': 'catalog', 'bytes': 20}]}
        if second_source == 'unavailable':
            assert values[1].error['code'] == 'SOURCE_OFFLINE'
        else:
            assert values[1].value == {'source': second_source, 'rows': [
                {'id': 'b', 'score': 5, 'source': second_source, 'bytes': 20}]}
    assert calls.count(('file_read', 'catalog')) == calls.count(('file_read', second_source)) == 3
    assert calls.count(('script', 'file_normalize')) == (3 if second_source == 'unavailable' else 6)
    if second_source == 'unavailable':
        from ibl_v2_entry import handle_request
        code = source.replace('return [fn:audit]', '$records=[fn:audit]') + ';return 10/$n'
        failed = handle_request({'edition': 2, 'code': code, 'inputs': {'n': 0}}, str(tmp_path))
        assert not failed['success'], failed
        before = [call for call in calls if call[0] == 'file_read']
        fixed = {'edition': 2, 'code': code.replace('10/$n', '10/($n+1)'), 'inputs': {'n': 0},
                 'repair': {'run_id': failed['resume']['run_id']}}
        ready = handle_request({**fixed, 'check': True}, str(tmp_path))
        assert ready.get('ok'), ready
        fixed['repair']['plan_hash'] = ready['repair']['plan_hash']
        done = handle_request(fixed, str(tmp_path))
        assert done['success'] and done['value'] == 10, done
        # Completed success and failure observations both replay their receipts.
        assert [call for call in calls if call[0] == 'file_read'] == before


def parallel_adapters(reg, calls):
    reg['archive:write'] = Adapter({'version': 1, 'params': {'path': 'Text'}, 'result': 'Number',
        'effects': ['write_external'], 'write_resources': {'record': 'path'}},
        lambda rt, a: calls.append(('write', a['path'])) or 1)
    reg['archive:read'] = Adapter({'version': 1, 'params': {'path': 'Text'},
        'result': {'source': 'Text', '$closed': True},
        'effects': ['read_external'], 'read_resources': {'record': 'path'}},
        lambda rt, a: calls.append(('read', a['path'])) or {'source': a['path']})
    reg['archive:opaque'] = Adapter({'version': 1, 'params': {'path': 'Text'}, 'result': 'Number',
        'effects': ['unknown']}, lambda rt, a: calls.append(('opaque', a['path'])) or 1)


PAIR = '[def:pair]($left,$right,$a,$b){return $left{path:$a} & $right{path:$b}}'
FANOUT = '[def:fanout]($items,$worker){return [table:each]{items:$items,parallel:2}{return $worker{path:$it}}}'


def test_parallel_branches_preserve_positions_resources_and_unknown_effects(abilities, monkeypatch):
    from function_library import register, definitions
    reg, calls, _ = abilities
    parallel_adapters(reg, calls)
    register('pair', '#!ibl edition=2\n' + PAIR, edition=2)
    lib = definitions()
    code = 'return [fn:pair]{left:&[archive:write],right:&[archive:read],a:"one",b:"two"}'
    with monkeypatch.context() as blocked:
        blocked.setattr(Compiler, '_function', lambda *a, **k: pytest.fail('lower body analysis'))
        good = compile_program(code, reg, definitions=lib.interfaces_only())
        conflict = compile_program(code.replace('b:"two"', 'b:"one"'), reg, definitions=lib.interfaces_only())
        opaque = compile_program(code.replace('archive:write', 'archive:opaque'), reg, definitions=lib.interfaces_only())
    assert not good.issues and good.result_type.positions == (NUMBER, Type('Record', (('source', TEXT),), open=False)), good.report()
    assert good.effects - {'pure'} == {'read_external', 'write_external'}
    assert any(i['code'] == 'PARALLEL_WRITE_CONFLICT' for i in conflict.issues), conflict.report()
    assert 'unknown' in opaque.effects
    assert any(w['code'] == 'PARALLEL_RESOURCE_UNKNOWN' for w in opaque.preflight['warnings']), opaque.report()
    assert calls == []
    opaque.definitions = lib
    rejected = Runtime(opaque).run()
    assert rejected['diagnostic']['code'] == 'PARALLEL_RESOURCE_CONFLICT' and calls == [], rejected
    good.definitions = lib
    result = Runtime(good).run()
    assert result['success'] and result['value'] == [1, {'source': 'two'}], result
    assert sorted(calls) == [('read', 'two'), ('write', 'one')]


@pytest.mark.parametrize('items,conflict', [('[]', False), ('["one"]', False), ('["one","two"]', True)])
def test_stored_parallel_each_uses_cardinality_for_static_admission(abilities, items, conflict):
    from function_library import register, definitions
    reg, calls, _ = abilities
    parallel_adapters(reg, calls)
    source = '[def:fixed]($items,$worker){return [table:each]{items:$items,parallel:2}{return $worker{path:"same"}}}'
    register('fixed', '#!ibl edition=2\n' + source, edition=2)
    call = 'return [fn:fixed]{items:' + items + ',worker:&[archive:write]}'
    for prefix, lib in [(source, None), ('', definitions().interfaces_only())]:
        plan = compile_program(prefix + call, reg, definitions=lib)
        assert any(i['code'] == 'PARALLEL_WRITE_CONFLICT' for i in plan.issues) == conflict, plan.report()
    assert calls == []


def test_stored_parallel_each_checks_actual_aliases_before_any_write(abilities):
    from function_library import register, definitions
    reg, calls, _ = abilities
    parallel_adapters(reg, calls)
    register('fanout', '#!ibl edition=2\n' + FANOUT, edition=2)
    lib = definitions()
    code = 'return [fn:fanout]{items:$paths,worker:&[archive:write]}'
    plan = compile_program(code, reg, definitions=lib.interfaces_only(), input_types={'paths': Type('List', item=TEXT)})
    assert not plan.issues and 'write_external' in plan.effects, plan.report()
    assert calls == []
    plan.definitions = lib
    rejected = Runtime(plan, {'paths': ['same', 'same']}).run()
    assert rejected['diagnostic']['code'] == 'PARALLEL_RESOURCE_CONFLICT' and calls == [], rejected
    result = Runtime(plan, {'paths': ['one', 'two']}).run()
    assert result['success'] and result['value'] == [1, 1], result
    assert sorted(calls) == [('write', 'one'), ('write', 'two')]


def test_parallel_completed_effects_are_reused_after_tail_repair(abilities, tmp_path):
    from function_library import register, definitions
    from ibl_v2_entry import handle_request
    reg, calls, _ = abilities
    parallel_adapters(reg, calls)
    register('fanout', '#!ibl edition=2\n' + FANOUT, edition=2)
    register('publish_many', '#!ibl edition=2\n[def:publish_many]($items,$worker){'
             'return {receipts:[fn:fanout]{items:$items,worker:$worker}}}', edition=2)
    code = '$sent=[fn:publish_many]{items:["one","two"],worker:&[archive:write]};return 10/$n'
    checked = compile_program(code, reg, definitions=definitions().interfaces_only(), inputs={'n': 0})
    assert not checked.issues and calls == [], checked.report()
    failed = handle_request({'edition': 2, 'code': code, 'inputs': {'n': 0}}, str(tmp_path))
    assert not failed['success'] and sorted(calls) == [('write', 'one'), ('write', 'two')], failed
    fixed = {'edition': 2, 'code': code.replace('10/$n', '10/($n+1)'), 'inputs': {'n': 0},
             'repair': {'run_id': failed['resume']['run_id']}}
    prepared = handle_request({**fixed, 'check': True}, str(tmp_path))
    assert prepared.get('ok'), prepared
    fixed['repair']['plan_hash'] = prepared['repair']['plan_hash']
    done = handle_request(fixed, str(tmp_path))
    assert done['success'] and done['value'] == 10, done
    assert sorted(calls) == [('write', 'one'), ('write', 'two')]


@pytest.mark.parametrize('mode,body,kind,expected', [
    ('map', 'return $it+1', 'List', [2, 3]),
    ('flat_map', 'return [$it,$it+1]', 'List', [1, 2, 2, 3]),
    ('effect', '$unused=$it+1', 'Unit', None),
])
def test_iteration_modes_share_source_and_saved_transfer(abilities, mode, body, kind, expected):
    from function_library import register, definitions
    from ibl_v2_ir import unpack, Unit
    reg, calls, _ = abilities
    source = '[def:rows]($items){return [table:each]{items:$items,parallel:2,mode:"' + mode + '"}{' + body + '}}'
    register('rows', '#!ibl edition=2\n' + source, edition=2)
    lib = definitions()
    for prefix, library in [(source, None), ('', lib.interfaces_only())]:
        plan = compile_program(prefix + 'return [fn:rows]{items:[1,2]}', reg, definitions=library)
        assert not plan.issues and plan.result_type.kind == kind, plan.report()
        if library is not None:
            plan.definitions = lib
        out = Runtime(plan).run()
        assert out['success'], out
        value = unpack(out['value_wire']['data'])
        assert isinstance(value, Unit) if kind == 'Unit' else value == expected
    assert calls == []



def test_parallel_collect_does_not_convert_permission_fault_to_success(abilities):
    from function_library import register, definitions
    reg, calls, _ = abilities
    def denied(rt, args):
        calls.append(('denied', args['path']))
        raise Fault('ACCESS_DENIED', 'not authorized', kind='permission')
    reg['archive:denied'] = Adapter({'version': 1, 'params': {'path': 'Text'}, 'result': 'Number',
                                    'effects': ['read_external']}, denied)
    source = '[def:collect]($worker){return [table:each]{items:["one"],parallel:2,on_error:"collect"}{return $worker{path:$it}}}'
    register('collect', '#!ibl edition=2\n' + source, edition=2)
    lib = definitions()
    plan = compile_program('return [fn:collect]{worker:&[archive:denied]}', reg,
                           definitions=lib.interfaces_only())
    assert not plan.issues and plan.result_type.item.kind == 'Result' and calls == [], plan.report()
    plan.definitions = lib
    result = Runtime(plan).run()
    assert not result['success'] and result['diagnostic']['code'] == 'ACCESS_DENIED', result
    assert result['diagnostic']['kind'] == 'permission' and calls == [('denied', 'one')]


def test_parallel_result_keeps_foreign_ref_lifetime_boundary(abilities):
    from function_library import register, definitions
    reg, calls, _ = abilities
    register('pair_values', '#!ibl edition=2\n[def:pair_values]($left,$right){return $left & $right}', edition=2)
    plan = compile_program('return [fn:pair_values]{left:$ref,right:1}', reg,
                           definitions=definitions().interfaces_only(), input_types={'ref': Type('ForeignRef')},
                           value_protocols=['ibl-value/1'])
    assert any(i['code'] == 'VALUE_PROTOCOL' for i in plan.issues), plan.report()
    assert plan.result_type.positions[0].kind == 'ForeignRef' and calls == []



@pytest.mark.parametrize('branch_statement', [False, True])
def test_partial_parallel_function_edit_resumes_without_repeating_writes(abilities, tmp_path, branch_statement):
    import threading
    from function_library import register
    from ibl_v2_entry import handle_request
    reg, calls, _ = abilities
    parallel_adapters(reg, calls)
    meet = threading.Barrier(2)
    def write(rt, args):
        calls.append(('write', args['path']))
        meet.wait(timeout=10)
        return 1
    reg['archive:write'] = Adapter(reg['archive:write'].contract, write)
    register('fanout', '#!ibl edition=2\n' + FANOUT, edition=2)
    step = ('[def:step]($path,$n){[if:$path=="two"]{[archive:write]{path:$path};return 10/$n}'
            '[else]{[archive:write]{path:$path};return 10}};' if branch_statement else
            '[def:step]($path,$n){[archive:write]{path:$path};return 10/($path=="two" ? $n : 1)};')
    code = (step + '$worker=($path)=>[fn:step]{path:$path,n:$n};'
            'return [fn:fanout]{items:["one","two"],worker:$worker}')
    failed = handle_request({'edition': 2, 'code': code, 'inputs': {'n': 0}}, str(tmp_path))
    assert not failed['success'] and sorted(calls) == [('write', 'one'), ('write', 'two')], failed
    fixed = {'edition': 2, 'code': code.replace('? $n : 1', '? ($n+1) : 1').replace('10/$n', '10/($n+1)'), 'inputs': {'n': 0},
             'repair': {'run_id': failed['resume']['run_id']}}
    checked = handle_request({**fixed, 'check': True}, str(tmp_path))
    assert checked['ok'], checked
    assert sorted(calls) == [('write', 'one'), ('write', 'two')]
    fixed['repair']['plan_hash'] = checked['repair']['plan_hash']
    repaired = handle_request(fixed, str(tmp_path))
    assert repaired['success'] and repaired['value'] == [10, 10], repaired
    assert sorted(calls) == [('write', 'one'), ('write', 'two')]
    resumed = handle_request({**fixed, 'repair': None, 'resume': failed['resume']}, str(tmp_path))
    assert resumed['success'] and resumed['value'] == [10, 10], resumed
    assert sorted(calls) == [('write', 'one'), ('write', 'two')]



def test_parallel_capture_does_not_move_an_earlier_effect_into_a_branch(abilities):
    from function_library import register, definitions
    reg, calls, _ = abilities
    parallel_adapters(reg, calls)
    definition = '[def:report]($read,$write){$earlier=$read{path:"same"};return {results:($earlier & $write{path:"same"})}}'
    register('report', '#!ibl edition=2\n' + definition, edition=2)
    lib = definitions()
    source = 'return [fn:report]{read:&[archive:read],write:&[archive:write]}'
    for prefix, library in [(definition, None), ('', lib.interfaces_only())]:
        plan = compile_program(prefix + source, reg, definitions=library)
        assert not plan.issues, plan.report()
        assert plan.effects - {'pure'} == {'read_external', 'write_external'}
        if library is not None:
            plan.definitions = lib
        result = Runtime(plan).run()
        assert result['success'] and result['value'] == {'results': [{'source': 'same'}, 1]}, result
    assert calls == [('read', 'same'), ('write', 'same')] * 2


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
