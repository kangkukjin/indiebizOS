"""선언된 업무 명령의 원자 확정. 외부 호출·사람 대기는 하지 않는다."""
import copy
import json
import time

from common.record_contract import (digest, dump, fail, resolve, expression,
                                    validate_values, keys, name)
from common.value_semantics import values_equal
from record_policy import check_auth, roles, allowed, can_read, artifact_ids, can_use_artifact
from record_store import (transaction, definition, meta, uid, get_record, body, decode_record)


def request_hash(args):
    return digest({k: args.get(k) for k in ('command', 'definition_revision', 'input', 'expected', 'reason')})


def apply(space, args, auth, root=None, *, task_guard=None):
    check_auth(auth, space, args.get('command', ''))
    name(args.get('request_id'))
    if args['request_id'].startswith('admin_'):
        fail('validation', 'admin_ 요청 접두는 관리 작업 전용입니다.')
    if len(dump(args).encode()) > 262144:
        fail('validation', '명령 입력은 256KiB 이하여야 합니다.')
    with transaction(space, root, write=True) as conn:
        member_roles = roles(conn, auth)
        active, active_rev = definition(conn)
        previous = conn.execute('SELECT * FROM requests WHERE subject=? AND request_id=?',
                                (auth.subject, args['request_id'])).fetchone()
        fingerprint = request_hash(args)
        if previous:
            if previous['hash'] != fingerprint:
                fail('duplicate_key', '같은 요청 ID에 다른 내용이 전달되었습니다.')
            return visible_receipt(conn, json.loads(previous['receipt']), active, auth, member_roles, replayed=True)
        if meta(conn, 'paused') or meta(conn, 'recovery_required'):
            fail('forbidden', '업무 공간이 중지되었거나 복구 확인이 필요합니다.')
        if task_guard:
            task = conn.execute('SELECT state,target_revision FROM tasks WHERE id=?', (task_guard['task_id'],)).fetchone()
            if not task or task['state'] != 'open' or task['target_revision'] != task_guard['target_revision']:
                fail('conflict', '만료 처리 대상 작업이 이미 변경되었습니다.')
        rev = args.get('definition_revision')
        if type(rev) is not int:
            fail('definition_changed', '업무 정의 버전이 필요합니다.')
        contract, _ = definition(conn, rev)
        command = contract.get('commands', {}).get(args.get('command'))
        current_command = active.get('commands', {}).get(args.get('command'))
        if not command:
            fail('not_found', '업무 명령을 찾을 수 없습니다.')
        if not current_command:
            fail('forbidden', '현재 정책에서 중지한 명령입니다.')
        inputs = validate_values(args.get('input', {}), command.get('input', {}), defaults=True)
        if any(c.get('reason_required') for c in (command, current_command)) and not str(args.get('reason', '')).strip():
            fail('validation', '처리 사유가 필요합니다.')
        env = {'input': inputs, 'actor': {'subject': auth.subject, 'roles': member_roles}, 'now': time.time(), '_command': args['command']}
        if task_guard:
            env['_task_guard'] = task_guard['task_id']
        if not all(allowed({k: v for k, v in policy.items() if k not in {'where', 'deny_self'}}, auth, member_roles, env=env)
                   for policy in (command['allow'], current_command['allow'])):
            fail('forbidden', '이 명령을 실행할 권한이 없습니다.')
        if any(c.get('confirmation') == 'human' for c in (command, current_command)):
            row = conn.execute('SELECT * FROM confirmations WHERE token=?', (args.get('confirmation', ''),)).fetchone()
            if not row or row['subject'] != auth.subject or row['hash'] != fingerprint or row['used'] or row['expires'] < time.time():
                fail('forbidden', '현재 대상과 입력에 대한 사람의 확인이 필요합니다.')
            conn.execute('UPDATE confirmations SET used=1 WHERE token=?', (row['token'],))
        expected = args.get('expected', [])
        if not isinstance(expected, list):
            fail('validation', 'expected는 대상 버전 목록이어야 합니다.')
        pinned = False
        for read_alias, spec in command.get('read', {}).items():
            record = get_record(conn, spec['collection'], resolve(spec['id'], env))
            internal = all(spec['collection'] in c.get('internal_access', []) for c in (command, current_command))
            if record['_archived'] or not internal and not can_read(active, spec['collection'], record, auth, member_roles):
                fail('not_found', '기록을 찾을 수 없습니다.')
            if spec['version'] == 'observed':
                versions = [v.get('revision') for v in expected if isinstance(v, dict) and
                            v.get('collection') == spec['collection'] and v.get('id') == record['_id']]
                if len(versions) != 1 or type(versions[0]) is not int or versions[0] != record['_revision']:
                    fail('conflict', '기록이 변경되었습니다. 다시 읽고 판단하세요.')
                if contract['collections'][spec['collection']].get('process'):
                    if record['_definition_revision'] != rev:
                        fail('definition_changed', '업무 인스턴스에 고정된 정의 버전을 사용하세요.')
                    pinned = True
            for prior in env.values():
                if isinstance(prior, dict) and prior.get('_id') == record['_id'] and prior.get('_collection') == record['_collection']:
                    record = prior
                    break
            env[read_alias] = record
        primary = next((env[k] for k in command.get('read', {})), None)
        if rev != active_rev and not pinned:
            fail('definition_changed', '새 업무에는 최신 정의를 사용하세요.')
        if not all(allowed(policy, auth, member_roles, record=primary, env=env)
                   for policy in (command['allow'], current_command['allow'])):
            fail('forbidden', '이 명령의 관계·상태 권한을 충족하지 않습니다.')
        for condition in command.get('require', []):
            if resolve(condition, env) is not True:
                fail('rule_failed', '업무 조건을 충족하지 않습니다.')
        commit_id = uid('commit')
        conn.execute('INSERT INTO commits VALUES (?,?,?,?,?,?,?)',
                     (commit_id, auth.subject, auth.executor, args['command'], str(args.get('reason', ''))[:4000], rev, time.time()))
        changed = {}
        new_tasks = []
        complete = True
        for step in command.get('change', []):
            op, spec = next(iter(step.items()))
            if op == 'task':
                if spec.get('op') == 'complete' and changed:
                    fail('validation', '승인 작업 소비는 기록 변경보다 먼저 선언해야 합니다.')
                from record_tasks import task_change
                if not task_change(conn, spec, env, contract, auth, member_roles, commit_id, new_tasks):
                    complete = False
                    break  # 다인 승인 중간 표만 저장한다. quorum 도달 전 후속 변경 없음.
                continue
            mutate(conn, op, spec, env, contract, args['command'], auth, rev, changed, new_tasks)
        validate_final(conn, active, changed, auth)
        for key, (before, record) in changed.items():
            collection, ident = key
            record['_revision'] = (before['_revision'] if before else 0) + 1
            record['_definition_revision'] = rev
            conn.execute('INSERT OR REPLACE INTO records VALUES (?,?,?,?,?,?,?,?)',
                         (collection, ident, record['_revision'], rev, dump(body(record)), record['_created_by'], auth.subject, int(record['_archived'])))
            conn.execute('INSERT INTO revisions(commit_id,collection,id,revision,before_body,after_body) VALUES (?,?,?,?,?,?)',
                         (commit_id, collection, ident, record['_revision'], dump(before) if before else None, dump(record)))
        from record_tasks import persist_tasks, emit_events
        persist_tasks(conn, new_tasks, env, auth, commit_id, rev)
        effects = emit_events(conn, command.get('emit', []) if complete else [], env, contract, auth, commit_id, rev)
        receipt = {'success': True, 'status': 'committed', 'commit_id': commit_id,
                   'request_id': args['request_id'], 'replayed': False,
                   'changed': [{'collection': c, 'id': i, 'revision': r['_revision']} for (c, i), (_, r) in changed.items()],
                   'effects': effects}
        conn.execute('INSERT INTO requests VALUES (?,?,?,?)', (auth.subject, args['request_id'], fingerprint, dump(receipt)))
        return visible_receipt(conn, receipt, active, auth, member_roles)


