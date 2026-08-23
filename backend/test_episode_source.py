"""주행기록의 시험 격리 회귀 (B18-2, 2026-08-22)

재현하는 결함:
  ① 시험 프로세스가 남긴 주행이 실사용과 같은 칸에 쌓였다 — 최근 원장 999건 중 36건이
     시험 유래(test_role_tags)였고, 그중 1건은 start 만 하고 끝나지 않은 고아였다(ep1423).
  ② 그 고아가 red_apply/_current_episode_id 의 "열린 턴" 재해소에 걸릴 수 있었다 —
     영원히 ended_at NULL 이므로 자기수리 적용이 상한(900초)까지 헛기다린다.
  ③ 1000칸 상한이 시험 행에도 자리를 내줘 실사용 주행이 일찍 창 밖으로 밀려났다.
  ④ 결정화 감지기·조합 지표가 그 행을 사람의 마찰로 셌다.

처방은 B18-1(action_health)과 같은 규율: **지우지 않고 표식**(source=usage|test),
판정은 이름 규약이 아니라 **프로세스 정체**, 판정 정본은 base 층 한 벌.

실행: .venv/bin/python -m pytest backend/test_episode_source.py
"""
import os
import sqlite3
import sys

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401


def _tmp_db(tmp_path):
    """episode 스키마만 있는 빈 DB — 라이브 원장을 건드리지 않는 읽기/상한 시험용."""
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


def _row(conn, table, source, agent, ended=True, eid=None):
    if table == "episode_log":
        conn.execute(
            "INSERT INTO episode_log (started_at, ended_at, agent, user_message, log, total_ms, task_id, source)"
            " VALUES ('2026-08-22T00:00:00', ?, ?, 'm', 'log', 1, '', ?)",
            ('2026-08-22T00:01:00' if ended else None, agent, source))
    else:
        conn.execute(
            "INSERT INTO episode_summary (episode_id, started_at, agent, user_message, source)"
            " VALUES (?, '2026-08-22T00:00:00', ?, 'm', ?)", (eid, agent, source))
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def test_single_source_of_test_detection():
    """판정은 한 벌이어야 한다 — 복제하면 두 원장의 '시험'이 다른 뜻으로 갈라진다."""
    import runtime_utils
    import pulse_db
    assert callable(runtime_utils.in_test_process)
    assert pulse_db._in_test_process() == runtime_utils.in_test_process()
    # 판정 *코드*가 다시 복제됐는지만 본다(설명 산문에 'pytest' 가 있는 건 정상).
    src = open(pulse_db.__file__, encoding="utf-8").read()
    assert '"pytest" in sys.modules' not in src, \
        "pulse_db 가 판정을 다시 복제했다 — runtime_utils.in_test_process 에 위임할 것"
    print("OK 시험 판정 단일 소스 (pulse_db → runtime_utils 위임)")


def test_live_episode_from_test_process_is_marked():
    """이 배터리 자신이 남기는 주행이 'test' 로 적재되는가 (라이브 원장, 뒷정리 포함)."""
    import episode_logger as EL
    EL._ensure_episode_tables()
    ids = []
    try:
        EL.EpisodeLogger.start_episode("test_episode_source", "시험 격리 표식 확인")
        ep = EL.EpisodeLogger.current()
        assert ep is not None and ep.episode_id
        conn = EL._get_db()
        opened = conn.execute("SELECT source FROM episode_log WHERE id=?", (ep.episode_id,)).fetchone()
        conn.close()
        # ★개설(START) 시점에 이미 찍혀야 한다 — 턴이 죽어도 남는 행이 그 행이다.
        assert opened["source"] == "test", f"개설 행 source={opened['source']!r}"
        EL.EpisodeLogger.end_episode()
        conn = EL._get_db()
        row = conn.execute("SELECT id, source FROM episode_log WHERE id=?", (ep.episode_id,)).fetchone()
        srow = conn.execute("SELECT id, source FROM episode_summary WHERE episode_id=?",
                            (ep.episode_id,)).fetchone()
        conn.close()
        ids = [("episode_log", row["id"])] + ([("episode_summary", srow["id"])] if srow else [])
        assert row["source"] == "test"
        assert srow is not None and srow["source"] == "test", "요약도 같이 표시돼야 한다"
        print("OK 시험 프로세스의 주행 = source:test (log·summary 양쪽)")
    finally:
        conn = EL._get_db()
        for table, rid in ids:
            conn.execute(f"DELETE FROM {table} WHERE id=?", (rid,))
        conn.commit()
        conn.close()


