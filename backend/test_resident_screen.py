"""Live desktop ownership, transient delivery, revocation and bounded input."""
import boot_paths
import time
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import api_resident_screen
import device_registry
import limb_keys
import resident_pcs
import resident_screen as screen
import resident_store


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(limb_keys, '_store_path', lambda: tmp_path / 'keys.json')
    monkeypatch.setattr(limb_keys, '_cache', None)
    monkeypatch.setenv('INDIEBIZ_RUNTIME_STATE_DIR', str(tmp_path))
    monkeypatch.setattr(device_registry, 'register', lambda *a, **k: None)
    monkeypatch.setattr(screen, '_sessions', {})
    monkeypatch.setattr(api_resident_screen.lan, 'offer', lambda *a, **k: {})

    def make(name='screen-pc', kind='pc'):
        rec = limb_keys.resident_enroll(limb_keys.resident_invite(name)['key'], uuid.uuid4().hex, kind=kind, adapter='indiebiz-v1' if kind == 'phone' else 'resident-v1')
        limb_keys.resident_update(rec['device_id'], capabilities={'desktop_stream': 1, 'elevation': True, 'ops': ['info', 'desktop']}, last_seen=time.time())
        return rec
    return make


@pytest.mark.parametrize('kind', ['pc', 'phone'])
def test_screen_stream_device_owner_auth_delivery_and_close(setup, kind):
    rec, other, sid = setup(kind=kind), setup('other'), uuid.uuid4().hex
    app = FastAPI()
    app.include_router(api_resident_screen.router)
    with TestClient(app, base_url='http://localhost') as client:
        assert client.post('/remote-pcs/screens', json={'target': rec['device_id'], 'id': sid}).status_code == 200
        job = screen._sessions[sid].job
        with client.websocket_connect('/limb/resident/screen/' + sid) as wrong:
            wrong.send_json({'key': other['key'], 'installation_id': other['registration']['installation_id']})
            assert wrong.receive()['type'] == 'websocket.close'
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect('/remote-pcs/screens/' + sid + '/stream', headers={'x-forwarded-for': '1.2.3.4'}):
                pass
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect('/remote-pcs/screens/' + sid + '/stream', headers={'host': 'localhost', 'origin': 'https://untrusted.example'}):
                pass
        with client.websocket_connect('/limb/resident/screen/' + sid) as helper:
            helper.send_json({'key': rec['key'], 'installation_id': rec['registration']['installation_id']})
            assert helper.receive_json()['type'] == 'ready'
            with client.websocket_connect('/remote-pcs/screens/' + sid + '/stream', headers={'host': 'localhost'}) as owner:
                assert owner.receive_json()['state'] == 'starting'
                helper.send_bytes(b'\xff\xd8test-screen\xff\xd9')
                assert owner.receive_json()['state'] == 'running'
                assert owner.receive_bytes() == b'\xff\xd8test-screen\xff\xd9'
                owner.send_json({'type': 'text', 'text': '한글'})
                while (message := helper.receive_json())['type'] == 'heartbeat':
                    pass
                assert message == {'type': 'text', 'text': '한글'}
                assert client.delete('/remote-pcs/screens/' + sid).status_code == 200
                assert owner.receive_json()['state'] == 'closed'
                while (message := helper.receive_json())['type'] == 'heartbeat':
                    pass
                assert message['type'] == 'close'
        assert screen._sessions[sid].frame == b''
        assert not screen._sessions[sid].inputs
        history = resident_store.history(job=job)
        assert 'test-screen' not in str(history) and '한글' not in str(history)


def test_expiry_capability_and_one_owner(setup):
    rec, sid = setup(), uuid.uuid4().hex
    with pytest.raises(ValueError, match='unsupported'):
        resident_pcs.submit(rec['device_id'], {'op': 'desktop'})
    limb_keys.resident_update(rec['device_id'], capabilities={})
    with pytest.raises(ValueError, match='헬퍼'):
        screen.create(rec['device_id'], sid)
    limb_keys.resident_update(rec['device_id'], capabilities={'desktop_stream': 1})
    screen.create(rec['device_id'], sid)
    with pytest.raises(ValueError, match='먼저 닫으세요'):
        screen.create(rec['device_id'], uuid.uuid4().hex)
    screen.attach(sid)
    with pytest.raises(ValueError, match='already_attached'):
        screen.attach(sid)
    screen._sessions[sid].lease.rewind(screen._sessions[sid].lease.lease_s + 1)
    assert screen.status(sid)['state'] == 'closed'
    assert screen.take(sid) == [{'type': 'close'}]
    screen.create(rec['device_id'], uuid.uuid4().hex)


