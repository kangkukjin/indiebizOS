"""기존 SQLite 사건의 재기동 인계·소유권·중복/불확실 결과 보존."""
import boot_paths  # noqa: F401
import json
import sqlite3

import pytest
import conversation_sessions as sessions
from conversation_handoff import Handoff, _calls
import steer_inbox as inbox


@pytest.fixture
def store(tmp_path):
    path = tmp_path / 'conversations.db'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE conversations(id INTEGER PRIMARY KEY, role TEXT, content TEXT, source TEXT)')
    return sessions.SessionStore(path, 'conversations', 'system_ai')


def test_restart_delivered_but_unconfirmed_steering_and_effects_reach_next_turn(store, monkeypatch):
    sid = store.create()['id']
    binding = store.begin(sid)
    with sessions.scope(binding):
        log = Handoff()
        log.record('started', {'message': '원래 목표'})
        with inbox.task_scope(['a'], 'dead', log.record):
            inbox.post('a', '사용자 정정', 'dead', require_active=True)
            assert inbox.drain('a', 'dead') == ['사용자 정정']
            log.observe({'type': 'tool_start', 'id': 'send', 'name': 'execute_ibl', 'input': {'code': 'send'}})
            log.observe({'type': 'tool_start', 'id': 'job', 'name': 'execute_ibl', 'input': {'code': 'job'}})
            log.observe({'type': 'tool_result', 'id': 'job', 'result': json.dumps({'success': True, 'accepted': True,
                         'task_ref': {'kind': 'script', 'task_id': 'existing-job'}})})
    monkeypatch.setattr(sessions, '_PROCESS', 'new-process')
    reopened = sessions.SessionStore(store.path, 'conversations', store.owner)
    new = reopened.begin(sid)
    with sessions.scope(new):
        recovery = Handoff().recovery()
    assert all(s in recovery for s in ['사용자 정정', '원래 목표', 'effect_unknown', 'accepted_unverified', 'existing-job'])
    assert '다시 제출하지 마라' in recovery
    other = reopened.create()['id']
    with sessions.scope(reopened.begin(other)):
        assert Handoff().recovery() == ''


def test_existing_surface_events_are_recovered_without_new_journal(store):
    sid = store.create()['id']
    old = store.begin(sid)
    with sessions.scope(old):
        sessions.record_event({'type': 'tool_start', 'id': 'read', 'name': 'Read', 'input': {'path': 'x'}})
        sessions.record_event({'type': 'tool_result', 'id': 'read', 'name': 'Read', 'result': 'old observation'})
        sessions.record_event({'type': 'tool_start', 'id': 'write', 'name': 'Bash', 'input': {'command': 'write'}})
    store.finish(old, 'interrupted')
    new = store.begin(sid)
    with sessions.scope(new):
        log = Handoff()
        context = log.recovery()
        assert 'old observation' in context and 'effect_unknown' in context
        log.finish(True, 'recovered')
    store.finish(new)
    with sessions.scope(store.begin(sid)):
        assert Handoff().recovery() == ''


def test_failed_recovery_is_offered_again_and_cancelled_is_not_authorization(store):
    sid = store.create()['id']
    old = store.begin(sid)
    with sessions.scope(old):
        Handoff().record('started', {'message': 'old request'})
        Handoff().finish(False)
    store.finish(old, 'cancelled')
    current = store.begin(sid)
    with sessions.scope(current):
        h = Handoff()
        context = h.recovery()
        assert '취소된 작업을 자동 재개하지 마라' in context
        assert '"state": "cancelled"' in context
        h.finish(False)
    store.finish(current, 'failed')
    with sessions.scope(store.begin(sid)):
        assert old.turn_id in Handoff().recovery()


def test_receipt_completion_not_inferred_from_acceptance_and_ids_not_order():
    rows = _calls([
        {'type': 'tool_start', 'id': 'a', 'name': 'write'},
        {'type': 'tool_start', 'id': 'b', 'name': 'read'},
        {'type': 'tool_result', 'id': 'b', 'result': '{"success":true,"items":[1]}'},
        {'type': 'tool_start', 'id': 'c', 'name': 'job'},
        {'type': 'tool_result', 'id': 'c', 'result': '{"success":true,"accepted":true,"resume":{"run_id":"keep"}}'},
    ])
    assert [r['state'] for r in rows] == ['effect_unknown', 'completed', 'accepted_unverified']
    assert rows[2]['resume'] == {'run_id': 'keep'}


