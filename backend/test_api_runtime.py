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


if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
