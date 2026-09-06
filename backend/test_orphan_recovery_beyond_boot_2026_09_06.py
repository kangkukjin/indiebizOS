"""부팅 밖 고아 회수 + 무주 run 의 귀속 (2026-09-06, ep2897)

재현하는 사고:
  10:04 정기보고앱이 [others:delegate] 로 하달한 턴이 열렸다. 10:33 에 일을 다 끝내고
  (보고서·HTML·필드노트 저장 완료) 주인 프로세스가 죽었지만 END 를 못 썼다. 부팅 회수는
  05:32 에 이미 돌았고 그때 이 행은 **존재하지도 않았다** — sweep 이 본 적 없으니
  _arm_resweep 도 안 걸렸고, 백엔드가 살아 있는 한 행은 영영 ended_at NULL 이었다.
  사용자가 "뭐가 돌고 있냐"고 물었을 때 원장은 '도는 중'이라고 거짓을 말했다.

  같은 턴에 드러난 둘째 구멍: 봉투에 episode_id 가 안 실린 실행은 초크포인트가 run 만
  세우고 episode_log 에 행이 없다. 궤적은 남는데 주인이 없어, 누가 쐈는지 답할 수 없었다.

두 겹으로 막는다:
  ①회수를 부팅 전용에서 뗀다 — 새 턴을 여는 손이 지난 고아를 회수한다(부팅은 특수 사례)
  ②무주 run 은 사건 자체에 귀속을 적는다 — unowned/origin/task_id

실행: .venv/bin/python -m pytest backend/test_orphan_recovery_beyond_boot_2026_09_06.py
"""
import sqlite3
import sys

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401


def _tmp_db(tmp_path):
    """episode 스키마만 있는 빈 DB — 라이브 원장을 건드리지 않는다."""
    import episode_logger as EL
    path = str(tmp_path / "world_pulse.db")

    def _get_db():
        conn = sqlite3.connect(path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    orig = EL._get_db
    EL._get_db = _get_db
    try:
        EL._ensure_episode_tables()
    except Exception:
        EL._get_db = orig
        raise
    return path, orig


def _open_row(path, owner):
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO episode_log (started_at, ended_at, agent, user_message, log, total_ms,"
        " task_id, source, owner) VALUES ('2026-09-06T10:04:25', NULL, 'system_ai',"
        " '유튜브 AI 팁 보고서 써줘', '', NULL, '', 'usage', ?)", (owner,))
    eid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return eid


def _ended(path, eid):
    conn = sqlite3.connect(path)
    r = conn.execute("SELECT ended_at FROM episode_log WHERE id=?", (eid,)).fetchone()
    conn.close()
    return r[0]


def _dead_pid():
    import subprocess
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


# ─── ①회수는 부팅 전용이 아니다 ──────────────────────────────────────────────

def test_start_episode_sweeps_orphan_born_after_boot(tmp_path):
    """★사고의 심장: 부팅 뒤에 태어나 죽은 고아를, 다음 턴을 여는 손이 회수한다.

    부팅 sweep 은 이 행을 본 적이 없다(부팅 시점에 없던 행) — 그래서 재회수 타이머도
    안 걸린다. 새 턴이 열릴 때 회수가 돌지 않으면 행은 영영 NULL 로 남는다(ep2897).
    """
    import episode_logger as EL
    path, orig = _tmp_db(tmp_path)
    try:
        eid = _open_row(path, f"{_dead_pid()}:1")       # 주인이 죽은 고아
        assert _ended(path, eid) is None                # 아직 열려 있다

        EL.EpisodeLogger.start_episode("system_ai", "다음 턴")   # 부팅이 아니라 '새 턴'
        try:
            assert _ended(path, eid), \
                "부팅 뒤에 생긴 고아가 새 턴에도 안 닫힌다 — ep2897 재발"
        finally:
            EL.EpisodeLogger.end_episode()
    finally:
        EL._get_db = orig


def test_start_episode_does_not_sweep_live_owner(tmp_path):
    """회수를 턴 시작으로 넓혀도 **살아 있는 주인의 행**은 건드리지 않는다(ep1689 불변)."""
    import episode_logger as EL
    path, orig = _tmp_db(tmp_path)
    try:
        eid = _open_row(path, EL._process_identity())   # 주인 = 지금 이 프로세스
        EL.EpisodeLogger.start_episode("system_ai", "다음 턴")
        try:
            assert _ended(path, eid) is None, \
                "살아 있는 턴이 새 턴 시작에 고아로 닫혔다 — ep1689 재발"
        finally:
            EL.EpisodeLogger.end_episode()
    finally:
        EL._get_db = orig


# ─── ②무주 run 은 귀속을 적는다 ──────────────────────────────────────────────

def test_unowned_run_records_attribution(tmp_path):
    """episode 없이 선 run 의 ibl.started 에 unowned/origin/task_id 가 실린다.

    ★왜: 궤적만 있고 원장에 행이 없는 실행은 '누가 쐈는지' 물을 곳이 없었다.
    """
    import episode_logger as EL
    path, orig = _tmp_db(tmp_path)
    try:
        with EL.trajectory_scope(task_id="task_probe_x") as tr:
            assert tr.episode_id is None, "이 시험의 전제: 무주 run"
            ident = EL.record_trajectory_event("ibl.started", {
                "unowned": tr.episode_id is None,
                "task_id": tr.task_id,
            })
            assert ident is not None and ident["episode_id"] is None

        conn = sqlite3.connect(path)
        row = conn.execute(
            "SELECT data FROM trajectory_event WHERE kind='ibl.started' "
            "ORDER BY ts DESC LIMIT 1").fetchone()
        conn.close()
        assert row, "무주 run 의 사건이 원장에 없다"
        assert '"unowned": true' in row[0], "무주 표식이 사건에 없다 — 귀속 불능 재발"
        assert "task_probe_x" in row[0], "task_id 가 사건에 없다"
    finally:
        EL._get_db = orig


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
