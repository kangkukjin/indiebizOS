import boot_paths  # noqa: F401
import json
from threading import Barrier, Event
import time

import pytest
import conversation_sessions as sessions
import task_workers
import task_worker_store as store
from conversation_db import ConversationDB
from thread_context import actor_context


def test_independent_sessions_overlap_and_followup_uses_history(tmp_path, monkeypatch):
    path = tmp_path / 'conversations.db'
    db = ConversationDB(str(path))
    db.create_task('parent', 'user', 'gui', 'parent', 'agent')
    parent_store = sessions.SessionStore(path, 'messages', 'pair:1:2')
    binding = parent_store.begin(parent_store.create()['id'])
    monkeypatch.setattr(task_workers, '_identity', lambda: (sessions.current(), 'test', 'parent', 'agent'))
    import delegation_tasks
    monkeypatch.setattr(delegation_tasks, '_owner_db_path', lambda _: path)
    from episode_logger import EpisodeLogger
    monkeypatch.setattr(EpisodeLogger, 'start_episode', lambda *a, **kw: None)
    monkeypatch.setattr(EpisodeLogger, 'end_episode', lambda: None)
    barrier = Barrier(2)
    seen = []

    class Runner:
        def cognitive_stream(self, message, history, **kwargs):
            if message in ('first', 'second'):
                barrier.wait(3)
            seen.append((sessions.current().session_id, message, history))
            yield {'type': 'tool_result', 'name': 'probe', 'input': {}, 'result': message + ' evidence'}
            yield {'type': 'final', 'content': message + ' result'}

    monkeypatch.setattr(task_workers, '_runner', lambda payload, sid: Runner())

    def wait(ref):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            row = db.get_task(ref['task_id'])
            if row['status'] in store.TERMINAL:
                assert row['status'] == 'completed', row
                return
            time.sleep(.01)
        pytest.fail('worker did not complete')

    with sessions.scope(binding), actor_context(agent_id='agent', task_id='parent'):
        a = task_workers.delegate({'request_id': 'a', 'message': 'first'}, str(tmp_path))
        b = task_workers.delegate({'request_id': 'b', 'message': 'second'}, str(tmp_path))
        assert a['worker_ref'] != b['worker_ref']
        wait(a['task_ref'])
        wait(b['task_ref'])
        again = task_workers.delegate({'request_id': 'a', 'message': 'first'}, str(tmp_path))
        assert again['task_ref'] == a['task_ref']
        followup = task_workers.delegate({'request_id': 'c', 'message': 'continue', 'worker_ref': a['worker_ref']}, str(tmp_path))
        wait(followup['task_ref'])
        assert followup['task_ref'] != a['task_ref']
        assert followup['worker_ref'] == a['worker_ref']
    history = next(h for sid, message, h in seen if message == 'continue')
    assert any('first evidence' in m['content'] for m in history)
    assert all('second' not in m['content'] for m in history)


def test_agent_steering_source_and_durable_idempotency(tmp_path, monkeypatch):
    from conversation_handoff import Handoff
    import steer_inbox
    path = tmp_path / 'conversations.db'
    db = ConversationDB(str(path))
    db.create_task('parent', 'user', 'gui', 'request', 'agent')
    parent_store = sessions.SessionStore(path, 'messages', 'pair:1:2')
    parent = parent_store.begin(parent_store.create()['id'])
    from test_task_worker_store import payload
    child = store.accept(path, 'parent', 'one', 'request', payload(parent.session_id))
    p = json.loads(child['worker_payload'])
    worker_store = sessions.SessionStore(path, 'messages', 'worker:' + parent.session_id, create_legacy=False)
    child_binding = worker_store.begin(child['worker_session'])
    with sessions.scope(child_binding):
        handoff = Handoff()
    monkeypatch.setattr(task_workers, 'authorize', lambda ref: (path, child, p))
    ref = {'kind': 'delegation', 'owner': 'test', 'task_id': child['task_id']}
    with steer_inbox.task_scope(['agent'], child['task_id'], journal=handoff.record):
        with actor_context(agent_id='parent'):
            first = task_workers.steer(ref, 'check binary files', 's1')
        texts = steer_inbox.drain('agent', child['task_id'])
        rendered = steer_inbox.render(texts)
        assert '부모 에이전트' in rendered and '[사용자 조향]' not in rendered
        steer_inbox.complete('agent', child['task_id'])
    # Already completed delivery can be queried after the ephemeral inbox is gone.
    retry = task_workers.steer(ref, 'check binary files', 's1')
    assert first['accepted'] and retry['delivery'] == 'completed'
    with pytest.raises(ValueError):
        task_workers.steer(ref, 'changed', 's1')


def test_recovery_waits_for_runtime_activation_and_failed_dispatch_can_retry(monkeypatch, tmp_path):
    import runtime_work
    registry = runtime_work.WorkRegistry('test-generation')
    monkeypatch.setattr(runtime_work, '_registry', registry)
    monkeypatch.setattr(task_workers, '_resume_armed', False)
    calls = []
    monkeypatch.setattr(task_workers, 'recover_all', lambda: calls.append('recovered'))
    task_workers.arm_resume()
    task_workers.resume()
    assert not calls
    with pytest.raises(runtime_work.AdmissionClosed):
        task_workers.dispatch(tmp_path / 'db', 'session')
    assert (str(tmp_path / 'db'), 'session') not in task_workers._dispatching
    registry.gate('ACTIVE')
    task_workers.resume()
    task_workers.resume()
    assert calls == ['recovered']


def test_empty_inherited_authority_never_becomes_unrestricted():
    from delegation_tasks import received, envelope
    from thread_context import get_allowed_nodes, set_allowed_nodes
    prior = get_allowed_nodes()
    try:
        set_allowed_nodes(set())
        env = envelope('worker:test')
        assert env['allowed'] == []
        with received(env):
            assert get_allowed_nodes() == set()
    finally:
        set_allowed_nodes(prior)


def test_resident_reply_wakes_queued_worker_after_commit(tmp_path, monkeypatch):
    path = tmp_path / 'conversations.db'
    db = ConversationDB(str(path))
    db.create_task('parent', 'user', 'gui', 'request', 'agent')
    session = sessions.SessionStore(path, 'messages', 'pair:1:2')
    from test_task_worker_store import payload
    child = store.accept(path, 'parent', 'one', 'request', payload(session.create()['id']))
    queued = store.accept(path, 'parent', 'two', 'followup', payload(json.loads(child['worker_payload'])['controller']),
                          session_id=child['worker_session'])
    store.claim(path, child['worker_session'])
    with sessions.connection(path) as conn:
        conn.execute('UPDATE tasks SET pending_delegations=1 WHERE task_id=?', (child['task_id'],))
    store.finish(path, child['task_id'], 'completed', 'child result')
    db.record_child_response(child['task_id'], {'child_task_id': 'resident', 'result': 'late result'})
    claimed = []
    monkeypatch.setattr(task_workers, 'dispatch', lambda p, sid: claimed.append(store.claim(p, sid)))
    task_workers.wake_after_reply(path, child['task_id'])
    assert claimed[0]['task_id'] == queued['task_id']


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