def visible_receipt(conn, receipt, defn, auth, member_roles, replayed=False):
    result = copy.deepcopy(receipt)
    result['replayed'] = replayed
    visible = []
    for change in result['changed']:
        row = get_record(conn, change['collection'], change['id'])
        if can_read(defn, change['collection'], row, auth, member_roles):
            visible.append(change)
    result['changed'] = visible
    for effect in result.get('effects', []):
        row = conn.execute('SELECT state FROM deliveries WHERE id=?', (effect['id'],)).fetchone()
        effect['status'] = row[0] if row else 'unknown'
    return result


def mutate(conn, op, spec, env, defn, command, auth, revision, changed, new_tasks):
    if op == 'create':
        keys(spec, {'collection', 'as', 'values'}, 'create')
        collection = spec.get('collection')
        if collection not in defn['collections']:
            fail('validation', '없는 기록 묶음입니다.')
        alias = name(spec.get('as'))
        if alias in env:
            fail('validation', '이미 사용한 기록 별칭입니다.')
        payload = resolve(spec.get('values', {}), env)
        if not isinstance(payload, dict):
            fail('validation', '생성 값은 객체여야 합니다.')
        process = defn['processes'][defn['collections'][collection]['process']] if defn['collections'][collection].get('process') else None
        if process:
            field = process.get('field', 'status')
            if field in payload and payload[field] != process['initial']:
                fail('validation', '초기 상태를 우회할 수 없습니다.')
            payload[field] = process['initial']
        payload = validate_values(payload, defn['collections'][collection]['fields'],
                                  additional=defn['collections'][collection].get('additional', False), defaults=True)
        record = {**payload, '_id': uid('r'), '_collection': collection, '_revision': 0,
                  '_definition_revision': revision, '_created_by': auth.subject, '_updated_by': auth.subject, '_archived': False}
        env[alias] = record
        changed[(collection, record['_id'])] = (None, record)
    else:
        record = env.get(spec.get('record'))
        if not isinstance(record, dict) or '_id' not in record:
            fail('validation', '변경 대상은 읽거나 생성한 기록 별칭이어야 합니다.')
        collection = record['_collection']
        key = (collection, record['_id'])
        changed.setdefault(key, (copy.deepcopy(record), record))
        process_name = defn['collections'][collection].get('process')
        process = defn.get('processes', {}).get(process_name, {})
        state_field = process.get('field', 'status')
        if op == 'patch':
            keys(spec, {'record', 'set'}, 'patch')
            patch = resolve(spec.get('set', {}), env)
            if not isinstance(patch, dict) or any(k.startswith('_') for k in patch) or process and state_field in patch:
                fail('validation', '상태·시스템 필드 직접 수정은 허용하지 않습니다.')
            record.update(patch)
        elif op == 'archive':
            keys(spec, {'record'}, 'archive')
            record['_archived'] = True
        elif op == 'transition':
            keys(spec, {'record', 'from', 'to'}, 'transition')
            edge = process.get('transitions', {}).get(command)
            if not edge or edge.get('from') != spec.get('from') or edge.get('to') != spec.get('to') or record.get(state_field) != spec['from']:
                fail('conflict', '현재 상태에서 허용되지 않는 전이입니다.')
            record[state_field] = spec['to']
            if edge.get('task'):
                new_tasks.append((record, copy.deepcopy(edge['task'])))
        else:
            fail('validation', '지원하지 않는 변경입니다.')
        record['_updated_by'] = auth.subject
    if len(changed) > 100:
        fail('validation', '한 명령은 100개 기록까지 변경할 수 있습니다.')


