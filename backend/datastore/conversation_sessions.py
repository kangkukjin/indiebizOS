"""대화 세션의 영속 소유권. 원문은 기존 테이블에, 실행/사건은 세션 아래에 보존한다."""
import json
import sqlite3
import uuid
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class Binding:
    db_path: str
    session_id: str
    owner: str
    turn_id: str = ""


_UNBOUND = object()
_current = ContextVar("conversation_session", default=_UNBOUND)
_PROCESS = uuid.uuid4().hex
_task_bindings = {}
_task_lock = threading.RLock()
_loaded_paths = set()


def current():
    binding = _current.get()
    if binding is not _UNBOUND:
        return binding
    # MCP/위임 결과는 별도 요청 스레드에서 돌아온다. 인증된 실행 task 신원으로 원 소속을 회수한다.
    from thread_context import get_current_task_id
    task = get_current_task_id()
    with _task_lock:
        return _task_bindings.get(task)


def bind_task(task):
    b = current()
    if not b:
        return
    with connection(b.db_path) as conn:
        conn.execute("INSERT OR IGNORE INTO conversation_task_links VALUES (?,?,?)", (task, b.session_id, b.turn_id))
    with _task_lock:
        _task_bindings[task] = b


def state_directory(binding):
    return Path(binding.db_path).parent / "conversation_state" / binding.session_id


@contextmanager
def scope(binding):
    token = _current.set(binding)
    try:
        yield binding
    finally:
        _current.reset(token)


def now():
    return datetime.now(timezone.utc).isoformat()


def pair_owner(a, b):
    return "pair:" + ":".join(map(str, sorted((int(a), int(b)))))


@contextmanager
def connection(path):
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_schema(conn, table):
    if table not in ("messages", "conversations"):
        raise ValueError("잘못된 대화 테이블")
    conn.execute("""CREATE TABLE IF NOT EXISTS conversation_sessions (
        id TEXT PRIMARY KEY, owner TEXT NOT NULL, title TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        legacy INTEGER NOT NULL DEFAULT 0)""")
    conn.execute("CREATE INDEX IF NOT EXISTS session_owner ON conversation_sessions(owner, updated_at)")
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    if "session_id" not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN session_id TEXT REFERENCES conversation_sessions(id)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS {table}_session ON {table}(session_id, id)")
    # 기존 SQLite 연결들이 foreign_keys를 켜지 않은 경우에도 잘못된 소속은 거절한다.
    for op in ("INSERT", "UPDATE OF session_id"):
        name = "insert" if op == "INSERT" else "update"
        conn.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_session_{name}
            BEFORE {op} ON {table} WHEN NEW.session_id IS NOT NULL AND NOT EXISTS
            (SELECT 1 FROM conversation_sessions WHERE id=NEW.session_id)
            BEGIN SELECT RAISE(ABORT, 'unknown conversation session'); END""")
    conn.execute("""CREATE TABLE IF NOT EXISTS conversation_turns (
        id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES conversation_sessions(id),
        state TEXT NOT NULL, process TEXT NOT NULL, started_at TEXT NOT NULL,
        finished_at TEXT, error TEXT, stream_content TEXT NOT NULL DEFAULT '')""")
    # CREATE IF NOT EXISTS는 기존 세션 DB의 열을 갱신하지 않는다.
    turn_cols = {r[1] for r in conn.execute("PRAGMA table_info(conversation_turns)")}
    if "stream_content" not in turn_cols:
        conn.execute("ALTER TABLE conversation_turns ADD COLUMN stream_content TEXT NOT NULL DEFAULT ''")
    conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS one_running_conversation_turn
        ON conversation_turns(session_id) WHERE state='running'""")
    conn.execute("""CREATE TABLE IF NOT EXISTS conversation_events (
        id INTEGER PRIMARY KEY, session_id TEXT NOT NULL REFERENCES conversation_sessions(id),
        turn_id TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL)""")
    conn.execute("CREATE INDEX IF NOT EXISTS conversation_events_session ON conversation_events(session_id,id)")
    conn.execute("""CREATE TABLE IF NOT EXISTS conversation_task_links (
        task_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, turn_id TEXT NOT NULL)""")


