"""실행 기록의 명시적 소유권. 목표·진행·과제 상태를 저장하지 않는다."""
import sqlite3
from pathlib import Path


def record(db_path, agent_key, task_id, episode_id):
    if not agent_key or not task_id or episode_id is None:
        return
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path), timeout=15) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS execution_identity ("
                     "agent_key TEXT NOT NULL, task_id TEXT NOT NULL, episode_id TEXT NOT NULL, "
                     "PRIMARY KEY(agent_key, task_id, episode_id))")
        conn.execute("INSERT OR IGNORE INTO execution_identity VALUES (?,?,?)",
                     (agent_key, task_id, str(episode_id)))


def record_current(runner):
    from thread_context import get_current_agent_id, get_current_task_id
    from conversation_sessions import current
    from episode_logger import capture_trace
    config = getattr(runner, "config", {}) or {}
    agent = get_current_agent_id() or config.get("id")
    task = get_current_task_id()
    trace = capture_trace()
    episode = getattr(trace, "episode_id", None)
    if not agent or not task or episode is None:
        return
    if config.get("_is_system_ai"):
        from system_ai_memory import MEMORY_DB_PATH
        db, owner = MEMORY_DB_PATH, "system_ai:" + str(agent)
    else:
        path = getattr(runner, "project_path", None)
        if not path:
            return
        db, owner = Path(path) / "conversations.db", str(agent)
    session = current()
    if session:
        owner += "@session:" + session.session_id
    record(db, owner, task, episode)


def read_bindings(db_path, *, episode_id=None, task_id=None, owner=None):
    from trace_read import bounded_rows, guarded, readonly, result
    def read():
        where, args = ("episode_id=?", [str(episode_id)]) if episode_id is not None else (
            "task_id=?", [task_id])
        if owner is not None:
            where += " AND agent_key=?"
            args.append(owner)
        with readonly(db_path) as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='execution_identity'").fetchone():
                return result("execution_identity", status="missing", reason="identity_schema_missing")
            rows = bounded_rows(conn, "SELECT agent_key,task_id,episode_id FROM execution_identity WHERE "
                                + where + " ORDER BY agent_key,task_id,episode_id", args)
            return result("execution_identity", rows)
    return guarded("execution_identity", read)
