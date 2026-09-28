"""Registered library scripts compose with IBL without adding vocabulary."""
import json
import re
from pathlib import Path

import boot_paths  # noqa: F401
import pytest
from common.expression_ir import ForeignRef, pack, unpack
from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime, Budget

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def registry():
    return load_registry(str(ROOT))


def run(code, registry, inputs=None, **kwargs):
    plan = compile_program(code, registry, inputs)
    assert not plan.issues, plan.report()
    return Runtime(plan, inputs, **kwargs).run()


def call(target, args=None, **kwargs):
    return '[self:script]' + json.dumps({'id': 'python_libraries', 'args': {
        'op': 'call', 'target': target, 'args': args or [], **kwargs}})


def test_design_examples_run_real_numpy_pandas(registry):
    section = (ROOT / 'docs/IBL_SYSTEM_CONSOLIDATION_DESIGN.md').read_text().split('### 6.8.')[1]
    samples = re.findall(r'```ibl\n(.*?)\n```', section, re.S)
    assert run(samples[0], registry)['value'] == {'평균': 4, '목록': [2, 4, 6]}
    assert run(samples[1], registry)['value'] == [{'분류': 'A', '금액': 8}]


@pytest.mark.parametrize('target,args,expected', [
    ('statistics:mean', [[2, 4, 6]], 4), ('builtins:str', ['error: failed traceback'], 'error: failed traceback'),
    ('builtins:list', [], []), ('builtins:sum', [[1, 2, 3]], 6),
    ('builtins:int', ['9007199254740993'], {'$ibl': 'integer', 'text': '9007199254740993'}),
])
def test_unregistered_calls_and_plain_values(registry, target, args, expected):
    out = run(call(target, args), registry)
    assert out['success'], out
    assert out['value'] == expected


def test_mutation_alias_and_release(registry):
    out = run('''$a=[self:script]{id:"python_libraries",args:{op:"call",target:"builtins:list",result:"ref"}}
$b=$a
$n=[self:script]{id:"python_libraries",args:{receiver:$a,op:"call",name:"append",args:[7]}}
$v=[self:script]{id:"python_libraries",args:{receiver:$b,op:"export",format:"list"}}
[self:script]{id:"python_libraries",args:{op:"release",receiver:$a}}
[self:script]{id:"python_libraries",args:{op:"release",receiver:$b}}
return {value:$v,n:$n,same:$a==$b}''', registry)
    assert out['success'], out
    assert out['value'] == {'value': [7], 'n': None, 'same': True}
    assert any(e['kind'] == 'tool_evidence' and e.get('python') for e in out['evidence'])


def test_conversion_failure_keeps_result_and_does_not_repeat(registry):
    out = run('''$r=null
[try]{$r=[self:script]{id:"python_libraries",args:{op:"call",target:"builtins:tuple",args:[[1,2]],result:"value"}}}
[catch]{$r=$error.partial}
return [self:script]{id:"python_libraries",args:{receiver:$r,op:"export",format:"list"}}''', registry)
    assert out['success'], out
    assert out['value'] == [1, 2]
    assert len([e for e in out['evidence'] if e['kind'] == 'invoke']) == 2
    assert out['source_complete'] is False  # recovered failure evidence is not erased


def test_foreign_output_wire_and_expired_scope(registry):
    out = run(call('builtins:tuple', [[1, 2]]), registry)
    assert out['value_wire']['protocol'] == 'ibl-value/2'
    ref = unpack(out['value_wire']['data'])
    assert isinstance(ref, ForeignRef)
    assert unpack(pack({'ref': ref})) == {'ref': ref}
    expired = run('[self:script]{id:"python_libraries",args:{op:"export",receiver:$ref,format:"list"}}', registry, {'ref': ref})
    assert expired['diagnostic']['kind'] == 'permission'
    plain = compile_program('[self:script]{id:"python_libraries",args:{op:"release",receiver:$ref}}', registry, {'ref': ref.fields()})
    assert not Runtime(plain, {'ref': ref.fields()}).run()['success']


@pytest.mark.parametrize('code', [
    '[self:script]{id:"python_libraries",args:{op:"call"}}', '[self:script]{id:"python_libraries",args:{op:"call",target:"math:sqrt",args:1}}',
    '[self:script]{id:"python_libraries",args:{op:"release"}}', '[self:script]{id:"python_libraries",args:{op:"modules",limit:0}}',
])
def test_invalid_contract_before_provider(registry, code):
    runtime = Runtime(compile_program(code, registry))
    assert not runtime.run()['success']
    assert not runtime.foreign_sessions


