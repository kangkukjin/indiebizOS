"""Terminal transport ownership, bounded delivery, lease and real PTY regression."""
import boot_paths
import base64
import time
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api_resident_pcs
import device_registry
import limb_keys
import resident_pcs
import resident_store
import resident_terminal as terminal


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(limb_keys, '_store_path', lambda: tmp_path / 'keys.json')
    monkeypatch.setattr(limb_keys, '_cache', None)
    monkeypatch.setenv('INDIEBIZ_RUNTIME_STATE_DIR', str(tmp_path))
    monkeypatch.setattr(device_registry, 'register', lambda *a, **k: None)
    monkeypatch.setattr(terminal, '_sessions', {})
    import resident_terminal_lan
    monkeypatch.setattr(resident_terminal_lan, 'offer', lambda handler: {})

    def make(name='terminal-pc'):
        rec = limb_keys.resident_enroll(limb_keys.resident_invite(name)['key'], uuid.uuid4().hex)
        limb_keys.resident_update(rec['device_id'], capabilities={'terminal': True}, last_seen=time.time())
        return rec
    return make


def test_terminal_bridge_bytes_input_order_close_and_ownership(setup):
    rec = setup()
    sid = uuid.uuid4().hex
    app = FastAPI()
    app.include_router(api_resident_pcs.router)
    with TestClient(app) as client:
        response = client.post('/remote-pcs/terminals', json={'target': rec['device_id'], 'id': sid})
        assert response.status_code == 200
        job = response.json()['job_id']
        assert terminal.create(rec['device_id'], sid)['job_id'] == job
        resident_pcs.sync(rec['key'], rec['registration']['installation_id'], [
            {'job_id': job, 'event_id': 'started', 'kind': 'started', 'payload': {}}])
        other = setup('other')
        with client.websocket_connect('/limb/resident/terminal/' + sid) as ws:
            ws.send_json({'key': other['key'], 'installation_id': other['registration']['installation_id']})
            assert ws.receive()['type'] == 'websocket.close'
        with client.websocket_connect('/limb/resident/terminal/' + sid) as ws:
            ws.send_json({'key': rec['key'], 'installation_id': rec['registration']['installation_id']})
            assert ws.receive_json()['type'] == 'ready'
            ws.send_bytes('한글\x1b[31m'.encode())
            for _ in range(100):
                state = client.get('/remote-pcs/terminals/' + sid).json()
                if state['data']:
                    break
                time.sleep(.01)
            assert base64.b64decode(state['data']) == '한글\x1b[31m'.encode()
            assert client.post('/remote-pcs/terminals/' + sid, json={'type': 'input', 'data': 'pwd\r', 'sequence': 1}).status_code == 200
            while (received := ws.receive_json())['type'] == 'heartbeat':
                pass
            assert received == {'type': 'input', 'data': 'pwd\r'}
            assert client.post('/remote-pcs/terminals/' + sid, json={'type': 'input', 'data': 'pwd\r', 'sequence': 1}).status_code == 400
            assert client.delete('/remote-pcs/terminals/' + sid).status_code == 200
            while (received := ws.receive_json())['type'] == 'heartbeat':
                pass
            assert received['type'] == 'close'
        assert resident_store.history(job=job)['tasks'][0]['state'] == 'cancel_requested'


