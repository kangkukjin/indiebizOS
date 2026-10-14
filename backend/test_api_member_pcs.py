"""실제 자격·프레즌스·HTTP로 독립 PC 등록과 회원/주인 경계를 검증한다."""
import boot_paths  # noqa: F401
import json
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api_member_pcs
import api_member
import api_limb
import limb_keys
import device_registry
import principal

HEADERS = {"origin": "http://localhost:5173", "sec-fetch-mode": "cors"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    import sys
    import business_manager
    import face_config
    import member_session
    monkeypatch.setenv("INDIEBIZ_BASE_PATH", str(tmp_path))
    monkeypatch.delenv("INDIEBIZ_USERDATA", raising=False)
    monkeypatch.setattr(limb_keys, "_cache", None)
    monkeypatch.setattr(device_registry, "_cache", None)
    monkeypatch.setattr(member_session, "_base", lambda: tmp_path)
    monkeypatch.setattr(member_session.MemberSessionManager, "_instance", None)
    def forbidden(*args, **kwargs):
        pytest.fail("PC 등록·인증이 이웃 명부를 사용했습니다")
    monkeypatch.setattr(business_manager, "BusinessManager", forbidden)
    monkeypatch.setattr(face_config, "load_config", lambda: {"direct_hosts": ["hub.example"]})
    monkeypatch.setattr(api_limb, "_notify_new_limb", lambda *args: None)
    monkeypatch.setattr(api_limb, "_notify_host_change", lambda *args: None)
    monkeypatch.setitem(sys.modules, "api_launcher_web", SimpleNamespace(
        is_external_request=lambda request: request.headers.get("x-test-external") == "yes",
        verify_session=lambda request: request.headers.get("x-test-owner") == "yes"))
    app = FastAPI()
    for router in (api_member_pcs.router, api_member.router, api_limb.router):
        app.include_router(router)
    with TestClient(app) as c:
        yield c


def register(client, **kw):
    response = client.post('/member-pcs', headers=HEADERS, json={"name": "업무 PC", **kw})
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    return response.json()


def connect(client, key):
    response = client.post('/limb/connect', json={"key": key, "mode": "member", "host": "test-host",
                                               "env": {"os": "darwin", "shell": True}})
    assert response.status_code == 200
    return response.json()


def test_owner_gate_and_no_neighbor_creation(client, tmp_path):
    for method, path, payload in [
        ('GET', '/member-pcs', None), ('POST', '/member-pcs', {'name': 'pc'}),
        ('PATCH', '/member-pcs/missing', {'enabled': False}),
        ('POST', '/member-pcs/missing/key', None), ('DELETE', '/member-pcs/missing', None),
    ]:
        assert client.request(method, path, json=payload).status_code == 403
        with principal.narrow(principal.member('other', None, 'other-pc')):
            assert client.request(method, path, json=payload, headers=HEADERS).status_code == 403
        assert client.request(method, path, json=payload, headers={**HEADERS, 'x-test-external': 'yes'}).status_code == 403
    issued = register(client, user_label="사무 담당", note="공용 업무", ttl_days=7)
    rec = limb_keys.validate(issued['key'])
    assert rec['neighbor_id'] is None
    assert rec['member_id'] == rec['device_id']
    assert rec['expires_at'] > time.time()
    ident, error = api_member._member_of(issued['key'])
    assert not error and ident[1:] == (rec['member_id'], None)
    assert not (tmp_path / 'data' / 'business.db').exists()
    response = client.get('/member-pcs', headers=HEADERS)
    assert issued['key'] not in response.text
    row = response.json()['pcs'][0]
    assert row['status'] == 'pending' and row['user_label'] == '사무 담당'
    assert 'neighbor_id' not in row and 'key' not in row
    assert client.post('/member-pcs', headers=HEADERS, json={'name': 'pc', 'neighbor_id': 1}).status_code == 422


def test_connection_separation_usage_and_status(client, tmp_path):
    first = register(client)
    second = register(client, name='다른 PC', user_label='같은 사람이어도 독립')
    ordinary = limb_keys.mint('주인 손발')
    assert client.post('/limb/connect', json={'key': first['key'], 'mode': 'limb'}).json()['error'] == 'member_mode_required'
    connected = connect(client, first['key'])
    assert connected['success'] and connected['member']['member_id'] == first['device_id']
    assert first['device_id'] not in [r['device_id'] for r in device_registry.live_with_capability(limb_keys.GUEST_PC_CLASS)]
    assert device_registry.get(first['device_id'])['owner'] == 'member'
    day = time.strftime('%Y-%m-%d')
    (tmp_path / 'data' / 'member_usage.json').write_text(json.dumps({first['device_id']: {day: {'turns': 3, 'tokens': 12}}}))
    rows = {p['device_id']: p for p in client.get('/member-pcs', headers=HEADERS).json()['pcs']}
    assert len(rows) == 2 and ordinary['device_id'] not in rows
    assert rows[first['device_id']]['status'] == 'online' and rows[first['device_id']]['turns_today'] == 3
    assert rows[second['device_id']]['turns_today'] == 0
    assert rows[first['device_id']]['host'] == 'test-host'
    assert client.patch('/member-pcs/' + first['device_id'], headers=HEADERS, json={'name': '수정 PC', 'note': '새 메모'}).status_code == 200
    assert limb_keys.validate(first['key'])['alias'] == '수정 PC'


def test_disable_resume_rotate_and_revoke(client):
    import member_bridge
    issued = register(client, ttl_days=7)
    device = issued['device_id']
    path = '/member-pcs/' + device
    connection = connect(client, issued['key'])
    old_session = connection['session']
    assert client.patch(path, headers=HEADERS, json={'enabled': False}).status_code == 200
    assert limb_keys.validate(issued['key']) is None
    assert not member_bridge.connected(device)
    assert not connect(client, issued['key'])['success']  # 자동 승인으로 중지 우회 불가
    assert client.get('/member-pcs', headers=HEADERS).json()['pcs'][0]['status'] == 'disabled'
    assert client.patch(path, headers=HEADERS, json={'enabled': True}).status_code == 200
    assert not member_bridge.connected(device)  # 다시 연결해야 한다
    assert client.post('/limb/poll', json={'key': issued['key'], 'session': old_session, 'wait': 0}).json()['stale']
    connect(client, issued['key'])
    rotated = client.post(path + '/key', headers=HEADERS).json()
    assert rotated['key'] != issued['key'] and rotated['device_id'] == device
    assert time.time() + 6 * 86400 < rotated['expires_at'] < time.time() + 8 * 86400
    assert limb_keys.validate(issued['key']) is None
    assert api_member._member_of(rotated['key'])[1] is None
    assert len(limb_keys.list_keys()) == 1
    assert not member_bridge.connected(device)
    assert client.delete(path, headers=HEADERS).status_code == 200
    assert limb_keys.validate(rotated['key']) is None
    assert client.get('/member-pcs', headers=HEADERS).json()['pcs'][0]['status'] == 'revoked'
    assert client.patch(path, headers=HEADERS, json={'enabled': True}).status_code == 409
    assert client.post(path + '/key', headers=HEADERS).status_code == 409


def test_late_poll_and_old_operations_cannot_cross_connection(client, monkeypatch):
    import phone_jobs
    issued = register(client)
    device = issued['device_id']
    session = connect(client, issued['key'])['session']
    wrong = phone_jobs.enqueue(device, json.dumps({'member': True, 'body_session': 'old', 'op': 'write'}))
    owner_job = phone_jobs.enqueue(device, json.dumps({'op': 'shell', 'cmd': 'no'}))
    current = phone_jobs.enqueue(device, json.dumps({'member': True, 'body_session': session, 'op': 'read'}))
    response = client.post('/limb/poll', json={'key': issued['key'], 'session': session, 'wait': 0}).json()
    assert [j['id'] for j in response['jobs']] == [current]
    assert phone_jobs.job_status(wrong)['state'] == 'queued'
    assert phone_jobs.job_status(owner_job)['state'] == 'queued'
    def late(*args):
        limb_keys.update_member_pc(device, enabled=False)
        return [{'id': 'must-not-deliver'}]
    monkeypatch.setattr(phone_jobs, 'pull_blocking', late)
    response = client.post('/limb/poll', json={'key': issued['key'], 'session': session, 'wait': 0}).json()
    assert response['stale'] and response['jobs'] == []


def test_non_member_targets_invalid_input_and_expired_status(client, monkeypatch):
    ordinary = limb_keys.mint('주인 PC')
    legacy = limb_keys.mint('구형 이웃', neighbor_id=7)
    for target in (ordinary, legacy):
        path = '/member-pcs/' + target['device_id']
        assert client.delete(path, headers=HEADERS).status_code == 404
        assert client.post(path + '/key', headers=HEADERS).status_code == 404
        assert limb_keys.validate(target['key'])
    assert client.post('/member-pcs', headers=HEADERS, json={'name': '  '}).status_code == 400
    issued = register(client, ttl_days=7)
    monkeypatch.setattr(limb_keys, '_now', lambda: time.time() + 8 * 86400)
    assert api_member._member_of(issued['key'])[1]
    assert client.get('/member-pcs', headers=HEADERS).json()['pcs'][0]['status'] == 'expired'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))


def test_native_turn_envelope_keeps_connection_generation(client, tmp_path, monkeypatch):
    import threading
    import member_bridge
    import member_runtime
    import phone_jobs
    issued = register(client)
    connection = connect(client, issued['key'])
    sent = []
    def enqueue(device, code, owner):
        sent.append((device, json.loads(code), owner))
        return 'job-test'
    monkeypatch.setattr(phone_jobs, 'enqueue', enqueue)
    monkeypatch.setattr(phone_jobs, 'wait_result', lambda *a, **k: {'success': True, 'content': 'ok'})
    device = issued['device_id']
    with principal.narrow(principal.member(device, None, device)):
        with member_runtime.turn_scope(tmp_path, device, 'turn', threading.Event(), {}) as state:
            assert member_bridge.request({'op': 'read', 'path': 'a.txt'})['success']
            assert state['body_session'] == connection['session']
            assert sent[0][0] == device and sent[0][2] == 'member:' + device
            assert sent[0][1]['member'] is True
            assert sent[0][1]['body_session'] == connection['session']
            limb_keys.touch(issued['key'], new_session=True)
            assert member_bridge.request({'op': 'read', 'path': 'a.txt'})['error_type'] == 'no_body'
            assert len(sent) == 1
