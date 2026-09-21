"""긴 감독 사건의 JSON 절단이 주행 목록 전체를 숨기지 않도록 한다."""
import boot_paths  # noqa: F401
import json
import sqlite3

import pytest
import episode_logger as el


@pytest.fixture
def journal_db(tmp_path, monkeypatch):
    path = tmp_path / "pulse.db"

    def connect():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(el, "_get_db", connect)
    el._ensure_episode_tables()
    return connect


def test_journal_keeps_rows_with_invalid_legacy_events(journal_db):
    events = [
        ("supervision.decision", '{"decision":"cut'),
        ("ibl.started", '{"code_chars":'),
        ("model.round", '{"round":'),
        ("model.round", '[]'),
        ("ibl.started", '{"code_chars":10,"action_count":2}'),
        ("model.round", '{"role":"execution","round":1}'),
    ]
    with journal_db() as conn:
        conn.execute("INSERT INTO episode_log(id,started_at,source) VALUES(1,'now','usage')")
        for seq, (kind, data) in enumerate(events):
            conn.execute("INSERT INTO trajectory_event(run_id,event_seq,episode_id,ts,kind,data,source) "
                         "VALUES('run',?,1,'now',?,?,'usage')", (seq, kind, data))
    rows = el.get_episode_journal()
    assert len(rows) == 1
    assert rows[0]["ibl_calls"] == 1
    assert rows[0]["ibl_actions"] == 2
    assert rows[0]["execution_rounds"] == 1


@pytest.mark.parametrize("text", ['가나다' * 3000, '\\"\n' * 3000])
def test_long_trajectory_payload_stays_valid_json(journal_db, text):
    with el.trajectory_scope(task_id="journal-json-test"):
        event = el.record_trajectory_event("supervision.decision", {"reason": text})
    assert event is not None
    with journal_db() as conn:
        data = conn.execute("SELECT data FROM trajectory_event WHERE kind='supervision.decision'").fetchone()[0]
    assert len(data) <= 4096
    parsed = json.loads(data)
    assert parsed["truncated"] is True
    assert parsed["original_chars"] > 4096
    assert parsed["preview"]


def test_journal_database_error_is_not_an_empty_history(monkeypatch):
    def fail():
        raise sqlite3.OperationalError("unavailable")

    monkeypatch.setattr(el, "_get_db", fail)
    with pytest.raises(sqlite3.OperationalError, match="unavailable"):
        el.get_episode_journal()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
