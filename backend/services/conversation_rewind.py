"""Durable, conflict-aware rewind. Files finish before the active conversation switches."""
import json
import time
from pathlib import Path
from contextlib import contextmanager

import conversation_sessions as sessions
import turn_checkpoints as checkpoints
from coding_store import CodingStore, identifier, fingerprint
from coding_git import safe_path, CodingConflict
import file_changes


@contextmanager
def session_lock(store, sid):
    from filelock import FileLock
    folder = Path(store.path).parent / 'conversation_state' / sid
    folder.mkdir(parents=True, exist_ok=True)
    with FileLock(str(folder / 'rewind.lock'), is_singleton=True):
        yield


def list_checkpoints(store, sid):
    with sessions.connection(store.path) as conn:
        store.require(conn, sid)
        rows = conn.execute('SELECT id FROM turn_checkpoints WHERE session_id=? ORDER BY created_at DESC', (sid,)).fetchall()
        return {'items': [{**checkpoints.checkpoint(conn, sid, row[0]), 'coverage': 'tracked_changes'} for row in rows]}


def _save(store, plan):
    with sessions.connection(store.path) as conn:
        conn.execute('INSERT INTO conversation_rewinds VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',
                     (plan['id'], plan['session_id'], json.dumps(plan, ensure_ascii=False)))
    return plan


def get(store, sid, rid):
    with sessions.connection(store.path) as conn:
        store.require(conn, sid)
        row = conn.execute('SELECT body FROM conversation_rewinds WHERE id=? AND session_id=?', (rid, sid)).fetchone()
        if not row: raise ValueError('이 세션의 복구 요청이 아닙니다')
        return json.loads(row[0])


def _journal(store, sid, point, db):
    changes = []
    for p in db.list('workspace_proposal'):
        owner = p.get('attribution') or {}
        if owner.get('session_id') != sid or str(Path(owner.get('db_path', '')).resolve()) != str(Path(store.path).resolve()):
            continue
        if p.get('created_at', 0) >= point['created_at']:
            if p['state'] in ('applying', 'recovery_required'):
                raise CodingConflict('미완료 파일 적용을 먼저 recover 하세요: ' + p['id'])
            if p['state'] == 'applied': changes.append(p)
    return sorted(changes, key=lambda p: (p.get('applied_at', p['created_at']), p['id']))


def preview(store, sid, checkpoint, mode='both', db=None):
    if mode not in ('files', 'conversation', 'both'): raise ValueError('mode: files/conversation/both')
    db = db or CodingStore()
    with session_lock(store, sid), sessions.connection(store.path) as conn:
        store.require(conn, sid); checkpoints.assert_unlocked(conn, sid)
        point = checkpoints.checkpoint(conn, sid, checkpoint)
        rev = checkpoints.revision(conn, sid)
        head = conn.execute(f'SELECT COALESCE(MAX(id),0) FROM {store.table} WHERE session_id=?', (sid,)).fetchone()[0]
    changes = _journal(store, sid, point, db)
    aggregate = {}
    if mode != 'conversation':
        for p in changes:
            root = p.get('root')
            if not root:
                for kind in ('file_workspace', 'project', 'code_view'):
                    try: root = db.get(kind, p['project'])['path']; break
                    except ValueError: pass
            if not root: raise ValueError('변경 저널의 작업 공간을 찾지 못했습니다')
            for edit in p['edits']:
                key = str(safe_path(root, edit['path']))
                if key not in aggregate:
                    aggregate[key] = {'path': edit['path'], 'root': root, 'root_identity': p['root_identity'],
                                      'before': edit['before'], 'after': edit['after']}
                else:
                    if aggregate[key]['after'] != edit['before']:
                        raise CodingConflict('중간에 다른 행위자의 파일 변경이 있습니다: ' + key)
                    aggregate[key]['after'] = edit['after']
    conflicts, edits = [], []
    for path, item in aggregate.items():
        if file_changes.state(Path(path)) != item['after'] or file_changes.identity(item['root']) != item['root_identity']:
            conflicts.append(path)
        if item['before'] != item['after']: edits.append(item)
    plan = {'id': identifier('rewind'), 'session_id': sid, 'checkpoint': checkpoint, 'mode': mode,
            'state': 'prepared', 'created_at': time.time(), 'expires_at': time.time() + 600,
            'revision': rev, 'message_head': head, 'changes': [p['id'] for p in changes],
            'edits': edits, 'conflicts': conflicts, 'coverage': 'tracked_changes',
            'external_effects': '네트워크·DB·관리되지 않은 셸 쓰기는 되돌리지 않습니다',
            'proposals': [], 'files': [{'path': str(Path(e['root']) / e['path']),
                                      'current': fingerprint(file_changes.decoded(e['after']['bytes'])),
                                      'restored': fingerprint(file_changes.decoded(e['before']['bytes']))} for e in edits]}
    import difflib
    def lines(value):
        data = file_changes.decoded(value['bytes'])
        if data is None: return []
        try:
            from lsp_positions import decode
            return decode(data)[0].splitlines(keepends=True)
        except (ValueError, UnicodeError): return ['[binary]\n']
    chunks = []
    for edit in edits:
        chunks.extend(difflib.unified_diff(lines(edit['after']), lines(edit['before']), fromfile=edit['path'], tofile=edit['path']))
    diff = ''.join(chunks)
    plan['diff'] = diff[:200000]
    plan['diff_truncated'] = len(diff) > 200000
    _save(store, plan)
    return public(plan)


