"""Shared hardware scripts: no retries or unsupported legacy mutations."""
import boot_paths  # noqa: F401
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

pytestmark = pytest.mark.usefixtures("installed_functions")
import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("phone_device", ROOT / "data/instruments/phone_device.py")
device = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(device)


def test_hardware_one_call_preserves_args_and_unverified_result():
    calls = []
    def bridge(method, text):
        calls.append((method, json.loads(text)))
        return {"success": True, "verified": False}
    assert device.run({"op": "torch", "enabled": True}, bridge)["verified"] is False
    assert calls == [("hardware", {"op": "torch", "enabled": True})]


def test_unknown_op_rejected_before_execution():
    def bridge(*_):
        pytest.fail("unsupported action reached device")
    with pytest.raises(ValueError):
        device.run({"op": "play"}, bridge)


def test_legacy_read_only_fallback_and_no_mutation():
    calls = []
    def old(*args):
        calls.append(args)
        raise RuntimeError("unsupported_device_call: hardware")
    assert device.run({"op": "status"}, old, lambda: {"hardware_control": 0}) == {"hardware_control": 0}
    with pytest.raises(RuntimeError, match="실행하지 않았습니다"):
        device.run({"op": "screen_off"}, old)
    assert len(calls) == 2


@pytest.mark.parametrize("message", ["timeout after side effect", "camera_permission_required"])
def test_runtime_error_never_retries_or_falls_back(message):
    calls = []
    def failed(*args):
        calls.append(args)
        raise RuntimeError(message)
    with pytest.raises(RuntimeError, match=message):
        device.run({"op": "torch", "enabled": True}, failed,
                   lambda: pytest.fail("incorrect fallback"))
    assert len(calls) == 1


@pytest.mark.parametrize("value", [None, {"success": False, "error": "denied"}, {}])
def test_bad_native_result_is_failure(value):
    with pytest.raises(RuntimeError):
        device.run({"op": "status"}, lambda *_: value)


def test_desktop_result_contract_and_single_execution():
    script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const ts=require('./frontend/node_modules/typescript');
const mod={exports:{}},calls=[];
const success={status:'completed',target:'phone \"one\"',result:{success:true,protocol:'android-control/1',platform:'android',verified:false,hardware_control:1}};
const driver={exports:{}};
vm.runInNewContext(ts.transpile(fs.readFileSync('frontend/src/lib/android-control.ts','utf8'),{module:ts.ModuleKind.CommonJS}),{exports:driver.exports,require:()=>({iblExecuteApp:async code=>{calls.push(code);return success}}),Error});
vm.runInNewContext(ts.transpile(fs.readFileSync('frontend/src/lib/phone-actions.ts','utf8'),{module:ts.ModuleKind.CommonJS}),
 {exports:mod.exports,require:()=>driver.exports,Error});
(async()=>{
 const m=mod.exports;
 const state=await m.runPhoneAction('phone "one"','torch',{enabled:true});
 assert.equal(state.verified,false);assert.equal(calls.length,1);
 assert.ok(calls[0].includes('[fn:Android제어]'));
 const args=JSON.parse(calls[0].split('[fn:Android제어]')[1]);
 assert.equal(args.대상,'phone "one"');assert.deepEqual(args.요청,{enabled:true,action:'torch'});
 for(const bad of [{success:false}, {success:true,result:{success:false}}, {success:true,result:{success:true,value:{success:false,error:'permission'}}}]) assert.throws(()=>m.phoneActionState(bad));
 assert.throws(()=>m.phoneActionCode('','status'));
 const previous={success:true,hardware_control:1,brightness:60,battery:80,capabilities:{settings_write:true,screen_on:true},sensors:[{id:'light',name:'Light'}]};
 const changed={success:true,hardware_control:1,observation_scope:'settings',brightness:100,brightness_auto:false,verified:true,capabilities:{settings_write:false}};
 const merged=m.mergeHardwareState(previous,changed);
 assert.equal(merged.brightness,100);assert.equal(merged.battery,80);
 assert.equal(merged.capabilities.settings_write,false);assert.equal(merged.capabilities.screen_on,true);
 assert.deepEqual(merged.sensors,previous.sensors);assert.equal(previous.brightness,60);
 const full={success:true,hardware_control:0};assert.equal(m.mergeHardwareState(merged,full),full);
 assert.equal(m.mergeHardwareState(null,changed).brightness,100);

})().catch(e=>{console.error(e);process.exitCode=1});
'''
    run = subprocess.run(['node', '-e', script], cwd=ROOT, text=True, capture_output=True, timeout=30)
    assert run.returncode == 0, run.stdout + run.stderr


def test_all_remote_app_commands_compile_and_do_not_refresh_twice():
    from ibl_v2_compile import compile_program
    from ibl_v2_adapters import load_registry
    manifest = yaml.safe_load((ROOT / 'data/instruments/phone_control.yaml').read_text())
    for mode in manifest['modes']:
        inputs = {v['key']: v.get('default', 'target') for v in mode['inputs']}
        for command in [mode, *mode.get('buttons', [])]:
            assert not command.get('refresh')
            code = '#!ibl edition=2\n' + command['action']
            from ibl_v2_store import installed_definitions
            plan = compile_program(code, load_registry(), inputs=inputs, definitions=installed_definitions())
            assert not plan.issues, plan.report()


@pytest.mark.parametrize('req,observed', [
    ({'action': 'brightness', 'value': 100}, {'brightness': 100, 'brightness_auto': False}),
    ({'action': 'brightness_auto', 'enabled': True}, {'brightness_auto': True}),
    ({'action': 'rotation', 'enabled': False}, {'auto_rotate': False, 'user_rotation': 1}),
    ({'action': 'timeout', 'seconds': 60}, {'screen_timeout_ms': 60000}),
])
def test_scoped_setting_observation_passes_driver_without_full_hardware_snapshot(req, observed):
    from test_android_control import pc
    value = {'success': True, 'verified': True, 'hardware_control': 1,
             'observation_scope': 'settings', **observed}
    assert pc.readback(req, value)
    assert not pc.readback(req, {**value, 'verified': False})
    assert not pc.readback(req, {'success': True, 'verified': True, 'observation_scope': 'settings'})


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
