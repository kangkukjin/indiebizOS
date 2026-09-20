"""공간별 SQLite. 모든 업무 변경과 영수증은 한 트랜잭션으로 확정한다."""
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from common.record_contract import RecordError, dump, fail, name

SCHEMA = '''
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE definitions(revision INTEGER PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE memberships(subject TEXT PRIMARY KEY, roles TEXT NOT NULL, revision INTEGER NOT NULL);
CREATE TABLE records(collection TEXT, id TEXT, revision INTEGER NOT NULL, definition_revision INTEGER NOT NULL,
 body TEXT NOT NULL, created_by TEXT NOT NULL, updated_by TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(collection,id));
CREATE TABLE commits(id TEXT PRIMARY KEY, subject TEXT, executor TEXT, command TEXT, reason TEXT,
 definition_revision INTEGER, at REAL NOT NULL);
CREATE TABLE revisions(seq INTEGER PRIMARY KEY AUTOINCREMENT, commit_id TEXT REFERENCES commits(id),
 collection TEXT, id TEXT, revision INTEGER, before_body TEXT, after_body TEXT);
CREATE TABLE requests(subject TEXT, request_id TEXT, hash TEXT, receipt TEXT, PRIMARY KEY(subject,request_id));
CREATE TABLE tasks(id TEXT PRIMARY KEY, collection TEXT, record_id TEXT, target_revision INTEGER,
 revision INTEGER, body TEXT, state TEXT NOT NULL, commit_id TEXT);
CREATE TABLE task_history(seq INTEGER PRIMARY KEY AUTOINCREMENT, commit_id TEXT REFERENCES commits(id),
 task_id TEXT, collection TEXT, record_id TEXT, target_revision INTEGER, body TEXT);
CREATE TABLE events(id TEXT PRIMARY KEY, commit_id TEXT, body TEXT, at REAL);
CREATE TABLE deliveries(id TEXT PRIMARY KEY, kind TEXT, body TEXT, state TEXT, due REAL, lease_until REAL,
 attempt INTEGER NOT NULL DEFAULT 0, result TEXT, subject TEXT, definition_revision INTEGER);
CREATE TABLE confirmations(token TEXT PRIMARY KEY, subject TEXT, hash TEXT, expires REAL, used INTEGER DEFAULT 0);
CREATE TABLE artifacts(id TEXT PRIMARY KEY, hash TEXT, size INTEGER, filename TEXT, subject TEXT, at REAL);
CREATE TABLE admin_log(seq INTEGER PRIMARY KEY AUTOINCREMENT, operation TEXT, subject TEXT, reason TEXT, body TEXT, at REAL);
CREATE INDEX records_collection ON records(collection,archived);
CREATE INDEX revisions_record ON revisions(collection,id,seq);
CREATE INDEX deliveries_due ON deliveries(state,due);
'''


def uid(prefix):
    return prefix + '_' + uuid.uuid4().hex


def root_path():
    from runtime_utils import get_data_path
    return Path(get_data_path()) / 'record_spaces'


def space_path(space, root=None):
    return Path(root or root_path()) / name(space)


def connect(space, root=None):
    path = space_path(space, root) / 'records.db'
    if not path.exists():
        fail('not_found', '업무 공간을 찾을 수 없습니다.')
    conn = sqlite3.connect(str(path), timeout=2, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA synchronous=FULL')
    return conn


@contextmanager
def transaction(space, root=None, *, write=False):
    conn = connect(space, root)
    deadline = time.monotonic() + 3
    conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
    try:
        conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        yield conn
        conn.execute('COMMIT')
    except sqlite3.OperationalError as exc:
        if conn.in_transaction:
            conn.rollback()
        if 'locked' in str(exc) or 'interrupt' in str(exc):
            raise RecordError('busy', '업무 공간이 사용 중입니다. 같은 요청 ID로 다시 시도하세요.') from exc
        raise
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()


def meta(conn, key):
    row = conn.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
    return json.loads(row[0]) if row else None


def put_meta(conn, key, value):
    conn.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (key, dump(value)))


def definition(conn, revision=None):
    revision = revision or meta(conn, 'active_revision')
    row = conn.execute('SELECT body FROM definitions WHERE revision=?', (revision,)).fetchone()
    if not row:
        fail('definition_changed', '업무 정의 버전을 확인하세요.')
    return json.loads(row[0]), revision


def get_record(conn, collection, ident):
    row = conn.execute('SELECT * FROM records WHERE collection=? AND id=?', (collection, ident)).fetchone()
    if not row:
        fail('not_found', '기록을 찾을 수 없습니다.')
    return decode_record(row)


def decode_record(row):
    return {**json.loads(row['body']), '_id': row['id'], '_collection': row['collection'],
            '_revision': row['revision'], '_definition_revision': row['definition_revision'],
            '_created_by': row['created_by'], '_updated_by': row['updated_by'], '_archived': bool(row['archived'])}


def body(record):
    return {k: v for k, v in record.items() if not k.startswith('_')}


def create_space(space, definition_value, auth, root=None):
    from record_policy import require_owner
    from common.record_contract import validate_definition
    require_owner(auth)
    definition_value = validate_definition(definition_value)
    folder = space_path(space, root)
    try:
        folder.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        fail('conflict', '이미 존재하는 업무 공간입니다.')
    conn = sqlite3.connect(str(folder / 'records.db'), isolation_level=None, timeout=2)
    try:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=FULL')
        conn.executescript(SCHEMA)
        conn.execute('BEGIN IMMEDIATE')
        for k, v in {'uuid': uid('space'), 'active_revision': 1, 'access_revision': 1,
                     'admin_revision': 1, 'paused': False, 'recovery_required': False}.items():
            put_meta(conn, k, v)
        conn.execute('INSERT INTO definitions VALUES (?,?)', (1, dump(definition_value)))
        conn.execute('INSERT INTO memberships VALUES (?,?,1)', (auth.subject, dump(['admin'])))
        conn.execute('COMMIT')
    finally:
        conn.close()
    return {'success': True, 'space': space, 'definition_revision': 1, 'admin_revision': 1}
