"""Phone picker regression: local IBL bindings, list shape and runtime readiness."""
import boot_paths  # noqa: F401
import json
from pathlib import Path
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_phone_picker_on_both_surfaces():
    manifest = yaml.safe_load((ROOT / 'data/instruments/phone_control.yaml').read_text())
    picker = manifest['modes'][0]['inputs'][0]
    script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const ts=require('./frontend/node_modules/typescript');
const inp=JSON.parse(process.argv[1]);
const core=fs.readFileSync('backend/static/app_render_core.js','utf8').split('/* --- ESM export')[0];
const desktop=fs.readFileSync('frontend/src/components/GenericInstrument.tsx','utf8');
const resolver=desktop.slice(desktop.indexOf('function resolveOptionsAction('),desktop.indexOf('// 배열은 option_value'));
const scope={};vm.createContext(scope);vm.runInContext(core+ts.transpile(resolver),scope);
assert.equal(scope.resolveOptionsAction(inp.options_action,{}).missing,false);
assert.equal(scope.resolveOptionsAction('$r = [n:a]{}; return $r.items >> [t:f]{where: ($p) => $p.id == $parent}',{}).missing,true);
assert.equal(scope.resolveOptionsAction('return [n:a]{id:$parent}',{parent:'some"value'}).code,'return [n:a]{id:$parent}');
const source=fs.readFileSync('frontend/surfaces/remote/launcher_appmode_rest_js.js','utf8');
const selected={dataset:{},options:[{value:'',textContent:inp.label}],value:'',remove(i){this.options.splice(i,1)},appendChild(o){this.options.push(o)}};
const elements={in_target:selected,in_parent:{value:''}};
const rows=['삼성0','삼성1','예나폰'].map((alias,i)=>({alias,device_id:'phone-'+i}));
let requests=[];
Object.assign(scope,{document:{getElementById:k=>elements[k]||null,createElement:()=>({})},
 CUR:{mode:{edition:2},optCache:{}},gatherInputs:()=>({target:''}),
 ibl:async req=>{requests.push(req);return {items:rows}}});
