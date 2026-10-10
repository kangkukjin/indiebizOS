"""관용구→실제 헬퍼 핸들러→상주 원장→task 어댑터 통합. 외부 PC에는 접속하지 않는다."""
import boot_paths  # noqa: F401
import importlib.util
from pathlib import Path

import pytest

from test_resident_pcs import registry  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def pc(registry, monkeypatch, tmp_path):
    import ibl_engine
    import ibl_routing
    import device_registry
    import resident_pcs as pcs
    import resident_store
    import task_receipts
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    from ibl_v2_store import definition_name
    from ibl_edition import source_context

    spec = importlib.util.spec_from_file_location('guestpc_idiom_handler',
        ROOT / 'data/packages/installed/tools/guest-helper/handler.py')
    handler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(handler)
    rec = registry('시험PC')
    state = {'connected': True}
    monkeypatch.setattr(handler, '_task_start_note', lambda *a: None)
    monkeypatch.setattr(device_registry, 'live_with_capability', lambda *a: [rec] if state['connected'] else [])
    monkeypatch.setattr(task_receipts, '_STATUS', {'guestpc': handler.task_status})
    monkeypatch.setattr(task_receipts, '_CANCEL', {'guestpc': handler.task_status_cancel})
    calls = []
    real_execute = ibl_engine.execute_ibl

    def leaf(step, *args, **kwargs):
        key, p = f"{step['_node']}:{step['action']}", step['params']
        calls.append((key, p))
        if key == 'self:task':
            return ibl_routing._task_op(p)
        if key == 'self:limb':
            return handler._OP_DISPATCHERS['limb_op'][p['op']](p)
        if key == 'limbs:guestpc':
            return handler._OP_DISPATCHERS['guestpc_op'][p['op']](p)
        if getattr(run, "real_local_tools", False):
            return real_execute(step, *args, **kwargs)
        raise AssertionError((key, p))

    monkeypatch.setattr(ibl_engine, 'execute_ibl', leaf)
    definitions = {definition_name(p.read_text()): p.read_text()
                   for p in (ROOT / 'data/idioms').glob('guestpc_*.ibl')}
    adapters = load_registry(str(tmp_path))

    def run(code, **inputs):
        plan = compile_program(code, adapters, definitions=definitions, inputs=inputs)
        assert not plan.issues, plan.issues
        with source_context(2):
            result = Runtime(plan, inputs, **getattr(run, 'runtime_options', {})).run()
        assert result['success'], {k: result.get(k) for k in ('error', 'diagnostic')}
        return result['value']

    def complete(job, payload):
        pcs.sync(rec['key'], 'a' * 32)
        pcs.sync(rec['key'], 'a' * 32, [{'job_id': job['task_ref']['task_id'],
            'event_id': 'result:' + job['task_ref']['task_id'], 'kind': 'result', 'payload': payload}])

    run.rec, run.calls, run.state = rec, calls, state
    run.handler, run.complete, run.path = handler, complete, tmp_path
    run.history = lambda: resident_store.history(device=rec['device_id'])['tasks']
    return run


def shell(pc):
    return pc('[fn:외부PC작업실행]{PC:"시험PC",명령:"echo ok",작업폴더:"/tmp",요청ID:"shell-1",환경:{AUDIT:"yes"}}')


def test_run_uses_real_resident_receipt_and_idempotency(pc):
    first = shell(pc)
    second = shell(pc)
    assert first['limb_name'] == '시험PC' and first['helper_mode'] == 'resident'
    assert first['task_ref'] == second['task_ref'] and len(pc.history()) == 1
    assert first['observation']['status'] == 'queued'
    pc.complete(first, {'exit': 0, 'output': 'ok'})
    checked = pc('[fn:외부PC작업확인]{작업:$job}', job=first)
    assert checked['command_ok'] and checked['result']['output'] == 'ok'


@pytest.mark.parametrize('payload,state,settled,ok', [
    ({'exit': 7, 'error': 'exit status 7', 'output': 'reason'}, 'failed', True, False),
    ({'exit': -1, 'cancelled': True}, 'cancelled', True, False),
    ({'exit': -1, 'timeout': True, 'error': 'timeout'}, 'failed', True, False),
    ({'unknown': True, 'error': 'helper restarted'}, 'unknown', False, None),
])
def test_check_preserves_real_failed_cancelled_and_unknown_evidence(pc, payload, state, settled, ok):
    job = shell(pc)
    pc.complete(job, payload)
    out = pc('[fn:외부PC작업확인]{작업:$job}', job=job)
    assert out['status'] == state and out['settled'] is settled
    assert out['command_ok'] is ok and out['result'] == payload
    assert out['task_ref'] == job['task_ref']