def test_abrupt_process_exit_keeps_accepted_and_unpaired_tool(store):
    """finally를 실행하지 않는 프로세스 죽음도 접수한 지시를 잃지 않는다."""
    import os
    import subprocess
    import sys
    from pathlib import Path
    sid = store.create()['id']
    child = '''
import boot_paths
import os, sys
import conversation_sessions as sessions
from conversation_handoff import Handoff
import steer_inbox
store = sessions.SessionStore(sys.argv[1], 'conversations', 'system_ai')
with sessions.scope(store.begin(sys.argv[2])):
    log = Handoff()
    log.record('started', {'message': '프로세스 종료 직전 작업'})
    with steer_inbox.task_scope(['child'], 'crash', log.record):
        steer_inbox.post('child', '절대 버리면 안 되는 지시', 'crash', require_active=True)
        steer_inbox.drain('child', 'crash')
        log.observe({'type':'tool_start', 'id':'uncertain', 'name':'Bash', 'input':{'command':'write'}})
        os._exit(23)
'''
    result = subprocess.run([sys.executable, '-B', '-c', child, str(store.path), sid],
                            cwd=Path(__file__).parent, env=dict(os.environ), timeout=15)
    assert result.returncode == 23
    # 저장소 재개는 다른 프로세스의 running 턴을 interrupted로 바꾼다.
    reopened = sessions.SessionStore(store.path, 'conversations', store.owner)
    with sessions.scope(reopened.begin(sid)):
        context = Handoff().recovery()
    assert '절대 버리면 안 되는 지시' in context
    assert 'uncertain' in context and 'effect_unknown' in context


def test_excerpt_does_not_acknowledge_unseen_turns_or_truncated_steering():
    h = Handoff()
    rows = [(str(i), 'interrupted', {'type': 'handoff.started', 'message': str(i)}) for i in range(8)]
    h._previous = lambda: rows
    context = h.recovery()
    assert len(h.sources) == 5
    assert all(f'"turn_id": "{i}"' in context for i in h.sources)
    h._previous = lambda: [('huge', 'interrupted', {'type': 'handoff.started', 'message': 'x'*20000})]
    assert 'partial' in h.recovery()
    assert h.sources == []


def test_research_steering_is_journaled_without_nested_database_transaction(tmp_path):
    from research_context import scope
    from research_store import ResearchStore
    import research_threads
    store = ResearchStore(tmp_path, 'handoff-test')
    tid = store.create_thread('복구')['id']
    run, _ = store.begin_run(tid, '원래 목표', 'first')
    actor = f'research:{store.uid}:{tid}'
    context = {'path': str(store.path), 'project_uid': store.uid, 'epoch': store.epoch,
               'thread_id': tid, 'run_id': run, 'mode': 'research'}
    with sessions.scope(None), scope(context):
        log = Handoff()
        with inbox.task_scope([actor], run, log.record):
            assert research_threads.steer(store, tid, '추가 지시', 'second', [])['steered']
            assert research_threads.steer(store, tid, '추가 지시', 'second', [])['steered']
            inbox.drain(actor, run)
    store.write_response(tid, run, '중단', 'interrupted')
    new, _ = store.begin_run(tid, '이어줘', 'third')
    with sessions.scope(None), scope({**context, 'run_id': new}):
        recovery = Handoff().recovery()
    assert recovery.count('추가 지시') == 1


def test_model_finished_but_surface_interrupted_still_hands_off_response(store):
    sid = store.create()['id']
    old = store.begin(sid)
    with sessions.scope(old):
        h = Handoff()
        h.record('started', {'message': '이전 요청'})
        h.finish(True, '생성됐지만 화면에 저장되지 못한 응답')
    store.finish(old, 'interrupted')
    with sessions.scope(store.begin(sid)):
        assert '생성됐지만 화면에 저장되지 못한 응답' in Handoff().recovery()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
