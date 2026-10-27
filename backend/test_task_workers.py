import boot_paths  # noqa: F401
import json
import os
from pathlib import Path
from threading import Barrier, Event
import time

import pytest
import conversation_sessions as sessions
import task_workers
import task_worker_store as store
from conversation_db import ConversationDB
from thread_context import actor_context


@pytest.fixture
def worker_program(tmp_path, monkeypatch, request):
    """Real IBL/dispatch/storage, with only the cognitive stream replaced."""
    import delegation_tasks
    import ibl_routing
    import routing_system
    import task_receipts
    from episode_logger import EpisodeLogger
    from ibl_v2_entry import handle_request
    from thread_context import get_task_origin

    monkeypatch.setitem(ibl_routing._SYSTEM_CAPS, 'delegate', routing_system._delegate_unified)
    monkeypatch.setitem(task_receipts._STATUS, 'delegation', delegation_tasks.task_status)

    path = tmp_path / 'conversations.db'
    db = ConversationDB(str(path))
    db.create_task('parent', 'user', 'gui', 'parallel review', 'agent')
    parent_store = sessions.SessionStore(path, 'messages', 'pair:1:2')
    binding = parent_store.begin(parent_store.create()['id'])
    monkeypatch.setattr(task_workers, '_identity', lambda: (sessions.current(), 'test', 'parent', 'agent'))
    monkeypatch.setattr(delegation_tasks, '_owner_db_path', lambda _: path)
    monkeypatch.setattr(delegation_tasks, 'get_task_row', lambda owner, task: db.get_task(task))
    monkeypatch.setattr(delegation_tasks, 'project_db', lambda owner: db)
    monkeypatch.setattr(EpisodeLogger, 'start_episode', lambda *a, **kw: None)
    monkeypatch.setattr(EpisodeLogger, 'end_episode', lambda: None)
    seen, evidence = [], []

    class Runner:
        def cognitive_stream(self, message, history, **kwargs):
            seen.append({'session': sessions.current().session_id, 'message': message,
                         'history': history, 'origin': get_task_origin()})
            # Opposite completion order is deliberate failure/latency injection.
            if message.startswith('slow'):
                time.sleep(.08)
            if message.startswith('raise'):
                raise RuntimeError('TRANSPORT_LOST: revision 9')
            if message.startswith('fail'):
                yield {'type': 'error', 'content': 'SOURCE_UNAVAILABLE: revision 7'}
            else:
                yield {'type': 'tool_result', 'name': 'probe', 'input': {}, 'result': message + ' evidence'}
                yield {'type': 'final', 'content': message + ' result'}

    monkeypatch.setattr(task_workers, '_runner', lambda payload, sid: Runner())

    def execute(code, inputs=None):
        payload = {'edition': 2, 'code': code, 'inputs': inputs or {}}
        checked = handle_request({**payload, 'check': True}, project_path=str(tmp_path))
        evidence.append({'check': checked})
        assert checked['ok'], checked
        result = handle_request(payload, project_path=str(tmp_path))
        evidence[-1]['result'] = result
        assert result['success'], result
        return result['value']

    with sessions.scope(binding), actor_context(agent_id='agent', task_id='parent', origin='training'):
        try:
            yield execute, seen, db
        finally:
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                with task_workers._dispatch_lock:
                    busy = any(p == str(path) for p, _ in task_workers._dispatching)
                if not busy:
                    break
                time.sleep(.01)
            assert not busy, 'training workers must be drained before applying repairs'
            with sessions.connection(path) as conn:
                rows = [dict(row) for row in conn.execute('SELECT * FROM tasks')]
            assert all(row['status'] in store.TERMINAL for row in rows if row['task_id'] != 'parent')
            assert db.get_task('parent')['pending_delegations'] == 0
            parent_store.finish(binding, 'completed')
            if directory := os.getenv('INDIEBIZ_WORKER_PROBE_OUTPUT'):
                out = Path(directory)
                out.mkdir(parents=True, exist_ok=True)
                (out / (request.node.name + '.json')).write_text(json.dumps(
                    {'executions': evidence, 'seen': seen, 'tasks': rows, 'drained': True},
                    ensure_ascii=False, indent=2, default=str))


@pytest.mark.parametrize('variant', ['duplicate', 'reverse', 'failure', 'empty'])
def test_parallel_program_preserves_receipts_and_terminal_results(worker_program, variant):
    execute, seen, db = worker_program
    source = (Path(__file__).resolve().parents[1] /
              'docs/experiments/long_sentence_imagination/round_92/main_v0.ibl').read_text()
    # Task creation has an opaque write footprint. Submit explicitly in order;
    # the accepted workers and read-only result waits still overlap.
    source = source.replace('[table:each]{parallel:4}', '[table:each]{parallel:1}', 1)
    a = {'id': 'a', 'message': 'slow A', 'context': {'revision': 7}}
    b = {'id': 'b', 'message': 'fast B', 'context': {'revision': 8}}
    requests = {'duplicate': [a, b, a], 'reverse': [b, a],
                'failure': [a, {**b, 'message': 'fail B'}], 'empty': []}[variant]
    value = execute(source, {'requests': requests})
    assert len(value['receipts']) == len(requests)
    assert len(seen) == len({row['id'] for row in requests})
    assert all(row['origin'] == 'training' for row in seen)
    for index, row in enumerate(value['results']):
        receipt = value['receipts'][index]
        assert row['task'] == receipt['task_ref']
        if requests[index]['message'].startswith('fail'):
            assert row['error'] and row['details']['state'] == 'failed'
        else:
            assert row['result']['state'] == 'succeeded'
            assert requests[index]['message'] in row['result']['result']
    if variant == 'duplicate':
        assert value['receipts'][0]['task_ref'] == value['receipts'][2]['task_ref']
    assert db.get_task('parent')['pending_delegations'] == 0