vm.runInContext(source.slice(source.indexOf('function resolveOptionsAction('),source.indexOf('/* select 변경 시')),scope);
(async()=>{
 await scope.fillOptions(inp);
 assert.equal(requests.length,1);assert.equal(requests[0].code,inp.options_action);
 assert.deepEqual(selected.options.slice(1).map(o=>o.textContent),['삼성0','삼성1','예나폰']);
 assert.deepEqual(selected.options.slice(1).map(o=>o.value),['phone-0','phone-1','phone-2']);
 assert.equal(scope.resolveOptionsAction('return [n:a]{id:$parent}').missing,true);
 elements.in_parent.value='ok';assert.equal(scope.resolveOptionsAction('return [n:a]{id:$parent}').missing,false);
 const mod={exports:{}};
 vm.runInNewContext(ts.transpile(fs.readFileSync('frontend/src/lib/phone-control.ts','utf8'),{module:ts.ModuleKind.CommonJS}),
  {exports:mod.exports,require:()=>({}),Error});
 const target=(id,extra={})=>({device_id:id,alias:id,connected:true,env:{os:'android'},registration:{state:'active',capabilities:{execution_contract:1,python:'3.12.7',runtimes:{python:{ready:true}}}},...extra});
 const list=mod.exports.phoneTargets({limbs:[target('s1'),target('s0'),target('yena'),target('removed',{revoked:true}),target('pc',{env:{os:'linux'}})]});
 assert.equal(list.length,3);assert.ok(list.every(p=>p.ready));
 const paused=target('paused');paused.registration.paused=true;
 const stopped=mod.exports.phoneTargets({limbs:[paused]})[0];assert.equal(stopped.ready,false);assert.equal(stopped.paused,true);
 assert.equal(mod.exports.phoneTargets({limbs:[target('invite',{invitation:true}),target(null),target('legacy',{registration:null})]}).length,0);
 assert.equal(mod.exports.phoneTargets({limbs:[target('old',{registration:{state:'active',capabilities:{execution_contract:1,python:'3.11'}}})]})[0].ready,false);
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    result = subprocess.run(['node', '-e', script, json.dumps(picker)], cwd=ROOT,
                            text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_template_guard_accepts_declared_envelope_inputs(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    from iblbuild_appview import validate_app_template_params
    action = {'params': {'inputs': 'object'}, 'app': {
        'action': 'return [limbs:test]{inputs:{op:"status"}}'}}
    data = {'nodes': {'limbs': {'actions': {'test': action}}}}
    assert validate_app_template_params(data, tmp_path) == []
    action['app']['action'] = 'return [limbs:test]{inputz:{op:"status"}}'
    assert any('inputz' in issue for issue in validate_app_template_params(data, tmp_path))


def test_phone_picker_handles_legacy_and_paused_devices_in_every_mode():
    from ibl_v2_entry import handle_request
    manifest = yaml.safe_load((ROOT / 'data/instruments/phone_control.yaml').read_text())
    row = {'device_id': 'phone', 'connected': True, 'revoked': False, 'expired': False,
           'registration': {'state': 'active', 'paused': False}, 'env': {'os': 'android'}}
    fixtures = [row, {**row, 'registration': None},
                {**row, 'device_id': 'paused', 'registration': {'state': 'active', 'paused': True}},
                {**row, 'device_id': 'pc', 'env': {'os': 'windows'}},
                {**row, 'device_id': 'offline', 'connected': False}]
    for mode in manifest['modes']:
        picker = next(i for i in mode['inputs'] if i['key'] == 'target')
        code = picker['options_action'].replace('[self:limb]{op: "list"}', '$fixture')
        result = handle_request({'edition': 2, 'code': code, 'inputs': {'fixture': {'limbs': fixtures}},
                                 'declared_inputs': ['fixture']}, str(ROOT), None)
        assert result['success'], result.get('error')
        assert result['value']['items'] == [row]


def test_phone_commands_read_current_hub_scripts_and_compile():
    from ibl_v2_compile import compile_program
    from ibl_v2_adapters import load_registry
    script = r'''
const fs=require('fs'),vm=require('vm'),ts=require('./frontend/node_modules/typescript');
const driver={exports:{}};
vm.runInNewContext(ts.transpile(fs.readFileSync('frontend/src/lib/android-control.ts','utf8'),{module:ts.ModuleKind.CommonJS}),{exports:driver.exports,require:()=>({}),Error});
const result=[];
for(const name of ['phone-control','phone-actions']) {
 const m={exports:{}};
 vm.runInNewContext(ts.transpile(fs.readFileSync('frontend/src/lib/'+name+'.ts','utf8'),{module:ts.ModuleKind.CommonJS}),
  {exports:m.exports,require:()=>driver.exports,Error});
 result.push(name==='phone-control'?m.exports.phoneCommandCode('phone "one"','set',4):m.exports.phoneActionCode('phone "one"','torch',{enabled:false}));
}
console.log(JSON.stringify(result));
'''
    output = subprocess.run(['node', '-e', script], cwd=ROOT, text=True, capture_output=True, timeout=30)
    assert output.returncode == 0, output.stderr
    codes = json.loads(output.stdout)
    from ibl_v2_store import installed_definitions
    for code in codes:
        assert code.count('[fn:Android제어]') == 1
        assert '[limbs:guestpc]' not in code
        plan = compile_program(code, load_registry(), definitions=installed_definitions())
        assert not plan.issues, plan.report()


def test_phone_app_propagates_device_failure_without_retry():
    from ibl_v2_entry import handle_request
    manifest = yaml.safe_load((ROOT / 'data/instruments/phone_control.yaml').read_text())
    # Every app result retains the complete failed task and its recovery evidence.
    task = {'status':'unknown','verified':False,'result':None,'task_ref':{'kind':'guestpc','task_id':'one'},
            'failure':{'message':'permission','next':'query original'}}
    for mode in manifest['modes']:
        for command in [mode, *mode.get('buttons', [])]:
            code = command['action']
            start = code.index('$state =')
            result = handle_request({'edition': 2, 'code': code[start:], 'inputs': {'r': task},
                'declared_inputs': ['r']}, str(ROOT), None)
            assert result['success'], result
            assert result['value']['control_task'] == task
            assert result['value']['status'] == 'unknown'
            assert result['value']['verified'] is False


if __name__ == '__main__':
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
