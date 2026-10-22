"""Task-scoped sessions in the existing conversation DB; no worker lifetime DB.

The tasks table owns dispatch, FIFO and request idempotency. Session events own
configuration and history. Active turns own exclusive use of a session.
"""
import hashlib
import json
import sqlite3
import uuid

import conversation_sessions as sessions

TERMINAL = ('completed', 'failed', 'cancelled')
PROCESS = sessions._PROCESS


def migrate(conn):
    # Schema discovery and ALTER must be one writer transaction: the first
    # parallel delegates may all arrive before any worker column exists.
    if not conn.in_transaction:
        conn.execute('BEGIN IMMEDIATE')
    columns = {r[1] for r in conn.execute('PRAGMA table_info(tasks)')}
    for name in ('worker_session', 'worker_root', 'worker_scope', 'worker_request',
                 'worker_fingerprint', 'worker_process', 'worker_payload'):
        if name not in columns:
            conn.execute(f'ALTER TABLE tasks ADD COLUMN {name} TEXT')
    conn.execute('''CREATE UNIQUE INDEX IF NOT EXISTS worker_request_once
                    ON tasks(worker_scope,worker_request) WHERE worker_request IS NOT NULL''')
    conn.execute('CREATE INDEX IF NOT EXISTS worker_session_queue ON tasks(worker_session,status)')
    conn.execute('CREATE INDEX IF NOT EXISTS worker_root_tree ON tasks(worker_root,parent_task_id)')


def event(conn, sid, kind, payload, turn=''):
    conn.execute('INSERT INTO conversation_events(session_id,turn_id,created_at,payload) VALUES (?,?,?,?)',
                 (sid, turn, sessions.now(), json.dumps({'type': kind, **payload}, ensure_ascii=False)))


def metadata(conn, sid):
    row = conn.execute('''SELECT payload FROM conversation_events WHERE session_id=?
                          AND json_extract(payload,'$.type')='worker.created' ORDER BY id LIMIT 1''', (sid,)).fetchone()
    return json.loads(row[0]) if row else None


