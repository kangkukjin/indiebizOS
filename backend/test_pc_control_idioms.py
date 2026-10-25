"""공개 PC 함수: 실제 컴파일·어댑터·영수증을 통한 대기와 재개, 장치 전송만 모의."""
import copy
import importlib.util
import json
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

pytestmark = pytest.mark.usefixtures("installed_functions")

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
    from script_workspace import request_scope
    state = {'terminal': False, 'calls': [], 'plans': [], 'connected': True}
    target = {'device_id': 'pc-1', 'connected': True, 'registration': {
        'state': 'active', 'capabilities': {'os': 'windows', 'shell': True}}}

    def leaf(step, *args, **kw):
        key, params = step['_node'] + ':' + step['action'], step['params']
        state['calls'].append((key, copy.deepcopy(params)))
        if key == 'self:script' and params['id'] == 'TV제어':
            state['startup_hook']('tv')
            assert params['args']['op'] == 'on'
            return {'success': True, 'value': {'success': True, 'power': 'on', 'verified': True, 'op': 'on', 'target': params['args']['target']}}
        if key == 'limbs:youtube':
            state['startup_hook']('search')
            assert params['op'] == 'search'
            return {'success': True, 'items': [{'title': 'candidate', 'duration': '1:23'}]}
        if key == 'self:limb':
            return {'success': True, 'limbs': [{**target, 'connected': state['connected']}]}
        if key == 'self:read':
            return {'success': True, 'text': 'native fixture', 'blocks': [], 'data': None}
        if key == 'self:script':
            assert params['id'] == 'PC제어부품'
            if params['args']['op'] == 'local':
                return {'success': True, 'value': {
                    'success': True, 'protocol': pc.PROTOCOL, 'platform': 'darwin',
                    'action': params['args']['request']['action'], 'request_id': 'local-test',
                    'source_sha256': 'test', 'verified': True}}
            value = pc.run(params['args'], params.get('_ibl_context', {}))
            if params['args']['op'] == 'prepare':
                state['plans'].append(value)
            return {'success': True, 'value': value}
        if key == 'limbs:guestpc':
            action = state['plans'][-1]['request']['action']
            assert params['background'] and params['timeout'] == (120 if action.startswith('youtube_') or action == 'chrome_launch' else 30)
            if 'startup_hook' in state:
                state['startup_hook']('browser')
            state['job'] = {'kind': 'guestpc', 'task_id': 'job-1'}
            return {'success': True, 'limb': 'pc-1', 'request_id': params['request_id'],
                    'task_ref': state['job']}
        if key == 'self:task':
            assert params['ref'] == state['job']
            plan = state['plans'][-1]
            native = dict(protocol=pc.PROTOCOL, request_id=plan['request']['request_id'],
                          platform='windows', action='status', success=True, verified=True, devices=[])
            native.update(state.get('native', {}))
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
        with request_scope(str(tmp_path)), Journal(tmp_path / 'runs', plan.fingerprint) as journal:
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


def test_search_video_row_and_native_error_survive_public_function_without_retransmit(flow):
    run, state = flow
    state['terminal'] = True
    state['native'] = {'action': 'youtube_replace', 'success': False, 'verified': False,
                       'error': 'YOUTUBE_PLAYER_ERROR: 문제가 발생했습니다.',
                       'last_observation': {'state': 'error', 'player_error': '문제가 발생했습니다.'}}
    row = {'url': 'https://www.youtube.com/watch?v=0eyvWdgx_gk',
           'title': '𝗣𝗟𝗔𝗬𝗟𝗜𝗦𝗧 가을밤 | 잔나비 •••', 'duration': '2:32:06'}
    result = run('return [fn:PC제어]{대상:"pc-1",요청:{action:"youtube_replace",video:$video}}', {'video': row})
    assert result['status'] == 'failed' and result['verified'] is False, result
    assert result['failure']['code'] == 'YOUTUBE_PLAYER_ERROR', result
    assert '반복' in result['failure']['next']
    assert result['result']['last_observation']['state'] == 'error'
    assert result['verification']['request']['title'] == row['title']
    assert result['verification']['request']['duration_seconds'] == 9126
    assert sum(k == 'limbs:guestpc' for k, _ in state['calls']) == 1


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