def public(plan):
    return {k: v for k, v in plan.items() if k not in ('edits',)}


def _quiesce(store, sid, db):
    from chat_session_service import cancel
    cancel(store, sid)
    import process_sessions
    for p in db.list('process_session'):
        owner = p.get('attribution') or {}
        if owner.get('session_id') == sid and owner.get('db_path') == store.path:
            value = process_sessions.query(p['id'], db=db)
            if value['state'] in ('queued', 'running'):
                process_sessions.query(p['id'], db=db, op='control', action='cancel', request_id='rewind-stop')
    import task_receipts as T
    with sessions.connection(store.path) as conn:
        refs = [json.loads(r[0]) for r in conn.execute('SELECT ref FROM conversation_owned_receipts WHERE session_id=? AND kind NOT IN (?,?)', (sid, 'rewind', 'process'))]
    # Explicit start receipts bind ownership; arbitrary tool stdout cannot enlist another session's job.
    for ref in refs:
        value = T.status(ref)
        if value['state'] in T.LIVE:
            T.cancel(ref)
    deadline = time.monotonic() + 15
    while True:
        with sessions.connection(store.path) as conn:
            live = conn.execute("SELECT id FROM conversation_turns WHERE session_id=? AND state='running'", (sid,)).fetchone()
        running = []
        for p in db.list('process_session'):
            owner = p.get('attribution') or {}
            if owner.get('session_id') == sid and owner.get('db_path') == store.path:
                if process_sessions.query(p['id'], db=db)['state'] in ('queued', 'running'):
                    running.append(p['id'])
        for ref in refs:
            value = T.status(ref)
            if value['state'] in T.LIVE or value['state'] == T.UNKNOWN:
                running.append(ref['task_id'])
        if not live and not running:
            break
        if time.monotonic() >= deadline:
            raise CodingConflict('실행 중인 턴·자식 작업의 중단 확인을 기다립니다: ' + ', '.join(running))
        time.sleep(.1)


