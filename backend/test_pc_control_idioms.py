"""공개 PC 함수: 실제 컴파일·어댑터·영수증을 통한 대기와 재개, 장치 전송만 모의."""
import copy
import importlib.util
import json
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pc_component_test', ROOT / 'data/scripts/pc_control.py')
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
    state = {'terminal': False, 'calls': [], 'plans': [], 'connected': True}
    target = {'device_id': 'pc-1', 'connected': True, 'registration': {
        'state': 'active', 'capabilities': {'os': 'windows', 'shell': True}}}

    def leaf(step, *args, **kw):
        key, params = step['_node'] + ':' + step['action'], step['params']
        state['calls'].append((key, copy.deepcopy(params)))
        if key == 'self:limb':
            return {'success': True, 'limbs': [{**target, 'connected': state['connected']}]}
        if key == 'self:read':
            return {'success': True, 'text': 'native fixture', 'blocks': [], 'data': None}
        if key == 'self:script':
            assert params['id'] == 'PC제어부품'
            value = pc.run(params['args'], params.get('_ibl_context', {}))
            if params['args']['op'] == 'prepare':
                state['plans'].append(value)
            return {'success': True, 'value': value}
        if key == 'limbs:guestpc':
            assert params['background'] and params['timeout'] == 30
            state['job'] = {'kind': 'guestpc', 'task_id': 'job-1'}
            return {'success': True, 'limb': 'pc-1', 'request_id': params['request_id'],
                    'task_ref': state['job']}
        if key == 'self:task':
            assert params['ref'] == state['job']
            plan = state['plans'][-1]
            native = dict(protocol=pc.PROTOCOL, request_id=plan['request']['request_id'],
                          platform='windows', action='status', success=True, verified=True, devices=[])
            import task_receipts
            return {'success': True, 'limb': 'pc-1', **task_receipts.view(state['job'],
                    'succeeded' if state['terminal'] else 'running',
                    result={'exit': 0, 'output': pc.MARKER + json.dumps(native)} if state['terminal'] else None)}
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
    first = run('return [fn:PC제어]{대상:"pc-1",요청:{action:"status"},대기:0}')
    assert first['status'] == 'pending', json.dumps(first, ensure_ascii=False)
    assert set(first['verification']) == {'request', 'platform', 'source_sha256'}
    assert 'stdin' not in json.dumps(first)
    state['terminal'] = True
    second = run('return [fn:PC제어확인]{작업:$task,대기:0}', {'task': first})
    assert second['status'] == 'completed' and second['verified'], second
    assert sum(k == 'limbs:guestpc' for k, _ in state['calls']) == 1
    assert sum(k == 'self:script' and p['args']['op'] == 'prepare' for k, p in state['calls']) == 1


@pytest.mark.parametrize('field', ['target', 'task_ref', 'verification', 'evidence_ref'])
def test_tampered_plan_is_never_verified(flow, field):
    run, state = flow
    task = run('return [fn:PC제어]{대상:"pc-1",요청:{action:"status"},대기:0}')
    assert task['status'] == 'pending', task
    task[field] = 'wrong' if field == 'target' else {}
    before = len(state['calls'])
    result = run('return [fn:PC제어확인]{작업:$task,대기:0}', {'task': task})
    assert result['status'] == 'unknown' and not result['verified'], result
    assert not any(k in {'limbs:guestpc','self:task'} for k, _ in state['calls'][before:])


def test_disconnected_target_never_submits(flow):
    run, state = flow
    state['connected'] = False
    result = run('return [fn:PC제어]{대상:"pc-1",요청:{action:"status"}}')
    assert result['status'] == 'failed'
    assert not any(k == 'limbs:guestpc' for k, _ in state['calls'])


def test_changed_verifier_returns_unknown(flow, monkeypatch):
    run, state = flow
    task = run('return [fn:PC제어]{대상:"pc-1",요청:{action:"status"},대기:0}')
    monkeypatch.setattr(pc, 'helper_hash', lambda: 'changed')
    result = run('return [fn:PC제어확인]{작업:$task,대기:0}', {'task': task})
    assert result['status'] == 'unknown' and not result['verified']


def test_receipt_from_another_actor_is_not_opened(flow, monkeypatch):
    import ibl_run_journal
    run, state = flow
    task = run('return [fn:PC제어]{대상:"pc-1",요청:{action:"status"},대기:0}')
    assert task['status'] == 'pending'
    monkeypatch.setattr(ibl_run_journal, 'receipt_access_scope', lambda: 'another_actor')
    result = run('return [fn:PC제어확인]{작업:$task,대기:0}', {'task': task})
    assert result['status'] == 'unknown' and not result['verified']


def test_app_keeps_pending_and_confirm_never_resubmits():
    import subprocess
    script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const ts=require('./frontend/node_modules/typescript'),m={exports:{}};
const calls=[];
const pending={status:'pending',target:'pc-1',task_ref:{kind:'guestpc',task_id:'one'},verification:{},evidence_ref:{}};
const native={success:true,protocol:'pc-control/1',platform:'windows',action:'status',devices:[]};
const mock={iblExecuteApp:async(code,options)=>{calls.push([code,options]);return calls.length===1?pending:{status:'completed',result:native};}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync('frontend/src/lib/pc-control.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports:m.exports,require:()=>mock});
(async()=>{
 let saved;
 try {await m.exports.controlPC('pc-1','windows','status');assert.fail('pending lost');}
 catch(e){assert.ok(e instanceof m.exports.PCUnfinished);saved=e;}
 await m.exports.confirmPC(saved.task,'windows',saved.action);
 assert.ok(calls[0][0].includes('[fn:PC제어]'));
 assert.ok(calls[1][0].includes('[fn:PC제어확인]'));
 assert.equal(JSON.parse(calls[1][0].split('[fn:PC제어확인]')[1]).작업.task_ref.task_id,'one');
})().catch(e=>{console.error(e);process.exit(1)});
'''
    result = subprocess.run(['node','-e',script],cwd=ROOT,text=True,capture_output=True,timeout=30)
    assert result.returncode == 0, result.stderr


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
