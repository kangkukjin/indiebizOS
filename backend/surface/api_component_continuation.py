"""부품 수리 중 사망한 일반 업무를 원래 대화에서 재개한다. 광역 수리 실행과 분리한다."""
import json
import time
from dataclasses import asdict
from pathlib import Path

import conversation_sessions as sessions
import repair_continuation as journal


def consume(row, base, generation, execute):
    """호출자는 기존 인계 파일 잠금과 runtime lease를 소유한다."""
    from task_cancellation import requested
    key = row['task_id']
    owner = 'system' if row['system_ai'] else row['project_id']

    def stop(status, reason, response=''):
        from api_task_repair import cancel_child
        cancel_child(row, base)
        latest = journal.read(key, base) or row
        journal.save({**latest, 'status': status, 'reason': reason, 'response': response}, base)

    try:
        if row.get('resume_blocked'):
            stop('blocked', row['resume_blocked'])
            return
        if journal.cancelled(row, base) or any(requested(owner, task) for task in
                (row['original_task_id'], row.get('execution_task_id'))):
            stop('cancelled', '사용자가 원래 업무를 취소했습니다.')
            return
        saved = row['budget']
        if (saved.get('deadline_at') is not None and saved['deadline_at'] <= time.time()
                or saved.get('hard_token_limit') is not None
                and saved['input'] + saved['output'] >= saved['hard_token_limit']):
            stop('blocked', '원래 업무의 시간·관측 토큰 한도가 끝났습니다.')
            return
        if row.get('attempt', 0) >= 3 and not row.get('repair_child'):
            stop('blocked', '부품 부모 업무가 프로세스 교체 후 3회 중단됐습니다. 증거를 보존했습니다.')
            return
        from task_repair import advance_parent
        from repair_policy import completion
        row = advance_parent(row, base, completion)
        if row is None:
            return
        b = sessions.Binding(**row['last_conversation'])
        original = sessions.Binding(**row['conversation'])
        if (b.db_path, b.owner, b.session_id) != (original.db_path, original.owner, original.session_id):
            raise ValueError('원래 대화와 재개 대화의 소유권이 다릅니다')
        if not Path(b.db_path).is_file():
            raise ValueError('원래 대화 저장소가 없습니다')
        table = 'conversations' if row['system_ai'] else 'messages'
        store = sessions.SessionStore(b.db_path, table, b.owner, create_legacy=False)
        with sessions.connection(b.db_path) as conn:
            store.require(conn, b.session_id)
            last = conn.execute('SELECT id,state FROM conversation_turns WHERE session_id=? '
                                'ORDER BY started_at DESC,id DESC LIMIT 1', (b.session_id,)).fetchone()
            if not last or last['id'] != b.turn_id or last['state'] == 'cancelled':
                stop('blocked', '원래 대화에 새 요청·취소가 있습니다. 이전 업무를 자동 재개하지 않습니다.')
                return
            events = [json.loads(r[0]) for r in conn.execute(
                'SELECT payload FROM conversation_events WHERE session_id=? AND turn_id=? ORDER BY id',
                (b.session_id, b.turn_id))]
        finished = [e for e in events if e.get('type') == 'handoff.finished' and e.get('success')]
        if finished and not row.get('returning_from_repair'):
            stop('completed', '중단 전에 실행 종료 영수증이 있습니다. 도구를 재실행하지 않습니다.',
                 finished[-1].get('response', ''))
            return
        if last['state'] == 'running':
            return  # 같은 프로세스의 살아 있는 대화. 다음 ACTIVE 스캔에서 다시 확인한다.
        # 같은 원장의 실행 키를 유지해 예산·취소를 공유하고 새 대화 턴만 연다.
        resume_task = row.get('resume_task_id') or ('component-resume-' + key.removeprefix('component-parent-'))
        bound = store.begin(b.session_id)
        row.update(status='running', generation=generation, process=sessions._PROCESS, resume_task_id=resume_task,
                   execution_task_id=resume_task, attempt=row.get('attempt', 0) + (0 if row.get('returning_from_repair') else 1),
                   resume_conversation=asdict(bound), last_conversation=asdict(bound))
        row.pop('execution_error', None)
        row.pop('returning_from_repair', None)
        journal.save(row, base)
        error = None
        try:
            with sessions.scope(bound), journal.resuming(row):
                sessions.bind_task(resume_task)
                answer = execute(row)
            latest = journal.read(key, base) or row
            if latest.get('status') == 'running':
                journal.save({**latest, 'status': 'cancelled' if answer.get('cancelled') else 'blocked' if answer.get('error') else 'completed',
                              'response': answer.get('response', ''), 'evaluation': answer.get('evaluation') or {}}, base)
            _settle_tasks(row, journal.read(key, base))
        except BaseException as exc:
            error = str(exc) or type(exc).__name__
            raise
        finally:
            store.finish(bound, 'failed' if error else 'completed', error=error)
    except Exception as exc:
        from logging_utils import mask_secrets
        stop('blocked', mask_secrets(str(exc)))


def _settle_tasks(row, latest):
    """모델 응답의 실행 종료를 원래 task 조회에도 연결한다. 목표 판정은 별도 보존한다."""
    with sessions.connection(row['conversation']['db_path']) as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks'").fetchone():
            return
        for task in {row['original_task_id'], row['execution_task_id']}:
            conn.execute('UPDATE tasks SET status=?,result=?,completed_at=CURRENT_TIMESTAMP WHERE task_id=?',
                         (latest['status'], latest.get('response', '')[:500], task))
