"""작업 항목·타이머·사건은 업무 변경과 같은 연결에서 저장한다."""
import json
import time

from common.record_contract import RecordError, dump, fail, resolve, keys
from record_store import uid, get_record


def task_change(conn, spec, env, defn, auth, roles, commit_id, pending):
    op = spec.get('op')
    if op == 'create':
        record = env.get(spec.get('record'))
        if not record or '_id' not in record:
            fail('validation', '작업 항목 대상 기록이 필요합니다.')
        config = resolve({k: v for k, v in spec.items() if k not in {'op', 'record', 'timeout_input'}}, env)
        if 'timeout_input' in spec:
            config['timeout_input'] = spec['timeout_input']
        pending.append((record, config))
        return True
    task_id = resolve(spec.get('id'), env)
    task = conn.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
    if not task or task['state'] != 'open':
        fail('conflict', '열린 작업 항목을 찾을 수 없습니다.')
    config = json.loads(task['body'])
    timer_cancel = op == 'cancel' and env.get('_task_guard') == task_id and config.get('timeout_command') == env['_command']
    if not timer_cancel and task['revision'] != resolve(spec.get('revision'), env):
        fail('conflict', '작업 항목이 변경되었습니다.')
    target = get_record(conn, task['collection'], task['record_id'])
    target_alias = spec.get('record')
    read_aliases = defn['commands'][env['_command']].get('read', {})
    candidates = [env.get(target_alias)] if target_alias else [env.get(k) for k in read_aliases]
    if not any(isinstance(r, dict) and r.get('_collection') == task['collection'] and
               r.get('_id') == task['record_id'] and r.get('_revision') == task['target_revision']
               for r in candidates):
        fail('conflict', '작업 항목과 명령이 읽은 검토 대상이 다릅니다.')
    if target['_revision'] != task['target_revision']:
        fail('conflict', '검토 대상 버전이 변경되었습니다.')
    eligible = auth.subject in config.get('subjects', []) or bool(set(roles) & set(config.get('roles', [])))
    if not timer_cancel and (not eligible or config.get('assignee') not in (None, auth.subject)):
        fail('forbidden', '이 작업 항목의 담당자가 아닙니다.')
    if op == 'claim':
        config['assignee'] = auth.subject
        state = 'open'
        complete = True
    elif op == 'complete':
        if config.get('command') and config['command'] != env['_command']:
            fail('forbidden', '작업 항목에 지정된 명령을 사용하세요.')
        if config.get('deny_self', True) and target['_created_by'] == auth.subject:
            fail('forbidden', '자신이 작성한 기록은 승인할 수 없습니다.')
        votes = config.setdefault('votes', [])
        if any(v['subject'] == auth.subject for v in votes):
            fail('conflict', '이미 처리한 승인입니다.')
        votes.append({'subject': auth.subject, 'roles': roles, 'commit_id': commit_id})
        complete = len(votes) >= config.get('quorum', 1) and set(config.get('required_roles', [])) <= {r for v in votes for r in v['roles']}
        state = 'completed' if complete else 'open'
    elif op == 'cancel':
        state, complete = 'cancelled', True
    else:
        fail('validation', 'task op는 create/claim/complete/cancel입니다.')
    conn.execute('UPDATE tasks SET body=?, state=?, revision=revision+1 WHERE id=?', (dump(config), state, task_id))
    task_history(conn, commit_id, task_id, task['collection'], task['record_id'], task['target_revision'],
                 {'operation': op, 'state': state, 'revision': task['revision'] + 1,
                  'assignee': config.get('assignee'), 'approvals': len(config.get('votes', []))})
    return complete


def task_history(conn, commit_id, ident, collection, record_id, target_revision, detail):
    conn.execute('INSERT INTO task_history(commit_id,task_id,collection,record_id,target_revision,body) VALUES (?,?,?,?,?,?)',
                 (commit_id, ident, collection, record_id, target_revision, dump(detail)))