@pytest.mark.parametrize('principal_kind', ['member', 'body', 'portal', 'anonymous'])
def test_nonowner_denied(registry, principal_kind):
    import principal
    with principal.narrow(principal.Principal(kind=principal_kind, id='foreign'), 'test'):
        out = run(call('builtins:print', ['MUST NOT RUN']), registry)
    assert not out['success'] and out['diagnostic']['kind'] == 'permission'


def test_restricted_owner_denied_even_self_node(registry):
    from thread_context import set_allowed_nodes, get_allowed_nodes
    old = get_allowed_nodes()
    try:
        set_allowed_nodes({'self', 'others', 'table'})
        out = run(call('builtins:print', ['MUST NOT RUN']), registry)
        assert out['diagnostic']['code'] == 'LOCAL_CODE_PERMISSION'
    finally:
        set_allowed_nodes(old)


def test_error_stage_and_no_effect_call(registry):
    out = run(call('math:sqrt', [], kwargs={'x': 4}), registry)
    assert not out['success']
    assert out['diagnostic']['details']['stage'] == 'bind'
    assert out['diagnostic']['details']['invoked'] is False
    missing = run(call('no_such_installed_python_package:fn'), registry)
    assert missing['diagnostic']['code'] == 'PY_MODULE_MISSING'


def test_stdout_is_diagnostic_not_value(registry):
    out = run(call('builtins:print', ['hello']), registry)
    assert out['success'] and out['value'] is None
    assert any('hello' in e.get('script', {}).get('diagnostics', '') for e in out['evidence'])


def test_timeout_closes_worker(registry):
    plan = compile_program(call('time:sleep', [2], timeout=.1), registry)
    runtime = Runtime(plan)
    out = runtime.run()
    assert out['diagnostic']['code'] == 'PY_TIMEOUT'
    assert all(s.closed and s.proc.poll() is not None for s in runtime.foreign_sessions.values())


def test_replay_does_not_recreate_python_state(registry):
    code = call('statistics:mean', [[2, 4]])
    original = run(code, registry)
    replay = run(code, registry, recordings=original['recordings'], replay=True)
    assert replay['diagnostic']['code'] == 'PY_STATE_EXPIRED'


def test_objects_compose_through_local_functions(registry):
    out = run('''[def:make]($x){return [self:script]{id:"python_libraries",args:{op:"call",target:"builtins:tuple",args:[$x]}}}
$a=[fn:make]{x:[1,2]}
return [self:script]{id:"python_libraries",args:{op:"call",target:"operator:getitem",args:[$a,1]}}''', registry)
    assert out['value'] == 2


def test_modules_describe_and_decimal(registry):
    out = run('''$m=[self:script]{id:"python_libraries",args:{op:"modules",query:"numpy",limit:2}}
$d=[self:script]{id:"python_libraries",args:{op:"describe",target:"statistics:mean"}}
$x=[self:script]{id:"python_libraries",args:{op:"call",target:"decimal:Decimal",args:["1.234567890123456789"]}}
return {modules:$m,description:$d,number:$x}''', registry)
    assert out['success'], out
    assert out['value']['modules']['items']
    assert out['value']['description']['signature'][0]['name'] == 'data'
    assert out['value']['number']['text'] == '1.234567890123456789'


def test_callable_and_async_results(registry):
    out = run('''$pow=[self:script]{id:"python_libraries",args:{op:"getattr",target:"builtins:pow",result:"ref"}}
$f=[self:script]{id:"python_libraries",args:{op:"call",target:"functools:partial",args:[$pow,2]}}
$x=[self:script]{id:"python_libraries",args:{op:"call",receiver:$f,args:[5]}}
$n=[self:script]{id:"python_libraries",args:{op:"call",target:"asyncio:sleep",args:[0]}}
return {x:$x,n:$n}''', registry)
    assert out['value'] == {'x': 32, 'n': None}, out


def test_dataframe_export_and_attribute(registry):
    out = run('''$df=[self:script]{id:"python_libraries",args:{op:"call",target:"pandas:DataFrame",args:[{a:[1,2]}]}}
$shape=[self:script]{id:"python_libraries",args:{receiver:$df,op:"getattr",name:"shape"}}
$s=[self:script]{id:"python_libraries",args:{receiver:$shape,op:"export",format:"list"}}
$r=[self:script]{id:"python_libraries",args:{receiver:$df,op:"export",format:"records"}}
return {shape:$s,rows:$r.items,schema:$r.schema}''', registry)
    assert out['success'], out
    assert out['value']['shape'] == [2, 1]
    assert out['value']['rows'] == [{'a': 1}, {'a': 2}]
    assert out['value']['schema']['index'] == 'omitted'


