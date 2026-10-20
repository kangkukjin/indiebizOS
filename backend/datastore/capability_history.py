"""구성요소의 관측·검증·수리 원장. 실행 성공과 검증은 서로 다른 사건이다."""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from runtime_utils import get_base_path


def now():
    return datetime.now(timezone.utc).isoformat()


def storage_path(root=None):
    if root is not None:
        return Path(root) / 'data/capability_history.db'
    state = os.environ.get('INDIEBIZ_RUNTIME_STATE_DIR')
    return (Path(state) if state else get_base_path() / 'data') / 'capability_history.db'


@contextmanager
def connection(path=None):
    path = Path(path) if path else storage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS components (
                key TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
                revision TEXT NOT NULL, implementation_revision TEXT NOT NULL,
                dependency_revision TEXT NOT NULL, created_at TEXT,
                first_observed_at TEXT NOT NULL, last_observed_at TEXT NOT NULL,
                implementation_changed_at TEXT, dependencies_changed_at TEXT,
                present INTEGER NOT NULL DEFAULT 1, metadata TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, key TEXT NOT NULL, event TEXT NOT NULL,
                at TEXT NOT NULL, revision TEXT, scope TEXT, outcome TEXT,
                evidence TEXT, reason TEXT, previous_revision TEXT);
            CREATE INDEX IF NOT EXISTS capability_events_key ON events(key, id);
            CREATE TABLE IF NOT EXISTS executions (
                key TEXT PRIMARY KEY, at TEXT NOT NULL, success INTEGER,
                source TEXT NOT NULL);
        ''')
        yield conn
        conn.commit()
    finally:
        conn.close()


def _event(conn, key, event, at, revision, **fields):
    columns = ('scope', 'outcome', 'evidence', 'reason', 'previous_revision')
    cur = conn.execute('INSERT INTO events (key,event,at,revision,scope,outcome,evidence,reason,previous_revision) '
                       'VALUES (?,?,?,?,?,?,?,?,?)',
                       (key, event, at, revision, *(fields.get(k) for k in columns)))
    return cur.lastrowid


def observe(inventory, path=None):
    """완전한 목록만 원자적으로 반영한다. 최초 관측을 생성·변경·수리로 꾸미지 않는다."""
    at = now()
    with connection(path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        previous = {r['key']: dict(r) for r in conn.execute('SELECT * FROM components')}
        for key, item in inventory.items():
            old = previous.get(key)
            changed = at if old and old['implementation_revision'] != item['implementation_revision'] else None
            deps_changed = at if old and old['dependency_revision'] != item['dependency_revision'] else None
            conn.execute('''INSERT INTO components VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(key) DO UPDATE SET kind=excluded.kind, name=excluded.name,
                revision=excluded.revision, implementation_revision=excluded.implementation_revision,
                dependency_revision=excluded.dependency_revision,
                created_at=COALESCE(components.created_at,excluded.created_at),
                last_observed_at=excluded.last_observed_at,
                implementation_changed_at=excluded.implementation_changed_at,
                dependencies_changed_at=excluded.dependencies_changed_at,
                present=1, metadata=excluded.metadata''',
                (key, item['kind'], item['name'], item['revision'], item['implementation_revision'],
                 item['dependency_revision'], item.get('created_at'), at, at,
                 changed or (old or {}).get('implementation_changed_at'),
                 deps_changed or (old or {}).get('dependencies_changed_at'), 1,
                 json.dumps(item.get('metadata', {}), ensure_ascii=False)))
            if old is None or not old['present'] or old['revision'] != item['revision']:
                event = 'first_observed' if old is None else 'restored' if not old['present'] else 'changed'
                _event(conn, key, event, at, item['revision'], previous_revision=(old or {}).get('revision'),
                       reason='implementation' if changed else 'dependencies' if deps_changed else None)
        for key, old in previous.items():
            if key not in inventory and old['present']:
                conn.execute('UPDATE components SET present=0,last_observed_at=? WHERE key=?', (at, key))
                _event(conn, key, 'absent', at, old['revision'])
    return at


def record(key, event, expected_revision, *, scope='', outcome='', evidence='', reason='', path=None):
    if event not in {'verified', 'repaired'}:
        raise ValueError('기록 종류는 verified 또는 repaired입니다.')
    if not isinstance(evidence, str) or not evidence.strip():
        raise ValueError('검사 결과 파일·실호출 기록·커밋 등 evidence가 필요합니다.')
    if event == 'verified' and (not isinstance(scope, str) or not scope.strip()
                                or outcome not in {'passed', 'failed'}):
        raise ValueError('검증 범위 scope와 outcome(passed/failed)이 필요합니다.')
    if event == 'repaired' and (not isinstance(reason, str) or not reason.strip()):
        raise ValueError('수리한 결함을 reason으로 기록하세요.')
    with connection(path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT revision,present FROM components WHERE key=?', (key,)).fetchone()
        if not row or not row['present']:
            raise ValueError('현재 존재하는 구성요소가 아닙니다.')
        if not expected_revision or row['revision'] != expected_revision:
            raise ValueError('REVISION_CHANGED: 현재 revision을 다시 조회하고 그 구현을 검증하세요.')
        return _event(conn, key, event, now(), expected_revision, scope=scope, outcome=outcome,
                      evidence=evidence, reason=reason)


def record_execution(key, success, *, at=None, source='runtime', path=None):
    """실행 시각만 갱신한다. 구현을 실행 직전에 고정한 증거가 없으므로 revision을 추정하지 않는다."""
    with connection(path) as conn:
        conn.execute('''INSERT INTO executions VALUES (?,?,?,?) ON CONFLICT(key) DO UPDATE SET
            at=excluded.at,success=excluded.success,source=excluded.source
            WHERE excluded.at >= executions.at''',
                     (key, at or now(), int(success) if success is not None else None, source))


def rows(path=None):
    with connection(path) as conn:
        items = [dict(r) for r in conn.execute('SELECT * FROM components ORDER BY key')]
        events = {}
        for row in conn.execute("SELECT * FROM events WHERE event IN ('verified','repaired') ORDER BY id"):
            events.setdefault(row['key'], []).append(dict(row))
        runs = {r['key']: dict(r) for r in conn.execute('SELECT * FROM executions')}
    for item in items:
        item['metadata'] = json.loads(item['metadata'])
        item['present'] = bool(item['present'])
        history = events.get(item['key'], [])
        repairs = [e for e in history if e['event'] == 'repaired']
        repair = repairs[-1] if repairs else None
        # 동일 범위의 최신 판정이 과거 성공을 대체한다. 다른 범위를 전체 검증으로 합치지 않는다.
        latest = {e['scope']: e for e in history if e['event'] == 'verified'}
        checks = []
        for check in latest.values():
            current = (item['present'] and check['revision'] == item['revision']
                       and (not repair or check['id'] > repair['id']))
            checks.append({**check, 'current': current,
                           'status': ('current' if check['outcome'] == 'passed' else 'failed') if current else 'stale'})
        statuses = {c['status'] for c in checks}
        item.update(verifications=checks, last_checked_at=max((c['at'] for c in checks), default=None),
                    last_verified_at=max((c['at'] for c in history if c['event'] == 'verified'
                                          and c['outcome'] == 'passed'), default=None),
                    last_repaired_at=repair['at'] if repair else None, last_repair=repair,
                    last_execution=runs.get(item['key']),
                    verification_status=('failed' if 'failed' in statuses else 'stale' if 'stale' in statuses
                                         else 'current' if 'current' in statuses else 'unverified'),
                    change_time_basis='observed_at; exact edit time may be earlier')
    return items


def history(key, *, after=0, limit=50, path=None):
    if type(after) is not int or after < 0 or type(limit) is not int or limit <= 0:
        raise ValueError('after는 0 이상, limit은 양의 정수여야 합니다.')
    with connection(path) as conn:
        result = [dict(r) for r in conn.execute(
            'SELECT * FROM events WHERE key=? AND id>? ORDER BY id LIMIT ?', (key, after, limit + 1))]
    more = len(result) > limit
    return {'items': result[:limit], 'next_cursor': result[limit - 1]['id'] if more else None}