def test_readers_hide_test_rows_by_default(tmp_path):
    import episode_logger as EL
    path, orig = _tmp_db(tmp_path)
    try:
        conn = EL._get_db()
        u = _row(conn, "episode_log", "usage", "데이터")
        t = _row(conn, "episode_log", "test", "test_role_tags")
        legacy = _row(conn, "episode_log", None, "옛행")   # 칸 생기기 전 = 실사용
        _row(conn, "episode_summary", "usage", "데이터", eid=u)
        _row(conn, "episode_summary", "test", "test_role_tags", eid=t)
        conn.commit()
        conn.close()

        ids = {r["id"] for r in EL.get_episode_list(50)}
        assert u in ids and legacy in ids and t not in ids, ids
        assert t in {r["id"] for r in EL.get_episode_list(50, include_test=True)}
        jids = {r["id"] for r in EL.get_episode_journal(50)}
        assert u in jids and t not in jids, jids
        agents = {r["agent"] for r in EL.get_episode_summaries(50)}
        assert "데이터" in agents and "test_role_tags" not in agents, agents
        assert "test_role_tags" in {r["agent"] for r in EL.get_episode_summaries(50, include_test=True)}
        print("OK 읽기 기본값=실사용만 (NULL=실사용, include_test 로 열림)")
    finally:
        EL._get_db = orig


def test_cap_evicts_test_rows_first(tmp_path):
    """1000칸은 몸이 자기 삶을 되짚는 창 — 시험 행이 실사용을 밀어내면 안 된다."""
    import episode_logger as EL
    path, orig = _tmp_db(tmp_path)
    orig_max = EL.MAX_EPISODES
    try:
        conn = EL._get_db()
        old_usage = _row(conn, "episode_log", "usage", "데이터")      # 가장 오래된 실사용
        t1 = _row(conn, "episode_log", "test", "test_a")
        t2 = _row(conn, "episode_log", "test", "test_b")
        new_usage = _row(conn, "episode_log", "usage", "희정")
        conn.commit()
        conn.close()
        EL.MAX_EPISODES = 2
        EL._cleanup_old_episodes()
        conn = EL._get_db()
        left = {r[0] for r in conn.execute("SELECT id FROM episode_log")}
        conn.close()
        assert left == {old_usage, new_usage}, f"남은 행={left} (시험분이 먼저 버려져야)"
        print("OK 상한 축출 순서: 시험분 먼저, 그 다음 오래된 것")
    finally:
        EL.MAX_EPISODES = orig_max
        EL._get_db = orig