def accept(path, parent, request_id, message, payload, *, session_id=None):
    fingerprint = hashlib.sha256(json.dumps([message, {k: v for k, v in payload.items() if k != 'limits'}, session_id], sort_keys=True,
                                           ensure_ascii=False).encode()).hexdigest()
    with sessions.connection(path) as conn:
        migrate(conn)
        conn.commit()
        conn.execute('BEGIN IMMEDIATE')
        parent_row = conn.execute('SELECT * FROM tasks WHERE task_id=?', (parent,)).fetchone()
        # Scope is the concrete requesting task; a later root can use a fresh id.
        prior = conn.execute('SELECT * FROM tasks WHERE worker_scope=? AND worker_request=?',
                             (parent, request_id)).fetchone()
        if prior:
            if prior['worker_fingerprint'] != fingerprint:
                raise ValueError('같은 request_id로 다른 위임을 접수할 수 없습니다')
            return dict(prior)
        if not parent_row or parent_row['status'] in TERMINAL:
            raise ValueError('살아 있는 부모 작업이 필요합니다')
        parent_row = dict(parent_row)
        root = parent_row.get('worker_root') or parent
        count = conn.execute('SELECT COUNT(*) FROM tasks WHERE worker_root=?', (root,)).fetchone()[0]
        depth = json.loads(parent_row.get('worker_payload') or '{}').get('depth', 0) + 1
        if count >= 32 or depth > 8:
            raise ValueError('위임 트리 생성 수(32) 또는 깊이(8) 한도를 넘었습니다')
        if session_id:
            saved = metadata(conn, session_id)
            if not saved or saved['controller'] != payload['controller']:
                raise ValueError('이 대화가 소유한 worker_ref가 아닙니다')
            if payload.get('workspace') != saved.get('workspace'):
                raise ValueError('후속 작업은 기존 작업 공간을 유지해야 합니다')
        else:
            session_id = uuid.uuid4().hex
            stamp = sessions.now()
            conn.execute('INSERT INTO conversation_sessions(id,owner,title,created_at,updated_at) VALUES (?,?,?,?,?)',
                         (session_id, 'worker:' + payload['controller'], message[:120], stamp, stamp))
            event(conn, session_id, 'worker.created', payload)
        payload = {**payload, 'depth': depth, 'envelope': {**payload['envelope'],
                   'chain': list(payload['envelope'].get('chain', [])) + ['worker:' + session_id]}}
        task = 'task_worker_' + uuid.uuid4().hex
        from episode_logger import trajectory_run_id
        conn.execute('''INSERT INTO tasks(task_id,requester,requester_channel,original_request,
            delegated_to,delegation_context,parent_task_id,run_id,parent_run_id,status,
            worker_session,worker_root,worker_scope,worker_request,worker_fingerprint,worker_payload)
            VALUES (?,?,?,?,?,?,?,?,?,'queued',?,?,?,?,?,?)''',
            (task, payload['actor'], 'task', message, session_id, '{}', parent,
             trajectory_run_id(task), parent_row.get('run_id') or trajectory_run_id(parent),
             session_id, root, parent, request_id, fingerprint, json.dumps(payload, ensure_ascii=False)))
        context = json.loads(parent_row.get('delegation_context') or '{}')
        context.setdefault('delegations', []).append({'child_task_id': task, 'delegated_to': session_id,
                                                      'scope': 'task', 'mode': 'async'})
        conn.execute('UPDATE tasks SET pending_delegations=COALESCE(pending_delegations,0)+1,delegation_context=? WHERE task_id=?',
                     (json.dumps(context, ensure_ascii=False), parent))
        conn.execute('INSERT INTO conversation_task_links VALUES (?,?,?)', (task, session_id, ''))
        event(conn, session_id, 'worker.dispatch_pending', {'task_id': task, 'parent_task_id': parent})
        return dict(conn.execute('SELECT * FROM tasks WHERE task_id=?', (task,)).fetchone())


