"""Real catalog/file/script/API boundaries, isolated from user assets."""
import boot_paths  # noqa: F401
import importlib.util
import json
from pathlib import Path
import sys
import pytest
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime
from ibl_v2_entry import handle_request
from ibl_v2_ir import unpack

ROOT = Path(__file__).resolve().parents[1]


def test_transitive_definitions_are_pinned_and_warm_cold_equivalent():
    definitions = {'outer':'[def:outer]($x){[fn:inner]{x:$x}}',
                   'inner':'[def:inner]($x){return {old:$x}}'}
    source = '$v=[fn:outer]{x:7}\nreturn $v.old'
    first = compile_program(source, definitions=definitions)
    definitions['inner']='[def:inner]($x){return {new:$x}}'
    second = compile_program(source, definitions=definitions)
    assert not first.issues and second.issues
    assert first.fingerprint != second.fingerprint
    assert Runtime(first).run()['value'] == 7
    assert compile_program(source, definitions=definitions).report() == second.report()


def test_local_definition_shadows_library_but_library_does_not_capture_caller():
    defs={'f':'[def:f](){return 1}', 'g':'[def:g](){[fn:f]{}}'}
    plan=compile_program('[def:f](){return 2}\n[fn:f]{} & [fn:g]{}',definitions=defs)
    assert Runtime(plan).run()['value']==[2,1]


def test_unreachable_broken_library_does_not_break_program():
    plan=compile_program('return 3',definitions={'broken':'malformed'})
    assert Runtime(plan).run()['value']==3


def test_real_catalog_closure_pipeline():
    result=handle_request({'edition':2,'code':'''$min=4
[{id:"a",score:3},{id:"b",score:8}] >> [table:filter]{where:($r)=>$r.score >= $min}
 >> [table:select]{columns:($r)=>{id:$r.id,total:$r.score*2}}''' .replace('\n >>',' >>')})
    assert result['success'],result
    assert result['value']==[{'id':'b','total':16}]


def test_real_file_document_roundtrip_keeps_literal_text_and_evidence(tmp_path):
    source=tmp_path/'source.md'
    source.write_text('# 제목\n\n원문 $missing ${x}\n')
    code='''$doc=[self:read]{path:"source.md"}
$path=[self:write]{path:"outputs/copy.txt",content:$doc.text}
return {text:$doc.text,blocks:$doc.blocks,receipt:$path,origin:evidence($doc)}'''
    result=handle_request({'edition':2,'code':code},str(tmp_path))
    assert result['success'],result
    assert (tmp_path/'outputs/copy.txt').read_text()==source.read_text()
    assert result['value']['text']==source.read_text()
    assert result['value']['origin']['events']
    assert any(e['kind']=='tool_evidence' for e in result['evidence'])


def test_file_map_collect_preserves_failure_coverage(tmp_path):
    (tmp_path/'a.txt').write_text('a')
    code='[table:each]{items:["a.txt","missing.txt"],on_error:"collect"}{[self:read]{path:$it}}'
    result=handle_request({'edition':2,'code':code},str(tmp_path))
    assert result['success'] and not result['source_complete'],result
    rows=unpack(result['value_wire']['data'])
    assert [row.ok for row in rows]==[True,False]
    assert rows[0].value['text']=='a'


def test_edition_entry_conflict_fail_closed_and_v1_unaffected():
    assert handle_request({'code':'[self:time]{}'}) is None
    r=handle_request({'code':'#!ibl edition=2\nreturn 1','edition':1})
    assert not r['success'] and not r['executed']
    assert handle_request({'code':'return 1','edition':2,'files':['x']})['status']=='invalid'


def test_checker_exception_reports_failed(monkeypatch):
    import ibl_v2_compile
    monkeypatch.setattr(ibl_v2_compile,'compile_program',lambda *a,**k:1/0)
    out=handle_request({'edition':2,'code':'return 1','check':True})
    assert out['status']=='failed' and not out['ok'] and not out['executed']


