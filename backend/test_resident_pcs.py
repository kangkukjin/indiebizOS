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
def test_resident_binary_roundtrip_crash_and_ui(tmp_path, monkeypatch):
    """Uses an isolated hub and built binary; never installs an OS autostart service."""
    import platform
    import time
    import threading
    import socket
    import subprocess
    import uvicorn
    from playwright.sync_api import sync_playwright
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
        latency = round((time.monotonic() - start) * 1000)
        assert pcs.submit(rec['device_id'], {'op': 'shell', 'cmd': 'printf resident-ok', 'timeout': 10}, 'smoke-once')['job_id'] == job['job_id']
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
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for width in (390, 1280):
                page = browser.new_page(viewport={'width': width, 'height': 900})
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.goto(url + '/remote-pcs/app')
                page.wait_for_function("document.querySelector('#target').options.length===1")
                assert page.locator('#device').inner_text().find('맥12-테스트') >= 0
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), page.evaluate('[...document.querySelectorAll("*")].filter(e=>e.getBoundingClientRect().right>innerWidth).map(e=>[e.tagName,e.id,e.className])')
                assert not errors, errors
                page.screenshot(path=str(work / f'ui-{width}.png'), full_page=True)
                page.close()
            browser.close()
        print(json.dumps({'shell_first_result_ms': latency, 'binary_roundtrip_bytes': len(payload), 'dedup': True, 'crash_children_reaped': True, 'restart_state': 'unknown', 'ui_widths': [390, 1280], 'work_dir': str(work)}, ensure_ascii=False))
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
