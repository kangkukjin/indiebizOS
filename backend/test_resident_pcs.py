"""Resident registration isolation, durable execution and binary transport contracts."""
import boot_paths
import hashlib
import importlib.util
import json
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import api_resident_pcs
import device_registry
import limb_keys
import phone_jobs
import resident_pcs as pcs
import resident_store

@pytest.fixture
def registry(tmp_path, monkeypatch):
    monkeypatch.setattr(limb_keys, '_store_path', lambda: tmp_path / 'keys.json')
    monkeypatch.setattr(limb_keys, '_cache', None)
    monkeypatch.setenv('INDIEBIZ_RUNTIME_STATE_DIR', str(tmp_path))
    monkeypatch.setattr(device_registry, 'register', lambda *a, **k: None)

    def make(name='desk'):
        invite = limb_keys.resident_invite(name)
        return limb_keys.resident_enroll(invite['key'], 'a' * 32)
    return make

def test_invitation_bound_once_and_legacy_denied(registry):
    inv = limb_keys.resident_invite('room')
    assert limb_keys.validate(inv['key']) is None
    a = limb_keys.resident_enroll(inv['key'], 'b' * 32)
    assert limb_keys.resident_enroll(inv['key'], 'b' * 32)['key'] == a['key']
    with pytest.raises(ValueError, match='invitation_used'):
        limb_keys.resident_enroll(inv['key'], 'c' * 32)
    assert limb_keys.validate(a['key']) is None
    pcs.remove(a['device_id'])
    with pytest.raises(ValueError, match='registration_closed'):
        limb_keys.resident_enroll(inv['key'], 'b' * 32)
    assert limb_keys.resident_auth(a['key'], 'b' * 32, cleanup=True)
    with pytest.raises(ValueError):
        limb_keys.resident_auth(a['key'], 'b' * 32)

def test_alias_revoke_targets_registration_not_consumed_invitation(registry):
    rec = registry('same-name')
    assert limb_keys.revoke('same-name')['device_id'] == rec['device_id']
    with pytest.raises(ValueError, match='invalid_registration'):
        pcs.sync(rec['key'], 'a' * 32)


def test_owner_context_survives_device_sync_without_changing_pause(registry):
    rec = registry('office')
    limb_keys.resident_update(rec['device_id'], paused=True)
    app = FastAPI()
    app.include_router(api_resident_pcs.router)
    with TestClient(app) as client:
        response = client.put('/remote-pcs/context', json={
            'target': rec['device_id'], 'context': '  작은방 프린터 연결 PC  '})
        assert response.status_code == 200
        assert response.json()['registration']['paused'] is True
        assert client.put('/remote-pcs/context', json={
            'target': rec['device_id'], 'context': ['invalid']}).status_code == 400
    pcs.sync(rec['key'], 'a' * 32, capabilities={'os': 'windows'})
    limb_keys.invalidate()
    saved = pcs.resolve(rec['device_id'], active=False)['registration']
    assert saved['context'] == '작은방 프린터 연결 PC'
    assert saved['paused'] is True
    assert saved['capabilities']['os'] == 'windows'

def test_command_the_device_never_pulled_expires_instead_of_pending_forever(registry, monkeypatch):
    rec = registry()
    command = {'op': 'update', 'transfer_id': 'x', 'sha256': '0' * 64}
    jid = resident_store.submit(rec, command, 'r1')
    assert resident_store.pending(rec['device_id'], 'update') == jid
    monkeypatch.setattr(phone_jobs, 'JOB_TTL', -1.0)  # the PC went down before its next sync
    assert resident_store.pending(rec['device_id'], 'update') is None
    task = resident_store.history(rec['device_id'])['tasks'][0]
    assert task['state'] == task['outcome'] == 'failed'
    assert task['result'] == {'error': 'expired', 'delivered': False}
    assert [e['kind'] for e in resident_store.history(job=jid)['events']] == ['queued', 'expired']
    assert resident_store.wait_result(jid, 0) == {'error': 'expired', 'delivered': False}
    # 만료 행이 보존 기한 뒤 지워진 뒤에 처음 보더라도 같은 결론이다.
    monkeypatch.setattr(phone_jobs, 'JOB_TTL', 600.0)
    other = resident_store.submit(rec, {'op': 'info'}, 'r2')
    with phone_jobs._db() as db:
        db.execute("DELETE FROM jobs WHERE id=?", (other,))
    assert resident_store.pending(rec['device_id'], 'info') is None
    assert resident_store.history(job=other)['tasks'][0]['state'] == 'failed'
    # 전달된 작업은 건드리지 않는다.
    live = resident_store.submit(rec, {'op': 'shell', 'cmd': 'x'}, 'r3')
    assert pcs.sync(rec['key'], 'a' * 32)['jobs'][0]['id'] == live
    monkeypatch.setattr(phone_jobs, 'JOB_TTL', -1.0)
    assert resident_store.pending(rec['device_id'], 'shell') == live