def _predicate(owner, table):
    if table == "conversations":
        if owner in ("appmaker", "rehearsal"):
            return "source=?", [owner]
        return "(source IS NULL OR source NOT IN ('appmaker','rehearsal'))", []
    _, a, b = owner.split(":")
    return ("((from_agent_id=? AND to_agent_id=?) OR (from_agent_id=? AND to_agent_id=?)) "
            "AND COALESCE(contact_type,'gui') NOT IN ('research','rehearsal')"), [a, b, b, a]


def legacy(conn, owner, table):
    sid = "legacy-" + uuid.uuid5(uuid.NAMESPACE_URL, owner).hex
    stamp = now()
    conn.execute("""INSERT OR IGNORE INTO conversation_sessions
        (id,owner,title,created_at,updated_at,legacy) VALUES (?,?,?,?,?,1)""",
        (sid, owner, "기존 대화", stamp, stamp))
    where, args = _predicate(owner, table)
    conn.execute(f"UPDATE {table} SET session_id=? WHERE session_id IS NULL AND {where}", [sid, *args])
    return sid


def resolve(conn, path, owner, table):
    """실행 중인 소유권만 계승한다. 다른 대화 상대의 위임 기록은 그 상대의 기존 대화다."""
    b = current()
    if b and Path(b.db_path).resolve() == Path(path).resolve() and b.owner == owner:
        row = conn.execute("SELECT owner FROM conversation_sessions WHERE id=?", (b.session_id,)).fetchone()
        if not row or row[0] != owner:
            raise ValueError("세션 소유자가 일치하지 않습니다")
        return b.session_id
    return legacy(conn, owner, table)


def touch(conn, sid, content=None):
    conn.execute("UPDATE conversation_sessions SET updated_at=? WHERE id=?", (now(), sid))
    if content:
        conn.execute("""UPDATE conversation_sessions SET title=? WHERE id=? AND title='새 세션'""",
                     (" ".join(content.split())[:60], sid))