def test_http_models_and_model_tool_preserve_edition_inputs():
    from api_ibl import IBLRequest, ValidateRequest, validate_code
    from tool_loader import build_execute_ibl_tool
    assert IBLRequest(code='return $x',edition=2,inputs={'x':2}).inputs=={'x':2}
    assert ValidateRequest(code='return $x',edition=2,inputs={'x':2}).edition==2
    assert validate_code('#!ibl edition=2\nreturn 2')['valid']
    from api_ibl import validate_request_code
    assert validate_request_code('return $x',edition=2,inputs={'x':2})['valid']
    properties=build_execute_ibl_tool()['input_schema']['properties']
    assert {'edition','inputs','check'} <= properties.keys()


def script_module():
    path=ROOT/'data/packages/installed/tools/system_essentials/script_ops.py'
    spec=importlib.util.spec_from_file_location('v2_script_test',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_v2_real_process_and_old_protocol_unchanged(tmp_path,monkeypatch):
    s=script_module()
    contract={'version':1,'params':{'x':'Number'},'result':'Record','effects':['pure'],
              'adapter':{'protocol':'ibl-script/2'}}
    script=tmp_path/'v2.py'
    script.write_text('import json,sys\nr=json.load(sys.stdin)\nassert r["protocol"]=="ibl-script/2"\nprint(json.dumps({"protocol":"ibl-script/2","ok":True,"value":{"error":"business","n":r["args"]["x"]*2}}))\n')
    old=tmp_path/'old.py'
    old.write_text('import json,sys\nr=json.load(sys.stdin)\nassert "protocol" not in r\nprint(json.dumps({"items":[{"n":r["x"]}]}))\n')
    registry={'v2':{'file':'v2.py','interpreter':'python','callable_contract':contract},
              'old':{'file':'old.py','interpreter':'python'}}
    monkeypatch.setattr(s,'_read_registry',lambda:registry)
    monkeypatch.setattr(s,'_SCRIPT_DIR',tmp_path)
    monkeypatch.setattr(s,'_RUN_DIR',tmp_path/'runs')
    monkeypatch.setattr(s,'_update_state',lambda *a,**kw:None)
    monkeypatch.setattr(s,'_resolve_interpreter',lambda *a:(sys.executable,None))
    output=s.op_run({'id':'v2','args':{'x':3},'_ibl_edition':2})
    assert output['success'] and output['value']=={'error':'business','n':6},output
    adapted = s.op_run({'id':'old','args':{'x':3},'_ibl_edition':2})
    assert adapted['success'] and adapted['value'] == {'items':[{'n':3}]}
    assert adapted['script_protocol'] == 'registered-json/1'
    assert not s.op_run({'id':'v2','args':{'x':3}})['success']
    assert s.op_run({'id':'old','args':{'x':3}})['items']==[{'n':3}]


def test_script_v2_rejects_missing_or_wrong_contract(tmp_path,monkeypatch):
    s=script_module()
    contract={'version':1,'params':{},'result':'Number','effects':['pure'],
              'adapter':{'protocol':'ibl-script/2'}}
    for stdout in ['{"ok":true,"value":1}', '{"protocol":"ibl-script/2","ok":true,"value":"bad"}']:
        value,error=s._runtime.v2_output(stdout,contract)
        assert error


def test_workflow_save_load_and_legacy_id_guard(tmp_path,monkeypatch):
    import ibl_usage_db
    monkeypatch.setattr(ibl_usage_db, 'DB_PATH', str(tmp_path/'usage.db'))
    monkeypatch.setattr(ibl_usage_db.IBLUsageDB, '_instance', None)
    import workflow_store
    from ibl_v2_store import action,definitions
    from workflow_engine import execute_workflow
    monkeypatch.setattr(workflow_store,'_get_workflows_path',lambda:tmp_path)
    saved=action('save',{'edition':2,'code':'[def:double]($x){return $x*2}'},'.')
    assert saved['success'],saved
    assert definitions()=={'double':'[def:double]($x){return $x*2}'}
    assert action('run',{'edition':2,'name':'double','params':{'x':4}},'.')['value']==8
    assert not execute_workflow('double')['success']
    workflow_store.save_workflow({'id':'old','name':'old','steps':['[self:time]{}']})
    assert not action('save',{'edition':2,'workflow_id':'old','code':'[def:old](){return 1}'},'.')['success']
    assert workflow_store.get_workflow('old').get('edition',1)==1


def test_member_and_remote_script_protocol_rejected_before_exchange(monkeypatch):
    s=script_module()
    assert not s.member_script({'_ibl_edition':2},{},lambda *a:{'items':[]},None)['success']
    import requests
    monkeypatch.setattr(requests, 'get', lambda *a, **kw: (_ for _ in ()).throw(OSError('offline')))
    monkeypatch.setattr(requests, 'post', lambda *a, **kw: pytest.fail('execution before negotiation'))
    from ibl_engine import forward_to_phone, _forward_to_mac
    assert forward_to_phone('http://invalid','self','script',{'_ibl_edition':2})['error_type']=='capability'
    assert _forward_to_mac('self','script',{'_ibl_edition':2})['error_type']=='capability'


def test_script_business_path_text_is_not_expanded():
    s=script_module()
    raw={'note':'~workspace/this is literal $data'}
    assert s._stdin_args({'args':raw},expand_paths=False)[0]==raw


def test_v2_model_projection_preserves_value_and_links_full_evidence(monkeypatch):
    import model_result_view as view
    stored=[]
    class Store:
        def evidence(self,raw):
            stored.append(json.loads(raw))
            return {'id':'fixture','path':'/fixture'}
    monkeypatch.setattr(view,'evidence_store',lambda:Store())
    monkeypatch.setattr(view,'_read_reference',lambda ref,result:{'read_args':{'ref':ref['id']}})
    result={'edition':2,'success':True,'value':{'error':'data','items':[]},
            'value_wire':{'protocol':'ibl-value/1','data':['record',[]]},
            'evidence':[{'kind':'invoke'}],'source_map':{},'recordings':[],'source_complete':True}
    out=view.project_result(result)
    assert out['value']==result['value'] and 'evidence' not in out
    assert stored[0]==result and out['result_ref']['read_args']


def test_tool_evidence_is_in_the_value_dependency_graph(tmp_path):
    (tmp_path/'a.txt').write_text('hello')
    out=handle_request({'edition':2,'code':'$x=[self:read]{path:"a.txt"}\nreturn evidence($x)'},str(tmp_path))
    assert out['success']
    assert any(e['kind']=='tool_evidence' and e['attachments'].get('path') for e in out['value']['events'])


def test_script_plain_json_refuses_numbers_that_need_tagged_transport():
    s=script_module()
    with pytest.raises(ValueError):
        s._runtime._v2_json_safe({'id':2**70})


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))


