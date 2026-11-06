"""Conversation revision/checkpoint metadata. Original messages are never deleted."""
import json
import time
import uuid


def schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS turn_checkpoints (
        id TEXT PRIMARY KEY, session_id TEXT NOT NULL, turn_id TEXT NOT NULL,
        created_at REAL NOT NULL, messages TEXT NOT NULL, revision INTEGER NOT NULL,
        pinned INTEGER NOT NULL DEFAULT 0)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS conversation_revisions (
        session_id TEXT PRIMARY KEY, revision INTEGER NOT NULL DEFAULT 0)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS conversation_hidden_messages (
        session_id TEXT NOT NULL, message_id INTEGER NOT NULL,
        PRIMARY KEY(session_id,message_id))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS conversation_rewinds (
        id TEXT PRIMARY KEY, session_id TEXT NOT NULL, body TEXT NOT NULL)''')


def visible(table):
    if table not in ('messages', 'conversations'): raise ValueError('잘못된 대화 테이블')
    return f'NOT EXISTS (SELECT 1 FROM conversation_hidden_messages hidden WHERE hidden.session_id={table}.session_id AND hidden.message_id={table}.id)'


def revision(conn, sid):
    row = conn.execute('SELECT revision FROM conversation_revisions WHERE session_id=?', (sid,)).fetchone()
    return row[0] if row else 0


def capture(conn, table, sid, tid, *, pinned=False):
    ids = [r[0] for r in conn.execute(f'SELECT id FROM {table} WHERE session_id=? AND {visible(table)} ORDER BY id', (sid,))]
    item = {'id': uuid.uuid4().hex, 'session_id': sid, 'turn_id': tid, 'created_at': time.time(),
            'messages': ids, 'revision': revision(conn, sid), 'pinned': pinned}
    conn.execute('INSERT INTO turn_checkpoints VALUES (?,?,?,?,?,?,?)',
                 (item['id'], sid, tid, item['created_at'], json.dumps(ids), item['revision'], int(pinned)))
    return item


def switch(conn, table, sid, checkpoint):
    keep = set(checkpoint['messages'])
    all_ids = [r[0] for r in conn.execute(f'SELECT id FROM {table} WHERE session_id=?', (sid,))]
    conn.execute('DELETE FROM conversation_hidden_messages WHERE session_id=?', (sid,))
    conn.executemany('INSERT INTO conversation_hidden_messages VALUES (?,?)', [(sid, mid) for mid in all_ids if mid not in keep])
    conn.execute('INSERT INTO conversation_revisions VALUES (?,1) ON CONFLICT(session_id) DO UPDATE SET revision=revision+1', (sid,))


def checkpoint(conn, sid, key):
    row = conn.execute('SELECT * FROM turn_checkpoints WHERE id=? AND session_id=?', (key, sid)).fetchone()
    if not row: raise ValueError('이 세션의 체크포인트가 아닙니다')
    out = dict(row); out['messages'] = json.loads(out['messages'])
    return out


def assert_unlocked(conn, sid):
    row = conn.execute("SELECT id FROM conversation_rewinds WHERE session_id=? AND json_extract(body,'$.state') NOT IN ('prepared','completed','cancelled')", (sid,)).fetchone()
    if row: raise ValueError('대화 복구가 진행 중입니다: ' + row[0])