def test_finish_and_direct_detach_cannot_remove_resident(pc):
    import resident_pcs
    job = shell(pc)
    pc.complete(job, {'exit': 0})
    out = pc('[fn:외부PC작업마무리]{PC:"시험PC",작업들:[$job],해제:true}', job=job)
    assert out['status'] == 'detach_not_supported' and not out['detached']
    assert not pc.handler._detach({'limb': pc.rec['device_id']})['success']
    assert resident_pcs.resolve(pc.rec['device_id'])['registration']['state'] == 'active'
    out = pc('[fn:외부PC작업마무리]{PC:"시험PC",작업들:[$job]}', job=job)
    assert out['ok'] and out['commands_ok']


@pytest.mark.parametrize('paused,state', [(True, 'active'), (False, 'removal_pending')])
def test_prepare_distinguishes_unavailable_resident(pc, paused, state):
    import limb_keys
    limb_keys.resident_update(pc.rec['device_id'], paused=paused, state=state)
    out = pc('[fn:외부PC준비]{PC:"시험PC",환경조회:false}')
    assert out['status'] == ('paused' if paused else 'unavailable')
    assert not pc.history()


def test_cancel_waits_for_confirmation_and_does_not_resubmit(pc):
    import resident_pcs
    job = shell(pc)
    resident_pcs.sync(pc.rec['key'], 'a' * 32)
    out = pc('[fn:외부PC작업중지확인]{작업:$job}', job=job)
    assert out['status'] == 'cancel_requested' and not out['stopped']
    pc.complete(job, {'cancelled': True, 'exit': -1})
    done = pc('[fn:외부PC작업중지확인]{작업:$job}', job=out)
    assert done['stopped'] and done['settled'] and len(pc.history()) == 1


def test_invalid_stop_wait_does_not_cancel(pc):
    job = shell(pc)
    out = pc('[fn:외부PC작업중지확인]{작업:$job,대기:241}', job=job)
    assert out['status'] == 'invalid_input'
    assert pc.history()[0]['state'] == 'queued'


def transfer_call(pc, kind, job=None, **overrides):
    params = {'PC': '시험PC', '중앙경로': str(pc.path / 'local.bin'),
              '원격경로': '/remote/data.bin', '요청ID': kind + '-1', '대기': 0, '작업': job or {}}
    params.update(overrides)
    name = '외부PC파일보내기' if kind == 'send' else '외부PC파일가져오기'
    return pc(f'[fn:{name}]{{**$params}}', params=params)


def test_send_recovers_lost_receipt_and_then_verifies_remote_commit(pc):
    import resident_pcs
    (pc.path / 'local.bin').write_bytes(b'\x00\xff binary\x00')
    job = transfer_call(pc, 'send')
    retry = transfer_call(pc, 'send')
    assert job['task_ref'] == retry['task_ref'] and job['transfer_id'] == retry['transfer_id']
    assert not job['verified'] and len(pc.history()) == 1
    meta = resident_pcs.transfer_info(job['transfer_id'])
    pc.complete(job, {'path': '/remote/data.bin', 'sha256': meta['sha256'], 'state': 'committed'})
    done = transfer_call(pc, 'send', job)
    assert done['verified'] and done['sha256'] == meta['sha256']
    assert len(pc.history()) == 1
    assert transfer_call(pc, 'send', job, 원격경로='/wrong')['status'] == 'resume_mismatch'


def test_receive_wait_collect_and_repeat_are_one_remote_job(pc):
    import hashlib
    import resident_pcs
    job = transfer_call(pc, 'receive')
    assert not job['collected'] and not (pc.path / 'local.bin').exists()
    data = b'\x00\xff received bytes'
    tid = job['transfer_id']
    resident_pcs.transfer_meta(tid, len(data), hashlib.sha256(data).hexdigest())
    resident_pcs.transfer_write(tid, 0, data)
    result = resident_pcs.transfer_commit(tid)
    pc.complete(job, result)
    done = transfer_call(pc, 'receive', job)
    assert done['collected'] and done['verified']
    assert (pc.path / 'local.bin').read_bytes() == data
    assert transfer_call(pc, 'receive', done)['collected']
    assert len(pc.history()) == 1
    (pc.path / 'local.bin').write_bytes(b'other')
    conflict = transfer_call(pc, 'receive', done)
    assert conflict['status'] == 'collect_failed' and conflict['task_ref'] == job['task_ref']
    assert (pc.path / 'local.bin').read_bytes() == b'other'