def persist_tasks(conn, pending, env, auth, commit_id, definition_revision):
    for record, config in pending:
        keys(config, {'roles', 'subjects', 'assignee', 'command', 'quorum', 'required_roles',
                      'deny_self', 'label', 'due_seconds', 'timeout_command', 'timeout_input'}, 'task')
        if not config.get('roles') and not config.get('subjects'):
            fail('validation', '작업 항목에는 담당 역할 또는 주체가 필요합니다.')
        if type(config.get('quorum', 1)) is not int or not 1 <= config.get('quorum', 1) <= 100:
            fail('validation', '승인 인원은 1~100입니다.')
        ident = uid('task')
        config['created_by'] = auth.subject
        config['due_at'] = time.time() + config['due_seconds'] if config.get('due_seconds') is not None else None
        conn.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?)',
                     (ident, record['_collection'], record['_id'], record['_revision'], 1, dump(config), 'open', commit_id))
        task_history(conn, commit_id, ident, record['_collection'], record['_id'], record['_revision'],
                     {'operation': 'create', 'state': 'open', 'revision': 1, 'assignee': config.get('assignee'), 'approvals': 0})
        if config.get('timeout_command') and config['due_at'] is not None:
            context = {**env, 'task': {'id': ident, 'revision': 1}}
            payload = {'command': config['timeout_command'], 'input': resolve(config.get('timeout_input', {}), context),
                       'expected': [{'collection': record['_collection'], 'id': record['_id'], 'revision': record['_revision']}],
                       'task_id': ident, 'target_revision': record['_revision']}
            enqueue(conn, uid('timer'), 'command', payload, auth.subject, definition_revision, config['due_at'])


def enqueue(conn, ident, kind, payload, subject, revision, due=None):
    conn.execute('INSERT OR IGNORE INTO deliveries(id,kind,body,state,due,lease_until,subject,definition_revision) VALUES (?,?,?,?,?,?,?,?)',
                 (ident, kind, dump(payload), 'pending', due or time.time(), 0, subject, revision))


def emit_events(conn, specs, env, defn, auth, commit_id, revision):
    effects = []
    for spec in specs:
        keys(spec, {'event', 'record', 'payload', 'effect'}, 'emit')
        record = env.get(spec.get('record'), {})
        event_id = uid('event')
        payload = resolve(spec.get('payload', {}), env)
        event = {'event': spec.get('event'), 'record': record, 'payload': payload}
        conn.execute('INSERT INTO events VALUES (?,?,?,?)', (event_id, commit_id, dump(event), time.time()))
        effect_name = spec.get('effect')
        if effect_name:
            config = defn.get('effects', {}).get(effect_name)
            if not config:
                fail('validation', '정의되지 않은 외부 처리입니다.')
            effect_id = uid('effect')
            enqueue(conn, effect_id, 'effect', {'config': config, 'payload': payload,
                    'origin_command': env['_command'], 'effect_name': effect_name,
                    'authorization': {k: v for k, v in env.items() if k != 'actor'}}, auth.subject, revision)
            effects.append({'id': effect_id, 'status': 'pending'})
        for index, subscription in enumerate(defn.get('subscriptions', {}).get(spec.get('event'), [])):
            ctx = {**env, 'event': event}
            request = {'command': subscription['command'], 'input': resolve(subscription.get('input', {}), ctx),
                       'expected': resolve(subscription.get('expected', []), ctx)}
            enqueue(conn, event_id + '_' + str(index), 'command', request, auth.subject, revision)
    return effects


def effect_followup(conn, ident, payload, result, subject, revision, state):
    """자동 결과와 사람의 대사가 동일한 후속 명령을 한 번 등록한다."""
    if state not in {'succeeded', 'failed'}:
        return
    config = payload['config']
    prefix = 'success' if state == 'succeeded' else 'failure'
    if config.get(prefix + '_command'):
        request = {'command': config[prefix + '_command'], 'input': {}, 'expected': []}
        try:
            request['input'] = resolve(config.get(prefix + '_input', {}), {'result': result, 'payload': payload['payload']})
        except RecordError as exc:
            # 후속 값 계산 실패가 이미 확인한 원격 결과를 되돌리면 재발송 위험이 생긴다.
            enqueue(conn, ident + '_result', 'command', request, subject, revision)
            conn.execute("UPDATE deliveries SET state='blocked',result=? WHERE id=? AND state='pending'",
                         (dump(exc.result()), ident + '_result'))
            return
        enqueue(conn, ident + '_result', 'command', request, subject, revision)
