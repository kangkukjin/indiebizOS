"""Durable document metadata and immutable bytes; no editor or format conversion."""
import hashlib
import json
import os
import sqlite3
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path

from runtime_utils import get_base_path


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identifier():
    return uuid.uuid4().hex


def sync_directory(path):
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


class OfficeStore:
    def __init__(self, root=None):
        self.root = Path(root or Path(get_base_path()) / "data/document_workspace").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.blobs = self.root / "blobs"
        self.blobs.mkdir(exist_ok=True)
        self.db = self.root / "state.db"
        with self.connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS objects (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id TEXT NOT NULL, body TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db, timeout=30)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @contextmanager
    def lock(self):
        # A separate SQLite transaction is a portable process lock. Metadata
        # commits remain durable while this lock spans a filesystem replacement.
        conn = sqlite3.connect(self.root / "writer.db", timeout=30)
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield
        finally:
            conn.rollback()
            conn.close()

    def put(self, kind, row, conn=None):
        if conn is None:
            with self.connect() as transaction:
                self.put(kind, row, transaction)
            return
        conn.execute("INSERT INTO objects VALUES (?, ?, ?) ON CONFLICT(id) "
                     "DO UPDATE SET body=excluded.body WHERE objects.kind=excluded.kind",
                     (row["id"], kind, json.dumps(row, ensure_ascii=False, allow_nan=False)))

    def get(self, kind, key):
        with self.connect() as conn:
            row = conn.execute("SELECT body FROM objects WHERE kind=? AND id=?", (kind, key)).fetchone()
        if row is None:
            raise ValueError("문서 작업 항목을 찾을 수 없습니다")
        return json.loads(row[0])

    def list(self, kind):
        with self.connect() as conn:
            return [json.loads(row[0]) for row in conn.execute(
                "SELECT body FROM objects WHERE kind=? ORDER BY rowid DESC", (kind,))]

    def event(self, document_id, body, conn):
        conn.execute("INSERT INTO events(document_id,body) VALUES (?,?)",
                     (document_id, json.dumps(body, ensure_ascii=False)))

    def events(self, document_id, after=0):
        with self.connect() as conn:
            return [{"sequence": row[0], **json.loads(row[1])} for row in conn.execute(
                "SELECT sequence,body FROM events WHERE document_id=? AND sequence>? "
                "ORDER BY sequence LIMIT 200", (document_id, after))]

    def blob(self, data):
        key = digest(data)
        target = self.blobs / key
        if target.exists():
            if digest(target.read_bytes()) != key:
                raise OSError("문서 복구 데이터의 해시가 일치하지 않습니다")
            return key
        fd, temporary = tempfile.mkstemp(dir=self.blobs)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            sync_directory(self.blobs)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return key

    def bytes(self, key):
        if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
            raise ValueError("잘못된 문서 바이트 참조")
        data = (self.blobs / key).read_bytes()
        if digest(data) != key:
            raise OSError("문서 바이트가 손상되었습니다")
        return data