@pytest.mark.parametrize('days', [-1, float('nan'), float('inf'), True])
def test_invalid_temporary_duration_never_becomes_unlimited(registry, days):
    with pytest.raises(ValueError):
        limb_keys.resident_invite('temporary', days)


def test_persistence_failure_does_not_leave_issued_key(monkeypatch, registry):
    registry()
    import os

    def fail(*args):
        raise OSError('disk full')
    monkeypatch.setattr(os, 'replace', fail)
    with pytest.raises(OSError):
        limb_keys.resident_invite('lost')
    assert limb_keys._cache is None
    assert all((r['alias'] != 'lost' for r in limb_keys.list_keys()))

def event(jid, kind='result', payload=None, eid='result-1'):
    return {'job_id': jid, 'event_id': eid, 'kind': kind, 'payload': payload or {'exit': 0}}

def test_idempotent_submit_event_reconnect_and_process_outcome(registry):
    rec = registry()
    cmd = {'op': 'shell', 'cmd': 'echo hello'}
    first = pcs.submit(rec['device_id'], cmd, 'same')
    assert pcs.submit(rec['device_id'], cmd, 'same')['job_id'] == first['job_id']
    with pytest.raises(ValueError, match='request_id_conflict'):
        pcs.submit(rec['device_id'], {**cmd, 'cmd': 'echo changed'}, 'same')
    sync = pcs.sync(rec['key'], 'a' * 32)
    assert len(sync['jobs']) == 1
    assert json.loads(sync['jobs'][0]['code'])['generation'] == rec['registration']['generation']
    # A response is not receipt: until the device reports any event for the job it is offered again.
    assert [j['id'] for j in pcs.sync(rec['key'], 'a' * 32)['jobs']] == [first['job_id']]
    started = {'job_id': first['job_id'], 'event_id': 'started-1', 'kind': 'started', 'payload': {}}
    assert pcs.sync(rec['key'], 'a' * 32, [started])['jobs'] == []
    assert pcs.sync(rec['key'], 'a' * 32)['jobs'] == []
    ev = event(first['job_id'], payload={'exit': 7, 'output': 'failed'})
    assert pcs.sync(rec['key'], 'a' * 32, [ev])['ack'] == ['result-1']
    assert pcs.sync(rec['key'], 'a' * 32, [ev])['ack'] == ['result-1']
    history = resident_store.history(job=first['job_id'])
    assert history['tasks'][0]['state'] == 'failed'
    assert len([e for e in history['events'] if e['kind'] == 'result']) == 1
    assert phone_jobs.peek_result(first['job_id'])['result']['exit'] == 7
    limb_keys.invalidate()
    assert pcs.resolve(rec['device_id'])['key'] == rec['key']

def test_wrong_installation_job_and_transfer_denied(registry):
    a, b = (registry('a'), registry('b'))
    with pytest.raises(ValueError):
        pcs.sync(a['key'], 'b' * 32)
    jid = pcs.submit(a['device_id'], {'op': 'info'})['job_id']
    with pytest.raises(ValueError, match='job_not_owned'):
        pcs.sync(b['key'], 'a' * 32, [event(jid)])
    transfer = pcs.transfer_create(a['device_id'], 'from_pc', 'hello')
    app = FastAPI()
    app.include_router(api_resident_pcs.router)
    with TestClient(app) as client:
        r = client.post('/limb/resident/transfers/' + transfer['id'], json={'key': b['key'], 'installation_id': 'a' * 32})
        assert r.status_code == 403

def test_pause_cancel_remove_and_expiry(registry, monkeypatch):
    rec = registry()
    jid = pcs.submit(rec['device_id'], {'op': 'info'})['job_id']
    limb_keys.resident_update(rec['device_id'], paused=True)
    assert not pcs.sync(rec['key'], 'a' * 32)['jobs']
    with pytest.raises(ValueError, match='unavailable'):
        pcs.submit(rec['device_id'], {'op': 'info'})
    limb_keys.resident_update(rec['device_id'], paused=False)
    pcs.sync(rec['key'], 'a' * 32)
    assert resident_store.cancel(jid)
    assert resident_store.history(job=jid)['tasks'][0]['state'] == 'cancel_requested'
    assert jid in pcs.sync(rec['key'], 'a' * 32)['cancel']
    pcs.sync(rec['key'], 'a' * 32, [event(jid, payload={'cancelled': True})])
    assert resident_store.history(job=jid)['tasks'][0]['state'] == 'cancelled'
    assert pcs.remove(rec['device_id'])['registration']['state'] == 'removal_pending'
    assert not pcs.sync(rec['key'], 'a' * 32)['jobs']
    limb_keys.resident_update(rec['device_id'], state='removed')
    assert pcs.sync(rec['key'], 'a' * 32)['state'] == 'removed'
    inv = limb_keys.resident_invite('temporary', ttl_days=1)
    tmp = limb_keys.resident_enroll(inv['key'], 'c' * 32)
    monkeypatch.setattr(limb_keys, '_now', lambda: tmp['expires_at'] + 1)
    assert pcs.sync(tmp['key'], 'c' * 32)['state'] == 'removal_pending'