@pytest.mark.parametrize('source,edition,expected', [
    ('return 3', None, 2),
    ('#!ibl edition=1\n[self:time]{}', None, 1),
    ('[self:time]{}', 1, 1),
    ('return 3', 2, 2),
])
def test_model_and_mcp_authoring_defaults_agree(monkeypatch, source, edition, expected):
    import anyio
    import system_tools
    import mcp_server
    from ibl_edition import source_edition
    request = {'code': source}
    if edition is not None:
        request['edition'] = edition
    seen = []
    def execute(payload, *args, **kwargs):
        seen.append(payload)
        return json.dumps({'success': True, 'value': 3})
    monkeypatch.setattr(system_tools, '_execute_ibl_unified', execute)
    system_tools._execute_tool_inner('execute_ibl', request, '.')
    monkeypatch.setattr(mcp_server, '_post_backend', lambda path, payload, timeout: execute(payload))
    async def call():
        return await mcp_server.execute_ibl(source, edition=edition)
    anyio.run(call)
    assert len(seen) == 2
    assert all(source_edition(p['code'], p.get('edition')) == expected for p in seen)
    assert 'edition' not in request if edition is None else request['edition'] == edition


def test_invalid_current_code_never_retries_as_legacy(monkeypatch, tmp_path):
    import system_tools
    from ibl_edition import authoring_request
    request = authoring_request({'code': '[def:f]{return 1};[fn:f]{}'})
    out = handle_request(request, str(tmp_path))
    assert out['edition'] == 2 and not out['success'] and not out['executed']