class SessionStore:
    def __init__(self, path, table, owner):
        self.path, self.table, self.owner = str(path), table, owner
        with connection(path) as conn:
            ensure_schema(conn, table)
            legacy(conn, owner, table)
            with _task_lock:
                if self.path not in _loaded_paths:
                    for row in conn.execute("""SELECT t.task_id,t.session_id,t.turn_id,s.owner FROM conversation_task_links t
                        JOIN conversation_sessions s ON s.id=t.session_id"""):
                        _task_bindings[row[0]] = Binding(self.path, row[1], row[3], row[2])
                    _loaded_paths.add(self.path)
            conn.execute("""UPDATE conversation_turns SET state='interrupted',finished_at=?
                WHERE state='running' AND process!=?""", (now(), _PROCESS))

    def require(self, conn, sid):
        # 이전 DB의 archived 열은 읽거나 갱신하지 않는다. 모든 대화는 항상 재개할 수 있다.
        row = conn.execute("""SELECT id,owner,title,created_at,updated_at,legacy
            FROM conversation_sessions WHERE id=? AND owner=?""", (sid, self.owner)).fetchone()
        if not row:
            raise ValueError("이 대상에 속한 세션이 아닙니다")
        return dict(row)

    def list(self):
        with connection(self.path) as conn:
            return [dict(r) for r in conn.execute("""SELECT s.id,s.owner,s.title,s.created_at,s.updated_at,s.legacy,
                EXISTS(SELECT 1 FROM conversation_turns t WHERE t.session_id=s.id AND t.state='running') AS running
                FROM conversation_sessions s WHERE owner=? ORDER BY updated_at DESC,id""", (self.owner,))]

    def create(self, title="새 세션"):
        sid, stamp = uuid.uuid4().hex, now()
        with connection(self.path) as conn:
            conn.execute("""INSERT INTO conversation_sessions
                (id,owner,title,created_at,updated_at) VALUES (?,?,?,?,?)""",
                (sid, self.owner, title.strip()[:120] or "새 세션", stamp, stamp))
            return self.require(conn, sid)

    def update(self, sid, title=None):
        with connection(self.path) as conn:
            self.require(conn, sid)
            if title is not None:
                if not title.strip():
                    raise ValueError("세션 이름을 입력해주세요")
                conn.execute("UPDATE conversation_sessions SET title=? WHERE id=?", (title.strip()[:120], sid))
            return self.require(conn, sid)

    def history(self, sid, before=None, limit=50):
        if not 1 <= limit <= 100:
            raise ValueError("대화 조회 개수는 1~100이어야 합니다")
        with connection(self.path) as conn:
            self.require(conn, sid)
            rows = conn.execute(f"SELECT * FROM {self.table} WHERE session_id=? AND id<? ORDER BY id DESC LIMIT ?",
                                (sid, before or 9223372036854775807, limit + 1)).fetchall()
            messages = []
            human = None
            if self.table == "messages":
                r = conn.execute("SELECT id FROM agents WHERE name='user'").fetchone()
                human = r[0] if r else None
            for row in reversed(rows[:limit]):
                r = dict(row)
                timestamp = r.get("timestamp") or r.get("message_time")
                if timestamp:
                    parsed = datetime.fromisoformat(timestamp)
                    if parsed.tzinfo is None:
                        parsed = parsed.astimezone() if self.table == "conversations" else parsed.replace(tzinfo=timezone.utc)
                    timestamp = parsed.isoformat()
                messages.append({"id": str(r["id"]), "content": r["content"],
                    "role": r.get("role", "user" if r.get("from_agent_id") == human else "assistant"),
                    "timestamp": timestamp,
                    "images": json.loads(r["images"]) if r.get("images") else []})
            return {"messages": messages, "has_older": len(rows) > limit}

    def begin(self, sid):
        tid = uuid.uuid4().hex
        with connection(self.path) as conn:
            self.require(conn, sid)
            try:
                conn.execute("INSERT INTO conversation_turns(id,session_id,state,process,started_at,finished_at,error) VALUES (?,?,?,?,?,?,?)",
                             (tid, sid, "running", _PROCESS, now(), None, None))
            except sqlite3.IntegrityError as exc:
                raise ValueError("이 세션에는 이미 실행 중인 작업이 있습니다") from exc
        return Binding(self.path, sid, self.owner, tid)

    def finish(self, binding, state="completed", error=None):
        with connection(self.path) as conn:
            conn.execute("UPDATE conversation_turns SET state=?,finished_at=?,error=? WHERE id=?",
                         (state, now(), error, binding.turn_id))
            touch(conn, binding.session_id)


def record_event(payload):
    b = current()
    if not b or not b.turn_id or payload.get("type") == "pong":
        return
    kind = payload.get("type")
    with connection(b.db_path) as conn:
        if kind == "stream_chunk":
            conn.execute("UPDATE conversation_turns SET stream_content=substr(stream_content || ?, -64000) WHERE id=?",
                         (str(payload.get("content", "")), b.turn_id))
            return
        if kind in ("tool_start", "response", "error", "cancelled"):
            conn.execute("UPDATE conversation_turns SET stream_content='' WHERE id=?", (b.turn_id,))
        conn.execute("INSERT INTO conversation_events(session_id,turn_id,created_at,payload) VALUES (?,?,?,?)",
                     (b.session_id, b.turn_id, now(), json.dumps(payload, ensure_ascii=False, default=str)))


def bounded_history(history, max_chars=60000):
    """긴 최근 발화도 상한을 둔다. 원문은 DB에 보존하고 생략을 표시한다."""
    result, remaining = [], max_chars
    for row in reversed(history):
        if remaining <= 0:
            break
        item = dict(row)
        content = str(item.get("content", ""))
        if len(content) > min(16000, remaining):
            cap = min(16000, remaining)
            content = content[:cap//2] + "\n[일부 생략 — 세션 원문에서 확인 가능]\n" + content[-cap//2:]
        item["content"] = content
        remaining -= len(content)
        result.append(item)
    return list(reversed(result))