def test_binary_resume_hash_and_empty(registry):
    rec = registry()
    data = bytes(range(256)) * 12
    row = pcs.transfer_create(rec['device_id'], 'to_pc', 'data.bin', len(data), hashlib.sha256(data).hexdigest())
    tid = row['id']
    pcs.transfer_write(tid, 0, data[:500])
    assert pcs.transfer_info(tid)['offset'] == 500
    with pytest.raises(ValueError, match='offset_conflict'):
        pcs.transfer_write(tid, 0, data)
    with pytest.raises(ValueError, match='incomplete'):
        pcs.transfer_commit(tid)
    pcs.transfer_write(tid, 500, data[500:])
    assert pcs.transfer_commit(tid)['state'] == 'committed'
    assert pcs.transfer_commit(tid)['state'] == 'committed'
    assert pcs.transfer_path(tid).read_bytes() == data
    empty = pcs.transfer_create(rec['device_id'], 'to_pc', 'empty', 0, hashlib.sha256(b'').hexdigest())
    assert pcs.transfer_commit(empty['id'])['state'] == 'committed'
    corrupt = pcs.transfer_create(rec['device_id'], 'to_pc', 'bad', 1, hashlib.sha256(b'x').hexdigest())
    pcs.transfer_write(corrupt['id'], 0, b'y')
    with pytest.raises(ValueError, match='hash_mismatch'):
        pcs.transfer_commit(corrupt['id'])
    with pytest.raises(ValueError):
        pcs.transfer_create(rec['device_id'], 'to_pc', '../escape')

def test_api_transport_auth_and_replay(registry):
    rec = registry()
    app = FastAPI()
    app.include_router(api_resident_pcs.router)
    with TestClient(app) as client:
        assert client.post('/limb/resident/sync', json={'key': 'wrong', 'installation_id': 'a' * 32}).status_code == 400
        data = {'key': rec['key'], 'installation_id': 'a' * 32}
        pcs.remove(rec['device_id'])
        assert client.post('/limb/resident/removed', json=data).status_code == 200
        assert client.post('/limb/resident/removed', json=data).status_code == 200
        assert client.post('/remote-pcs/command', json={'target': rec['device_id'], 'command': {'op': 'info'}}).status_code == 400

def test_interactive_explicit_and_wake_route(registry):
    rec = registry()
    with pytest.raises(ValueError, match='needs_interactive'):
        pcs.submit(rec['device_id'], {'op': 'click'})
    with pytest.raises(ValueError, match='wake_route_not_configured'):
        pcs.wake(rec['device_id'])
    relay = registry('relay')
    pcs.configure_wake(rec['device_id'], '00:11:22:33:44:55', '192.0.2.255', relay['device_id'])
    out = pcs.wake(rec['device_id'])
    rows = resident_store.history(job=out['job_id'])['tasks']
    assert rows[0]['device'] == relay['device_id']
    assert rows[0]['summary']['op'] == 'wake'

