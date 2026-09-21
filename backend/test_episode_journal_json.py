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
        # 구버전 DB를 재현한다. 관문 설치 이후에는 이 손상을 새로 쓸 수 없다.
        conn.execute("DROP TRIGGER trajectory_data_insert")
        conn.execute("INSERT INTO episode_log(id,started_at,source) VALUES(1,'now','usage')")
        for seq, (kind, data) in enumerate(events):
            conn.execute("INSERT INTO trajectory_event(run_id,event_seq,episode_id,ts,kind,data,source) "
                         "VALUES('run',?,1,'now',?,?,'usage')", (seq, kind, data))
    el._ensure_episode_tables()
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
    assert parsed["omitted_fields"] == 1
    assert len(parsed["sha256"]) == 64


@pytest.mark.parametrize("size", [0, 4095, 4096, 4097, 50000])
def test_payload_boundary_round_trip_preserves_small_fields(journal_db, size):
    from trajectory_payload import encode_payload
    original = {"name": "execute_ibl", "action_count": 3, "code_chars": 81,
                "context": "", "nested": {"ok": True}}
    original["context"] = "x" * max(0, size - len(json.dumps(original, sort_keys=True)))
    encoded = encode_payload(original)
    decoded = json.loads(encoded)
    with journal_db() as conn:
        assert conn.execute("SELECT json_valid(?)", (encoded,)).fetchone()[0] == 1
    assert len(encoded) <= 4096
    assert decoded["name"] == "execute_ibl"
    assert decoded["code_chars"] == 81 and decoded["action_count"] == 3
    assert decoded["nested"] == {"ok": True}
    assert bool(decoded.get("truncated")) == (size > 4096)
    assert "truncated" not in original


def test_structured_masking_never_edits_json_syntax():
    from trajectory_payload import encode_payload
    data = {"password": 123456789, "nested": [{"api_key": 'quoted\\"\nsecret'}],
            "text": '그는 "password=abcdefghijk"라고 말했다', "count": 7}
    encoded = encode_payload(data)
    parsed = json.loads(encoded)
    assert parsed["password"] == "****"
    assert parsed["nested"][0]["api_key"] == "****"
    assert "abcdefghijk" not in encoded
    assert parsed["count"] == 7


def test_long_supervisor_event_preserves_original_store_link(journal_db, tmp_path):
    from types import SimpleNamespace
    from conscious_supervisor import Supervisor
    from supervision_store import TurnStore
    from episode_trace_reader import read_trace_store_links
    store = TurnStore(tmp_path / "supervision")
    subject = SimpleNamespace(store=store, task="long-supervisor", phase="evaluate")
    decision = {"status": "APPROVED", "reason": "긴 근거" * 3000}
    with journal_db() as conn:
        conn.execute("INSERT INTO episode_log(id,started_at,source) VALUES(1,'now','usage')")
        db_path = conn.execute("PRAGMA database_list").fetchone()[2]
    with el.trajectory_scope(task_id=subject.task, episode_id=1):
        original = Supervisor.log(subject, "decision", role="evaluate", decision=decision)
    links = read_trace_store_links(db_path, [1])["rows"]
    assert len(links) == 1
    assert links[0]["store"] == str(store.directory)
    assert links[0]["seq"] == original["seq"]
    restored = json.loads((store.directory / "events.jsonl").read_text())
    assert restored["decision"] == decision
    assert len(el.get_episode_journal(include_test=True)) == 1


@pytest.mark.parametrize("bad", ['{"cut":', '[]', 'null', '42', '{"n":NaN}', None])
def test_database_rejects_invalid_insert_and_update(journal_db, bad):
    with journal_db() as conn:
        insert = "INSERT INTO trajectory_event(run_id,event_seq,ts,kind,data) VALUES('guard',?,'now','probe',?)"
        conn.execute(insert, (1, '{}'))
        with pytest.raises(sqlite3.IntegrityError, match="must be a JSON object"):
            conn.execute(insert, (2, bad))
        with pytest.raises(sqlite3.IntegrityError, match="must be a JSON object"):
            conn.execute("UPDATE trajectory_event SET data=? WHERE run_id='guard'", (bad,))
        assert conn.execute("SELECT data FROM trajectory_event").fetchall()[0][0] == '{}'


def test_invalid_writer_input_is_visible_without_breaking_run(journal_db, caplog):
    with el.trajectory_scope(task_id="invalid-number"):
        assert el.record_trajectory_event("probe.invalid", {"n": float("nan")}) is None
        assert el.record_trajectory_event("probe.valid", {"n": 1}) is not None
    assert "궤적 사건 저장 실패 (probe.invalid): ValueError" in caplog.text


def test_migration_installs_guards_without_rewriting_legacy_data():
    import schema_migrations
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE trajectory_event(data TEXT)")
    conn.execute("INSERT INTO trajectory_event VALUES (?)", ('{"cut":',))
    conn.execute("PRAGMA user_version=1")
    conn.commit()
    assert schema_migrations.apply(conn, "world_pulse") == 2
    assert schema_migrations.apply(conn, "world_pulse") == 2
    assert conn.execute("SELECT data FROM trajectory_event").fetchone()[0] == '{"cut":'
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO trajectory_event VALUES ('bad')")
    conn.close()


def test_journal_database_error_is_not_an_empty_history(monkeypatch):
    def fail():
        raise sqlite3.OperationalError("unavailable")

    monkeypatch.setattr(el, "_get_db", fail)
    with pytest.raises(sqlite3.OperationalError, match="unavailable"):
        el.get_episode_journal()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
