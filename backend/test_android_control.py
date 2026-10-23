"""Android driver: real IBL compile/runtime/receipts, mocked device transport."""
import copy
import importlib.util
import json
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('android_component_test', ROOT / 'data/scripts/android_control.py')
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)


@pytest.fixture
def flow(tmp_path, monkeypatch):
    import ibl_engine
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    from ibl_run_journal import Journal
    from ibl_v2_store import installed_definitions
    from ibl_edition import source_context
    from script_workspace import request_scope
    # Pin an isolated copy: dynamic exec otherwise fingerprints unrelated live scripts.
    import ibl_dependencies
    import yaml
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    entry = yaml.safe_load((ROOT / 'data/scripts/registry.yaml').read_text())['Android제어부품']
    (scripts / 'registry.yaml').write_text(yaml.safe_dump({'Android제어부품': entry}, allow_unicode=True))
    (scripts / 'android_control.py').write_bytes((ROOT / 'data/scripts/android_control.py').read_bytes())
    snapshot = ibl_dependencies.script_snapshot
    monkeypatch.setattr(ibl_dependencies, 'script_snapshot', lambda args, **kw: snapshot(args, root=scripts, **kw))
    state = {'terminal': False, 'calls': [], 'plans': [], 'connected': True}
    target = {'device_id': 'pc-1', 'connected': True, 'registration': {
        'state': 'active', 'capabilities': {'os': 'android', 'execution_contract': 1, 'runtimes': {'python': {'ready': True}}}}}

    def leaf(step, *args, **kw):
        key, params = step['_node'] + ':' + step['action'], step['params']
        state['calls'].append((key, copy.deepcopy(params)))
        if key == 'self:limb':
            return {'success': True, 'limbs': [{**target, 'connected': state['connected']}]}
        if key == 'self:read':
            return {'success': True, 'text': 'def run(args): return {}', 'blocks': [], 'data': None}
        if key == 'self:script':
            assert params['id'] == 'Android제어부품'
            value = pc.run(params['args'], params.get('_ibl_context', {}))
            if params['args']['op'] == 'prepare':
                state['plans'].append(value)
            return {'success': True, 'value': value}
        if key == 'limbs:guestpc':
            assert params['background'] and params['timeout'] == 20
            from phone_execution_contract import validate
            validate({k: params[k] for k in ('op', 'code', 'timeout', 'mode') if k in params})
            state['job'] = {'kind': 'guestpc', 'task_id': 'job-1'}
            return {'success': True, 'limb': 'pc-1', 'request_id': params['request_id'],
                    'task_ref': state['job']}
        if key == 'self:task':
            assert params['ref'] == state['job']
            plan = state['plans'][-1]
            native = dict(protocol=pc.PROTOCOL, request_id=plan['request_id'],
                          platform='android', action='status', success=True, verified=True, driver_status='completed',
                          source_sha256=plan['source_sha256'], hardware_control=1, screen_on=True, locked=False, battery=80, capabilities={})
            native.update(state.get("native_override", {}))
            import task_receipts
            return {'success': True, 'limb': 'pc-1', **task_receipts.view(state['job'],
                    'succeeded' if state['terminal'] else 'running',
                    result={'success': True, 'value': native} if state['terminal'] else None)}
        raise AssertionError(key)

    monkeypatch.setattr(ibl_engine, 'execute_ibl', leaf)
    registry = load_registry(str(tmp_path))
    def run(code, inputs=None):
        inputs = inputs or {}
        plan = compile_program('#!ibl edition=2\n' + code, registry, inputs=inputs,
                               definitions=installed_definitions())
        assert not plan.issues, plan.report()
        with source_context(2), request_scope(str(tmp_path)), Journal(tmp_path / 'runs', plan.fingerprint) as journal:
            result = Runtime(plan, inputs, journal=journal).run()
        assert result['success'], result
        return result['value']
    return run, state


def test_pending_then_new_run_confirms_without_retransmit(flow):
    run, state = flow
    first = run('return [fn:Android제어]{대상:"pc-1",요청:{action:"status"},대기:0}')
    assert first['status'] == 'pending', json.dumps(first, ensure_ascii=False)
    assert set(first['verification']) == {'request', 'request_id', 'platform', 'source_sha256'}
    assert 'code' not in first['verification']
    state['terminal'] = True
    second = run('return [fn:Android제어확인]{작업:$task,대기:0}', {'task': first})
    assert second['status'] == 'completed' and second['verified'], second
    assert sum(k == 'limbs:guestpc' for k, _ in state['calls']) == 1
    assert sum(k == 'self:script' and p['args']['op'] == 'prepare' for k, p in state['calls']) == 1