@pytest.mark.parametrize('module_name', ['pandas', 'pandas.core.frame'])
def test_dataframe_export_uses_public_type_identity(module_name, monkeypatch):
    from runpy import run_path
    pandas = pytest.importorskip('pandas')
    export_value = run_path(str(ROOT / 'data/scripts/python_library/python_bridge_values.py'))['export_value']
    from common.expression_ir import Fault
    monkeypatch.setattr(pandas.DataFrame, '__module__', module_name)
    frame = pandas.DataFrame({'a': [1, 2]})
    result, evidence = export_value(frame, 'records', {})
    assert result['items'] == [{'a': 1}, {'a': 2}]
    assert result['schema']['index'] == evidence['conversion']['index'] == 'omitted'
    with pytest.raises(Fault, match='문자열 열 이름'):
        export_value(pandas.DataFrame([[1, 2]], columns=['a', 'a']), 'records', {})
    # 클래스 이름·모듈 문자열만 같은 임의 객체를 DataFrame으로 승인하지 않는다.
    impostor = type('DataFrame', (), {'__module__': module_name})()
    with pytest.raises(Fault, match='지원하지 않는 자료형'):
        export_value(impostor, 'records', {})


def test_explicit_old_wire_consumer_gets_protocol_error(registry):
    out = run(call('builtins:tuple', [[1]]), registry, value_protocols=['ibl-value/1'])
    assert out['diagnostic']['code'] == 'VALUE_PROTOCOL_UNSUPPORTED'
    assert out['diagnostic']['details']['value_preview']['$ibl'] == 'foreign_ref'


def test_crash_is_uncertain_not_retried(registry):
    out = run(call('os:_exit', [7]), registry)
    assert out['diagnostic']['code'] == 'PY_WORKER_LOST'
    assert out['diagnostic']['details']['effect_status'] == 'unknown'
    assert len(out['recordings']) == 1


def test_partial_ref_honors_old_consumer_protocol(registry):
    out = run(call('builtins:tuple', [[1]], result='value'), registry,
              value_protocols=['ibl-value/1'])
    assert out['diagnostic']['code'] == 'PY_VALUE_CONVERSION'
    assert 'partial_wire' not in out
    assert out['partial_wire_error']['code'] == 'VALUE_PROTOCOL_UNSUPPORTED'


def test_negative_timeout_rejected_before_worker(registry):
    rt = Runtime(compile_program('[self:script]{id:"python_libraries",args:{op:"call",target:"math:sqrt",timeout:-1}}', registry))
    out = rt.run()
    assert out['diagnostic']['code'] == 'ARGUMENT_CONTRACT'
    assert not rt.foreign_sessions


def test_export_bytes_uses_output_gate(tmp_path):
    registry = load_registry(str(tmp_path))
    out = run('''$b=[self:script]{id:"python_libraries",args:{op:"call",target:"builtins:bytes",args:[[0,1,255]]}}
return [self:script]{id:"python_libraries",args:{receiver:$b,op:"export",format:"bytes",options:{path:"sample.bin"}}}''', registry)
    assert out['success'], out
    assert Path(out['value']['path']).read_bytes() == b'\x00\x01\xff'
    assert Path(out['value']['path']).parent == tmp_path / 'outputs'


def test_environment_change_between_check_and_call_is_refused(registry, monkeypatch):
    import python_environment_lock
    plan = compile_program(call('statistics:mean', [[1, 2]]), registry)
    monkeypatch.setattr(python_environment_lock, 'fingerprint', lambda _: 'changed')
    out = Runtime(plan).run()
    assert out['diagnostic']['code'] == 'DEFINITION_CHANGED'


def test_model_projection_keeps_foreign_expiration(registry, tmp_path, monkeypatch):
    import model_result_view
    from supervision_store import TurnStore
    monkeypatch.setattr(model_result_view, 'evidence_store', lambda: TurnStore(tmp_path))
    out = run(call('builtins:tuple', [[1]]), registry)
    shown = model_result_view.project_result(out)
    assert shown['success']
    assert shown['value']['lifetime'] == 'execution_only'


def test_mutation_evidence_reaches_export_without_expanding_every_prior_event(registry):
    out = run('''$a=[self:script]{id:"python_libraries",args:{op:"call",target:"builtins:list",result:"ref"}}
[self:script]{id:"python_libraries",args:{receiver:$a,op:"call",name:"append",args:[7]}}
$v=[self:script]{id:"python_libraries",args:{receiver:$a,op:"export",format:"list"}}
return evidence($v)''', registry)
    assert out['success'], out
    calls = [e['python'] for e in out['value']['events'] if e.get('python')]
    assert any(e['member'] == 'append' for e in calls)
    assert any(e['operation'] == 'export' for e in calls)


