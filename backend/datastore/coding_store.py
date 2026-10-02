"""코딩 앱 상태와 재구독 사건. 과제 의미는 기존 PursuitLedger가 소유한다."""
import hashlib
import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from logging_utils import mask_secret_data
from runtime_utils import get_base_path

_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


def identifier(prefix):
    return prefix + "_" + uuid.uuid4().hex


def fingerprint(value):
    if not isinstance(value, bytes):
        value = json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(value).hexdigest()


class CodingStore:
    def __init__(self, root=None):
        self.root = Path(root or Path(get_base_path()) / "data/coding").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "state.db"
        with self.connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS objects (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL, run_id TEXT NOT NULL,
                    type TEXT NOT NULL, time REAL NOT NULL, body TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS coding_events_task ON events(task_id, sequence);
            """)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @contextmanager
    def lock(self, key):
        """스레드와 프로세스 모두 직렬화한다. 외부 Git 도구는 지문 대조로 감지한다."""
        import fcntl
        name = str(self.root) + ":" + key
        with _LOCKS_GUARD:
            lock = _LOCKS.setdefault(name, threading.RLock())
        with lock:
            folder = self.root / "locks"
            folder.mkdir(exist_ok=True)
            with (folder / fingerprint(name)).open("a") as stream:
                fcntl.flock(stream, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(stream, fcntl.LOCK_UN)

    def save(self, kind, row):
        with self.connect() as conn:
            conn.execute("INSERT INTO objects VALUES (?, ?, ?) ON CONFLICT(id) "
                         "DO UPDATE SET body=excluded.body",
                         (row["id"], kind, json.dumps(row, ensure_ascii=False)))
        return row

    def get(self, kind, key):
        with self.connect() as conn:
            row = conn.execute("SELECT body FROM objects WHERE kind=? AND id=?", (kind, key)).fetchone()
        if row is None:
            raise ValueError("존재하지 않는 코딩 대상: " + key)
        return json.loads(row[0])

    def list(self, kind):
        with self.connect() as conn:
            return [json.loads(r[0]) for r in conn.execute(
                "SELECT body FROM objects WHERE kind=? ORDER BY rowid DESC", (kind,))]

    def event(self, task_id, run_id, event_type, data):
        now = time.time()
        safe = mask_secret_data(data)
        with self.connect() as conn:
            cursor = conn.execute("INSERT INTO events(task_id,run_id,type,time,body) VALUES(?,?,?,?,?)",
                                  (task_id, run_id, event_type, now, json.dumps(safe, ensure_ascii=False)))
            seq = cursor.lastrowid
        from episode_logger import record_trajectory_event
        record_trajectory_event("coding." + event_type, {
            "coding_task_id": task_id, "coding_run_id": run_id,
            "sequence": seq, **safe})
        return seq

    def events(self, task_id, after=0, limit=200):
        if after < 0 or not 1 <= limit <= 1000:
            raise ValueError("잘못된 사건 페이지")
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM events WHERE task_id=? AND sequence>? "
                                "ORDER BY sequence LIMIT ?", (task_id, after, limit)).fetchall()
        return [{**dict(r), "body": json.loads(r["body"])} for r in rows]