def test_order_frame_replacement_validation_and_revocation(setup):
    rec, sid = setup(), uuid.uuid4().hex
    screen.create(rec['device_id'], sid)
    for value in (b'HTTP', b'\xff\xd8', b'\xff\xd8' + b'x' * screen.MAX_FRAME):
        with pytest.raises(ValueError):
            screen.put_frame(sid, value)
    screen.put_frame(sid, b'\xff\xd8one')
    screen.put_frame(sid, b'\xff\xd8two')
    assert screen.frame(sid, 0) == (2, b'\xff\xd8two')
    assert screen.frame(sid, 2) == (2, b'')
    for value in ({'type': 'exec', 'cmd': 'whoami'}, {'type': 'pointer', 'x': float('nan'), 'y': 0, 'buttons': 0},
                  {'type': 'pointer', 'x': 1, 'y': 0, 'buttons': True}, {'type': 'text', 'text': 'a' * 16385},
                  {'type': 'key', 'code': 'A;exec', 'key': '', 'down': True}):
        with pytest.raises(ValueError):
            screen.input_message(sid, value)
    for i in range(1000):
        screen.input_message(sid, {'type': 'pointer', 'x': i / 1000, 'y': 0, 'buttons': 0})
    screen.input_message(sid, {'type': 'pointer', 'x': .5, 'y': .5, 'buttons': 1})
    screen.input_message(sid, {'type': 'pointer', 'x': .5, 'y': .5, 'buttons': 0})
    assert [m['buttons'] for m in screen.take(sid)] == [0, 1, 0]
    for _ in range(256):
        screen.input_message(sid, {'type': 'reset'})
    with pytest.raises(ValueError, match='backpressure'):
        screen.input_message(sid, {'type': 'reset'})
    limb_keys.revoke(rec['device_id'])
    with pytest.raises(ValueError):
        screen.input_message(sid, {'type': 'reset'})


def test_elevation_requires_explicit_supported_shell(setup):
    rec = setup()
    for command in ({'op': 'read', 'elevate': True}, {'op': 'shell', 'elevate': 'true'},
                    {'op': 'shell', 'elevate': True, 'mode': 'observe', 'timeout': 10}):
        with pytest.raises(ValueError):
            resident_pcs.submit(rec['device_id'], command)
    receipt = resident_pcs.submit(rec['device_id'], {'op': 'shell', 'cmd': 'id', 'elevate': True})
    assert receipt['job_id']
    limb_keys.resident_update(rec['device_id'], capabilities={})
    with pytest.raises(ValueError, match='새 헬퍼'):
        resident_pcs.submit(rec['device_id'], {'op': 'shell', 'cmd': 'id', 'elevate': True})


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))


def test_phone_screen_requires_owner_entry_and_supports_permission_status(setup):
    rec, sid = setup(kind='phone'), uuid.uuid4().hex
    with pytest.raises(ValueError, match='unsupported'):
        resident_pcs.submit(rec['device_id'], {'op': 'desktop', 'screen_id': sid})
    assert screen.create(rec['device_id'], sid)['device_kind'] == 'phone'
    screen.device_status(sid, {'code': 'permission'})
    assert '폰에서' in screen.status(sid)['message']
    assert screen.status(sid)['state'] == 'starting'
    with pytest.raises(ValueError):
        screen.device_status(sid, {'code': 'arbitrary', 'message': 'private'})
    screen.put_frame(sid, b'\xff\xd8phone')
    screen.input_message(sid, {'type': 'navigation', 'action': 'home'})
    assert screen.take(sid) == [{'type': 'navigation', 'action': 'home'}]
    with pytest.raises(ValueError):
        screen.input_message(sid, {'type': 'navigation', 'action': 'unlock'})
    screen.device_status(sid, {'code': 'accessibility'})
    assert screen.status(sid)['state'] == 'closed'
    assert screen.frame(sid, 0)[1] == b''
    assert screen.take(sid) == [{'type': 'close'}]
