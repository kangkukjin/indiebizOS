"""한정 구현 수리의 기존 실행 표면 연결. 새 스케줄러·새 수리 실행기는 만들지 않는다."""
from dataclasses import asdict

import conversation_sessions as sessions
import repair_continuation as journal
import task_repair


def ready(row, base=None):
    """부모 구간이 종료된 뒤에만 같은 대화의 자식 구간을 연다."""
    parent = task_repair.parent_of(row, base)
    b = parent['last_conversation']
    with sessions.connection(b['db_path']) as conn:
        turn = conn.execute('SELECT state FROM conversation_turns WHERE id=?', (b['turn_id'],)).fetchone()
    return bool(turn and turn[0] != 'running')


def execute(row, callback):
    if not ready(row):
        raise RuntimeError('원래 업무의 실행 구간이 아직 끝나지 않았습니다')
    parent = task_repair.parent_of(row)
    b = sessions.Binding(**parent['last_conversation'])
    store = sessions.SessionStore(b.db_path, 'conversations' if parent['system_ai'] else 'messages',
                                  b.owner, create_legacy=False)
    bound = store.begin(b.session_id)
    parent['last_conversation'] = asdict(bound)
    journal.save(parent)
    latest = journal.read(row['task_id']) or row
    journal.save({**latest, 'process': sessions._PROCESS})
    error = None
    try:
        with sessions.scope(bound):
            sessions.bind_task(row['resume_task_id'])
            return callback(row)
    except BaseException as exc:
        error = str(exc) or type(exc).__name__
        raise
    finally:
        store.finish(bound, 'failed' if error else 'completed', error=error)


def cancel_child(parent, base):
    key = parent.get('repair_child')
    if key:
        from restart_protocol import atomic_json
        atomic_json(journal.directory(base) / (journal.key(key) + '.cancel'), {'cancelled': True})