@pytest.mark.parametrize('stdout,exit_code,expected,kind', [
    ('{"items":[{"n":3}],"run":"receipt"}', 0, {'items':[{'n':3}], 'run':'receipt'}, None),
    ('plain text ' * 5000, 0, 'plain text ' * 5000 + '\n', None),
    ('{"success":false,"error":"failed"}', 0, None, 'runtime'),
    ('{"success":false,"error":"denied","blocked":true}', 0, None, 'permission'),
    ('{"items":[1],"error_count":1}', 0, None, 'partial'),
    ('{"items":[1]}', 7, None, 'runtime'),
], ids=['whole-json', 'full-text', 'failure', 'permission', 'partial', 'exit-code'])
def test_existing_script_runs_directly_with_whole_value_and_failure_evidence(
        tmp_path, monkeypatch, stdout, exit_code, expected, kind):
    s = script_module()
    script = tmp_path / 'old.py'
    script.write_text('import json,sys\nr=json.load(sys.stdin)\nassert r=={"x":3}\n'
                      + 'print(' + repr(stdout) + ')\nsys.exit(' + str(exit_code) + ')\n')
    monkeypatch.setattr(s, '_read_registry', lambda: {'old': {'file':'old.py','interpreter':'python'}})
    monkeypatch.setattr(s, '_SCRIPT_DIR', tmp_path)
    monkeypatch.setattr(s, '_RUN_DIR', tmp_path / 'runs')
    monkeypatch.setattr(s, '_update_state', lambda *a, **kw: None)
    monkeypatch.setattr(s, '_resolve_interpreter', lambda *a: (sys.executable, None))
    import ibl_engine
    monkeypatch.setattr(ibl_engine, 'execute_ibl', lambda ti, *a, **kw: s.op_run(ti['params']))
    from ibl_v2_adapters import load_registry
    plan = compile_program('[self:script]{id:"old",args:{x:3}}', load_registry(str(tmp_path)))
    out = Runtime(plan).run()
    if kind is None:
        assert out['success'] and out['value'] == expected, out
    else:
        assert not out['success'] and out['diagnostic']['kind'] == kind, out


def test_script_management_contract_uses_same_current_call_surface(monkeypatch):
    import ibl_engine
    observed = []
    def leaf(ti, *args, **kwargs):
        observed.append(ti['params'])
        return {'success': True, 'items': [], 'count': 0}
    monkeypatch.setattr(ibl_engine, 'execute_ibl', leaf)
    from ibl_v2_adapters import load_registry
    registry = load_registry()
    for code in ('[self:script]{}', '[self:script]{op:"status",job_id:"job",wait:1}'):
        out = Runtime(compile_program(code, registry)).run()
        assert out['success'] and out['value']['items'] == [], out
    assert [p['op'] for p in observed] == ['list', 'status']


def test_current_contract_help_does_not_teach_legacy_parameters():
    from model_result_view import describe_actions
    from ibl_access import render_action_line
    from ibl_registry import load_nodes_installed
    out = describe_actions(['table:filter', 'self:script'], {'table', 'self'}, edition=2)
    for row in out['actions']:
        definition = row['definition']
        assert 'callable_contract' in definition
        assert 'target_description' not in definition and 'returns' not in definition
        assert 'params' not in definition  # One authoritative signature, inside callable_contract.
    assert out['actions'][0]['definition']['callable_contract']['params']['where'] == 'Callable'
    config = load_nodes_installed()['nodes']['self']['actions']['script']
    line = render_action_line('self', 'script', config)
    assert '(args)' in line and 'Unknown' in line and 'input_as' not in line
