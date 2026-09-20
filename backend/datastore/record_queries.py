"""조회·이력·영수증은 현재 접근 정책을 먼저 적용한다."""
import base64
import json

from common.record_contract import digest, dump, fail
from common.row_conditions import _match
from common.value_semantics import sort_records
from record_store import transaction, definition, meta, get_record, decode_record
from record_policy import check_auth, roles, projection, can_read, allowed


def query(space, args, auth, root=None):
    check_auth(auth, space)
    with transaction(space, root) as conn:
        member_roles = roles(conn, auth)
        defn, revision = definition(conn)
        op = args.get('op', 'describe')
        collection = args.get('collection')
        if op == 'describe':
            pinned_defn = defn
            if args.get('id') and collection:
                record = get_record(conn, collection, args['id'])
                projection(defn, collection, record, auth, member_roles)
                pinned_defn, revision = definition(conn, record['_definition_revision'])
            items = []
            for c, spec in defn['collections'].items():
                policy = spec.get('access', {}).get('read', {})
                if not allowed({k: v for k, v in policy.items() if k != 'where'}, auth, member_roles):
                    continue
                if collection and collection != c:
                    continue
                fields = {k: s for k, s in spec['fields'].items() if policy.get('fields') is None or k in policy['fields']}
                items.append({'collection': c, 'label': spec.get('label', c), 'fields': fields})
            commands = [{'command': k, 'label': c.get('label', k), 'input': c.get('input', {}),
                         'confirmation': 'human' if any(x.get('confirmation') == 'human' for x in (c, defn['commands'][k])) else None,
                         'reason_required': any(x.get('reason_required', False) for x in (c, defn['commands'][k])),
                         'observed': {a: s for a, s in c.get('read', {}).items() if s['version'] == 'observed'}}
                        for k, c in pinned_defn['commands'].items() if k in defn['commands'] and
                        all(allowed({f: v for f, v in policy.items() if f not in {'where', 'deny_self'}}, auth, member_roles)
                            for policy in (c['allow'], defn['commands'][k]['allow']))]
            return {'success': True, 'items': items, 'commands': commands, 'definition_revision': revision,
                    'notice': defn.get('notice', '제출한 업무 데이터는 이 공간의 운영자 기기에 저장됩니다.'),
                    'admin_revision': meta(conn, 'admin_revision') if auth.subject == 'owner' else None}
        if op == 'receipt':
            if str(args.get('request_id', '')).startswith('admin_'):
                fail('validation', '관리 영수증은 관리 API에서 조회하세요.')
            from record_commands import visible_receipt
            row = conn.execute('SELECT receipt FROM requests WHERE subject=? AND request_id=?', (auth.subject, args.get('request_id'))).fetchone()
            if not row:
                return {'success': True, 'items': [], 'status': 'not_committed'}
            receipt = visible_receipt(conn, json.loads(row[0]), defn, auth, member_roles, replayed=True)
            return {'success': True, 'items': [receipt]}
        if op == 'inbox':
            items = []
            for row in conn.execute('SELECT * FROM tasks ORDER BY id'):
                config = json.loads(row['body'])
                if row['state'] != args.get('state', 'open'):
                    continue
                if not (auth.subject in config.get('subjects', []) or set(member_roles) & set(config.get('roles', []))):
                    continue
                target = get_record(conn, row['collection'], row['record_id'])
                if not can_read(defn, row['collection'], target, auth, member_roles):
                    continue
                items.append({'id': row['id'], 'revision': row['revision'], 'collection': row['collection'],
                              'record_id': row['record_id'], 'target_revision': row['target_revision'], 'state': row['state'],
                              'label': config.get('label', ''), 'command': config.get('command'), 'due_at': config.get('due_at'),
                              'assignee': config.get('assignee'), 'approvals': len(config.get('votes', []))})
            return page(items, args, conn, auth)
        if collection not in defn['collections']:
            fail('not_found', '기록 묶음을 찾을 수 없습니다.')
        policy = defn['collections'][collection].get('access', {}).get('read', {})
        visible_fields = set(policy.get('fields', defn['collections'][collection]['fields'])) | {'_id', '_revision', '_collection', '_archived', '_definition_revision'}
        if op in {'detail', 'history'}:
            record = get_record(conn, collection, args.get('id'))
            visible = projection(defn, collection, record, auth, member_roles)
            if op == 'detail':
                return {'success': True, 'items': [visible]}
            items = []
            for row in conn.execute('SELECT r.*, c.subject,c.executor,c.command,c.reason,c.at FROM revisions r JOIN commits c ON c.id=r.commit_id WHERE collection=? AND r.id=? ORDER BY seq DESC', (collection, args.get('id'))):
                before = json.loads(row['before_body']) if row['before_body'] else None
                after = json.loads(row['after_body'])
                # 과거의 행 범위도 재검사한다. 현재 담당자가 옛 비공개 담당 정보를 얻지 않게 한다.
                if not can_read(defn, collection, after, auth, member_roles):
                    continue
                items.append({'revision': row['revision'], 'commit_id': row['commit_id'], 'at': row['at'],
                              'command': row['command'], 'subject': row['subject'], 'executor': row['executor'], 'reason': row['reason'],
                              'before': {k: v for k, v in (before or {}).items() if k in visible_fields} if before and can_read(defn, collection, before, auth, member_roles) else None,
                              'after': {k: v for k, v in after.items() if k in visible_fields}})
            for row in conn.execute('SELECT t.*,c.subject,c.executor,c.command,c.reason,c.at FROM task_history t JOIN commits c ON c.id=t.commit_id WHERE collection=? AND record_id=?', (collection, args.get('id'))):
                historical = conn.execute('SELECT after_body FROM revisions WHERE collection=? AND id=? AND revision=?',
                                          (collection, args['id'], row['target_revision'])).fetchone()
                if not historical or not can_read(defn, collection, json.loads(historical[0]), auth, member_roles):
                    continue
                items.append({'kind': 'task', 'task_id': row['task_id'], 'revision': row['target_revision'],
                              'commit_id': row['commit_id'], 'at': row['at'], 'subject': row['subject'],
                              'executor': row['executor'], 'command': row['command'], 'reason': row['reason'],
                              'after': json.loads(row['body'])})
            items.sort(key=lambda item: item['at'], reverse=True)
            return page(items, args, conn, auth)
        if op != 'query':
            fail('validation', '지원 op: describe/query/detail/apply/history/inbox/receipt')
        fields = args.get('fields', sorted(visible_fields))
        if not isinstance(fields, list) or set(fields) - visible_fields:
            fail('forbidden', '열람할 수 없는 필드입니다.')
        where = args.get('where', {})
        check_where(where, visible_fields)
        order = args.get('order')
        if order and (not isinstance(order, dict) or order.get('field') not in visible_fields or set(order) - {'field', 'descending'}):
            fail('forbidden', '정렬 필드를 확인하세요.')
        items = []
        for row in conn.execute('SELECT * FROM records WHERE collection=? AND archived=0 ORDER BY id', (collection,)):
            record = decode_record(row)
            if can_read(defn, collection, record, auth, member_roles):
                visible = projection(defn, collection, record, auth, member_roles)
                if _match(visible, where):
                    items.append(visible)
        if order:
            items = sort_records(items, order['field'], bool(order.get('descending')))
        return page([{k: v for k, v in item.items() if k in fields} for item in items], args, conn, auth)