@pytest.mark.parametrize('field', ['target', 'task_ref', 'verification', 'evidence_ref'])
def test_tampered_plan_is_never_verified(flow, field):
    run, state = flow
    task = run('return [fn:Android제어]{대상:"pc-1",요청:{action:"status"},대기:0}')
    assert task['status'] == 'pending', task
    task[field] = 'wrong' if field == 'target' else {}
    before = len(state['calls'])
    result = run('return [fn:Android제어확인]{작업:$task,대기:0}', {'task': task})
    assert result['status'] == 'unknown' and not result['verified'], result
    assert not any(k in {'limbs:guestpc','self:task'} for k, _ in state['calls'][before:])


def test_disconnected_target_never_submits(flow):
    run, state = flow
    state['connected'] = False
    result = run('return [fn:Android제어]{대상:"pc-1",요청:{action:"status"}}')
    assert result['status'] == 'failed'
    assert not any(k == 'limbs:guestpc' for k, _ in state['calls'])


@pytest.mark.parametrize('evidence', [
    None, [], 'lost', 1, False,
    {'plan': None, 'job': {}}, {'plan': {}, 'job': None},
    {'plan': [], 'job': {}}, {'plan': {}, 'job': 'lost'},
])
def test_malformed_receipt_returns_unknown_without_transport(flow, evidence):
    run, state = flow
    task = run('return [fn:Android제어]{대상:"pc-1",요청:{action:"status"},대기:0}')
    task['evidence_ref'] = evidence
    before = len(state['calls'])
    result = run('return [fn:Android제어확인]{작업:$task,대기:0}', {'task': task})
    assert result['status'] == 'unknown' and not result['verified'], result
    assert result['target'] == task['target']
    assert result['task_ref'] == task['task_ref']
    assert not any(k in {'limbs:guestpc', 'self:task'} for k, _ in state['calls'][before:])


def test_changed_verifier_returns_unknown(flow, monkeypatch):
    run, state = flow
    task = run('return [fn:Android제어]{대상:"pc-1",요청:{action:"status"},대기:0}')
    monkeypatch.setattr(pc, 'helper_hash', lambda: 'changed')
    result = run('return [fn:Android제어확인]{작업:$task,대기:0}', {'task': task})
    assert result['status'] == 'unknown' and not result['verified']


def test_receipt_from_another_actor_is_not_opened(flow, monkeypatch):
    import ibl_run_journal
    run, state = flow
    task = run('return [fn:Android제어]{대상:"pc-1",요청:{action:"status"},대기:0}')
    assert task['status'] == 'pending'
    monkeypatch.setattr(ibl_run_journal, 'receipt_access_scope', lambda: 'another_actor')
    result = run('return [fn:Android제어확인]{작업:$task,대기:0}', {'task': task})
    assert result['status'] == 'unknown' and not result['verified']



@pytest.mark.parametrize('payload', [
    {'action': 'wifi', 'enabled': True}, {'action': 'volume', 'value': True},
    {'action': 'volume_step', 'value': 0}, {'action': 'brightness', 'value': 256},
    {'action': 'rotation', 'enabled': 'false'}, {'action': 'status', 'extra': 1},
    {'action': 'sensor', 'sensor': 'unknown'}, {'action': 'torch', 'enabled': True, 'camera_id': ''},
])
def test_invalid_request_rejected_before_preparation(payload):
    with pytest.raises(ValueError):
        pc.prepare({'request': payload, 'source': 'raise AssertionError("executed")'})


def test_generated_python_runs_same_verifier_and_preserves_request_identity():
    source = 'def run(args):\n return dict(success=True, hardware_control=1, screen_on=True, locked=False, battery=80, capabilities={})'
    plan = pc.prepare({'request': {'action': 'status'}, 'source': source})
    ns = {}
    exec(plan['code'], ns)
    result = ns['result']
    assert result['verified'] and result['driver_status'] == 'completed'
    assert result['request_id'] == plan['request_id']
    assert result['source_sha256'] == plan['source_sha256']
    assert result['verification_scope'] == 'os_state_readback'


@pytest.mark.parametrize('action,raw', [
    ('brightness', {'verified': True, 'brightness': 99, 'brightness_auto': False}),
    ('screen_off', {'verified': True, 'screen_on': True}),
    ('torch', {'verified': True, 'torches': [{'id':'0', 'enabled':False}]}),
    ('sensor', {'sensor':'light', 'reading':{'values':[], 'timestamp_ns':1}}),
])
def test_provider_verified_flag_cannot_override_readback(action, raw):
    requests = {'brightness': {'value':100}, 'screen_off': {}, 'torch':{'enabled':True}, 'sensor':{'sensor':'light'}}
    source = 'def run(args): return ' + repr({'success': True, **raw})
    out = pc.run_device({'action':action, **requests[action]}, source, 'r', 'hash')
    assert out['driver_status'] == 'failed' and not out['verified']
    assert 'POSTCONDITION_FAILED' in out['error']


