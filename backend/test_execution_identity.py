"""실행 소유권은 과거 의미 과제와 독립적으로 기록한다."""
import sqlite3
from types import SimpleNamespace
import boot_paths  # noqa: F401
import execution_identity as identity
import thread_context as tc


def test_record_and_scoped_read_are_idempotent_without_task_ledger(tmp_path):
    db = tmp_path / "conversations.db"
    identity.record(db, "owner@session:a", "task", 1)
    identity.record(db, "owner@session:a", "task", 1)
    identity.record(db, "owner@session:b", "task", 2)
    rows = identity.read_bindings(db, task_id="task", owner="owner@session:a")["rows"]
    assert len(rows) == 1 and rows[0]["episode_id"] == "1"
    assert not identity.read_bindings(db, episode_id=2, owner="owner@session:a")["rows"]
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [("execution_identity",)]


def test_current_execution_records_trusted_episode_and_session(tmp_path, monkeypatch):
    runner = SimpleNamespace(project_path=tmp_path, config={"id": "owner"})
    monkeypatch.setattr("episode_logger.capture_trace", lambda: SimpleNamespace(episode_id=42))
    monkeypatch.setattr("conversation_sessions.current", lambda: SimpleNamespace(session_id="conversation"))
    with tc.actor_context(agent_id="owner", task_id="execution"):
        identity.record_current(runner)
    rows = identity.read_bindings(tmp_path / "conversations.db", episode_id=42)["rows"]
    assert rows == [{"agent_key": "owner@session:conversation", "task_id": "execution", "episode_id": "42"}]


if __name__ == "__main__":
    import pytest
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