@pytest.mark.parametrize('evidence', [
    None, [], 'lost', 1, False,
    {'plan': None, 'job': {}}, {'plan': {}, 'job': None},
    {'plan': [], 'job': {}}, {'plan': {}, 'job': 'lost'},
])
def test_malformed_receipt_returns_unknown_without_transport(flow, evidence):
    run, state = flow
    task = run('return [fn:PC제어]{대상:"pc-1",요청:{action:"status"},대기:0}')
    task['evidence_ref'] = evidence
    before = len(state['calls'])
    result = run('return [fn:PC제어확인]{작업:$task,대기:0}', {'task': task})
    assert result['status'] == 'unknown' and not result['verified'], result
    assert result['target'] == task['target']
    assert result['task_ref'] == task['task_ref']
    assert not any(k in {'limbs:guestpc', 'self:task'} for k, _ in state['calls'][before:])


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


def test_batch_missing_target_selects_once_and_never_submits(flow):
    run, state = flow
    result = run('return [fn:PC조회묶음]{대상:"missing"}')
    assert len(result['items']) == 4
    assert all(r['status'] == 'failed' and not r['verified'] and r['task_ref'] is None for r in result['items'])
    assert all('접수되지' in r['failure']['next'] for r in result['items'])
    assert sum(k == 'self:limb' for k, _ in state['calls']) == 1
    assert sum(k == 'self:script' and p['args']['op'] == 'select' for k, p in state['calls']) == 1
    assert not any(k in {'self:read', 'limbs:guestpc', 'self:task'} for k, _ in state['calls'])


def test_batch_reads_share_selection_but_keep_fresh_results(flow):
    run, state = flow
    state['terminal'] = True
    code = 'return [fn:PC조회묶음]{대상:"pc-1",항목:["status","status"]}'
    for _ in range(2):
        result = run(code)
        assert all(r['status'] == 'completed' and r['verified'] for r in result['items']), result
    assert sum(k == 'self:limb' for k, _ in state['calls']) == 2
    assert sum(k == 'self:script' and p['args']['op'] == 'select' for k, p in state['calls']) == 2
    assert sum(k == 'self:read' for k, _ in state['calls']) == 2
    assert sum(k == 'limbs:guestpc' for k, _ in state['calls']) == 4


def test_local_batch_skips_remote_inventory_and_reads_every_item(flow):
    run, state = flow
    result = run('return [fn:PC조회묶음]{대상:"__local__",항목:["status","status"]}')
    assert all(r['verified'] for r in result['items'])
    assert sum(k == 'self:read' for k, _ in state['calls']) == 1
    assert sum(k == 'self:script' and p['args']['op'] == 'local' for k, p in state['calls']) == 2
    assert not any(k in {'self:limb', 'limbs:guestpc'} for k, _ in state['calls'])


def test_batch_rejects_mutations_before_target_resolution(flow):
    run, state = flow
    with pytest.raises(AssertionError, match='읽기 동작만'):
        run('return [fn:PC조회묶음]{대상:"__local__",항목:["status","lock"]}')
    assert state['calls'] == []


def test_tv_guide_starts_independent_preparation_together_without_duplicate_queries(flow):
    import re
    import threading
    run, state = flow
    state['terminal'] = True
    windows = [{'window_id': 1, 'state': 'minimized', 'tabs': [
        {'tab_id': 'A', 'url': 'https://www.youtube.com/', 'name': 'YouTube'}]}]
    state['native'] = {'action': 'chrome_launch', 'surface': 'app:com.google.Chrome',
                       'running': True, 'windows': windows}
    barrier = threading.Barrier(3)
    seen = []
    def reached(branch):
        seen.append(branch)
        barrier.wait(timeout=15)
    state['startup_hook'] = reached
    guide = (ROOT / 'data/guides/tv_control.md').read_text()
    code = re.search(r'<!-- example:tv_pc_startup -->\s*```ibl\n(.*?)```', guide, re.S)[1]
    code = code.replace('등록된 TV의 device_id', 'tv-1').replace('연결된 Windows PC의 device_id', 'pc-1')
    result = run(code)
    assert sorted(seen) == ['browser', 'search', 'tv']
    assert result[0]['result']['power'] == 'on'
    assert result[1]['result']['status'] == 'completed', result
    assert result[1]['result']['result']['windows'] == windows
    assert len(state['plans']) == 1 and state['plans'][0]['request']['action'] == 'chrome_launch'
    assert sum(k == 'self:task' for k, _ in state['calls']) == 1
    assert sum(k == 'self:script' and p['id'] == 'TV제어' for k, p in state['calls']) == 1