@pytest.mark.parametrize('first_message', ['review A', 'fail A'])
def test_followup_preserves_structured_context_and_failure(worker_program, first_message):
    execute, seen, _ = worker_program
    value = execute('''
$a=[others:delegate]{scope:"task",request_id:"first",message:$message,
 context:{revision:7,policy:"원본 보존",budget:3200000}}
[try] { [self:task]{op:"wait",ref:$a.task_ref,timeout:5} }
[catch] { null }
$b=[others:delegate]{scope:"task",request_id:"next",worker_ref:$a.worker_ref,
 message:"앞 판본과 유지 조건을 확인하고 후속 처리해 줘"}
$result=[self:task]{op:"wait",ref:$b.task_ref,timeout:5}
return {a:$a,b:$b,result:$result}
''', {'message': first_message})
    assert value['a']['worker_ref'] == value['b']['worker_ref']
    assert value['a']['task_ref'] != value['b']['task_ref']
    prior = next(row['history'] for row in seen if row['message'].startswith('앞 판본'))
    user_input = next(row['content'] for row in prior if row['role'] == 'user')
    assert '원본 보존' in user_input and '3200000' in user_input and 'revision' in user_input
    if first_message.startswith('fail'):
        assert any('SOURCE_UNAVAILABLE' in row['content'] for row in prior)


@pytest.mark.parametrize('message,reason', [
    ('fail A', 'SOURCE_UNAVAILABLE'), ('raise A', 'TRANSPORT_LOST'),
])
def test_followup_reports_failed_attempt_even_without_final_response(worker_program, message, reason):
    execute, seen, _ = worker_program
    execute('''
$a=[others:delegate]{scope:"task",request_id:"first",message:$message}
[try] { [self:task]{op:"wait",ref:$a.task_ref,timeout:5} }
[catch] { null }
$b=[others:delegate]{scope:"task",request_id:"next",worker_ref:$a.worker_ref,message:"retry"}
return [self:task]{op:"wait",ref:$b.task_ref,timeout:5}
''', {'message': message})
    prior = next(row['history'] for row in seen if row['message'] == 'retry')
    assert any(reason in row['content'] and 'failed' in row['content'] for row in prior)


@pytest.mark.parametrize('changed', ['message', 'context', 'allowed'])
def test_duplicate_request_rejects_changed_contract_before_new_work(worker_program, changed):
    execute, seen, db = worker_program
    value = execute('''
$a=[others:delegate]{scope:"task",request_id:"one",message:"A",context:{revision:7}}
$conflict=[try] {
  [others:delegate]{scope:"task",request_id:"one",message:$message,context:$context,allowed:$allowed}
} [catch] { {rejected:true,message:$error.message} }
$done=[self:task]{op:"wait",ref:$a.task_ref,timeout:5}
return {conflict:$conflict,done:$done}
''', {'message': 'changed' if changed == 'message' else 'A',
      'context': {'revision': 8 if changed == 'context' else 7},
      'allowed': ['table'] if changed == 'allowed' else []})
    assert value['conflict']['rejected'] and 'request_id' in value['conflict']['message']
    assert len(seen) == 1 and db.get_task('parent')['pending_delegations'] == 0


def test_queued_followup_keeps_prior_context_without_repeating_other_worker(worker_program):
    execute, seen, _ = worker_program
    value = execute('''
$a=[others:delegate]{scope:"task",request_id:"first",message:"slow A",context:{revision:7,policy:"원본 보존"}}
$b=[others:delegate]{scope:"task",request_id:"followup",worker_ref:$a.worker_ref,message:"continue A"}
$c=[others:delegate]{scope:"task",request_id:"other",message:"other B",context:{revision:99}}
$results=[self:task]{op:"wait",ref:$b.task_ref,timeout:5} & [self:task]{op:"wait",ref:$c.task_ref,timeout:5}
return {a:$a,b:$b,c:$c,results:$results}
''')
    assert value['a']['worker_ref'] == value['b']['worker_ref']
    assert value['a']['worker_ref'] != value['c']['worker_ref']
    followup = next(row for row in seen if row['message'] == 'continue A')
    text = json.dumps(followup['history'], ensure_ascii=False)
    assert '원본 보존' in text and 'slow A' in text and 'evidence' in text
    assert 'other B' not in text and '99' not in text
    assert len(seen) == 3


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