def _claim(store, plan):
    if plan['state'] != 'prepared':
        return plan
    if time.time() > plan['expires_at']:
        raise ValueError('미리보기가 만료됐습니다')
    if plan['conflicts']:
        raise CodingConflict('외부 변경 충돌: ' + ', '.join(plan['conflicts']))
    with sessions.connection(store.path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        checkpoints.assert_unlocked(conn, plan['session_id'])
        head = conn.execute(f'SELECT COALESCE(MAX(id),0) FROM {store.table} WHERE session_id=?', (plan['session_id'],)).fetchone()[0]
        if head != plan['message_head'] or checkpoints.revision(conn, plan['session_id']) != plan['revision']:
            raise CodingConflict('미리보기 이후 대화가 변경됐습니다. 다시 미리보세요')
        plan['state'] = 'quiescing'
        conn.execute('UPDATE conversation_rewinds SET body=? WHERE id=?', (json.dumps(plan), plan['id']))
    return plan


def execute(store, sid, rid, db=None):
    db = db or CodingStore()
    with session_lock(store, sid):
        plan = get(store, sid, rid)
        if plan['state'] == 'completed': return public(plan)
        if plan['state'] == 'cancelled': raise ValueError('취소된 복구입니다')
        with sessions.connection(store.path) as conn:
            point = checkpoints.checkpoint(conn, sid, plan['checkpoint'])
        _claim(store, plan)
        if plan['state'] == 'quiescing':
            _quiesce(store, sid, db)
            changes = _journal(store, sid, point, db)
            if [p['id'] for p in changes] != plan['changes']:
                plan['state'] = 'prepared'; _save(store, plan)
                raise CodingConflict('미리보기 이후 파일 변경이 생겼습니다. 다시 미리보세요')
            with sessions.connection(store.path) as conn:
                backup = checkpoints.capture(conn, store.table, sid, 'before-' + rid, pinned=True)
                plan['backup_checkpoint'] = backup['id']
            groups = {}
            for edit in plan['edits']:
                if file_changes.state(safe_path(edit['root'], edit['path'])) != edit['after']:
                    raise CodingConflict('복구 직전 외부 변경: ' + edit['path'])
                groups.setdefault(edit['root'], []).append({'path': edit['path'], 'before': edit['after'], 'after': edit['before']})
            from file_workspace import FileWorkspace
            with sessions.scope(sessions.Binding(store.path, sid, store.owner)):
                for root, edits in groups.items():
                    row = FileWorkspace(db).open(root)
                    prop = file_changes.prepare(db, row, edits, metadata={'rewind': rid})
                    plan['proposals'].append({'row': row, 'proposal': prop['proposal']})
            plan['state'] = 'applying_files'; _save(store, plan)
        if plan['state'] == 'applying_files':
            for item in plan['proposals']:
                file_changes.apply(db, item['row'], item['proposal'], recover=True)
            plan['state'] = 'files_applied'; _save(store, plan)
        if plan['state'] == 'files_applied':
            with sessions.connection(store.path) as conn:
                conn.execute('BEGIN IMMEDIATE')
                if plan['mode'] != 'files': checkpoints.switch(conn, store.table, sid, point)
                plan['state'] = 'conversation_switched'
                conn.execute('UPDATE conversation_rewinds SET body=? WHERE id=?', (json.dumps(plan), rid))
        if plan['state'] == 'conversation_switched':
            if plan['mode'] != 'files':
                directory = sessions.state_directory(sessions.Binding(store.path, sid, store.owner))
                for name in ('todo', 'question', 'plan_mode'):
                    path = directory / (name + '_state.json')
                    if path.exists(): path.replace(directory / (rid + '-' + path.name))
            plan['state'] = 'completed'; plan['completed_at'] = time.time(); _save(store, plan)
        return public(plan)


def cancel(store, sid, rid):
    with session_lock(store, sid):
        plan = get(store, sid, rid)
        if plan['state'] not in ('prepared', 'cancelled'): raise ValueError('복구 적용을 시작한 뒤에는 중단하지 않습니다. 재시도로 복구하세요')
        plan['state'] = 'cancelled'; _save(store, plan)
        return public(plan)


def submit(store, sid, rid, db=None):
    """The independent worker survives the turn it cancels and backend reloads."""
    import subprocess
    import sys
    db = db or CodingStore()
    with session_lock(store, sid):
        plan = get(store, sid, rid)
        plan.pop('error', None)
        _claim(store, plan)
        _save(store, plan)
    db.save('rewind_task', {'id': rid, 'path': store.path, 'table': store.table,
                            'owner': store.owner, 'sid': sid})
    if plan['state'] not in ('completed', 'cancelled'):
        folder = db.root / 'rewinds'; folder.mkdir(exist_ok=True)
        backend = Path(__file__).resolve().parents[1]
        code = ('import sys; sys.path.insert(0,sys.argv[1]); import boot_paths; '
                'from conversation_rewind import worker; worker(sys.argv[2],sys.argv[3])')
        from runtime_work import service_scope
        with service_scope(), open(folder / (rid + '.log'), 'ab') as log:
            subprocess.Popen([sys.executable, '-c', code, str(backend), str(db.root), rid, '--indiebiz-owned-session'],
                             stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                             start_new_session=True, close_fds=True)
    import task_receipts as T
    return T.receipt('rewind', rid, owner=sid, rewind=public(plan))


def worker(root, rid):
    db = CodingStore(root)
    item = db.get('rewind_task', rid)
    store = sessions.SessionStore(item['path'], item['table'], item['owner'], recover_turns=False)
    # SessionStore normally marks old process turns interrupted. A rewind worker
    # must not mistake the live chat host for a crashed host; use existing run state.
    try:
        execute(store, item['sid'], rid, db)
    except BaseException as exc:
        plan = get(store, item['sid'], rid)
        if plan['state'] == 'quiescing' and not plan['proposals']:
            plan['state'] = 'prepared'
        plan['error'] = str(exc); _save(store, plan)


def task_status(ref):
    import task_receipts as T
    db = CodingStore(); item = db.get('rewind_task', ref['task_id'])
    store = sessions.SessionStore(item['path'], item['table'], item['owner'], recover_turns=False)
    plan = get(store, item['sid'], ref['task_id'])
    state = 'succeeded' if plan['state'] == 'completed' else 'cancelled' if plan['state'] == 'cancelled' else 'failed' if plan.get('error') else 'running'
    return T.view(ref, state, result=public(plan), progress=public(plan), error=plan.get('error'),
                  accepted_at=plan['created_at'], ended_at=plan.get('completed_at'))


def task_cancel(ref):
    db = CodingStore(); item = db.get('rewind_task', ref['task_id'])
    store = sessions.SessionStore(item['path'], item['table'], item['owner'], recover_turns=False)
    cancel(store, item['sid'], ref['task_id'])
    return task_status(ref)