def test_transfer_failure_returns_diagnostics_and_never_collects(pc):
    job = transfer_call(pc, 'receive')
    pc.complete(job, {'error': 'transfer_failed', 'detail': 'permission denied'})
    out = transfer_call(pc, 'receive', job)
    assert out['status'] == 'failed' and not out['collected']
    assert out['result']['detail'] == 'permission denied'
    assert not (pc.path / 'local.bin').exists()


def test_wake_waits_on_probe_and_resumes_without_another_signal(pc, monkeypatch):
    import resident_pcs
    signals = []
    pc.state['connected'] = False
    monkeypatch.setattr(resident_pcs, 'wake', lambda target: signals.append(target) or {'success': True, 'state': 'signal_sent', 'ready': False})
    job = pc('[fn:외부PC깨워준비]{PC:"시험PC",요청ID:"probe-1",대기:0}')
    assert not job['ready'] and job['status'] == 'queued' and len(signals) == 1
    pc.complete(job, {'os': 'darwin', 'cwd': '/home/user', 'resident': {'version': 'resident-v1'}})
    done = pc('[fn:외부PC깨워준비]{PC:"시험PC",요청ID:"probe-1",대기:0,작업:$job}', job=job)
    assert done['ready'] and done['env']['os'] == 'darwin'
    assert len(signals) == 1 and len(pc.history()) == 1


def test_wake_without_route_has_no_probe_side_effect(pc):
    pc.state['connected'] = False
    # Call the real producer: the idiom must not silently invent a LAN route.
    out = pc.handler._resident_operation({'op': 'wake', 'limb': pc.rec['device_id']})
    assert not out['success'] and 'wake_route_not_configured' in out['error']
    assert not pc.history()


@pytest.mark.parametrize('source,field', [('https://example.test/radio', 'url'), ('/remote/song.mp3', 'path')])
def test_media_receipt_observation_and_stop(pc, source, field):
    import resident_pcs
    code = '[fn:외부PC재생]{PC:"시험PC",소스:$source,요청ID:"play-1",작업:$job}'
    job = pc(code, source=source, job={})
    assert not job['playback_verified'] and job['status'] == 'queued'
    assert pc.history()[0]['summary'][field] == source
    resident_pcs.sync(pc.rec['key'], 'a' * 32)
    resident_pcs.sync(pc.rec['key'], 'a' * 32, [{'job_id': job['job_id'], 'event_id': 'started', 'kind': 'started', 'payload': {}}])
    observed = pc(code, source=source, job=job)
    assert observed['status'] == 'running' and not observed['playback_verified']
    assert len(pc.history()) == 1
    stopped = pc('[fn:외부PC작업중지확인]{작업:$job}', job=job)
    assert stopped['status'] == 'cancel_requested'


def test_media_player_failure_is_not_playback_success(pc):
    job = pc('[fn:외부PC재생]{PC:"시험PC",소스:"/remote/song.mp3",요청ID:"play-1"}')
    pc.complete(job, {'error': 'needs_media_player'})
    out = pc('[fn:외부PC작업확인]{작업:$job}', job=job)
    assert out['status'] == 'failed' and out['command_ok'] is False
    assert out['result']['error'] == 'needs_media_player'


def test_success_without_transfer_proof_is_not_verified(pc):
    (pc.path / 'local.bin').write_bytes(b'data')
    job = transfer_call(pc, 'send')
    pc.complete(job, {'message': 'received'})
    out = transfer_call(pc, 'send', job)
    assert not out['verified'] and not out['ok']


def test_guide_and_all_seed_examples_compile(pc):
    import json
    import re
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_store import definition_name
    sources = {definition_name(p.read_text()): p.read_text()
               for p in (ROOT / 'data/idioms').glob('guestpc_*.ibl')}
    seeds = json.loads((ROOT / 'data/idioms/guestpc_seeds.json').read_text())
    guide = (ROOT / 'data/guides/guest_helper.md').read_text()
    examples = re.findall(r'<!-- example:guestpc_\w+ -->\s*```ibl\n(.*?)\n```', guide, re.S)
    assert len(examples) == len(sources) == 9
    adapters = load_registry(str(pc.path))
    inputs = {'작업': {'limb': 'fixture', 'task_ref': {'kind': 'guestpc', 'task_id': 'fixture'}}}
    for source in examples + [r['ibl_code'] for r in seeds]:
        plan = compile_program(source, adapters, definitions=sources, inputs=inputs)
        assert not plan.issues, plan.issues


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))


