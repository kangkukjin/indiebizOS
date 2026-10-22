import boot_paths  # noqa: F401
import json

import pytest

import conversation_sessions as sessions
from conversation_db import ConversationDB
import task_worker_store as workers


@pytest.fixture
def database(tmp_path):
    path = tmp_path / 'conversations.db'
    db = ConversationDB(str(path))
    db.create_task('parent', 'user', 'gui', 'parent request', 'agent')
    session = sessions.SessionStore(path, 'messages', 'pair:1:2')
    sid = session.create()['id']
    return path, db, sid


def payload(sid):
    return {'controller': sid, 'actor': 'agent', 'agent_id': 'agent', 'owner': 'test',
            'project_path': '.', 'envelope': {'chain': ['parent']}, 'workspace': None,
            'principal': {'kind': 'owner', 'id': ''}}


def test_accept_is_atomic_idempotent_and_session_fifo(database):
    path, db, sid = database
    first = workers.accept(path, 'parent', 'one', 'request', payload(sid))
    retry = workers.accept(path, 'parent', 'one', 'request', payload(sid))
    assert first['task_id'] == retry['task_id']
    assert db.get_task('parent')['pending_delegations'] == 1
    with pytest.raises(ValueError):
        workers.accept(path, 'parent', 'one', 'changed', payload(sid))
    second = workers.accept(path, 'parent', 'two', 'follow up', payload(sid), session_id=first['worker_session'])
    assert workers.claim(path, first['worker_session'])['task_id'] == first['task_id']
    assert workers.claim(path, first['worker_session']) is None
    workers.finish(path, first['task_id'], 'completed', 'answer')
    workers.finish(path, first['task_id'], 'failed', 'late error')
    assert workers.claim(path, first['worker_session'])['task_id'] == second['task_id']
    assert db.get_task('parent')['pending_delegations'] == 1
    workers.finish(path, second['task_id'], 'completed', 'followup answer')
    assert db.get_task('parent')['pending_delegations'] == 0


def test_parent_completion_waits_for_owned_children(database):
    path, db, sid = database
    child = workers.accept(path, 'parent', 'one', 'request', payload(sid))
    assert workers.defer_completion(path, 'parent', 'parent output')
    assert db.get_task('parent')['status'] == 'waiting_children'
    workers.finish(path, child['task_id'], 'failed', 'child error')
    assert db.get_task('parent')['status'] == 'completed'
    assert db.get_task('parent')['result'] == 'parent output'
    with pytest.raises(ValueError):
        workers.accept(path, 'parent', 'late', 'request', payload(sid))


@pytest.mark.parametrize('state', ['completed', 'failed', 'cancelled'])
@pytest.mark.parametrize('nested_state', ['completed', 'failed'])
def test_sealed_worker_preserves_first_outcome_while_children_finish(database, state, nested_state):
    path, db, sid = database
    child = workers.accept(path, 'parent', 'one', 'request', payload(sid))
    nested = workers.accept(path, child['task_id'], 'nested', 'nested', payload(child['worker_session']))
    workers.finish(path, child['task_id'], state, 'original outcome')
    assert db.get_task(child['task_id'])['status'] == 'waiting_children'
    workers.finish(path, child['task_id'], 'failed' if state == 'completed' else 'completed', 'late duplicate')
    workers.finish(path, nested['task_id'], nested_state, 'nested output')
    assert db.get_task(child['task_id'])['status'] == state
    assert db.get_task(child['task_id'])['result'] == 'original outcome'
    assert db.get_task('parent')['pending_delegations'] == 0


def test_history_keeps_cancelled_result_as_observation_and_in_order(database):
    path, _, sid = database
    child = workers.accept(path, 'parent', 'one', 'request', payload(sid))
    workers.finish(path, child['task_id'], 'cancelled', 'partially checked; do not resend')
    followup = workers.accept(path, 'parent', 'two', 'inspect', payload(sid), session_id=child['worker_session'])
    with sessions.connection(path) as conn:
        workers.event(conn, child['worker_session'], 'worker.history',
                      {'message': {'role': 'user', 'content': 'inspect'}})
    workers.finish(path, followup['task_id'], 'completed', 'inspected')
    messages = workers.history(path, child['worker_session'])
    assert messages[0]['role'] == 'assistant'
    assert 'cancelled' in messages[0]['content'] and 'do not resend' in messages[0]['content']
    assert messages[1] == {'role': 'user', 'content': 'inspect'}


def test_history_recovers_legacy_context_from_exact_task_turn_without_writes(database):
    path, _, sid = database
    first_payload = payload(sid)
    first_payload['envelope']['context'] = {'revision': 7, 'policy': '원본 보존'}
    child = workers.accept(path, 'parent', 'one', 'same request', first_payload)
    workers.finish(path, child['task_id'], 'completed', 'first')
    second_payload = payload(sid)
    second_payload['envelope']['context'] = {'revision': 8, 'policy': '새 사본'}
    second = workers.accept(path, 'parent', 'two', 'same request', second_payload,
                            session_id=child['worker_session'])
    with sessions.connection(path) as conn:
        for task, turn in [(child, 'old-turn'), (second, 'new-turn')]:
            conn.execute('UPDATE conversation_task_links SET turn_id=? WHERE task_id=?',
                         (turn, task['task_id']))
            workers.event(conn, child['worker_session'], 'worker.history',
                          {'message': {'role': 'user', 'content': 'same request'}}, turn)
        before = list(conn.execute('SELECT payload FROM conversation_events'))
    workers.finish(path, second['task_id'], 'completed', 'second')
    messages = workers.history(path, child['worker_session'])
    assert len(messages) == 4
    assert '원본 보존' in messages[1]['content'] and '7' in messages[1]['content']
    assert '새 사본' in messages[3]['content'] and '8' in messages[3]['content']
    assert messages[1]['role'] == messages[3]['role'] == 'assistant'
    with sessions.connection(path) as conn:
        after = list(conn.execute('SELECT payload FROM conversation_events'))
    assert [tuple(r) for r in before] == [tuple(r) for r in after[:-1]]


