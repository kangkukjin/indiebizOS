"""재규정의 HTTP 대기와 모델 완료를 분리하고 같은 결과 티켓을 회수한다."""
import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import boot_paths  # noqa: F401
import pytest


@pytest.mark.parametrize('outcome', ['revised', 'deadline', 'exception'])
def test_reframe_transport_timeout_recovers_same_backend_result(monkeypatch, outcome):
    import mcp_server
    from api_ibl import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from common.spill import ticket_recover

    entered, release = threading.Event(), threading.Event()
    calls, submissions = [], []
    expected = {'revised': outcome == 'revised', 'reason': outcome}

    def execute(payload, agent, task):
        calls.append((payload, agent, task))
        entered.set()
        assert release.wait(5)
        if outcome == 'exception':
            raise RuntimeError('model unavailable')
        return json.dumps(expected)

    monkeypatch.setattr('reframe.execute_reframe', execute)
    monkeypatch.setattr(mcp_server, '_http_identity', lambda ctx: ('worker', '', 'task', ''))
    app = FastAPI()
    app.include_router(router)
    pool = ThreadPoolExecutor(max_workers=1)
    polls = []
    with TestClient(app) as client:
        def post(path, payload, timeout):
            if path == '/ibl/reframe':
                submissions.append((payload, pool.submit(client.post, path, json=payload)))
                assert entered.wait(5)
                # HTTP 대기만 먼저 끝났다. 실제 서버 워커와 모델 대역은 계속 실행 중이다.
                return json.dumps({'_surface_timeout': True, '_timeout_s': timeout})
            assert path == '/ibl/recover'
            polls.append(payload['ticket'])
            if len(polls) == 1:
                assert ticket_recover(payload['ticket'])['status'] == 'running'
                release.set()
                return json.dumps({'status': 'running'})
            submissions[0][1].result(timeout=5)
            return client.post(path, json=payload).text

        monkeypatch.setattr(mcp_server, '_post_backend', post)
        try:
            result = json.loads(asyncio.run(mcp_server.reframe('broken', 'evidence')))
        finally:
            release.set()
            pool.shutdown(wait=True)
    assert len(calls) == len(submissions) == 1
    assert calls[0][1:] == ('worker', 'task')
    assert len(polls) >= 2 and set(polls) == {submissions[0][0]['ticket']}
    assert result['_recovered_from_ticket'] == polls[0]
    if outcome == 'exception':
        assert result['revised'] is False and result['error'] == 'model unavailable'
    else:
        assert all(result[k] == v for k, v in expected.items())


def test_reframe_cancelled_wait_does_not_resubmit(monkeypatch):
    import mcp_server
    calls = []
    monkeypatch.setattr('completion_lease.channel_cancelled', lambda channel: True)
    monkeypatch.setattr(mcp_server, '_post_backend', lambda path, payload, timeout:
                        calls.append((path, payload)) or json.dumps({'_surface_timeout': True}))
    result = json.loads(asyncio.run(mcp_server.reframe('broken', 'evidence')))
    assert result['completion_wait'] == 'cancelled'
    assert result['ticket'] == calls[0][1]['ticket']
    assert [path for path, _ in calls] == ['/ibl/reframe']
