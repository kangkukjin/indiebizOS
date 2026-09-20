"""업무 HTTP 경계와 공개 앱 계약 검증."""
import copy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import principal
import api_records
import record_store
from test_managed_records import definition_data


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(record_store, 'root_path', lambda: tmp_path)
    import record_facade
    monkeypatch.setattr(record_facade, 'root_path', lambda: tmp_path)
    import vocabulary_state
    monkeypatch.setattr(vocabulary_state, 'is_active', lambda *a, **k: True)
    app = FastAPI()
    @app.middleware('http')
    async def identify(request, call_next):
        token = principal.set_transport(principal.ANONYMOUS if request.headers.get('x-test-anonymous') else principal.OWNER)
        try:
            return await call_next(request)
        finally:
            principal.reset_transport(token)
    app.include_router(api_records.router)
    with TestClient(app) as client:
        yield client


def test_no_anonymous_or_cross_origin_mutation(client):
    assert client.get('/records/spaces', headers={'x-test-anonymous': '1'}).status_code == 403
    assert client.post('/m/records/spaces/shop/actions/describe', json={}).status_code == 401
    assert client.post('/records/admin/shop/create', json={'definition': definition_data()}, headers={'origin': 'https://evil.test'}).status_code == 403


def test_typed_action_and_idempotency(client):
    assert client.post('/records/admin/shop/create', json={'definition': definition_data()}).status_code == 200
    data = {'definition_revision': 1, 'input': {'sku': 'a', 'available': 1}, 'expected': [], 'request_id': 'r1'}
    route = '/records/spaces/shop/actions/command:stock'
    first = client.post(route, json=data)
    assert first.json()['success'], first.text
    assert client.post(route, json=data).json()['replayed']
    assert client.post(route, json={**data, 'actor': 'owner'}).status_code == 400
    assert client.post('/records/spaces/shop/actions/sql', json={}).status_code == 404
    rows = client.post('/records/spaces/shop/actions/query', json={'collection': 'stocks'}).json()['items']
    assert len(rows) == 1 and rows[0]['available'] == 1


def test_human_confirmation_is_bound_to_input(client):
    definition = definition_data()
    definition['commands']['stock']['confirmation'] = 'human'
    client.post('/records/admin/shop/create', json={'definition': definition})
    data = {'definition_revision': 1, 'input': {'sku': 'a', 'available': 1}, 'expected': [], 'request_id': 'r1', 'reason': ''}
    route = '/records/spaces/shop/actions/command:stock'
    assert client.post(route, json=data).status_code == 403
    assert client.post('/records/spaces/shop/confirm', json={**data, 'command': 'stock'}).status_code == 403
    page = client.get('/records/app')
    csrf = page.cookies['record_csrf']
    token = client.post('/records/spaces/shop/confirm', json={**data, 'command': 'stock'}, headers={'x-record-csrf': csrf}).json()['confirmation']
    assert client.post(route, json={**data, 'input': {'sku': 'b', 'available': 1}, 'confirmation': token}).status_code == 403
    assert client.post(route, json={**data, 'confirmation': token}).json()['success']
    assert client.post(route, json=data).json()['replayed']


def test_public_routes_keep_admin_private():
    from api_launcher_web import is_public_remote_path
    assert is_public_remote_path('POST', '/m/records/spaces/shop/actions/describe')
    assert not is_public_remote_path('POST', '/records/admin/shop/publish')


def test_member_key_keeps_shared_commands_in_current_role(client, monkeypatch):
    import api_member
    monkeypatch.setattr(api_member, '_member_of', lambda key: (({'device_id': 'record-test'}, '7', 1), None)
                        if key == 'valid-test-key' else (None, {'error': 'invalid'}))
    client.post('/records/admin/shop/create', json={'definition': definition_data()})
    grant = {'request_id': 'grant', 'reason': '업무 배정', 'expected_revision': 1,
             'subject': 'neighbor:7', 'roles': ['clerk']}
    assert client.post('/records/admin/shop/membership', json=grant).json()['success']
    stock = client.post('/records/spaces/shop/actions/command:stock', json={
        'definition_revision': 1, 'input': {'sku': 'a', 'available': 1}, 'expected': [], 'request_id': 'seed'}).json()['changed'][0]['id']
    headers = {'x-member-key': 'valid-test-key', 'x-test-anonymous': '1'}
    denied = client.post('/m/records/spaces/shop/actions/command:stock', headers=headers, json={
        'definition_revision': 1, 'input': {'sku': 'b', 'available': 1}, 'request_id': 'denied'})
    assert denied.status_code == 403, denied.text
    accepted = client.post('/m/records/spaces/shop/actions/command:order', headers=headers, json={
        'definition_revision': 1, 'input': {'stock_id': stock, 'quantity': 1}, 'request_id': 'member-order'})
    assert accepted.json()['success'], accepted.text
    ident = accepted.json()['changed'][0]['id']
    history = client.post('/m/records/spaces/shop/actions/history', headers=headers,
                          json={'collection': 'orders', 'id': ident}).json()['items']
    assert history[0]['subject'] == 'neighbor:7'
    client.post('/records/admin/shop/membership', json={**grant, 'request_id': 'revoke', 'expected_revision': 2, 'roles': []})
    assert client.post('/m/records/spaces/shop/actions/detail', headers=headers,
                       json={'collection': 'orders', 'id': ident}).status_code == 404


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
