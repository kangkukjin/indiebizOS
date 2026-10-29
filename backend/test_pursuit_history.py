"""은퇴 기록은 쓰기/모델 호출 없이 원래 소유 범위로만 조회한다."""
import sqlite3
import boot_paths  # noqa: F401
from pursuit_history import read_trace_bindings, read_trace_text


def test_historical_read_preserves_owner_and_original_database(tmp_path):
    db = tmp_path / "old.db"
    with sqlite3.connect(db) as conn:
        conn.executescript("""
        CREATE TABLE pursuit(id,agent_key,version,status);
        CREATE TABLE pursuit_turn(pursuit_id,task_id,episode_id,state,source_order,input,response);
        INSERT INTO pursuit VALUES('old','owner',3,'active');
        INSERT INTO pursuit_turn VALUES('old','task','1','applied',1,'original request','saved answer');
        """)
    original = db.read_bytes()
    assert read_trace_bindings(db, episode_id=1, owner="owner")["rows"][0]["pursuit_id"] == "old"
    assert not read_trace_bindings(db, episode_id=1, owner="other")["rows"]
    assert read_trace_text(db, "old", "task", "owner", "response", 0, 100)["rows"][0]["text"] == "saved answer"
    assert read_trace_text(db, "old", "task", "other", "response", 0, 100)["status"] == "missing"
    assert db.read_bytes() == original


if __name__ == "__main__":
    import pytest
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