def check_where(where, fields):
    if isinstance(where, list):
        for condition in where:
            check_where(condition, fields)
    elif isinstance(where, dict):
        referenced = [where['field']] if 'field' in where else list(where)
        if set(referenced) - fields:
            fail('forbidden', '검색할 수 없는 필드입니다.')
    else:
        fail('validation', '관리 기록의 where는 필드가 명시된 객체 또는 AND 목록입니다.')


def page(items, args, conn, auth):
    limit = args.get('limit', 100)
    if type(limit) is not int or not 1 <= limit <= 200:
        fail('validation', 'limit은 1~200입니다.')
    binding = digest({'space': meta(conn, 'uuid'), 'subject': auth.subject, 'access': meta(conn, 'access_revision'),
                      'snapshot': conn.execute('SELECT COUNT(*) FROM commits').fetchone()[0],
                      'definition': meta(conn, 'active_revision'), 'query': {k: v for k, v in args.items() if k != 'cursor'}})
    start = 0
    if args.get('cursor'):
        try:
            cursor = json.loads(base64.urlsafe_b64decode(args['cursor']))
            if cursor['binding'] != binding or type(cursor['offset']) is not int or cursor['offset'] < 0:
                fail('conflict', '조회 조건이나 권한이 변경되었습니다.')
            start = cursor['offset']
        except (ValueError, KeyError, TypeError):
            fail('validation', '잘못된 cursor입니다.')
    selected = items[start:start + limit]
    more = start + limit < len(items)
    cursor = base64.urlsafe_b64encode(dump({'binding': binding, 'offset': start + limit}).encode()).decode() if more else None
    return {'success': True, 'items': selected, 'count': len(selected), 'total': len(items), 'truncated': more, 'cursor': cursor}
