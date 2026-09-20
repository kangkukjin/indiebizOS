"""IBL·HTTP가 공유하는 기록 진입점. 읽기와 쓰기에 같은 인증·공간 정책 적용."""
from common.record_contract import RecordError, fail
from record_policy import check_auth
from record_store import root_path


def execute(args, auth, root=None):
    check_auth(auth, args.get('space', ''), args.get('command', '') if args.get('op') == 'apply' else '')
    if root is None:
        from vocabulary_state import is_active
        if not is_active('record-ops'):
            fail('forbidden', '공동 업무 묶음이 잠들어 있습니다.')
    allowed = {'op', 'space', 'collection', 'id', 'where', 'fields', 'order', 'cursor', 'limit',
               'command', 'definition_revision', 'input', 'expected', 'request_id', 'reason', 'confirmation', 'state'}
    if set(args) - allowed:
        fail('validation', '선언되지 않은 기록 입력입니다.')
    op = args.get('op', 'describe')
    if op == 'describe' and not args.get('space'):
        return spaces(auth, root)
    if not args.get('space'):
        fail('validation', 'space가 필요합니다. describe로 업무 공간을 먼저 조회하세요.')
    if op == 'apply':
        from record_commands import apply
        return apply(args['space'], args, auth, root)
    from record_queries import query
    return query(args['space'], args, auth, root)


def spaces(auth, root=None):
    from pathlib import Path
    from record_queries import query
    items = []
    for db in Path(root or root_path()).glob('*/records.db'):
        try:
            info = query(db.parent.name, {'op': 'describe'}, auth, root)
            items.append({'space': db.parent.name, 'title': db.parent.name,
                          'definition_revision': info['definition_revision'],
                          'url': '/records/app?space=' + db.parent.name})
        except RecordError:
            continue
    return {'success': True, 'items': items}