def test_guestpc_receipt_projects_failure_and_cancel(registry):
    path = Path(__file__).resolve().parents[1] / 'data/packages/installed/tools/guest-helper/handler.py'
    spec = importlib.util.spec_from_file_location('resident_guest_test', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rec = registry()
    out = mod._op_shell({'limb': rec['device_id'], 'cmd': 'false', 'background': True})
    ref = out['task_ref']
    assert mod.task_status(ref)['state'] == 'queued'
    pcs.sync(rec['key'], 'a' * 32, [])
    pcs.sync(rec['key'], 'a' * 32, [event(out['job_id'], payload={'exit': 2, 'error': 'failed'})])
    assert mod.task_status(ref)['state'] == 'failed'
    new = pcs.submit(rec['device_id'], {'op': 'info'})
    assert mod.task_status_cancel(new['task_ref'])['state'] == 'cancelled'

def test_websocket_uses_same_authenticated_ledger(registry):
    rec = registry()
    app = FastAPI()
    app.include_router(api_resident_pcs.router)
    jid = pcs.submit(rec['device_id'], {'op': 'info'})['job_id']
    with TestClient(app) as client, client.websocket_connect('/limb/resident/ws') as ws:
        ws.send_json({'key': rec['key'], 'installation_id': 'a' * 32})
        assert ws.receive_json()['jobs'][0]['id'] == jid
        ws.send_json({'key': rec['key'], 'installation_id': 'a' * 32, 'events': [event(jid)]})
        assert ws.receive_json()['ack'] == ['result-1']
    assert resident_store.history(job=jid)['tasks'][0]['state'] == 'succeeded'


def test_bundle_uses_direct_tunnel_and_contains_executable(registry, monkeypatch):
    import io
    import zipfile
    import face_config
    monkeypatch.setattr(face_config, 'load_config', lambda: {
        'public_base': 'https://cdn.example', 'direct_hosts': ['hub.example']})
    app = FastAPI()
    app.include_router(api_resident_pcs.router)
    with TestClient(app) as client:
        response = client.post('/remote-pcs/bundle', json={'alias': 'Mac12', 'platform': 'mac-amd64'})
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        cfg = json.loads(archive.read('indiebiz-helper.json'))
        assert cfg['base'] == 'https://hub.example'
        assert cfg['mode'] == 'enroll'
        assert limb_keys.validate(cfg['key']) is None
        assert archive.getinfo('indiebiz-helper-mac-amd64').external_attr >> 16 & 0o111
        assert archive.read('SHA256SUMS').decode().startswith(
            hashlib.sha256(archive.read('indiebiz-helper-mac-amd64')).hexdigest())

@pytest.mark.system
def test_resident_binary_roundtrip_crash(tmp_path, monkeypatch):
    """Uses an isolated hub and built binary; never installs an OS autostart service."""
    import platform
    import time
    import threading
    import socket
    import subprocess
    import uvicorn
    root = Path(__file__).resolve().parents[1]
    if platform.system() == 'Darwin':
        binary_name = 'indiebiz-helper-mac-arm64' if platform.machine() == 'arm64' else 'indiebiz-helper-mac-amd64'
    elif platform.system() == 'Linux' and platform.machine() == 'x86_64':
        binary_name = 'indiebiz-helper-linux'
    else:
        pytest.skip('POSIX native binary integration fixture')
    if not (root / 'helper/dist' / binary_name).is_file():
        pytest.skip('build helper binaries first')
    work = tmp_path
    monkeypatch.setenv('INDIEBIZ_RUNTIME_STATE_DIR', str(work))
    monkeypatch.setattr(limb_keys, '_store_path', lambda: work / 'keys.json')
    monkeypatch.setattr(limb_keys, '_cache', None)
    monkeypatch.setattr(device_registry, 'register', lambda *a, **k: None)
    rec = limb_keys.resident_enroll(limb_keys.resident_invite('맥12-테스트')['key'], 'b' * 32)
    app = FastAPI()
    app.include_router(api_resident_pcs.router)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{port}'
    worker = work / 'worker'
    worker.mkdir()
    cfg = {'mode': 'resident', 'base': url, 'key': rec['key'], 'installation_id': 'b' * 32, 'generation': rec['registration']['generation'], 'data_dir': str(worker), 'alias': '맥12-테스트'}
    (worker / 'indiebiz-helper.json').write_text(json.dumps(cfg))
    # Optional setup failure remains diagnosable after the minimal helper connects.
    warning = 'test fixture: login autostart unavailable; current connection remains usable'
    (worker / 'installation_warnings.json').write_text(json.dumps([warning]))
    binary = root / 'helper/dist' / binary_name
    proc = None

    def wait(jid, timeout=15):
        end = time.time() + timeout
        while time.time() < end:
            row = resident_store.history(job=jid)['tasks'][0]
            if row['result'] is not None:
                return row
            time.sleep(0.05)
        raise AssertionError(('timed out', resident_store.history(job=jid)))
    try:
        for i in range(100):
            if server.started:
                break
            time.sleep(0.02)
        proc = subprocess.Popen([str(binary)], cwd=worker, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        start = time.monotonic()
        job = pcs.submit(rec['device_id'], {'op': 'shell', 'cmd': 'printf resident-ok', 'timeout': 10}, 'smoke-once')
        got = wait(job['job_id'])
        assert got['state'] == 'succeeded', got
        assert got['result']['output'] == 'resident-ok', got
        caps = limb_keys.get_by_device(rec['device_id'])['registration']['capabilities']
        assert caps['installation_warnings'] == [warning]
        assert set(caps['media_components']['components']) == {'ffmpeg', 'ffplay', 'mpv'}
        assert isinstance(caps['media_components']['missing'], list)
        latency = round((time.monotonic() - start) * 1000)
        assert pcs.submit(rec['device_id'], {'op': 'shell', 'cmd': 'printf resident-ok', 'timeout': 10}, 'smoke-once')['job_id'] == job['job_id']
        inherited = pcs.submit(rec['device_id'], {'op': 'shell',
            'cmd': 'sleep 4 & echo started', 'timeout': 10}, 'inherited-output')
        inherited_result = wait(inherited['job_id'])
        assert inherited_result['state'] == 'succeeded', inherited_result
        assert inherited_result['result']['exit'] == 0
        assert inherited_result['result']['output_incomplete'] is True
        assert 'Do not resubmit' in inherited_result['result']['warning']
        assert 'started' in inherited_result['result']['output']
        assert inherited_result['seconds'] < 4
        # Non-zero commands remain failed even with a surviving pipe holder.
        nonzero = pcs.submit(rec['device_id'], {'op': 'shell',
            'cmd': 'sleep 4 & echo reason; exit 7', 'timeout': 10}, 'nonzero-output')
        nonzero_result = wait(nonzero['job_id'])
        assert nonzero_result['state'] == 'failed' and nonzero_result['result']['exit'] == 7
        busy = [pcs.submit(rec['device_id'], {'op': 'shell', 'cmd': 'sleep 6', 'timeout': 15},
                           f'busy-{i}') for i in range(2)]
        deadline = time.monotonic() + 5
        while not all(resident_store.history(job=j['job_id'])['tasks'][0]['state'] == 'running' for j in busy):
            assert time.monotonic() < deadline
            time.sleep(0.05)
        queued = pcs.submit(rec['device_id'], {'op': 'shell', 'cmd': 'echo queued', 'timeout': 10}, 'queued-work')
        observe = pcs.submit(rec['device_id'], {'op': 'shell', 'cmd': 'echo observed',
            'mode': 'observe', 'timeout': 2}, 'check-during-work')
        observed = wait(observe['job_id'])
        assert observed['state'] == 'succeeded' and observed['result']['output'].strip() == 'observed'
        listing = pcs.submit(rec['device_id'], {'op': 'list', 'path': str(worker)}, 'list-during-work')
        assert wait(listing['job_id'])['state'] == 'succeeded'
        assert resident_store.history(job=queued['job_id'])['tasks'][0]['state'] == 'queued'
        for job in busy:
            finished = wait(job['job_id'])
            assert observed['ended_at'] < finished['ended_at']
        assert wait(queued['job_id'])['state'] == 'succeeded'
        limited = pcs.submit(rec['device_id'], {'op': 'shell', 'cmd': 'sleep 20',
            'mode': 'observe', 'timeout': 1}, 'limited-check')
        limited_result = wait(limited['job_id'])
        assert limited_result['outcome'] == 'timeout' and limited_result['result']['timeout']
        print(json.dumps({'inherited_pipe_seconds': inherited_result['seconds'],
                          'observation_queue_seconds': observed['started_at'] - observed['created']}, ensure_ascii=False))
        payload = bytes(range(256)) * 5000
        src = work / 'source.bin'
        src.write_bytes(payload)
        sent = pcs.transfer_local(rec['device_id'], {'action': 'send', 'local_path': str(src), 'path': str(worker / 'received.bin'), 'request_id': 'send-once'})
        assert wait(sent['job_id'])['state'] == 'succeeded'
        assert (worker / 'received.bin').read_bytes() == payload
        received = pcs.transfer_local(rec['device_id'], {'action': 'receive', 'path': str(worker / 'received.bin'), 'request_id': 'receive-once'})
        assert wait(received['job_id'])['state'] == 'succeeded'
        pcs.transfer_local(rec['device_id'], {'action': 'collect', 'local_path': str(work / 'collected.bin'), 'transfer_id': received['transfer_id']})
        assert (work / 'collected.bin').read_bytes() == payload
        marker = work / 'orphan'
        crash = pcs.submit(rec['device_id'], {'op': 'shell', 'cmd': f'(sleep 3; echo escaped > "{marker}") & wait', 'timeout': 30}, 'crash-job')
        for _ in range(100):
            if resident_store.history(job=crash['job_id'])['tasks'][0]['state'] == 'running':
                break
            time.sleep(0.02)
        time.sleep(0.25)
        proc.kill()
        proc.wait(timeout=5)
        time.sleep(3.2)
        assert not marker.exists(), 'child survived worker crash'
        proc = subprocess.Popen([str(binary)], cwd=worker, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        assert wait(crash['job_id'])['state'] == 'unknown'
        print(json.dumps({'shell_first_result_ms': latency, 'binary_roundtrip_bytes': len(payload), 'dedup': True, 'crash_children_reaped': True, 'restart_state': 'unknown', 'work_dir': str(work)}, ensure_ascii=False))
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)
        server.should_exit = True
        thread.join(timeout=30)
        assert not thread.is_alive(), 'isolated hub did not shut down'
if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))