def validate_final(conn, defn, changed, auth):
    """최종 이미지 전체의 고유성·참조·불변식. 중간 SQL 상태를 검증하지 않는다."""
    records = {}
    for row in conn.execute('SELECT * FROM records LIMIT 1001'):
        records[(row['collection'], row['id'])] = decode_record(row)
    if len(records) > 1000:
        fail('validation', '현재 공간의 확정 검사 상한(1000행)을 넘었습니다.')
    records.update({k: r for k, (_, r) in changed.items()})
    if len(records) > 1000:
        fail('validation', '공간당 1000행 상한을 넘었습니다.')
    uniques = {}
    for key, record in records.items():
        if record['_archived']:
            continue
        collection = key[0]
        spec = defn['collections'][collection]
        payload = validate_values(body(record), spec['fields'], additional=spec.get('additional', False))
        if spec.get('process'):
            process = defn['processes'][spec['process']]
            states = {process['initial']} | {e[k] for e in process['transitions'].values() for k in ('from', 'to')}
            if payload.get(process.get('field', 'status')) not in states:
                fail('rule_failed', '정의에 없는 업무 상태입니다.')
        if key in changed:
            before = changed[key][0] or {}
            for ident in artifact_ids(record, spec['fields']) - artifact_ids(before, spec['fields']):
                if not can_use_artifact(conn, ident, defn, auth, roles(conn, auth)):
                    fail('not_found', '사용할 수 있는 첨부를 찾을 수 없습니다.')
        for invariant in spec.get('invariants', []):
            if expression(invariant, {'record': record}) is not True:
                fail('rule_failed', '기록 불변식을 충족하지 않습니다.')
        for unique in spec.get('unique', []):
            value = [payload.get(field) for field in unique]
            if any(v is None for v in value):
                fail('validation', '고유 키에는 null을 사용할 수 없습니다.')
            bucket = uniques.setdefault((collection, tuple(unique)), [])
            if any(values_equal(value, old) for old in bucket):
                fail('rule_failed', '이미 사용된 고유 값입니다.')
            bucket.append(value)
        def refs(value, field):
            if value is None:
                return
            if field['type'] == 'record_ref':
                target = records.get((field['collection'], value))
                if not target or target['_archived']:
                    fail('rule_failed', '참조 기록이 없거나 보관되었습니다.')
            elif field['type'] == 'artifact_ref':
                if not conn.execute('SELECT 1 FROM artifacts WHERE id=?', (value,)).fetchone():
                    fail('rule_failed', '첨부를 먼저 반입하세요.')
            elif field['type'] == 'array':
                for item in value:
                    refs(item, field['items'])
            elif field['type'] == 'object':
                for k, s in field.get('fields', {}).items():
                    if k in value:
                        refs(value[k], s)
        for field, field_spec in spec['fields'].items():
            if field in payload:
                refs(payload[field], field_spec)
