"""Private HTTP entry points preserve launcher authentication and structured failures."""
import boot_paths  # noqa: F401
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from test_execution_trace import trace  # noqa: F401 -- shared synthetic owner stores


@pytest.fixture
def client(trace, monkeypatch):
    import api_execution_trace as api
    import api_launcher_web as auth
    _, root = trace
    monkeypatch.setattr(api, 'get_base_path', lambda: root)
    monkeypatch.setattr(auth, 'is_external_request', lambda request: False)
    app = FastAPI()
    app.include_router(api.router)
    with TestClient(app) as client:
        yield client


def test_http_trace_and_document(client):
    res = client.post('/world-pulse/episodes/1/trace', json={'limit': 1})
    assert res.status_code == 200
    page = res.json()
    assert page['next_cursor']
    assert client.post('/world-pulse/episodes/1/trace', json={'cursor': page['next_cursor']}).status_code == 200
    ref = page['links']['documents'][0]['source_ref']
    doc = client.post('/world-pulse/episodes/1/trace/document', json={'source_ref': ref, 'limit': 4})
    assert doc.status_code == 200 and doc.json()['text'] == 'raw '
    assert doc.json()['inspection_only']
    assert client.get('/world-pulse/episodes/999/trace').status_code == 404
    assert client.post('/world-pulse/episodes/1/trace', json={'limit': 101}).status_code == 422
    assert client.post('/world-pulse/episodes/1/trace/document', json={'source_ref': '/etc/passwd'}).status_code == 403


def test_http_task_scope_and_mismatched_owner(client):
    res = client.post('/world-pulse/execution-trace', json={
        'project': 'project-b', 'owner': 'agent-a', 'task_id': 'shared-task'})
    assert res.status_code == 200 and res.json()['identity']['episode_ids'] == [2]
    denied = client.post('/world-pulse/execution-trace', json={
        'project': '../project-b', 'owner': 'agent-a', 'task_id': 'shared-task'})
    assert denied.status_code == 403
    assert 'identity' not in denied.json()
    denied = client.post('/world-pulse/episodes/1/trace', json={'project': 'project-b', 'owner': 'agent-a'})
    assert denied.status_code == 403


def test_remote_launcher_auth_fails_closed(client, monkeypatch):
    import api_launcher_web as auth
    monkeypatch.setattr(auth, 'is_external_request', lambda request: True)
    monkeypatch.setattr(auth, 'verify_session', lambda request: False)
    assert client.get('/world-pulse/episodes/1/trace').status_code == 401
    monkeypatch.setattr(auth, 'verify_session', lambda request: True)
    assert client.get('/world-pulse/episodes/1/trace').status_code == 200
    def broken(request):
        raise RuntimeError('auth unavailable')
    monkeypatch.setattr(auth, 'verify_session', broken)
    assert client.get('/world-pulse/episodes/1/trace').status_code == 401
    monkeypatch.setattr(auth, 'is_external_request', broken)
    assert client.get('/world-pulse/episodes/1/trace').status_code == 503
    assert not auth.is_public_remote_path('POST', '/world-pulse/execution-trace')
    assert not auth.is_public_remote_path('GET', '/world-pulse/episodes/1/trace')


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
