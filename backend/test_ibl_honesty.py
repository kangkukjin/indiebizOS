"""Incomplete envelope evidence survives projection without inspecting business rows."""
import boot_paths  # noqa: F401
import pytest

from ibl_honesty import completion_evidence, merge_into
from ibl_v2_adapters import decode_envelope
from ibl_v2_ir import Fault


def test_errors_without_count_preserve_partial_rows_at_adapter_boundary():
    value = {"success": True, "items": [{"title": "available"}],
             "errors": ["source A: HTTP 429", {"source": "B", "status": 503}]}
    envelope = {"success": True, "value": value}
    merge_into(value, envelope)
    with pytest.raises(Fault) as failure:
        decode_envelope(envelope, {"value_path": "/value"})
    assert failure.value.code == "PARTIAL_SOURCE"
    assert failure.value.partial == value
    assert failure.value.details["completion"][0]["errors"] == value["errors"]


@pytest.mark.parametrize("value", [
    {"success": True, "errors": [], "items": []},
    {"success": True, "items": [{"errors": ["ordinary business field"]}]},
    {"success": True, "value": {"errors": ["typed business value"]}},
])
def test_empty_errors_and_business_values_are_not_failure_envelopes(value):
    assert completion_evidence(value) == []
    assert decode_envelope(value, {"value_path": ""})[0] == value


def test_repeated_completion_summary_does_not_duplicate_error_evidence():
    failure = {"errors": ["source unavailable"]}
    evidence = completion_evidence(failure)
    repeated = completion_evidence({**failure, "incomplete_steps": evidence})
    assert len(repeated) == 1 and repeated[0]['errors'] == failure['errors']


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))


@pytest.mark.parametrize('status,required,expected', [
    ('satisfied', True, False), ('unsatisfied', True, True),
    ('undetermined', True, True), ('unsatisfied', False, False),
])
def test_required_completion_shared_consumers(status, required, expected):
    from conscious_supervisor import _failed
    from ibl_result_transport import tool_result_is_error
    from workflow_verdict import is_error_result
    import json
    env = {'edition': 2, 'success': True, 'source_complete': True, 'value': 2,
           'completion': {'protocol': 'ibl-completion/1', 'status': status if required else 'undetermined',
                          'obligations': [{'id': 'x', 'required': required, 'status': status}]}}
    assert bool(completion_evidence(env)) is expected
    assert _failed(env) is expected
    assert is_error_result(env) is expected
    assert tool_result_is_error(json.dumps(env)) is expected
    assert completion_evidence({'edition': 2, 'success': True, 'value': env}) == []


def test_actual_app_helper_and_remote_core_consume_completion():
    import json
    import subprocess
    from pathlib import Path
    cases = []
    for state, complete in [('unsatisfied', True), ('undetermined', True), ('satisfied', False)]:
        cases.append({'edition': 2, 'success': True, 'source_complete': complete, 'value': 2,
                      'completion': {'protocol': 'ibl-completion/1', 'status': state,
                                     'obligations': [{'id': 'x', 'status': state, 'required': True}]}})
    js = r'''
const fs=require('fs'),vm=require('vm'),ts=require('./frontend/node_modules/typescript');
const core={};vm.createContext(core);
vm.runInContext(fs.readFileSync('backend/static/app_render_core.js','utf8').split('/* --- ESM export')[0],core);
const code=ts.transpileModule(fs.readFileSync('frontend/src/lib/instrument.ts','utf8'),
 {compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
const cases=JSON.parse(fs.readFileSync(0,'utf8'));
(async()=>{
 const out=[];
 for(const response of cases){
   let request;
   const box={exports:{},require:n=>n==='./ibl-completion'?core:n==='./remote-session'
      ?{iblSurface:{},checkRemoteSession:()=>{}}:{BACKEND_ORIGIN:'http://synthetic.invalid'},
      fetch:async(u,o)=>{request=JSON.parse(o.body);return {ok:true,status:200,json:async()=>response}}};
   vm.runInNewContext(code,box);
   try {await box.exports.iblExecuteApp('return 2',{completion:[{id:'x'}],allowIncomplete:true});
      out.push({accepted:true,request,remote:core.unwrapFinalResult(response)});}
   catch(e){out.push({accepted:false,request,remote:core.unwrapFinalResult(response)});}
 }
 process.stdout.write(JSON.stringify(out));
})().catch(e=>{process.stderr.write(String(e));process.exitCode=1});
'''
    out = subprocess.run(['node', '-e', js], input=json.dumps(cases), text=True, capture_output=True,
                         cwd=Path(__file__).resolve().parents[1], timeout=30, check=True)
    results = json.loads(out.stdout)
    assert [r['accepted'] for r in results] == [False, False, True]
    assert all(r['request']['completion'] == [{'id': 'x'}] for r in results)
    assert all(r['remote']['error'] for r in results[:2])
    assert results[2]['remote'] == 2


def test_completion_issue_survives_repeated_summary():
    env = {'edition': 2, 'success': True, 'completion': {
        'protocol': 'ibl-completion/1', 'status': 'unsatisfied',
        'obligations': [{'id': 'x', 'required': True, 'status': 'unsatisfied'}]}}
    evidence = completion_evidence(env)
    assert evidence
    assert completion_evidence({'incomplete_steps': evidence}) == evidence