def test_reusable_usb_names_isolation_retry_and_revocation(registry):
    inv = limb_keys.resident_installer()
    assert limb_keys.resident_installer()['key'] == inv['key']
    assert limb_keys.validate(inv['key']) is None
    a = limb_keys.resident_enroll(inv['key'], '1' * 32, '맥12')
    b = limb_keys.resident_enroll(inv['key'], '2' * 32, '작업PC')
    assert a['key'] != b['key'] != inv['key']
    assert limb_keys.resident_enroll(inv['key'], '1' * 32, 'retry')['key'] == a['key']
    with pytest.raises(ValueError, match='이미 등록된'):
        limb_keys.resident_enroll(inv['key'], '3' * 32, '맥12')
    with pytest.raises(ValueError):
        pcs.sync(inv['key'], '1' * 32)
    with pytest.raises(ValueError):
        pcs.sync(a['key'], '2' * 32)
    pcs.remove(a['device_id'])
    assert pcs.sync(a['key'], '1' * 32)['state'] == 'removal_pending'
    assert pcs.sync(b['key'], '2' * 32)['state'] == 'active'
    limb_keys.resident_update(a['device_id'], state='removed')
    replacement = limb_keys.resident_enroll(inv['key'], '7' * 32, '맥12')
    assert pcs.resolve('맥12')['device_id'] == replacement['device_id']
    assert pcs.resolve(a['device_id'], active=False)['registration']['state'] == 'removed'
    limb_keys.resident_installer_revoke()
    with pytest.raises(ValueError, match='invalid_invitation'):
        limb_keys.resident_enroll(inv['key'], '4' * 32, '새PC')
    assert pcs.sync(b['key'], '2' * 32)['state'] == 'active'
    assert limb_keys.resident_installer()['key'] != inv['key']


