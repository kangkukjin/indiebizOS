"""한글 fn 기록·구판 원문 복원·시험 코퍼스 격리 회귀."""
import hashlib
import json
import sqlite3

import boot_paths  # noqa: F401
import pytest

from test_fn_zero_rediagnosis_2026_09_07 import _load_script, _pulse_db, _run


def test_writer_records_unicode_heads_without_quoted_examples(monkeypatch, tmp_path,
                                                            isolated_episode_store):
    import episode_logger as el
    import system_tools_ibl as ibl

    monkeypatch.setattr(ibl, "_execute_ibl_unified_impl", lambda *a: '{"success":true}')
    code = ('# [fn:주석예시]\n[fn:주소마다읽기]\n[fn: 열추려보기]\n'
            '[self:write]{content:"[fn:본문예시]",path:"/tmp/example.txt"}')
    with el.trajectory_scope(task_id="task_unicode_telemetry"):
        ibl._execute_ibl_unified({"code": code}, str(tmp_path), agent_id="probe")
    with sqlite3.connect(isolated_episode_store) as conn:
        event = json.loads(conn.execute(
            "SELECT data FROM trajectory_event WHERE kind='ibl.started'").fetchone()[0])
    assert event["actions"] == ["fn:주소마다읽기", "fn:열추려보기", "self:write"]
    assert event["action_count"] == 3 and event["fn_count"] == 2


def test_fn_count_survives_action_list_preview_limit(monkeypatch, tmp_path,
                                                   isolated_episode_store):
    import episode_logger as el
    import system_tools_ibl as ibl

    monkeypatch.setattr(ibl, "_execute_ibl_unified_impl", lambda *a: '{"success":true}')
    code = '\n'.join(['[self:time]'] * 100 + ['[fn:한글호출]'] * 2)
    with el.trajectory_scope(task_id="task_long_fn_telemetry"):
        ibl._execute_ibl_unified({"code": code}, str(tmp_path), agent_id="probe")
    with sqlite3.connect(isolated_episode_store) as conn:
        event = json.loads(conn.execute(
            "SELECT data FROM trajectory_event WHERE kind='ibl.started'").fetchone()[0])
    assert len(event["actions"]) == 100
    assert event["action_count"] == 102 and event["fn_count"] == 2
    assert _load_script()._pair_trajectory([("ibl.started", json.dumps(event))])["fn"] == 2


@pytest.mark.parametrize("mode", ["episodes", "totals"])
@pytest.mark.parametrize("missing_corpus", [False, True])
def test_old_stats_recover_from_code_or_report_unknown(tmp_path, monkeypatch, capsys,
                                                     missing_corpus, mode):
    mod = _load_script()
    code = '[fn:주소마다읽기]{목록:[],개수:1}'
    db = _pulse_db(tmp_path, [(code, True), (code, True)], "")
    with sqlite3.connect(db) as conn:
        # 구판의 실제 결함: 코드는 남았지만 한글 머리 목록은 비어 있었다.
        conn.execute("UPDATE trajectory_event SET data=json_set(data,'$.actions',json('[]')) "
                     "WHERE kind='ibl.started'")
        if missing_corpus:
            conn.execute("DELETE FROM ibl_code_corpus")
    monkeypatch.setattr(mod, "DB", db)
    out = _run(mod, monkeypatch, capsys, {"last": 1, "mode": mode})
    row = out["items"][0]
    assert row["fn"] == (None if missing_corpus else 2)
    assert row["fn미측정"] == (2 if missing_corpus else 0)


def test_default_test_store_receives_corpus(isolated_episode_store, tmp_path):
    import episode_logger as el

    code = '[self:time] # isolated fn telemetry regression'
    assert el.record_ibl_code(code, success=True)
    with el._get_db() as conn:
        assert conn.execute('PRAGMA database_list').fetchone()[2] == str(isolated_episode_store)
        row = conn.execute('SELECT source FROM ibl_code_corpus WHERE code=?', (code,)).fetchone()
    assert row[0] == "test"
    assert list(tmp_path.iterdir()) == [], "계측 DB가 테스트 대상 파일 목록을 오염시키면 안 된다"


def test_fn_recognizer_ignores_test_only_corpus(tmp_path, monkeypatch):
    import runtime_utils
    import fn_recognizer

    monkeypatch.setattr(runtime_utils, 'get_base_path', lambda: tmp_path)
    (tmp_path / 'data').mkdir()
    code = '[self:time]; [self:time]'
    sha = hashlib.sha256(code.encode()).hexdigest()
    with sqlite3.connect(tmp_path / 'data/world_pulse.db') as conn:
        conn.execute('CREATE TABLE ibl_code_corpus '
                     '(code_sha256 TEXT, seen_count INTEGER, success_count INTEGER, source TEXT)')
        conn.execute('INSERT INTO ibl_code_corpus VALUES (?, 8, 7, ?)', (sha, 'test'))
    assert fn_recognizer.corpus_stats(code) is None
    with sqlite3.connect(tmp_path / 'data/world_pulse.db') as conn:
        conn.execute("UPDATE ibl_code_corpus SET source='usage'")
    assert fn_recognizer.corpus_stats(code) == {"seen_count": 8, "success_count": 7}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
