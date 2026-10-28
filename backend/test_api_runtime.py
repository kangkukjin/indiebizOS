"""재기동 중 기존 기기 작업의 통신은 접수 관문에 막히지 않는다."""
import boot_paths  # noqa: F401
import asyncio

import pytest
import runtime_work as rw
from api_runtime import RuntimeAdmission, _DEVICE_TRANSPORT


@pytest.mark.parametrize('path', sorted(_DEVICE_TRANSPORT))
def test_device_transport_survives_drain_without_work_lease(monkeypatch, path):
    reg = rw.WorkRegistry('test')
    reg.gate('DRAINING')
    monkeypatch.setattr(rw, '_registry', reg)
    seen = []
    async def app(scope, receive, send):
        assert reg.snapshot()['active_roots'] == 0
        await send({'type': 'http.response.start', 'status': 204, 'headers': []})
    async def receive():
        return {'type': 'http.request', 'body': b'{}'}
    async def send(message):
        seen.append(message)
    asyncio.run(RuntimeAdmission(app)({'type': 'http', 'method': 'POST', 'path': path, 'headers': []}, receive, send))
    assert seen[0]['status'] == 204
    assert reg.snapshot()['owners'] == []


@pytest.mark.parametrize('path', ['/limb/new-command', '/nodes/new-command', '/ibl/execute'])
def test_new_work_stays_closed(monkeypatch, path):
    reg = rw.WorkRegistry('test')
    reg.gate('DRAINING')
    monkeypatch.setattr(rw, '_registry', reg)
    seen = []
    async def app(*args):
        pytest.fail('new work admitted')
    async def receive():
        return {'type': 'http.request', 'body': b'{"code":"return 1"}'}
    async def send(message):
        seen.append(message)
    asyncio.run(RuntimeAdmission(app)({'type': 'http', 'method': 'POST', 'path': path, 'headers': []}, receive, send))
    assert seen[0]['status'] == 503


def test_existing_limb_job_finishes_during_drain_with_auth(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import api_limb
    import phone_jobs

    reg = rw.WorkRegistry('test')
    reg.gate('ACTIVE')
    monkeypatch.setattr(rw, '_registry', reg)
    lease = reg.reserve('existing-task')
    jid = phone_jobs.enqueue('pc', '{"op":"shell","cmd":"echo ok"}')
    reg.gate('DRAINING')
    monkeypatch.setattr(api_limb.limb_keys, 'validate', lambda key:
                        {'device_id': 'pc', 'approved': True, 'session': 's'} if key == 'test-key' else None)
    monkeypatch.setattr(api_limb.dr, 'heartbeat', lambda device: True)
    app = FastAPI()
    app.include_router(api_limb.router)
    app.add_middleware(RuntimeAdmission)
    with TestClient(app) as client:
        invalid = client.post('/limb/poll', json={'key': 'wrong', 'wait': 0})
        assert invalid.json()['error'] == 'invalid_or_expired_key'
        pulled = client.post('/limb/poll', json={'key': 'test-key', 'session': 's', 'wait': 0})
        assert pulled.status_code == 200
        assert pulled.json()['jobs'][0]['id'] == jid
        result = client.post('/limb/result', json={'key': 'test-key', 'session': 's', 'job_id': jid,
                                                  'result': {'exit': 0, 'stdout': 'ok'}})
        assert result.json()['success']
        assert phone_jobs.wait_result(jid, 0)['stdout'] == 'ok'
        lease.close()
        assert reg.snapshot()['owners'] == []


def test_resident_completion_unblocks_drain_with_auth_and_duplicate_ack(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import api_resident_pcs
    import device_registry
    import limb_keys
    import resident_pcs
    import resident_store

    monkeypatch.setattr(limb_keys, '_store_path', lambda: tmp_path / 'keys.json')
    monkeypatch.setattr(limb_keys, '_cache', None)
    monkeypatch.setenv('INDIEBIZ_RUNTIME_STATE_DIR', str(tmp_path))
    monkeypatch.setattr(device_registry, 'register', lambda *a, **k: None)
    reg = rw.WorkRegistry('test')
    reg.gate('ACTIVE')
    monkeypatch.setattr(rw, '_registry', reg)
    invitation = limb_keys.resident_invite('test-device')
    rec = limb_keys.resident_enroll(invitation['key'], 'a' * 32)
    auth = {'key': rec['key'], 'installation_id': 'a' * 32}
    lease = reg.reserve('waiting-for-device')
    task = resident_pcs.submit(rec['device_id'], {'op': 'info'}, 'existing')
    jid = task['job_id']
    resident_pcs.sync(**auth)  # Command delivered before draining.
    resident_pcs.sync(**auth, events=[{
        'job_id': jid, 'event_id': 'started', 'kind': 'started', 'payload': {}}])
    pending = resident_pcs.submit(rec['device_id'], {'op': 'info'}, 'queued')
    reg.gate('DRAINING')
    app = FastAPI()
    app.include_router(api_resident_pcs.router)
    app.add_middleware(RuntimeAdmission)
    event = {'job_id': jid, 'event_id': 'finished', 'kind': 'result',
             'payload': {'success': True, 'value': 'done'}}
    try:
        with TestClient(app) as client:
            invalid = client.post('/limb/resident/events', json={
                **auth, 'installation_id': 'b' * 32, 'events': [event]})
            assert invalid.status_code == 400
            assert resident_store.wait_result(jid, 0) is None
            for _ in range(2):  # A lost acknowledgement retries the same event.
                response = client.post('/limb/resident/events', json={
                    **auth, 'events': [event]})
                assert response.status_code == 200
                assert response.json()['ack'] == ['finished']
                assert response.json()['jobs'] == []
            assert resident_store.wait_result(jid, 0) == event['payload']
            history = resident_store.history(job=jid)
            assert history['tasks'][0]['state'] == 'succeeded'
            assert len([e for e in history['events'] if e['kind'] == 'result']) == 1
            assert resident_store.history(job=pending['job_id'])['tasks'][0]['state'] == 'queued'
            assert reg.snapshot()['active_roots'] == 1
            assert client.post('/limb/resident/enroll', json=auth).status_code == 503
            assert client.post('/ibl/execute', json={'code': 'return 1'}).status_code == 503
    finally:
        lease.close()
    assert reg.snapshot()['owners'] == []


@pytest.mark.parametrize('operation', ['result', 'progress', 'phone_result'])
def test_device_storage_does_not_block_event_loop(monkeypatch, operation):
    import threading
    import api_limb
    import api_nodes
    import phone_jobs
    loop_thread = threading.get_ident()
    seen = []
    def store(*args):
        assert threading.get_ident() != loop_thread
        seen.append(args)
        return True
    monkeypatch.setattr(api_limb.limb_keys, 'validate', lambda key: {'device_id': 'pc'})
    monkeypatch.setattr(api_limb, '_job_owned', store)
    monkeypatch.setattr(phone_jobs, 'set_result', store)
    monkeypatch.setattr(phone_jobs, 'set_partial', store)
    if operation == 'progress':
        call = api_limb.limb_progress(api_limb.ProgressRequest(key='test', job_id='j'))
    elif operation == 'result':
        call = api_limb.limb_result(api_limb.ResultRequest(key='test', job_id='j'))
    else:
        call = api_nodes.node_job_result(api_nodes.JobResultRequest(job_id='j'))
    assert asyncio.run(call)['success']
    assert seen


if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