def test_failed_history_survives_pruning_terminal_task_rows(database):
    path, _, sid = database
    child = workers.accept(path, 'parent', 'one', 'request', payload(sid))
    workers.finish(path, child['task_id'], 'failed', 'transport lost; inspect before retry')
    with sessions.connection(path) as conn:
        conn.execute('DELETE FROM tasks WHERE task_id=?', (child['task_id'],))
    messages = workers.history(path, child['worker_session'])
    assert len(messages) == 1
    assert 'failed' in messages[0]['content'] and 'inspect before retry' in messages[0]['content']


def test_recovery_dispatches_only_unstarted_and_keeps_failed_effects(database):
    path, db, sid = database
    first = workers.accept(path, 'parent', 'one', 'request', payload(sid))
    second = workers.accept(path, 'parent', 'two', 'request2', payload(sid))
    workers.claim(path, first['worker_session'])
    with sessions.connection(path) as conn:
        conn.execute("UPDATE tasks SET worker_process='dead' WHERE task_id=?", (first['task_id'],))
    queued = workers.recover(path)
    assert queued == [second['worker_session']]
    assert db.get_task(first['task_id'])['status'] == 'failed'


def test_cancel_propagates_only_owned_children(database, monkeypatch, tmp_path):
    monkeypatch.setenv('INDIEBIZ_RUNTIME_STATE_DIR', str(tmp_path / 'runtime'))
    path, db, sid = database
    first = workers.accept(path, 'parent', 'one', 'request', payload(sid))
    nested = workers.accept(path, first['task_id'], 'nested', 'request', payload(first['worker_session']))
    db.create_task('resident', 'user', 'gui', 'request', 'agent', parent_task_id='parent')
    workers.cancel_owned(path, 'test', 'parent')
    from task_cancellation import requested
    assert requested('test', first['task_id']) and requested('test', nested['task_id'])
    assert not requested('test', 'resident')


def test_worker_followup_cannot_be_taken_over_by_other_session(database):
    path, _, sid = database
    child = workers.accept(path, 'parent', 'one', 'request', payload(sid))
    with pytest.raises(ValueError, match='소유'):
        workers.accept(path, 'parent', 'two', 'request', payload('stranger'), session_id=child['worker_session'])


def test_mixed_resident_and_owned_children_both_gate_parent(database):
    path, db, sid = database
    child = workers.accept(path, 'parent', 'one', 'request', payload(sid))
    with sessions.connection(path) as conn:
        conn.execute('UPDATE tasks SET pending_delegations=pending_delegations+1 WHERE task_id=?', ('parent',))
    workers.defer_completion(path, 'parent', 'parent output')
    workers.finish(path, child['task_id'], 'completed', 'owned output')
    assert db.get_task('parent')['status'] == 'waiting_children'
    db.record_child_response('parent', {'child_task_id': 'resident', 'result': 'resident output'})
    assert db.get_task('parent')['status'] == 'completed'


def test_worker_waiting_for_resident_reply_closes_ancestor(database):
    path, db, sid = database
    child = workers.accept(path, 'parent', 'one', 'request', payload(sid))
    with sessions.connection(path) as conn:
        conn.execute('UPDATE tasks SET pending_delegations=1 WHERE task_id=?', (child['task_id'],))
    workers.defer_completion(path, 'parent', 'parent output')
    workers.finish(path, child['task_id'], 'completed', 'child output')
    db.record_child_response(child['task_id'], {'child_task_id': 'resident', 'result': 'resident output'})
    assert db.get_task(child['task_id'])['status'] == 'completed'
    assert db.get_task('parent')['status'] == 'completed'
    messages = workers.history(path, child['worker_session'])
    assert any('resident output' in message['content'] for message in messages)


def test_followup_history_preserves_steering_source_and_delivery(database):
    path, _, sid = database
    child = workers.accept(path, 'parent', 'one', 'request', payload(sid))
    with sessions.connection(path) as conn:
        workers.event(conn, child['worker_session'], 'handoff.steer.accepted',
                      {'id': 'directive', 'source': 'agent', 'instruction': 'check binary files'})
        workers.event(conn, child['worker_session'], 'handoff.steer.held', {'ids': ['directive']})
    messages = workers.history(path, child['worker_session'])
    assert messages[0]['role'] == 'assistant'
    assert 'held' in messages[0]['content'] and 'check binary files' in messages[0]['content']


def test_first_parallel_delegates_serialize_schema_and_request_acceptance(database):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    path, db, sid = database
    barrier = Barrier(8)

    def accept(index):
        barrier.wait(3)
        return workers.accept(path, 'parent', str(index), 'request', payload(sid))

    with ThreadPoolExecutor(8) as pool:
        accepted = list(pool.map(accept, range(8)))
    assert len({row['task_id'] for row in accepted}) == 8
    assert db.get_task('parent')['pending_delegations'] == 8


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