@pytest.mark.parametrize('name', ['', ' ', 'x' * 81, 'pc\nname'])
def test_usb_invalid_name_does_not_register(registry, name):
    inv = limb_keys.resident_installer()
    with pytest.raises(ValueError):
        limb_keys.resident_enroll(inv['key'], '5' * 32, name)
    assert not pcs.devices()


def test_usb_folder_all_platforms_no_preassigned_pc_and_stable_key(registry, monkeypatch, tmp_path):
    monkeypatch.setenv('INDIEBIZ_BASE_PATH', str(tmp_path))
    monkeypatch.setattr(pcs, 'public_base', lambda: 'https://central.example')
    dist = tmp_path / 'helper' / 'dist'
    dist.mkdir(parents=True)
    for src in pcs.USB_BINARIES:
        (dist / src).write_bytes(src.encode())
    assert not pcs.usb_status()['ready']
    ready = pcs.prepare_usb()
    root = Path(ready['folder'])
    assert ready['ready'] and root.name == 'pc-helper'
    cfg = json.loads((root / 'indiebiz-helper.json').read_text())
    assert cfg['mode'] == 'enroll' and 'alias' not in cfg
    assert len((root / 'SHA256SUMS').read_text().splitlines()) == len(pcs.USB_BINARIES)
    for src, dest in pcs.USB_BINARIES.items():
        assert (root / dest).read_bytes() == src.encode()
        assert (root / dest).stat().st_mode & 0o111
    assert not (root / 'indiebiz-helper.json').stat().st_mode & 0o077
    pcs.prepare_usb()
    assert json.loads((root / 'indiebiz-helper.json').read_text())['key'] == cfg['key']
    app = FastAPI()
    app.include_router(api_resident_pcs.router)
    with TestClient(app) as client:
        out = client.post('/limb/resident/enroll', json={'key': cfg['key'], 'installation_id': '6' * 32, 'alias': '맥12'})
        assert out.status_code == 200 and out.json()['alias'] == '맥12'
        listing = client.get('/remote-pcs')
        assert listing.json()['items'][0]['alias'] == '맥12'
        assert cfg['key'] not in listing.text and out.json()['key'] not in listing.text
        assert client.get('/remote-pcs/app', follow_redirects=False).headers['location'] == '/launcher/app'
        assert client.post('/remote-pcs/usb/revoke').json()['ready'] is False