def test_capability_gate_no_agent_terminal_and_limits(setup):
    rec = setup()
    with pytest.raises(ValueError, match='unsupported'):
        resident_pcs.submit(rec['device_id'], {'op': 'terminal'})
    limb_keys.resident_update(rec['device_id'], capabilities={})
    with pytest.raises(ValueError, match='헬퍼 교체'):
        terminal.create(rec['device_id'], uuid.uuid4().hex)
    limb_keys.resident_update(rec['device_id'], capabilities={'terminal': True})
    sid = uuid.uuid4().hex
    terminal.create(rec['device_id'], sid)
    terminal.create(rec['device_id'], uuid.uuid4().hex)
    with pytest.raises(ValueError, match='열린 터미널'):
        terminal.create(rec['device_id'], uuid.uuid4().hex)
    terminal.attach(sid, rec['device_id'])
    with pytest.raises(ValueError, match='already_attached'):
        terminal.attach(sid, rec['device_id'])
    terminal.output(sid, b'a' * (terminal.OUTPUT_LIMIT + 9))
    state = terminal.poll(sid, 0)
    assert state['gap'] and state['cursor'] == 9 + 65536
    for i in range(4):
        terminal.input_message(sid, {'type': 'input', 'data': 'a' * 16384, 'sequence': i + 1})
    with pytest.raises(ValueError, match='backpressure'):
        terminal.input_message(sid, {'type': 'input', 'data': 'a', 'sequence': 5})
    assert len(terminal.take(sid)) == 4
    terminal._sessions[sid].seen -= terminal.LEASE_SECONDS + 1
    assert terminal.take(sid) == [{'type': 'close'}]
    assert terminal.poll(sid, 0)['state'] == 'closed'


def test_revocation_and_input_validation(setup):
    rec = setup()
    sid = uuid.uuid4().hex
    terminal.create(rec['device_id'], sid)
    terminal.attach(sid, rec['device_id'])
    for value in (0, True, 501, '80'):
        with pytest.raises(ValueError, match='size'):
            terminal.input_message(sid, {'type': 'resize', 'cols': value, 'rows': 20})
    limb_keys.revoke(rec['device_id'])
    with pytest.raises(ValueError):
        terminal.input_message(sid, {'type': 'input', 'sequence': 1, 'data': 'x'})
    assert terminal.poll(sid, 0)['state'] == 'closed'


def test_owner_stream_auth_push_order_and_disconnect(setup):
    rec = setup()
    sid = uuid.uuid4().hex
    terminal.create(rec['device_id'], sid)
    terminal.attach(sid, rec['device_id'], 'lan')
    app = FastAPI()
    app.include_router(api_resident_pcs.router)
    from starlette.websockets import WebSocketDisconnect
    with TestClient(app, base_url='http://localhost') as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect('/remote-pcs/terminals/' + sid + '/stream',
                                          headers={'x-forwarded-for': '1.2.3.4'}):
                pass
        with client.websocket_connect('/remote-pcs/terminals/' + sid + '/stream', headers={'host': 'localhost'}) as ws:
            assert ws.receive_json()['route'] == 'lan'
            start = time.monotonic()
            terminal.output(sid, b'instant')
            assert base64.b64decode(ws.receive_json()['data']) == b'instant'
            assert time.monotonic() - start < .5  # cannot wait for the 1s heartbeat
            for seq in range(1, 51):
                ws.send_json({'type': 'input', 'data': 'x', 'sequence': seq})
            until = time.monotonic() + 2
            while terminal._sessions[sid].sequence < 50 and time.monotonic() < until:
                time.sleep(.01)
            assert terminal._sessions[sid].sequence == 50
            assert terminal.take(sid) == [{'type': 'input', 'data': 'x'}] * 50
            ws.close()
            until = time.monotonic() + 2
            while terminal.poll(sid, 0)['state'] != 'closed' and time.monotonic() < until:
                time.sleep(.01)
        assert terminal.poll(sid, 0)['state'] == 'closed'


