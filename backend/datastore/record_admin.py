"""공간 관리 변경도 버전과 요청 영수증으로 보호한다."""
import json
import time

from common.record_contract import validate_definition, dump, digest, fail, name, keys, resolve
from record_policy import require_owner, roles
from record_store import transaction, definition, meta, put_meta, decode_record, uid, body


def administer(space, operation, args, auth, root=None):
    require_owner(auth)
    if not str(args.get('reason', '')).strip():
        fail('validation', '관리 변경 사유가 필요합니다.')
    name(args.get('request_id'))
    fingerprint = digest({'operation': operation, 'args': args})
    with transaction(space, root, write=True) as conn:
        roles(conn, auth)
        request_id = 'admin_' + args['request_id']
        prior = conn.execute('SELECT * FROM requests WHERE subject=? AND request_id=?', (auth.subject, request_id)).fetchone()
        if prior:
            if prior['hash'] != fingerprint:
                fail('duplicate_key', '같은 관리 요청 ID에 다른 내용입니다.')
            return json.loads(prior['receipt'])
        revision = meta(conn, 'admin_revision')
        if args.get('expected_revision') != revision:
            fail('conflict', '관리 설정이 변경되었습니다.')
        if operation in {'publish', 'migrate'}:
            value = validate_definition(args.get('definition'))
            from record_commands import validate_final
            # 기존 데이터가 새 계약을 만족하지 않으면 원자적으로 거절한다.
            existing, _ = definition(conn)
            if set(existing['collections']) - set(value['collections']):
                fail('validation', '기존 기록 묶음 제거는 지원하지 않습니다.')
            new_revision = meta(conn, 'active_revision') + 1
            if operation == 'migrate':
                migrate(conn, value, args.get('transforms', {}), new_revision, args['reason'], auth)
            else:
                validate_final(conn, value, {}, auth)
            conn.execute('INSERT INTO definitions VALUES (?,?)', (new_revision, dump(value)))
            put_meta(conn, 'active_revision', new_revision)
        elif operation == 'membership':
            subject = args.get('subject', '')
            member_roles = args.get('roles')
            if not (subject == 'owner' or subject.startswith('neighbor:') and len(subject) > 9) or not isinstance(member_roles, list) or any(not isinstance(r, str) for r in member_roles):
                fail('validation', '업무 주체와 역할 목록을 확인하세요.')
            if subject == 'owner' and 'admin' not in member_roles:
                fail('validation', '공간 관리자를 제거할 수 없습니다.')
            if member_roles:
                conn.execute('INSERT INTO memberships VALUES (?,?,1) ON CONFLICT(subject) DO UPDATE SET roles=excluded.roles,revision=memberships.revision+1', (subject, dump(member_roles)))
            else:
                conn.execute('DELETE FROM memberships WHERE subject=?', (subject,))
            put_meta(conn, 'access_revision', meta(conn, 'access_revision') + 1)
        elif operation == 'pause':
            if type(args.get('paused')) is not bool:
                fail('validation', 'paused 불리언이 필요합니다.')
            put_meta(conn, 'paused', args['paused'])
        elif operation == 'reconcile':
            ident, outcome = args.get('id'), args.get('outcome')
            if outcome not in {'succeeded', 'failed', 'pending', 'cancelled'}:
                fail('validation', '대사 결과 상태를 확인하세요.')
            row = conn.execute('SELECT * FROM deliveries WHERE id=?', (ident,)).fetchone()
            if not row or row['state'] == 'leased':
                fail('conflict', '진행 중 처리는 대사할 수 없습니다.')
            if row['state'] in {'succeeded', 'failed', 'cancelled'}:
                fail('conflict', '종결된 처리는 다시 보내지 않습니다. 새 보상 명령을 사용하세요.')
            if not str(args.get('evidence', '')).strip():
                fail('validation', '대사한 결과의 근거가 필요합니다.')
            conn.execute('UPDATE deliveries SET state=?,result=?,lease_until=0 WHERE id=?', (outcome, dump({'reason': args['reason'], 'evidence': args.get('evidence', '')}), ident))
            if row['kind'] == 'effect':
                from record_tasks import effect_followup
                effect_followup(conn, ident, json.loads(row['body']), {'status': outcome, 'evidence': args['evidence']},
                                row['subject'], row['definition_revision'], outcome)
        elif operation == 'recovery_complete':
            if conn.execute("SELECT 1 FROM deliveries WHERE state IN ('unknown','leased') LIMIT 1").fetchone():
                fail('conflict', '결과 불명확한 외부 처리를 먼저 대사하세요.')
            put_meta(conn, 'recovery_required', False)
        else:
            fail('validation', '지원하지 않는 관리 명령입니다.')
        put_meta(conn, 'admin_revision', revision + 1)
        conn.execute('INSERT INTO admin_log(operation,subject,reason,body,at) VALUES (?,?,?,?,?)',
                     (operation, auth.subject, args['reason'], dump(args), time.time()))
        result = {'success': True, 'admin_revision': revision + 1, 'definition_revision': meta(conn, 'active_revision')}
        conn.execute('INSERT INTO requests VALUES (?,?,?,?)', (auth.subject, request_id, fingerprint, dump(result)))
        return result


def migrate(conn, defn, transforms, revision, reason, auth):
    """명시적으로 멈춘 공간의 데이터와 정의를 한 확정으로 이전한다."""
    if not meta(conn, 'paused') or meta(conn, 'recovery_required'):
        fail('conflict', '복구가 끝난 공간을 먼저 중지하세요.')
    if conn.execute("SELECT 1 FROM tasks WHERE state='open' LIMIT 1").fetchone():
        fail('conflict', '열린 검토 작업을 먼저 종결하세요.')
    if conn.execute("SELECT 1 FROM deliveries WHERE state NOT IN ('succeeded','failed','cancelled') LIMIT 1").fetchone():
        fail('conflict', '대기·미확인 후속 처리를 먼저 종결하세요.')
    keys(transforms, defn['collections'], 'transforms')
    import copy
    from record_commands import validate_final
    changed = {}
    for row in conn.execute('SELECT * FROM records'):
        before = decode_record(row)
        record = copy.deepcopy(before)
        transform = transforms.get(row['collection'], {})
        keys(transform, {'set', 'drop'}, 'transform')
        patch = resolve(transform.get('set', {}), {'record': before})
        drop = transform.get('drop', [])
        if not isinstance(patch, dict) or not isinstance(drop, list) or any(not isinstance(k, str) or k.startswith('_') for k in [*patch, *drop]):
            fail('validation', '이전 대상은 업무 필드입니다.')
        for key in drop:
            record.pop(key, None)
        record.update(patch)
        record.update(_definition_revision=revision, _revision=before['_revision'] + 1, _updated_by=auth.subject)
        changed[(row['collection'], row['id'])] = (before, record)
    validate_final(conn, defn, changed, auth)
    commit_id = uid('commit')
    conn.execute('INSERT INTO commits VALUES (?,?,?,?,?,?,?)',
                 (commit_id, auth.subject, auth.executor, 'admin:migrate', reason, revision, time.time()))
    for (collection, ident), (before, record) in changed.items():
        conn.execute('UPDATE records SET body=?,revision=?,definition_revision=?,updated_by=? WHERE collection=? AND id=?',
                     (dump(body(record)), record['_revision'], revision, auth.subject, collection, ident))
        conn.execute('INSERT INTO revisions(commit_id,collection,id,revision,before_body,after_body) VALUES (?,?,?,?,?,?)',
                     (commit_id, collection, ident, record['_revision'], dump(before), dump(record)))