def test_turn_does_not_evict_its_own_row(tmp_path):
    """**턴은 자기 기록을 자기가 지우지 않는다** (2026-08-23 실측 수리).

    재현 조건은 '원장이 상한을 넘긴 상태'다. B18-2 가 축출 정렬 맨 앞에 출처 키를 세우면서,
    `id ASC` 가 실사용 행에 주던 보호(방금 쓴 행 = 가장 새 행 = 축출 후보의 반대편)가
    **시험 행에서만** 사라졌다 — 원장의 유일한 시험 행은 곧 '가장 오래된 시험 행'이라
    `_finalize` 가 행을 닫고 요약까지 쓴 직후, 자기가 부른 정리가 그 행을 지웠다.

    증상이 고약했던 이유: 위 `test_live_episode_from_test_process_is_marked` 가 원장
    적재량에 따라 통과·실패를 오갔다(999건이면 통과, 1001건이면 실패). **주변 상태로
    답이 바뀌는 가드는 신뢰할 수 없다** — 초록을 봐도 무엇이 증명된 건지 알 수 없다.
    """
    import episode_logger as EL
    path, orig = _tmp_db(tmp_path)
    orig_max = EL.MAX_EPISODES
    try:
        conn = EL._get_db()
        old = [_row(conn, "episode_log", "usage", f"옛{i}") for i in range(3)]
        conn.commit()
        conn.close()
        EL.MAX_EPISODES = 2                      # 이미 3건 = 상한 초과 상태에서 턴을 연다

        EL.EpisodeLogger.start_episode("test_self_evict", "자기 축출 재현")
        ep = EL.EpisodeLogger.current()
        eid = ep.episode_id
        assert eid, "행 개설 자체가 실패했다"
        EL.EpisodeLogger.end_episode()           # ← _finalize 가 정리를 부르는 자리

        conn = EL._get_db()
        row = conn.execute("SELECT id, source, ended_at FROM episode_log WHERE id=?", (eid,)).fetchone()
        left = conn.execute("SELECT COUNT(*) FROM episode_log").fetchone()[0]
        conn.close()
        assert row is not None, "턴이 방금 쓴 자기 행을 스스로 지웠다"
        assert row["source"] == "test" and row["ended_at"], dict(row)
        # 보호는 '한 칸 덜 지우기'가 아니다 — 후보에서 빼고 그 다음 것을 지우므로 상한은 정확하다.
        assert left == EL.MAX_EPISODES, f"상한이 안 지켜졌다: {left} != {EL.MAX_EPISODES}"
        assert old[0] not in {r[0] for r in _ids(EL)}, "가장 오래된 것부터 지운다는 규칙은 그대로"
        print("OK 상한 초과에서도 방금 쓴 행은 축출 후보가 아니다 (상한은 정확히 유지)")
    finally:
        EL.MAX_EPISODES = orig_max
        EL._get_db = orig


def _ids(EL):
    conn = EL._get_db()
    rows = conn.execute("SELECT id FROM episode_log").fetchall()
    conn.close()
    return rows


def test_open_episode_resolution_skips_test_rows(tmp_path):
    """②의 핵심 — 무필터 폴백은 살리되(ep1282), 죽은 시험 고아는 후보가 아니다."""
    import episode_logger as EL
    import red_apply
    path, orig = _tmp_db(tmp_path)
    try:
        conn = EL._get_db()
        live = _row(conn, "episode_log", "usage", "system_ai", ended=False)
        ghost = _row(conn, "episode_log", "test", "test_role_tags", ended=False)
        assert ghost > live, "시험 고아가 더 최신이어야 재현이 된다"
        conn.commit()
        conn.close()

        # agent 필터 0건 → 무필터 2차 폴백. 옛 코드는 여기서 ghost 를 집었다.
        assert red_apply._resolve_open_episode(path, "agent_001") == live
        assert red_apply._resolve_open_episode(path, None) == live
        print("OK 열린 턴 재해소가 시험 고아를 건너뛴다")
    finally:
        EL._get_db = orig


def test_analysis_readers_exclude_test(tmp_path):
    """결정화 감지기·조합 지표는 *사람이 겪은 마찰*만 센다 (질의문 가드)."""
    import vocab_crystallization as VC
    src = open(VC.__file__, encoding="utf-8").read()
    assert "COALESCE(source, 'usage') <> 'test'" in src, "결정화 스캔이 시험분을 다시 센다"
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    m = open(os.path.join(root, "scripts", "ibl_composition_metrics.py"), encoding="utf-8").read()
    assert "COALESCE(source, 'usage') <> 'test'" in m, "조합 지표가 시험분을 다시 센다"
    print("OK 분석 독자(결정화·조합지표) 시험분 제외")


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    # ★두 번째 러너를 두지 않는다. 손으로 적은 러너는 반드시 드리프트한다 — 새 시험 함수를
    # 러너에 안 적으면 직접 실행이 **그 시험만 조용히 건너뛰고 종료코드 0** 을 낸다.
    # 실측(2026-08-23): 배터리 44개·시험 303건 중 **147건**이 직접 실행에서 한 번도 안 돌았고,
    # 27·28회차 상상훈련이 그 초록을 "전부 통과"로 보고서에 적었다(거짓 초록).
    # 위임하면 직접 실행도 살고(순찰·손버릇) 수집은 pytest 가 하므로 드리프트가 불가능하다.
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__] + _sys.argv[1:]))
