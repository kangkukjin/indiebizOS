"""Shared hardware scripts: no retries or unsupported legacy mutations."""
import boot_paths  # noqa: F401
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest
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
const success={success:true,result:{success:true,value:{success:true,verified:false,hardware_control:1}}};
vm.runInNewContext(ts.transpile(fs.readFileSync('frontend/src/lib/phone-actions.ts','utf8'),{module:ts.ModuleKind.CommonJS}),
 {exports:mod.exports,require:(path)=>path.endsWith('?raw')?{default:'SHARED_SCRIPT'}:{iblExecuteApp:async code=>{calls.push(code);return success}},Error});
(async()=>{
 const m=mod.exports;
 const state=await m.runPhoneAction('phone "one"','torch',{enabled:true});
 assert.equal(state.verified,false);assert.equal(calls.length,1);
 const args=JSON.parse(calls[0].split('[limbs:guestpc]')[1]);
 assert.equal(args.limb,'phone "one"');assert.equal(args.code,'SHARED_SCRIPT');assert.deepEqual(args.inputs,{enabled:true,op:'torch'});
 for(const bad of [{success:false}, {success:true,result:{success:false}}, {success:true,result:{success:true,value:{success:false,error:'permission'}}}]) assert.throws(()=>m.phoneActionState(bad));
 assert.throws(()=>m.phoneActionCode('','status'));
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
            compile_program(code, load_registry(), inputs=inputs)


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
