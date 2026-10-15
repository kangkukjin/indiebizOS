"""수신 후 연결 단절/서버 재시작에도 접수 ID를 다시 실행하지 않는다."""
import boot_paths  # noqa: F401
import threading
import time
import pytest
import member_desktop_requests as service
import limb_keys
import client_agent


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv('INDIEBIZ_BASE_PATH', str(tmp_path))
    monkeypatch.delenv('INDIEBIZ_USERDATA', raising=False)
    service.LIVE.clear()
    rec = {'key': 'test', 'device_id': 'device', 'member_id': 'member', 'session': 'session'}
    monkeypatch.setattr(limb_keys, 'validate', lambda key: rec)
    yield rec
    for row in service.LIVE.values():
        row['state'] = 'cancelled'
    service.LIVE.clear()


def test_submit_duplicate_restart_and_other_member(state, monkeypatch, tmp_path):
    calls, done = [], threading.Event()
    def run(*args, **kwargs):
        calls.append(args)
        done.wait(2)
        kwargs['on_event']({'type': 'progress'})
        return {'success': True, 'response': 'PRIVATE CONTENT'}
    monkeypatch.setattr(client_agent, 'run', run)
    envelope = {'request_id': 'one', 'conversation_id': 'task', 'message': 'PRIVATE INPUT'}
    assert service.submit(state, envelope, {})['state'] == 'accepted'
    assert service.submit(state, envelope, {})['success']
    assert service.submit(state, {**envelope, 'message': 'changed'}, {})['error'] == 'request_id_conflict'
    assert service.status({**state, 'device_id': 'other'}, 'one')['error'] == 'request_not_found'
    done.set()
    for _ in range(100):
        result = service.status(state, 'one')
        if result['state'] == 'completed':
            break
        time.sleep(.01)
    assert result['state'] == 'completed' and len(calls) == 1
    assert result['events'][0]['seq'] == 1
    assert not service.status(state, 'one', after=1)['events']
    service.LIVE.clear()  # Simulated server restart, persistent receipt survives.
    assert service.submit(state, envelope, {})['state'] == 'unknown'
    assert len(calls) == 1
    disk = (tmp_path / 'data/member_requests.sqlite3').read_bytes()
    assert b'PRIVATE' not in disk


def test_cancel_is_terminal_and_late_success_does_not_reopen(state, monkeypatch):
    done = threading.Event()
    def run(*args, **kwargs):
        done.wait(2)
        return {'success': True}
    monkeypatch.setattr(client_agent, 'run', run)
    from member_session import MemberSessionManager
    monkeypatch.setattr(MemberSessionManager, '_instance', None)
    service.submit(state, {'request_id': 'one', 'conversation_id': 'task'}, {})
    assert service.cancel(state, 'one')['state'] == 'cancelled'
    done.set()
    time.sleep(.03)
    assert service.status(state, 'one')['state'] == 'cancelled'


def test_submit_sweeps_expired_results_before_capacity(state, monkeypatch):
    service.LIVE.update({('old', str(i)): {'state': 'completed', 'finished': time.monotonic()-1801} for i in range(512)})
    monkeypatch.setattr(client_agent, 'run', lambda *a, **kw: {'success': True})
    result = service.submit(state, {'request_id': 'new', 'conversation_id': 'task'}, {})
    assert result['state'] == 'accepted'
    assert all(k[0] != 'old' for k in service.LIVE)
    for _ in range(100):
        if service.status(state, 'new')['state'] == 'completed':
            break
        time.sleep(.01)
    assert service.status(state, 'new')['state'] == 'completed'


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))


def test_worker_exception_becomes_unknown_without_retry_or_private_error(state, monkeypatch):
    calls = []
    def run(*args, **kwargs):
        calls.append(1)
        raise RuntimeError('PRIVATE PATH AND CONTENT')
    monkeypatch.setattr(client_agent, 'run', run)
    envelope = {'request_id': 'crash', 'conversation_id': 'task'}
    service.submit(state, envelope, {})
    for _ in range(100):
        result = service.status(state, 'crash')
        if result['state'] not in ('accepted', 'running'):
            break
        time.sleep(.01)
    assert result['state'] == 'unknown'
    assert result['result']['error_type'] == 'result_unknown'
    assert 'PRIVATE' not in str(result)
    assert service.submit(state, envelope, {})['state'] == 'unknown'
    assert len(calls) == 1
    assert service.LIVE[('device', 'crash')]['finished'] > 0
    with service._db() as db:
        assert db.execute("SELECT state FROM requests WHERE request='crash'").fetchone() == ('unknown',)


def test_event_window_reports_exact_missing_range_and_cursor_boundary(state, monkeypatch):
    def run(*args, **kwargs):
        for n in range(300):
            kwargs['on_event']({'type': 'progress', 'n': n})
        return {'success': True}
    monkeypatch.setattr(client_agent, 'run', run)
    service.submit(state, {'request_id': 'burst', 'conversation_id': 'task'}, {})
    for _ in range(100):
        result = service.status(state, 'burst')
        if result['state'] == 'completed':
            break
        time.sleep(.01)
    assert result['events_gap'] == {'from': 1, 'to': 44}
    assert [e['seq'] for e in result['events']] == list(range(45, 301))
    assert service.status(state, 'burst', after=20)['events_gap'] == {'from': 21, 'to': 44}
    assert service.status(state, 'burst', after=44)['events_gap'] is None
    tail = service.status(state, 'burst', after=300)
    assert tail['events_gap'] is None and tail['events'] == []