def test_chunk_response_loss_is_idempotent_and_conflicting_bytes_rejected(registry):
    rec = registry()
    data = b'abcdef'
    row = pcs.transfer_create(rec['device_id'], 'from_pc', 'data', len(data), hashlib.sha256(data).hexdigest())
    tid = row['id']
    assert pcs.transfer_write(tid, 0, data[:3]) == pcs.transfer_write(tid, 0, data[:3])
    with pytest.raises(ValueError, match='offset_conflict'):
        pcs.transfer_write(tid, 0, b'xxx')
    pcs.transfer_write(tid, 3, data[3:])
    assert pcs.transfer_commit(tid)['state'] == 'committed'
    assert pcs.transfer_path(tid).read_bytes() == data


def test_failed_transfer_new_attempt_reuses_blob_and_request_is_still_idempotent(registry, tmp_path):
    rec = registry()
    source = tmp_path / 'source.bin'
    source.write_bytes(b'resume')
    args = {'action': 'send', 'local_path': str(source), 'path': '/remote/data', 'request_id': 'first'}
    first = pcs.transfer_local(rec['device_id'], args)
    pcs.sync(rec['key'], 'a'*32, [event(first['job_id'], payload={'error': 'transfer_failed'})])
    assert pcs.transfer_local(rec['device_id'], args)['job_id'] == first['job_id']
    retry_args = {**args, 'request_id': 'retry-1', 'transfer_id': first['transfer_id']}
    retry = pcs.transfer_local(rec['device_id'], retry_args)
    assert retry['job_id'] != first['job_id'] and retry['transfer_id'] == first['transfer_id']
    assert pcs.transfer_local(rec['device_id'], retry_args)['job_id'] == retry['job_id']
    assert resident_store.history(job=first['job_id'])['tasks'][0]['state'] == 'failed'


@pytest.mark.parametrize('command', [
    {'op': 'shell', 'mode': 'observe'},
    {'op': 'shell', 'mode': 'observe', 'timeout': 11},
    {'op': 'write', 'mode': 'observe', 'timeout': 1},
    {'op': 'shell', 'mode': 'observe', 'timeout': True},
])
def test_observation_requires_bounded_shell(registry, command):
    rec = registry()
    with pytest.raises(ValueError, match='mode:observe'):
        pcs.submit(rec['device_id'], command)
    assert not resident_store.history()['tasks']


@pytest.mark.parametrize('volume', [-1, 101, True, '0', float('nan'), float('inf')])
def test_media_invalid_volume_rejected_before_submission(registry, volume):
    rec = registry()
    with pytest.raises(ValueError, match='volume'):
        pcs.submit(rec['device_id'], {'op': 'media', 'path': '/audio.wav', 'volume': volume})
    assert not resident_store.history()['tasks']


def test_history_omits_image_bytes_but_retains_recovery_and_evidence(registry):
    rec = registry()
    job = pcs.submit(rec['device_id'], {'op': 'screen', 'mode': 'interactive'})['job_id']
    payload = {'b64': 'A' * 500000, 'width': 800, 'image_observation': 'uniform', 'warning': 'unknown cause'}
    pcs.sync(rec['key'], 'a' * 32, [event(job, payload=payload)])
    page = resident_store.history(job=job)
    assert len(json.dumps(page)) < 5000
    for result in [page['tasks'][0]['result'], page['events'][-1]['payload']]:
        assert 'b64' not in result and result['image_omitted']
        assert result['image_task_ref']['task_id'] == job
        assert result['warning'] == 'unknown cause'
    assert resident_store.wait_result(job, 0) == payload
    assert resident_store.history(job=job, include_images=True)['tasks'][0]['result'] == payload


def test_job_lost_in_a_dead_long_poll_is_offered_again_once_per_sync(registry):
    """2026-10-11 맥12: 헬퍼가 죽은 직후 접수된 작업이 죽은 연결의 응답에 실려 영영 queued 로 남았다."""
    rec = registry()
    lost = pcs.submit(rec['device_id'], {'op': 'shell', 'cmd': 'echo lost'}, 'lost')['job_id']
    assert [j['id'] for j in pcs.sync(rec['key'], 'a' * 32)['jobs']] == [lost]  # 죽은 연결이 가져간 응답
    later = pcs.submit(rec['device_id'], {'op': 'shell', 'cmd': 'echo later'}, 'later')['job_id']
    again = pcs.sync(rec['key'], 'a' * 32)['jobs']
    assert sorted(j['id'] for j in again) == sorted([lost, later])
    assert json.loads(next(j for j in again if j['id'] == lost)['code'])['cmd'] == 'echo lost'
    kinds = [e['kind'] for e in resident_store.history(job=lost)['events']]
    assert kinds.count('redelivered') == 1
    assert resident_store.history(job=lost)['tasks'][0]['state'] == 'queued'
    # 취소된 작업과 결과가 온 작업은 다시 내주지 않는다.
    pcs.sync(rec['key'], 'a' * 32, [{'job_id': lost, 'event_id': 'r-lost', 'kind': 'result', 'payload': {'exit': 0}}])
    resident_store.cancel(later, rec['device_id'])
    assert pcs.sync(rec['key'], 'a' * 32)['jobs'] == []
    assert [e['kind'] for e in resident_store.history(job=lost)['events']].count('redelivered') == 1