def test_alias_ignores_revoked_and_expired_registrations(pc, monkeypatch):
    original = pc.handler._OP_DISPATCHERS['limb_op']['list']
    def with_stale(args):
        out = original(args)
        out['items'] = [*out['items'],
            {'alias': '시험PC', 'device_id': 'old', 'revoked': True},
            {'alias': '시험PC', 'device_id': 'expired', 'expired': True}]
        return out
    monkeypatch.setitem(pc.handler._OP_DISPATCHERS['limb_op'], 'list', with_stale)
    out = pc('[fn:외부PC준비]{PC:"시험PC",환경조회:false}')
    assert out['ok'] and out['limb'] == pc.rec['device_id']
    assert not pc('[fn:외부PC준비]{PC:"old",환경조회:false}')['ok']


def test_sync_duplicate_and_background_observation_share_durable_result(pc, monkeypatch):
    import resident_pcs
    import phone_jobs
    original = resident_pcs.submit
    def completed(*args, **kwargs):
        job = original(*args, **kwargs)
        pc.complete(job, {'exit': 0, 'output': 'one execution'})
        return job
    monkeypatch.setattr(resident_pcs, 'submit', completed)
    args = {'limb': pc.rec['device_id'], 'cmd': 'echo once', 'request_id': 'sync-once'}
    first = pc.handler._op_shell(args)
    again = pc.handler._op_shell(args)
    job = pc.handler._op_shell({**args, 'background': True})
    assert first['result'] == again['result'] == pc.handler.task_status(job['task_ref'])['result']
    assert not phone_jobs.job_status(job['job_id'])['consumed']
    assert len(pc.history()) == 1


def test_noisy_job_timing_and_bounded_progress_remain_complete_in_history(pc):
    import resident_pcs
    import resident_store
    job = shell(pc)
    jid = job['job_id']
    import time
    start = time.time()
    events = [{'job_id': jid, 'event_id': 'start', 'kind': 'started', 'occurred_at': start, 'payload': {}}]
    events += [{'job_id': jid, 'event_id': f'log{i}', 'kind': 'log', 'occurred_at': start+1+i,
                'payload': {'text': '한글'*4000}} for i in range(140)]
    events += [{'job_id': jid, 'event_id': 'end', 'kind': 'result', 'occurred_at': start+150,
                'payload': {'exit': 0, 'output': 'done'}}]
    for offset in range(0, len(events), 64):
        resident_pcs.sync(pc.rec['key'], 'a'*32, events[offset:offset+64])
    page = resident_store.history(job=jid)
    assert len(page['events']) == 100 and page['tasks'][0]['seconds'] == 150
    done = pc('[fn:외부PC작업확인]{작업:$job}', job=job)
    assert done['started_at'] == start and done['ended_at'] == start+150 and done['seconds'] == 150
    assert done['result']['output'] == 'done' and len(done['progress']) == 5
    assert len(str(done['progress'])) < 9000
    rest = resident_store.history(job=jid, cursor=page['cursor'])
    assert rest['events'][-1]['kind'] == 'result'
    assert rest['events'][0]['payload']['text'] == '한글'*4000


def test_transfer_idiom_can_resume_terminal_failure_without_restarting_bytes(pc):
    (pc.path / 'local.bin').write_bytes(b'resume same transfer')
    first = transfer_call(pc, 'send')
    pc.complete(first, {'error': 'transfer_failed'})
    retry = transfer_call(pc, 'send', 요청ID='send-retry-1', 전송ID=first['transfer_id'])
    assert retry['transfer_id'] == first['transfer_id']
    assert retry['task_ref'] != first['task_ref']
    assert transfer_call(pc, 'send', 요청ID='send-retry-1', 전송ID=first['transfer_id'])['task_ref'] == retry['task_ref']


def test_pre_upgrade_sync_default_is_recovered_with_same_request(pc):
    import resident_pcs
    old = resident_pcs.submit(pc.rec['device_id'], {'op': 'shell', 'cmd': 'echo old', 'timeout': 120}, 'old-sync')
    pc.complete(old, {'exit': 0, 'output': 'old'})
    got = pc.handler._op_shell({'limb': pc.rec['device_id'], 'cmd': 'echo old', 'request_id': 'old-sync'})
    assert got['result']['output'] == 'old' and len(pc.history()) == 1


def test_large_read_explains_supported_file_recovery(pc, monkeypatch):
    import resident_pcs
    original = resident_pcs.submit
    def complete(*args, **kwargs):
        job = original(*args, **kwargs)
        pc.complete(job, {'op': 'read', 'content': 'partial', 'truncated': True})
        return job
    monkeypatch.setattr(resident_pcs, 'submit', complete)
    result = pc.handler._op_read({'limb': pc.rec['device_id'], 'path': '/remote/large'})
    assert 'transfer' in result['warning'] and 'collect' in result['warning']
    from ibl_v2_adapters import _partial_message
    assert 'transfer' in _partial_message(result, {'truncations': [{'scope': 'source'}]})
