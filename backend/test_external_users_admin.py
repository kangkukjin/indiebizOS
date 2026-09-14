"""주인 관리창의 인증·발급·폐기. 실제 자격/이웃 원장은 임시 폴더에만 만든다."""
import boot_paths  # noqa: F401
import json
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api_external_users as admin
import limb_keys
import principal

HEADERS = {"origin": "http://localhost:5173", "sec-fetch-mode": "cors"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    import sys
    import business_manager
    import face_config
    import member_session
    import member_bridge
    bm = business_manager.BusinessManager(tmp_path / "business.db")
    monkeypatch.setattr(business_manager, "BusinessManager", lambda: bm)
    monkeypatch.setenv("INDIEBIZ_BASE_PATH", str(tmp_path))
    monkeypatch.delenv("INDIEBIZ_USERDATA", raising=False)
    monkeypatch.setattr(limb_keys, "_cache", None)
    monkeypatch.setattr(member_session, "_base", lambda: tmp_path)
    monkeypatch.setattr(member_bridge, "connected", lambda device: False)
    monkeypatch.setattr(face_config, "load_config", lambda: {
        "public_base": "https://cdn.example", "direct_hosts": ["hub.example"]})
    monkeypatch.setitem(sys.modules, "api_launcher_web", SimpleNamespace(
        is_external_request=lambda request: request.headers.get("x-test-external") == "yes",
        verify_session=lambda request: request.headers.get("x-test-owner") == "yes"))
    app = FastAPI()
    app.include_router(admin.router)
    with TestClient(app) as c:
        yield c


def test_owner_gate_covers_reads_and_mutations(client):
    for method, path, body in [
        ("GET", "/external-users", None),
        ("POST", "/external-users/keys", {"neighbor_id": 1}),
        ("POST", "/external-users/people", {"name": "test"}),
        ("DELETE", "/external-users/keys/missing", None),
    ]:
        assert client.request(method, path, json=body).status_code == 403
        headers = {**HEADERS, "x-test-external": "yes", "authorization": "Bearer member-key"}
        assert client.request(method, path, json=body, headers=headers).status_code == 403
        with principal.narrow(principal.member("1", 4, "device")):
            assert client.request(method, path, json=body, headers=HEADERS).status_code == 403
    assert client.get('/external-users', headers={"x-test-external": "yes", "x-test-owner": "yes"}).status_code == 200


def test_issue_list_and_revoke_real_member_key(client, tmp_path):
    import api_member
    person = client.post('/external-users/people', headers=HEADERS,
                         json={"name": "테스트 회원", "level": 2}).json()
    issued = client.post('/external-users/keys', headers=HEADERS,
                         json={"neighbor_id": person['id'], "ttl_days": 7})
    assert issued.status_code == 200
    assert issued.headers['cache-control'] == 'no-store'
    key = issued.json()
    assert key['address']['url'] == 'https://hub.example/m/app'
    assert key['expires_at'] > time.time()
    assert limb_keys.validate(key['key'])['approved']
    assert api_member._member_of(key['key'])[1] is None
    day = time.strftime('%Y-%m-%d')
    (tmp_path / 'data' / 'member_usage.json').write_text(json.dumps({
        str(person['id']): {day: {"turns": 3, "tokens": 99}}}))
    ordinary = limb_keys.mint('주인 USB')
    response = client.get('/external-users', headers=HEADERS)
    rows = response.json()['keys']
    assert len(rows) == 1 and rows[0]['linked'] and rows[0]['turns_today'] == 3
    assert key['key'] not in response.text and ordinary['key'] not in response.text
    assert response.headers['cache-control'] == 'no-store'
    assert client.delete('/external-users/keys/' + ordinary['device_id'], headers=HEADERS).status_code == 404
    assert limb_keys.validate(ordinary['key'])
    assert client.delete('/external-users/keys/' + key['device_id'], headers=HEADERS).status_code == 200
    assert limb_keys.validate(key['key']) is None
    assert api_member._member_of(key['key'])[1]['error'] == 'invalid_or_expired_key'
    assert client.get('/external-users', headers=HEADERS).json()['keys'][0]['revoked']


def test_invalid_identity_or_link_does_not_leave_usable_key(client, monkeypatch):
    import body_trust
    assert client.post('/external-users/keys', headers=HEADERS,
                       json={"neighbor_id": 999}).status_code == 404
    assert limb_keys.list_keys() == []
    assert client.post('/external-users/people', headers=HEADERS, json={"name": "   "}).status_code == 400
    person = client.post('/external-users/people', headers=HEADERS, json={"name": "test"}).json()
    monkeypatch.setattr(body_trust, 'link_body', lambda *a: {"linked": False, "error": "broken"})
    assert client.post('/external-users/keys', headers=HEADERS,
                       json={"neighbor_id": person['id']}).status_code == 409
    assert all(k['revoked'] for k in limb_keys.list_keys())


def test_address_does_not_mistake_cdn_for_member_host(monkeypatch):
    import face_config
    monkeypatch.setattr(face_config, 'load_config', lambda: {"public_base": "https://cdn.example"})
    assert admin.member_address()['url'] == ''
    monkeypatch.setattr(face_config, 'load_config', lambda: {
        "public_base": "https://hub.example:9443", "direct_hosts": ["hub.example:9443"]})
    assert admin.member_address()['url'] == 'https://hub.example:9443/m/app'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
