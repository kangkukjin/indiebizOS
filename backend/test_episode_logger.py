"""에피소드별 주행 지표는 그 주행에 속한 훈련 호출도 보여준다."""
import boot_paths  # noqa: F401
import json
import sqlite3

import pytest

import episode_logger as el


@pytest.mark.parametrize("include_test", [False, True])
def test_journal_counts_training_calls_inside_user_episode(tmp_path, monkeypatch, include_test):
    path = tmp_path / "pulse.db"

    def connect():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(el, "_get_db", connect)
    el._ensure_episode_tables()
    with connect() as conn:
        for eid, source in [(1, "usage"), (2, "training"), (3, "test")]:
            conn.execute("INSERT INTO episode_log(id,started_at,source) VALUES(?,'now',?)",
                         (eid, source))
        events = [
            (1, "usage", "supervision.tool.started", {"name": "execute_ibl"}),
            (1, "usage", "ibl.started", {"code_chars": 0, "action_count": 0}),
            (1, "usage", "supervision.tool.started", {"name": "execute_ibl"}),
            (1, "usage", "ibl.started", {"code_chars": 30, "action_count": 2}),
            (1, "training", "supervision.tool.started", {"name": "execute_ibl"}),
            (1, "training", "ibl.started", {"code_chars": 40, "action_count": 3}),
            (1, "training", "supervision.tool.started", {"name": "execute_ibl"}),
            (1, "test", "supervision.tool.started", {"name": "execute_ibl"}),
            (1, "test", "ibl.started", {"code_chars": 50, "action_count": 7}),
            (2, "training", "ibl.started", {"code_chars": 60, "action_count": 99}),
        ]
        for seq, (eid, source, kind, data) in enumerate(events):
            conn.execute("INSERT INTO trajectory_event"
                         "(run_id,event_seq,episode_id,ts,kind,data,source) "
                         "VALUES('run',?,?,'now',?,?,?)",
                         (seq, eid, kind, json.dumps(data), source))
    rows = {r["id"]: r for r in el.get_episode_journal(include_test=include_test)}
    assert set(rows) == ({1, 2, 3} if include_test else {1})
    assert rows[1]["ibl_calls"] == (4 if include_test else 3)
    assert rows[1]["ibl_actions"] == (12 if include_test else 5)
    if include_test:
        assert rows[2]["ibl_calls"] == 1
        assert rows[2]["ibl_actions"] == 99
    else:
        # 훈련 에피소드가 더 최근이어도 목록의 실사용 선택·LIMIT는 유지한다.
        assert el.get_episode_journal(limit=1)[0]["id"] == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