@pytest.mark.parametrize('action', ['vibrate', 'settings_permission'])
def test_request_only_effects_never_claim_verification(action):
    request = pc.validate({'action': action})
    out = pc.run_device(request, 'def run(args): return {"success":True,"verified":True}', 'r', 'hash')
    assert out['driver_status'] == 'completed' and not out['verified']
    assert out['verification_scope'] == 'request_only'


def test_mutation_exception_preserves_unknown_without_reexecution():
    source = 'calls=[]\ndef run(args):\n calls.append(args)\n raise RuntimeError("lost after apply")'
    out = pc.run_device({'action':'brightness','value':100}, source, 'r', 'hash')
    assert out['driver_status'] == 'unknown' and not out['verified']
    assert out['error'] == 'lost after apply'


def test_volume_restore_keeps_verified_target(tmp_path):
    from test_phone_control import Audio, controls
    audio = Audio(9)
    path = str(tmp_path / 'receipt.json')
    controls.volume_control(audio, 3, path, 'half')
    restored = controls.volume_control(audio, 3, path, 'restore')
    assert restored['actual'] == restored['target'] == 9
    assert pc.readback({'action':'volume_restore','stream':'music'}, restored)
    assert not pc.readback({'action':'volume_restore','stream':'music'}, {**restored, 'target':4})


def test_script_wire_and_native_boundary_in_real_child_process(tmp_path):
    import subprocess
    import sys
    source = 'def run(args): return dict(success=True, hardware_control=1, screen_on=True, locked=False, battery=80, capabilities={})'
    payload = {'protocol':'ibl-script/2', 'args':{'op':'prepare','request':{'action':'status'},'source':source}}
    proc = subprocess.run([sys.executable, str(ROOT/'data/scripts/android_control.py')],
                          input=json.dumps(payload),capture_output=True,text=True,timeout=10)
    assert proc.returncode == 0, proc.stderr
    wire = json.loads(proc.stdout)
    assert wire['protocol'] == 'ibl-script/2' and wire['ok']
    plan = wire['value']
    native = subprocess.run([sys.executable, '-c', plan['code']+'\nimport json; print(json.dumps(result))'],
                            capture_output=True,text=True,timeout=10)
    value = json.loads(native.stdout)
    assert value['request_id'] == plan['request_id'] and value['verified']
    task = {'target':'phone', 'task_ref':{'kind':'guestpc','task_id':'one'},
            'verification':{k:plan[k] for k in ('request','request_id','platform','source_sha256')}}
    context = {'receipts':{'plan_ref':{'available':True,'producer':'Android제어부품','value':plan},
                          'job_ref':{'available':True,'action':'limbs:guestpc','value':{
                              'limb':'phone','task_ref':task['task_ref'],'request_id':plan['request_id']}}}}
    observation = {'task_ref':task['task_ref'],'state':'succeeded','result':{'success':True,'value':value}}
    assert pc.verify_task({'task':task,'observation':observation},context)['verified']
    for altered in [{'request_id':'wrong'},{'source_sha256':'wrong'},{'verified':True,'screen_on':None}]:
        obs = {**observation,'result':{'success':True,'value':{**value,**altered}}}
        assert not pc.verify_task({'task':task,'observation':obs},context)['verified']
    for state in ['failed','cancelled','interrupted','expired']:
        out = pc.verify_task({'task':task,'observation':{**observation,'state':state,'result':{'success':False,'error':'lost'}}},context)
        assert out['status'] == 'unknown' and not out['verified']


def test_app_pending_query_never_resubmits_and_lost_reply_blocks_replay():
    import subprocess
    script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const ts=require('./frontend/node_modules/typescript'),m={exports:{}},calls=[];
