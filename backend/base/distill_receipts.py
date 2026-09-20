"""증류 mutation과 같은 SQLite 트랜잭션에 쓰는 재배달 영수증."""
import json


def begin(conn, key):
    if not key:
        return None
    conn.execute("CREATE TABLE IF NOT EXISTS distill_receipts "
                 "(candidate_key TEXT PRIMARY KEY, result TEXT NOT NULL, projected INTEGER NOT NULL DEFAULT 0)")
    if "projected" not in {r[1] for r in conn.execute("PRAGMA table_info(distill_receipts)")}:
        conn.execute("ALTER TABLE distill_receipts ADD COLUMN projected INTEGER NOT NULL DEFAULT 0")
    conn.execute("BEGIN IMMEDIATE")
    row = conn.execute("SELECT result FROM distill_receipts WHERE candidate_key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def record(conn, key, result):
    if key:
        conn.execute("INSERT INTO distill_receipts (candidate_key, result) VALUES (?, ?)",
                     (key, json.dumps(result, ensure_ascii=False)))


def fingerprint(value):
    import hashlib
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


class DistillConflict(ValueError):
    """판단 후 비교 대상이 변경됨. 이번 후보를 종결하고 자동 재판정하지 않는다."""


def lookup(conn, key):
    if not key or not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='distill_receipts'").fetchone():
        return None
    row = conn.execute('SELECT result FROM distill_receipts WHERE candidate_key=?', (key,)).fetchone()
    return json.loads(row[0]) if row else None


def mark_projected(conn, key):
    if key:
        conn.execute('UPDATE distill_receipts SET projected=1 WHERE candidate_key=?', (key,))
        conn.commit()


def projection_pending(db_path):
    """DB→문서 반영 중인 행을 낡은 문서의 역동기화가 지우지 못하게 한다."""
    import os
    import sqlite3
    if not os.path.exists(db_path):
        return False
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        return pending_connection(conn)
    finally:
        conn.close()


def pending_connection(conn):
    columns = {r[1] for r in conn.execute('PRAGMA table_info(distill_receipts)')}
    if not columns:
        return False
    query = 'SELECT 1 FROM distill_receipts'
    if 'projected' in columns:
        query += ' WHERE projected=0'
    return conn.execute(query + ' LIMIT 1').fetchone() is not None


def atomic_text(path, text):
    """기계 생성 절을 포함한 문서를 반쪽 파일로 노출하지 않는다."""
    import os
    import tempfile
    from pathlib import Path
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