def test_mcp_and_http_preserve_value_protocol_negotiation(monkeypatch):
    import anyio
    import mcp_server
    from api_ibl import IBLRequest
    seen = []
    def post(path, payload, timeout):
        seen.append(IBLRequest(**payload))
        return {'success': True, 'value': 1}
    monkeypatch.setattr(mcp_server, '_post_backend', post)
    async def invoke():
        return await mcp_server.execute_ibl('return 1', value_protocols=['ibl-value/1'])
    anyio.run(invoke)
    assert seen[0].value_protocols == ['ibl-value/1']


def test_describe_is_passive_but_get_marks_failing_property_invoked(registry):
    out = run('''$getter=[self:script]{id:"python_libraries",args:{op:"getattr",target:"builtins:len"}}
$property=[self:script]{id:"python_libraries",args:{op:"call",target:"builtins:property",args:[$getter]}}
$bases=[self:script]{id:"python_libraries",args:{op:"call",target:"builtins:tuple"}}
$class=[self:script]{id:"python_libraries",args:{op:"call",target:"builtins:type",args:["Probe",$bases,{p:$property}]}}
$obj=[self:script]{id:"python_libraries",args:{op:"call",receiver:$class}}
$description=[self:script]{id:"python_libraries",args:{receiver:$obj,op:"describe",name:"p"}}
return [self:script]{id:"python_libraries",args:{receiver:$obj,op:"getattr",name:"p"}}''', registry)
    assert out['diagnostic']['details']['stage'] == 'invoke'
    assert out['diagnostic']['details']['invoked'] is True
    assert len(out['recordings']) == 7  # describe completed without running len


def test_script_discovery_and_retired_vocabulary(registry):
    assert 'self:python' not in registry
    assert compile_program('[self:python]{op:"modules"}', registry).issues
    out = run('[self:script]{op:"list"}', registry)
    row = next(x for x in out['value']['items'] if x['id'] == 'python_libraries')
    assert row['runnable']
    assert row['callable_contract']['adapter']['protocol'] == 'ibl-script-session/1'


def test_script_args_pipe_keeps_reference(registry):
    out = run('''$a=[self:script]{id:"python_libraries",args:{op:"call",target:"builtins:tuple",args:[[4,5]]}}
return {op:"export",receiver:$a,format:"list"} >> [self:script]{id:"python_libraries"}''', registry)
    assert out['value'] == [4, 5]


@pytest.mark.parametrize('extra', ['background:true', 'args_file:"unused.json"', 'timeout:-1'])
def test_session_incompatible_modes_fail_before_worker(registry, extra):
    rt = Runtime(compile_program('[self:script]{id:"python_libraries",' + extra + '}', registry))
    assert not rt.run()['success']
    assert not rt.foreign_sessions


def test_ordinary_script_receipts_still_replay(registry):
    from ibl_v2_adapters import Adapter
    actual = registry['self:script']
    calls = []
    def body(runtime, args):
        calls.append(args)
        return 42
    isolated = {'self:script': Adapter(actual.contract, body, stateful=actual.stateful)}
    code = '[self:script]{id:"ordinary_receipt_fixture"}'
    first = run(code, isolated)
    second = run(code, isolated, recordings=first['recordings'], replay=True)
    assert second['value'] == 42 and len(calls) == 1


def test_session_requires_local_action_capability(registry, monkeypatch):
    import device_registry
    monkeypatch.setattr(device_registry, 'local_capabilities', lambda: [])
    rt = Runtime(compile_program(call('statistics:mean', [[1, 2]]), registry))
    assert rt.run()['diagnostic']['code'] == 'SCRIPT_CAPABILITY'
    assert not rt.foreign_sessions


@pytest.mark.parametrize('field,value', [('effects', ['pure']), ('stateful', False), ('local_code', False)])
def test_session_contract_cannot_hide_effects_or_local_code(field, value):
    import yaml
    from ibl_v2_adapters import validate_contract
    contract = yaml.safe_load((ROOT / 'data/scripts/registry.yaml').read_text())['python_libraries']['callable_contract']
    if field == 'effects':
        contract[field] = value
    else:
        contract['adapter'][field] = value
    with pytest.raises(ValueError, match='unknown'):
        validate_contract(contract)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