const pending={status:'pending',target:'phone',task_ref:{kind:'guestpc',task_id:'one'},verification:{},evidence_ref:{}};
let response=pending;
vm.runInNewContext(ts.transpileModule(fs.readFileSync('frontend/src/lib/android-control.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,
 {exports:m.exports,require:()=>({iblExecuteApp:async(code)=>{calls.push(code);if(response instanceof Error)throw response;return response;}})});
(async()=>{
 const api=m.exports;
 const code=api.androidCommandCode('phone',{action:'volume_step',stream:'music',value:1});
 assert.throws(()=>api.androidState(pending));
 await api.executeAndroid('phone',code);
 await assert.rejects(()=>api.executeAndroid('phone',code));assert.equal(calls.length,1);
 response={status:'completed',target:'phone',result:{success:true,protocol:'android-control/1',platform:'android',verified:true}};
 await api.confirmAndroid(pending);assert.equal(calls.length,2);
 assert.ok(calls[1].includes('[fn:Android제어확인]'));assert.ok(!calls[1].includes('[fn:Android제어]'));
 response=new Error('lost');await assert.rejects(()=>api.executeAndroid('phone',code));
 assert.equal(api.pendingAndroidTask('phone').status,'unknown');
 await assert.rejects(()=>api.executeAndroid('phone',code));assert.equal(calls.length,3);
 api.dismissAndroidTask('phone');assert.equal(calls.length,3);
})().catch(e=>{console.error(e);process.exit(1)});
'''
    proc = subprocess.run(['node','-e',script],cwd=ROOT,text=True,capture_output=True,timeout=30)
    assert proc.returncode == 0, proc.stdout + proc.stderr


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))


# ── 긴문장 87회차 수리: needs_front 동작의 화면 문맥 검사(L87-2)·조건별 거절 코드(L87-3)
def _android_row():
    return {'device_id': 'p', 'connected': True, 'registration': {'state': 'active', 'capabilities': {
        'os': 'android', 'execution_contract': 1, 'runtimes': {'python': {'ready': True}}}}}


@pytest.mark.parametrize('context, action, allowed', [
    ('{"available": false, "origin": "scheduler", "reason": "정기·배경 실행"}', 'app_launch', False),
    ('{"available": false, "origin": "scheduler", "reason": "정기·배경 실행"}', 'ui_snapshot', False),
    ('{"available": false, "origin": "scheduler", "reason": "정기·배경 실행"}', 'status', True),
    ('{"available": false, "origin": "scheduler", "reason": "정기·배경 실행"}', 'volume_half', True),
    ('{"available": true, "origin": "user", "reason": null}', 'app_launch', True),
    ('{"available": true, "origin": "training", "reason": null}', 'app_launch', True),
    (None, 'app_launch', True),   # 허브 밖 직접 실행(환경 없음)=미상 — 막지 않는다. 허브 경로는 항상 싣는다.
])
def test_needs_front_actions_follow_hub_screen_context_before_any_transport(monkeypatch, context, action, allowed):
    if context is None:
        monkeypatch.delenv('INDIEBIZOS_SCREEN_CONTEXT', raising=False)
    else:
        monkeypatch.setenv('INDIEBIZOS_SCREEN_CONTEXT', context)
    request = {'action': action, **({'package': 'com.android.settings'} if action == 'app_launch' else {})}
    args = {'target': 'p', 'request': request, 'limbs': [_android_row()]}
    if allowed:
        assert pc.select_target(args)['target'] == 'p'
    else:
        with pytest.raises(ValueError, match='^SCREEN_CONTEXT_UNAVAILABLE: '):
            pc.select_target(args)


@pytest.mark.parametrize('mutate, code', [
    (lambda r: r.update(connected=False), 'TARGET_NOT_CONNECTED'),
    (lambda r: r.update(revoked=True), 'TARGET_REVOKED'),
    (lambda r: r['registration'].update(state='removed'), 'TARGET_INACTIVE'),
    (lambda r: r['registration'].update(paused=True), 'TARGET_INACTIVE'),
    (lambda r: r['registration']['capabilities'].update(execution_contract=0), 'CONTRACT_MISMATCH'),
    (lambda r: r['registration']['capabilities']['runtimes']['python'].update(ready=False), 'PYTHON_NOT_READY'),
    (lambda r: r['registration']['capabilities'].update(os='ios'), 'TARGET_NOT_ANDROID'),
    (lambda r: r.update(device_id='other'), 'TARGET_NOT_REGISTERED'),
])
def test_target_rejections_name_the_failed_condition(monkeypatch, mutate, code):
    monkeypatch.delenv('INDIEBIZOS_SCREEN_CONTEXT', raising=False)
    row = _android_row(); mutate(row)
    with pytest.raises(ValueError, match='^' + code + ': '):
        pc.select_target({'target': 'p', 'request': {'action': 'status'}, 'limbs': [row]})


def test_failure_objects_carry_code_from_message_prefix():
    assert pc.failure_code('UI_DRIVER_UPDATE_REQUIRED: 폰 APK를 업데이트하세요.') == 'UI_DRIVER_UPDATE_REQUIRED'
    assert pc.failure_code('원래 요청·대상·작업 참조와 다릅니다.') is None
    failure = pc.verify_task({'task': {}}, {})['failure']
    assert set(failure) == {'stage', 'code', 'message', 'next'} and failure['code'] is None
