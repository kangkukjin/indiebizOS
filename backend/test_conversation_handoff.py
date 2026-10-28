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


def _large_cancelled_turn(store, sid):
    old = store.begin(sid)
    with sessions.scope(old):
        h = Handoff()
        h.record('started', {'message': '취소한 발송 작업'})
        h.observe({'type': 'tool_start', 'id': 'send', 'name': 'send',
                   'input': {'body': '원문보존' * 10000}})
        h.record('steer.accepted', {'id': 'steer-1', 'instruction': '다시 발송하지 마'})
    store.finish(old, 'cancelled')
    return old


def _recovery_rows(context):
    return json.loads(context[context.index('{"source_turns"'):])['observations']


def test_unchanged_large_preview_is_short_after_success_and_survives_restart(store):
    sid = store.create()['id']
    old = _large_cancelled_turn(store, sid)
    current = store.begin(sid)
    with sessions.scope(current):
        h = Handoff()
        first = h.recovery()
        assert 'excerpt' in _recovery_rows(first)[0]
        assert h.sources == []  # 발췌 전달은 원문의 복구 확인이 아니다.
        h.finish(True, '새 요청 완료')
    store.finish(current)
    reopened = sessions.SessionStore(store.path, 'conversations', store.owner)
    for _ in range(3):
        current = reopened.begin(sid)
        with sessions.scope(current):
            h = Handoff()
            repeated = h.recovery()
            row = _recovery_rows(repeated)[0]
            assert len(repeated) < 1800 and len(repeated) < len(first) / 5
            assert row['unchanged_preview'] and row['partial']
            assert row['state'] == 'cancelled'
            assert row['tool_states'] == {'effect_unknown': 1}
            assert row['pending_steering_count'] == 1
            assert h.sources == []
            ref = row['source_ref']
            assert ref['where'] == {'session_id': sid, 'turn_id': old.turn_id}
            with sqlite3.connect(ref['path']) as conn:
                events = conn.execute('SELECT payload FROM conversation_events '
                                      'WHERE session_id=? AND turn_id=? ORDER BY id',
                                      (sid, old.turn_id)).fetchall()
            assert '원문보존' not in repeated
            assert '원문보존' * 10000 in json.loads(events[1][0])['input']['body']
            assert json.loads(events[-1][0])['instruction'] == '다시 발송하지 마'
            h.finish(True, '다음 요청 완료')
        reopened.finish(current)


@pytest.mark.parametrize('success,state', [(False, 'failed'), (True, 'interrupted'),
                                         (True, 'cancelled')])
def test_failed_or_undelivered_preview_is_not_suppressed(store, success, state):
    sid = store.create()['id']
    _large_cancelled_turn(store, sid)
    current = store.begin(sid)
    with sessions.scope(current):
        h = Handoff()
        h.recovery()
        h.finish(success, '표면에 전달되지 않은 응답')
    store.finish(current, state)
    next_turn = store.begin(sid)
    with sessions.scope(next_turn):
        h = Handoff()
        rows = _recovery_rows(h.recovery())
        # 최신 실패 턴이 예산을 먼저 쓰면 큰 기록은 다음 성공 턴에서 다시 제공된다.
        assert not any(row.get('unchanged_preview') for row in rows)
        h.finish(True, '최신 실패 확인')
    store.finish(next_turn)
    with sessions.scope(store.begin(sid)):
        row = _recovery_rows(Handoff().recovery())[0]
        assert 'excerpt' in row and not row.get('unchanged_preview')


@pytest.mark.parametrize('change', ['late_result', 'steering', 'hidden_middle'])
def test_changed_original_beyond_preview_is_presented_again(store, change):
    sid = store.create()['id']
    old = _large_cancelled_turn(store, sid)
    current = store.begin(sid)
    with sessions.scope(current):
        h = Handoff()
        before = _recovery_rows(h.recovery())[0]['fingerprint']
        h.finish(True, '완료')
    store.finish(current)
    with sessions.scope(old):
        h = Handoff()
        if change == 'late_result':
            h.observe({'type': 'tool_result', 'id': 'send', 'result': '{"success":true}'})
        elif change == 'steering':
            h.record('steer.accepted', {'id': 'steer-2', 'instruction': '새 지시'})
        else:
            with sqlite3.connect(store.path) as conn:
                ident, raw = conn.execute("SELECT id,payload FROM conversation_events WHERE turn_id=? "
                                          "AND payload LIKE '%tool_start%'", (old.turn_id,)).fetchone()
                payload = json.loads(raw)
                body = payload['input']['body']
                payload['input']['body'] = body[:20000] + '변경' + body[20002:]
                conn.execute('UPDATE conversation_events SET payload=? WHERE id=?',
                             (json.dumps(payload, ensure_ascii=False), ident))
    with sessions.scope(store.begin(sid)):
        h = Handoff()
        row = _recovery_rows(h.recovery())[0]
        assert 'excerpt' in row and not row.get('unchanged_preview')
        assert row['fingerprint'] != before
        assert h.sources == []


def test_short_reminder_allows_older_unseen_recovery_through(store):
    sid = store.create()['id']
    older = store.begin(sid)
    with sessions.scope(older):
        Handoff().record('started', {'message': '더 오래된 미완료 목표'})
    store.finish(older, 'interrupted')
    huge = _large_cancelled_turn(store, sid)
    current = store.begin(sid)
    with sessions.scope(current):
        h = Handoff()
        assert [r['turn_id'] for r in _recovery_rows(h.recovery())] == [huge.turn_id]
        h.finish(True, '완료')
    store.finish(current)
    with sessions.scope(store.begin(sid)):
        h = Handoff()
        rows = _recovery_rows(h.recovery())
        assert [r['turn_id'] for r in rows] == [huge.turn_id, older.turn_id]
        assert h.sources == [older.turn_id]


def test_research_preview_uses_same_delivery_rule_and_scoped_source(tmp_path):
    from research_context import scope
    from research_store import ResearchStore
    store = ResearchStore(tmp_path, 'preview-test')
    tid = store.create_thread('복구')['id']
    old, _ = store.begin_run(tid, '큰 요청', 'first')
    context = {'path': str(store.path), 'project_uid': store.uid, 'epoch': store.epoch,
               'thread_id': tid, 'run_id': old, 'mode': 'research'}
    with sessions.scope(None), scope(context):
        Handoff().record('started', {'message': '원문' * 20000})
    store.write_response(tid, old, '중단', 'interrupted')
    current, _ = store.begin_run(tid, '다음', 'second')
    with sessions.scope(None), scope({**context, 'run_id': current}):
        h = Handoff()
        assert 'excerpt' in _recovery_rows(h.recovery())[0]
        h.finish(True, '완료')
    store.write_response(tid, current, '완료', 'completed')
    new, _ = store.begin_run(tid, '다음', 'third')
    with sessions.scope(None), scope({**context, 'run_id': new}):
        h = Handoff()
        row = _recovery_rows(h.recovery())[0]
        assert row['unchanged_preview'] and h.sources == []
        assert row['source_ref']['where'] == {'thread_id': tid, 'run_id': old}
        assert row['source_ref']['table'] == 'research_events'
    other = store.create_thread('다른 대화')['id']
    other_run, _ = store.begin_run(other, '분리', 'fourth')
    with sessions.scope(None), scope({**context, 'thread_id': other, 'run_id': other_run}):
        assert Handoff().recovery() == ''


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