def claim(path, sid):
    with sessions.connection(path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute("SELECT 1 FROM tasks WHERE worker_session=? AND status IN ('running','waiting_children')", (sid,)).fetchone():
            return None
        row = conn.execute("SELECT * FROM tasks WHERE worker_session=? AND status='queued' ORDER BY rowid LIMIT 1", (sid,)).fetchone()
        if not row:
            return None
        conn.execute("UPDATE tasks SET status='running',worker_process=? WHERE task_id=?", (PROCESS, row['task_id']))
        return dict(row)


def finish(path, task, state, result):
    with sessions.connection(path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM tasks WHERE task_id=?', (task,)).fetchone()
        if not row or row['status'] in (*TERMINAL, 'waiting_children'):
            # The model outcome is already sealed while children drain. A late
            # duplicate completion must not replace its result or terminal state.
            return
        live = conn.execute("SELECT 1 FROM tasks WHERE parent_task_id=? AND worker_session IS NOT NULL AND status NOT IN ('completed','failed','cancelled')", (task,)).fetchone()
        if live or (row['pending_delegations'] or 0) > 0:
            # The result is retained, but completion waits for owned children.
            conn.execute("UPDATE tasks SET status='waiting_children',result=? WHERE task_id=?", (result, task))
            event(conn, row['worker_session'], 'worker.awaiting_children', {'task_id': task, 'terminal_state': state})
            return
        _finish(conn, row, state, result)


def _finish(conn, row, state, result):
    conn.execute('UPDATE tasks SET status=?,result=?,completed_at=CURRENT_TIMESTAMP WHERE task_id=?',
                 (state, result, row['task_id']))
    outcome = {'task_id': row['task_id'], 'state': state}
    if state in ('failed', 'cancelled'):
        # Session history outlives prunable task rows. Keep the failure evidence
        # in the same transaction as completion, even without a model final.
        outcome['result'] = result
    event(conn, row['worker_session'], 'worker.finished', outcome)
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    parent = cursor.execute('SELECT * FROM tasks WHERE task_id=?', (row['parent_task_id'],)).fetchone()
    if not parent:
        return
    context = json.loads(parent['delegation_context'] or '{}')
    context.setdefault('responses', []).append({'child_task_id': row['task_id'], 'agent': row['delegated_to'],
                                              'result': result, 'state': state})
    conn.execute('UPDATE tasks SET pending_delegations=MAX(0,COALESCE(pending_delegations,0)-1),delegation_context=? WHERE task_id=?',
                 (json.dumps(context, ensure_ascii=False), parent['task_id']))
    settle_waiting(conn, parent['task_id'])


def settle_waiting(conn, task):
    """Finish a sealed parent only after both owned and resident replies arrive."""
    if 'worker_session' not in {r[1] for r in conn.execute('PRAGMA table_info(tasks)')}:
        return
    # Legacy connections can use tuple rows; select through an explicit cursor.
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    parent = cursor.execute('SELECT * FROM tasks WHERE task_id=?', (task,)).fetchone()
    if parent and parent['status'] == 'waiting_children' and not parent['pending_delegations']:
        if parent['worker_session']:
            terminal = conn.execute("SELECT payload FROM conversation_events WHERE session_id=? AND json_extract(payload,'$.type')='worker.awaiting_children' AND json_extract(payload,'$.task_id')=? ORDER BY id DESC LIMIT 1", (parent['worker_session'], parent['task_id'])).fetchone()
            _finish(conn, parent, json.loads(terminal[0])['terminal_state'] if terminal else 'completed', parent['result'])
        else:
            conn.execute("UPDATE tasks SET status='completed',completed_at=CURRENT_TIMESTAMP WHERE task_id=?", (parent['task_id'],))


def defer_completion(path, task, result):
    with sessions.connection(path) as conn:
        columns = {r[1] for r in conn.execute('PRAGMA table_info(tasks)')}
        if 'worker_session' not in columns:
            return False
        conn.execute('BEGIN IMMEDIATE')
        live = conn.execute("SELECT 1 FROM tasks WHERE parent_task_id=? AND worker_session IS NOT NULL AND status NOT IN ('completed','failed','cancelled')", (task,)).fetchone()
        owned = conn.execute("SELECT 1 FROM tasks WHERE parent_task_id=? AND worker_session IS NOT NULL", (task,)).fetchone()
        if not owned:
            return False
        pending = conn.execute('SELECT pending_delegations FROM tasks WHERE task_id=?', (task,)).fetchone()
        waiting = bool(live or (pending and pending[0]))
        conn.execute("UPDATE tasks SET status=?,result=?,completed_at=CASE WHEN ? THEN NULL ELSE CURRENT_TIMESTAMP END WHERE task_id=? AND status NOT IN ('completed','failed','cancelled')",
                     ('waiting_children' if waiting else 'completed', result, waiting, task))
        return True


def history(path, sid):
    with sessions.connection(path) as conn:
        tasks = [dict(row) for row in conn.execute('''
            SELECT t.task_id,t.status,t.result,t.original_request,t.worker_payload,l.turn_id
            FROM tasks t LEFT JOIN conversation_task_links l ON l.task_id=t.task_id
            WHERE t.worker_session=?''', (sid,))]
        outcomes = {row['task_id']: {k: row[k] for k in ('task_id', 'status', 'result')} for row in tasks}
        turns = {row['turn_id']: row for row in tasks if row['turn_id']}
        events = [(json.loads(r[0]), r[1]) for r in conn.execute(
            'SELECT payload,turn_id FROM conversation_events WHERE session_id=? ORDER BY id', (sid,))]
        delivery = {}
        for entry, _ in events:
            if entry.get('type', '').startswith('handoff.steer.'):
                for ident in entry.get('ids', []):
                    delivery[ident] = entry['type'].rsplit('.', 1)[-1]
        messages = []
        for entry, turn in events:
            if entry.get('type') == 'worker.history':
                messages.append(entry['message'])
                task = turns.get(turn)
                if (task and entry['message'].get('role') == 'user'
                        and entry['message'].get('content') == task['original_request']):
                    # Older workers logged only the request text. Recover their
                    # context from that exact task/turn without rewriting events.
                    context = json.loads(task['worker_payload'])['envelope'].get('context')
                    if context not in (None, '', {}, []):
                        messages.append({'role': 'assistant',
                                         'content': '[이전 위임자가 준 구조화 맥락] ' +
                                         json.dumps(context, ensure_ascii=False)})
            elif entry.get('type') == 'worker.finished':
                outcome = ({'task_id': entry['task_id'], 'status': entry['state'], 'result': entry['result']}
                           if 'result' in entry else outcomes.get(entry.get('task_id'), {}))
                if outcome.get('status') in ('failed', 'cancelled'):
                    # Providers can fail/raise without ever yielding a final
                    # message. The durable task outcome is still follow-up context,
                    # and is an observation rather than a new user instruction.
                    messages.append({'role': 'assistant',
                                     'content': '[이전 실행 종료] ' + json.dumps(
                                         outcome, ensure_ascii=False)})
            elif entry.get('type') == 'handoff.steer.accepted':
                source = entry.get('source', 'user')
                state = delivery.get(entry['id'], 'accepted')
                messages.append({'role': 'user' if source == 'user' else 'assistant',
                                 'content': f"[이전 실행 조향: 출처={source}, 처리={state}] " + entry['instruction']})
        # A resident delegate can finish after this session's model turn ended.
        # Its durable response is context for the next turn, not a new user order.
        for row in conn.execute('SELECT task_id,delegation_context FROM tasks WHERE worker_session=? ORDER BY rowid', (sid,)):
            for reply in json.loads(row['delegation_context'] or '{}').get('responses', []):
                messages.append({'role': 'assistant', 'content': '[이전 위임의 자식 응답] ' +
                                 json.dumps({'parent_task_id': row['task_id'], **reply}, ensure_ascii=False)})
        return messages


def recover(path):
    """Unstarted jobs can dispatch; interrupted effects are never auto-retried."""
    with sessions.connection(path) as conn:
        migrate(conn)
        rows = conn.execute("SELECT * FROM tasks WHERE worker_session IS NOT NULL AND status='running' AND worker_process!=?", (PROCESS,)).fetchall()
    for row in rows:
        finish(path, row['task_id'], 'failed', '실행 프로세스가 종료되었습니다. 세션 기록을 확인해 후속 위임하세요. 외부 효과는 자동 재실행하지 않았습니다.')
    with sessions.connection(path) as conn:
        return [r[0] for r in conn.execute("SELECT DISTINCT worker_session FROM tasks WHERE status='queued' AND worker_session IS NOT NULL")]


def cancel_owned(path, owner, parent):
    from task_cancellation import request
    with sessions.connection(path) as conn:
        if 'worker_session' not in {r[1] for r in conn.execute('PRAGMA table_info(tasks)')}:
            return
        children = conn.execute("SELECT task_id FROM tasks WHERE parent_task_id=? AND worker_session IS NOT NULL AND status NOT IN ('completed','failed','cancelled')", (parent,)).fetchall()
    for child in children:
        request(owner, child[0])
        cancel_owned(path, owner, child[0])


def cancellation_requested(path, owner, task):
    from task_cancellation import requested
    with sessions.connection(path) as conn:
        for _ in range(10):
            if requested(owner, task):
                return True
            row = conn.execute('SELECT parent_task_id,worker_session FROM tasks WHERE task_id=?', (task,)).fetchone()
            if not row or not row['worker_session']:
                return False
            task = row['parent_task_id']
    return True
