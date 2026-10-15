"""실제 Go 실행부↔HTTP↔공통 client_agent. 모델 호출만 결정적인 턴으로 대체한다."""
import boot_paths  # noqa: F401
import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
from types import SimpleNamespace

import pytest
import requests
import uvicorn
from fastapi import FastAPI
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption, PublicFormat

pytestmark = pytest.mark.system


def test_real_executor_signed_roundtrip_files_shell_and_cancel(tmp_path, monkeypatch):
    binary = os.environ.get('MEMBER_DESKTOP_TEST_BINARY')
    if not binary:
        pytest.skip('set MEMBER_DESKTOP_TEST_BINARY to the built Go executor')
    import api_limb, api_member_desktop, member_session, member_runtime, member_bridge
    import limb_keys, device_registry, member_desktop_requests, member_jobs
    monkeypatch.setenv('INDIEBIZ_BASE_PATH', str(tmp_path))
    monkeypatch.delenv('INDIEBIZ_USERDATA', raising=False)
    monkeypatch.setattr(limb_keys, '_cache', None)
    monkeypatch.setattr(device_registry, '_cache', None)
    monkeypatch.setattr(api_limb, '_notify_new_limb', lambda *a: None)
    monkeypatch.setattr(api_limb, '_notify_host_change', lambda *a: None)
    member_desktop_requests.LIVE.clear()
    member_jobs._JOBS.clear()
    cancel = threading.Event()
    def turn(member, device, level, name, message, **kwargs):
        cancel.clear()
        with member_runtime.turn_scope(tmp_path / 'private', device, 'turn-' + kwargs['local_task_id'], cancel, {'deadline_s': 120}):
            member_runtime.current().update(local_task_id=kwargs['local_task_id'], body_session=kwargs['body_session'])
            if message == 'write':
                result = member_bridge.request({'op': 'write', 'path': 'proof.txt', 'content': 'local only'})
            elif message == 'shell':
                result = member_bridge.request({'op': 'shell', 'cmd': 'printf shell-ok', 'timeout': 10})
            else:
                result = member_bridge.request({'op': 'shell', 'cmd': 'sleep 30', 'timeout': 60})
            return {'success': result.get('success', not result.get('error')), 'response': json.dumps(result)}
    manager = SimpleNamespace(turn=turn, close=lambda *a: cancel.set())
    monkeypatch.setattr(member_session.MemberSessionManager, 'instance', lambda: manager)
    monkeypatch.setattr(member_session.MemberSessionManager, '_instance', manager)
    issued = limb_keys.mint('integration member', member_pc={})
    private = Ed25519PrivateKey.generate()
    public = base64.b64encode(private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    with limb_keys._lock:
        limb_keys._load()['keys'][issued['key']]['desktop'] = {'installation_id': 'test', 'public_key': public}
        limb_keys._save()
    app = FastAPI()
    app.include_router(api_limb.router)
    app.include_router(api_member_desktop.router)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='error', lifespan='off'))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    config = {'mode': 'member', 'desktop': True, 'base': f'http://127.0.0.1:{port}', 'key': issued['key'],
              'private_key': base64.b64encode(private.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())).decode(),
              'data_dir': str(tmp_path / 'executor')}
    process = subprocess.Popen([binary, '--member-desktop'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        process.stdin.write(json.dumps(config) + '\n')
        process.stdin.flush()
        ready = json.loads(process.stdout.readline())
        def local(path, body=None):
            response = requests.request('GET' if body is None else 'POST', ready['origin'] + '/member/' + path,
                                        json=body, headers={'X-Member-Token': ready['token']}, timeout=5)
            response.raise_for_status()
            return response.json()
        deadline = time.monotonic() + 10
        while not limb_keys.get_by_device(issued['device_id']).get('session'):
            assert time.monotonic() < deadline
            time.sleep(.05)
        assert requests.get(ready['origin'] + '/member/tasks', timeout=5).status_code == 403
        for message in ('write', 'shell', 'cancel'):
            queued = local('task/start', {'message': message})
            assert queued.get('success'), queued
            task = queued['task_id']
            deadline = time.monotonic() + 15
            approved = False
            while time.monotonic() < deadline:
                for approval in local('approvals'):
                    assert approval['command']['task_id'] == task
                    local('approve', {'key': approval['key'], 'allow': True})
                    approved = True
                if message == 'cancel' and approved:
                    local('close', {})
                result = local('task?id=' + task)
                if result['state'] != 'running':
                    break
                time.sleep(.1)
            assert approved
            assert result['state'] == ('cancelled' if message == 'cancel' else 'completed'), result
            if message == 'shell':
                assert 'shell-ok' in result['result']['response']
        assert (tmp_path / 'executor/workspace/proof.txt').read_text() == 'local only'
        assert not (tmp_path / 'proof.txt').exists()
        assert not (tmp_path / 'data/phone_jobs.db').exists(), 'member command persisted at hub'
        assert b'local only' not in (tmp_path / 'data/member_requests.sqlite3').read_bytes()
        process.stdin.close()
        process.wait(timeout=8)
        assert process.returncode == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        server.should_exit = True
        thread.join(timeout=3)
        sock.close()


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