@pytest.mark.parametrize("os_name,build,go_version", [
    ("darwin", "mac-amd64-legacy", "go1.22.12"),
    ("windows", "win-resident.exe", "go1.26.1"),
])
def test_helper_update_is_one_owner_action_and_never_an_agent_command(
        registry, monkeypatch, tmp_path, os_name, build, go_version):
    rec = registry()
    dist = tmp_path / 'helper' / 'dist'
    dist.mkdir(parents=True)
    (dist / 'indiebiz-helper-mac-amd64').write_bytes(b'regular build')
    (dist / ('indiebiz-helper-' + build)).write_bytes(b'legacy build')
    import runtime_utils
    monkeypatch.setattr(runtime_utils, 'get_base_path', lambda: tmp_path)
    legacy = hashlib.sha256(b'legacy build').hexdigest()

    def report(**caps):
        pcs.sync(rec['key'], 'a' * 32, capabilities={'os': os_name, 'arch': 'amd64', **caps})
        return [d for d in pcs.devices() if d['device_id'] == rec['device_id']][0]['helper']

    assert report()['state'] == 'unknown'  # 옛 헬퍼는 자기 판을 보고하지 않는다
    assert report(helper_sha256='0' * 64, go=go_version)['state'] == 'manual'
    with pytest.raises(ValueError, match='helper_update_unavailable'):
        pcs.update_helper(rec['device_id'])
    status = report(helper_sha256='0' * 64, go=go_version, self_update=True)
    assert status == {'state': 'available', 'current': '0' * 64, 'latest': legacy, 'rolled_back': False}
    if os_name == 'darwin':
        assert report(helper_sha256='0' * 64, go='go1.26.1', self_update=True)['latest'] == hashlib.sha256(b'regular build').hexdigest()
    report(helper_sha256='0' * 64, go=go_version, self_update=True)
    with pytest.raises(ValueError, match='unsupported_resident_operation'):
        pcs.submit(rec['device_id'], {'op': 'update', 'transfer_id': 'x', 'sha256': legacy}, 'agent')
    started = pcs.update_helper(rec['device_id'])
    assert started['state'] == 'updating' and started['sha256'] == legacy
    job = json.loads(pcs.sync(rec['key'], 'a' * 32)['jobs'][0]['code'])
    assert job['op'] == 'update' and job['sha256'] == legacy
    staged = pcs.transfer_info(job['transfer_id'])
    assert staged['state'] == 'committed' and staged['sha256'] == legacy and staged['direction'] == 'to_pc'
    assert pcs.transfer_path(job['transfer_id']).read_bytes() == b'legacy build'
    # 두 번 눌러도 교체는 하나다.
    assert pcs.update_helper(rec['device_id'])['job_id'] == started['job_id']
    assert [d for d in pcs.devices() if d['device_id'] == rec['device_id']][0]['helper']['state'] == 'updating'
    pcs.sync(rec['key'], 'a' * 32, [{'job_id': started['job_id'], 'event_id': 'u1', 'kind': 'result',
                                      'payload': {'updated': True, 'restarting': True}}])
    # 작업은 끝났지만 새 헬퍼가 아직 보고하기 전: 다시 누를 수 있는 상태로 보이지 않는다.
    assert report(helper_sha256='0' * 64, go=go_version, self_update=True)['state'] == 'updating'
    assert pcs.update_helper(rec['device_id'])['job_id'] == started['job_id']
    assert report(helper_sha256=legacy, go=go_version, self_update=True)['state'] == 'current'
    assert pcs.update_helper(rec['device_id'])['state'] == 'current'
    # 되돌려진 교체는 같은 판을 다시 권하되 실패했음을 알린다.
    (dist / ('indiebiz-helper-' + build)).write_bytes(b'legacy build 2')
    newer = hashlib.sha256(b'legacy build 2').hexdigest()
    status = report(helper_sha256=legacy, go=go_version, self_update=True,
                    helper_update={'outcome': 'rolled_back', 'to': newer})
    assert status['state'] == 'available' and status['rolled_back'] is True