@pytest.mark.system
def test_native_terminal_while_ai_busy_and_helper_crash(setup, tmp_path):
    import json
    import os
    import platform
    import socket
    import subprocess
    import threading
    from pathlib import Path
    import uvicorn

    suffix = {('Darwin', 'arm64'): 'mac-arm64', ('Darwin', 'x86_64'): 'mac-amd64',
              ('Linux', 'x86_64'): 'linux'}.get((platform.system(), platform.machine()))
    if not suffix:
        pytest.skip('POSIX native terminal fixture')
    binary = Path(__file__).resolve().parents[1] / 'helper/dist' / ('indiebiz-helper-' + suffix)
    rec = setup()
    app = FastAPI()
    app.include_router(api_resident_pcs.router)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    worker = tmp_path / 'worker'
    worker.mkdir()
    cfg = {'mode': 'resident', 'base': f'http://127.0.0.1:{port}', 'key': rec['key'],
           'installation_id': rec['registration']['installation_id'],
           'generation': rec['registration']['generation'], 'data_dir': str(worker)}
    (worker / 'indiebiz-helper.json').write_text(json.dumps(cfg))
    import resident_terminal_lan
    lan_server, lan_port, pin = resident_terminal_lan._start(api_resident_pcs.terminal_socket)
    lan_offer = {"urls": [f"https://127.0.0.1:{lan_port}"], "sha256": pin}
    proc = None
    sid = uuid.uuid4().hex
    cursor = 0
    sequence = 0

    def wait_for(predicate, timeout=15):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            value = predicate()
            if value:
                return value
            time.sleep(.04)
        raise AssertionError('condition timed out')

    def send(text):
        nonlocal sequence
        sequence += 1
        terminal.input_message(sid, {'type': 'input', 'sequence': sequence, 'data': text})

    def expect(text):
        nonlocal cursor
        collected = bytearray()
        def read():
            nonlocal cursor
            state = terminal.poll(sid, cursor)
            cursor = state['cursor']
            collected.extend(base64.b64decode(state['data']))
            return text.encode() in collected
        wait_for(read)
        return collected.decode(errors='replace')

    try:
        wait_for(lambda: server.started)
        proc = subprocess.Popen([str(binary)], cwd=worker, env={**os.environ, 'SHELL': '/bin/sh'},
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        wait_for(lambda: (resident_pcs.resolve(rec['device_id'])['registration'].get('capabilities') or {}).get('helper_sha256'))
        jobs = [resident_pcs.submit(rec['device_id'], {'op': 'shell', 'cmd': 'sleep 30'}) for _ in range(2)]
        wait_for(lambda: all(resident_store.history(job=j['job_id'])['tasks'][0]['state'] == 'running' for j in jobs))
        receipt = terminal.create(rec['device_id'], sid, 90, 25, lan=lan_offer)
        wait_for(lambda: terminal.poll(sid, 0)['state'] == 'running')
        assert terminal.poll(sid, 0)['route'] == 'lan'
        send("stty -echo; printf '\\122\\105\\101\\104\\131'; export IB_TERMINAL_VALUE=preserved\r")
        expect('READY')
        send('printf "%s" "$IB_TERMINAL_VALUE"\r')
        expect('preserved')
        terminal.input_message(sid, {'type': 'resize', 'cols': 113, 'rows': 41})
        send('stty size\r')
        expect('41 113')
        send('sleep 20\r')
        time.sleep(.2)
        send('\x03')
        send("printf '\\111\\116\\124\\105\\122\\122\\125\\120\\124'\r")
        expect('INTERRUPT')
        assert all(resident_store.history(job=j['job_id'])['tasks'][0]['state'] == 'running' for j in jobs)
        terminal.close(sid)
        wait_for(lambda: resident_store.history(job=receipt['job_id'])['tasks'][0]['result'] is not None)
        # A crash must not leave the foreground terminal command alive.
        sid, cursor, sequence = uuid.uuid4().hex, 0, 0
        terminal.create(rec['device_id'], sid)
        wait_for(lambda: terminal.poll(sid, 0)['state'] == 'running')
        marker = tmp_path / 'orphan-terminal'
        send(f"stty -echo; printf '\\103\\122\\101\\123\\110'; sleep 3; echo escaped > '{marker}'\r")
        expect('CRASH')
        proc.kill()
        proc.wait(timeout=5)
        time.sleep(3.5)
        assert not marker.exists(), 'terminal foreground survived helper crash'
        wait_for(lambda: terminal.poll(sid, cursor)['state'] == 'closed')
    finally:
        if proc and proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)
        lan_server.should_exit = True
        server.should_exit = True
        thread.join(timeout=30)
        assert not thread.is_alive()


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
