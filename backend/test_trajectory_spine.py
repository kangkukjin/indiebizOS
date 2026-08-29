"""최소 trajectory 척추 회귀.

episode memory 를 장황하게 만드는 대신 request/IBL/side-effect/end 핵심 사건만
append-only 순번으로 잇고, episode/task/write_ledger 가 같은 run_id 로 조인되는지 본다.
"""
import json
import importlib.util
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: E402,F401


def _tmp_db(tmp_path):
    import episode_logger as el
    path = str(tmp_path / "world_pulse.db")

    def get_db():
        conn = sqlite3.connect(path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    original = el._get_db
    el._get_db = get_db
    el._ensure_episode_tables()
    return path, original


def test_core_events_share_one_run_without_raw_payloads(tmp_path):
    import episode_logger as el
    import thread_context as tc
    import write_ledger as wl
    from system_tools_ibl import _execute_ibl_unified

    db_path, original_db = _tmp_db(tmp_path)
    original_ledger = wl._LEDGER_PATH
    wl._LEDGER_PATH = tmp_path / "write_ledger.jsonl"
    task_id = "task_trajectory_probe"
    try:
        tc.set_current_task_id(task_id)
        el.EpisodeLogger.start_episode("probe", "비밀 원문을 trajectory에 복제하지 마")
        ep = el.EpisodeLogger.current()
        assert ep is not None and ep.episode_id

        wl.log_write(tmp_path / "data" / "result.txt", gate="test", size=7)
        raw = _execute_ibl_unified({}, str(tmp_path), agent_id="probe")
        assert json.loads(raw).get("error")
        el.EpisodeLogger.end_episode()

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        episode = conn.execute(
            "SELECT run_id, task_id FROM episode_log WHERE id=?", (ep.episode_id,)
        ).fetchone()
        summary = conn.execute(
            "SELECT run_id FROM episode_summary WHERE episode_id=?", (ep.episode_id,)
        ).fetchone()
        events = conn.execute(
            "SELECT event_seq, kind, data FROM trajectory_event WHERE run_id=? "
            "ORDER BY event_seq", (episode["run_id"],)
        ).fetchall()
        conn.close()

        assert episode["task_id"] == task_id
        assert episode["run_id"] == el.trajectory_run_id(task_id)
        assert summary["run_id"] == episode["run_id"]
        assert [r["event_seq"] for r in events] == list(range(1, len(events) + 1))
        assert [r["kind"] for r in events] == [
            "request.received", "side_effect.write", "ibl.started",
            "ibl.finished", "run.ended",
        ]

        request_data = json.loads(events[0]["data"])
        ibl_data = json.loads(events[2]["data"])
        assert "비밀 원문" not in events[0]["data"]
        assert request_data["message_chars"] > 0 and request_data["message_sha256"]
        assert "code_sha256" in ibl_data and "code" not in ibl_data

        ledger = json.loads(wl._LEDGER_PATH.read_text(encoding="utf-8").strip())
        assert ledger["run"] == episode["run_id"]
        assert ledger["episode_id"] == ep.episode_id
        assert ledger["event_seq"] == 2
    finally:
        if el.EpisodeLogger.current() is not None:
            el.EpisodeLogger.end_episode()
        tc.clear_current_task_id()
        wl._LEDGER_PATH = original_ledger
        el._get_db = original_db


def test_same_task_continues_sequence_after_process_like_reentry(tmp_path):
    import episode_logger as el

    db_path, original_db = _tmp_db(tmp_path)
    task_id = "task_reentry"
    run_id = el.trajectory_run_id(task_id)
    try:
        with el.trajectory_scope(task_id=task_id):
            first = el.record_trajectory_event("probe.first")
        with el.trajectory_scope(task_id=task_id):
            second = el.record_trajectory_event("probe.second")
        assert first["run_id"] == second["run_id"] == run_id
        assert (first["event_seq"], second["event_seq"]) == (1, 2)

        conn = sqlite3.connect(db_path)
        seqs = [r[0] for r in conn.execute(
            "SELECT event_seq FROM trajectory_event WHERE run_id=? ORDER BY event_seq",
            (run_id,)).fetchall()]
        conn.close()
        assert seqs == [1, 2]
    finally:
        el._get_db = original_db


def test_task_rows_carry_child_and_parent_run_ids(tmp_path):
    from conversation_db import ConversationDB
    from episode_logger import trajectory_run_id

    db = ConversationDB(str(tmp_path / "conversation.db"))
    db.create_task("task_child", "user", "gui", "do it", "agent",
                   parent_task_id="task_parent")
    row = db.get_task("task_child")
    assert row["run_id"] == trajectory_run_id("task_child")
    assert row["parent_run_id"] == trajectory_run_id("task_parent")


def test_self_body_trajectory_recalls_by_all_three_ids_and_latest(tmp_path):
    import episode_logger as el
    import thread_context as tc

    db_path, original_db = _tmp_db(tmp_path)
    original_source = el._episode_source
    el._episode_source = lambda: "usage"  # self:body 기본 읽기는 시험분을 삶에서 거른다
    task_id = "task_body_recall"
    try:
        tc.set_current_task_id(task_id)
        el.EpisodeLogger.start_episode("probe", "원문은 trajectory items에 없어야 한다")
        ep = el.EpisodeLogger.current()
        el.record_trajectory_event("validation.completed", {"achieved": True})
        el.EpisodeLogger.end_episode()

        body_path = os.path.join(os.path.dirname(__file__), "..", "data", "packages",
                                 "installed", "tools", "system_essentials", "body_ops.py")
        spec = importlib.util.spec_from_file_location("body_ops_trajectory_test", body_path)
        body_ops = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(body_ops)

        probes = [
            {"episode_id": ep.episode_id},
            {"task_id": task_id},
            {"run_id": ep.trajectory.run_id},
            {},  # 식별자 없음 = 최근 실사용 episode
        ]
        for params in probes:
            out = body_ops.op_trajectory({"op": "trajectory", **params})
            assert out["success"] and out["items"], out
            assert out["run_id"] == ep.trajectory.run_id
            assert [r["event_seq"] for r in out["items"]] == [1, 2, 3]
            assert "원문은" not in json.dumps(out, ensure_ascii=False)

        bad = body_ops.op_trajectory({"run_id": ep.trajectory.run_id,
                                      "episode_id": ep.episode_id})
        assert bad["success"] is False and "하나만" in bad["message"]
        bad_id = body_ops.op_trajectory({"episode_id": "abc"})
        assert bad_id["success"] is False and "정수" in bad_id["message"]
    finally:
        if el.EpisodeLogger.current() is not None:
            el.EpisodeLogger.end_episode()
        tc.clear_current_task_id()
        el._episode_source = original_source
        el._get_db = original_db


def test_snapshot_restore_carries_trajectory_across_thread_hop(tmp_path):
    """스레드 이음매(snapshot→restore)가 궤적 신원을 나른다 — 2026-08-29 척추 수리의 관문.

    이게 깨지면 핸들러 타임아웃 스레드·오프로드풀·병렬 분기에서 실행되는 쓰기·사건이
    전부 고아 run 으로 되돌아간다(write_ledger run 0% 결손의 재발)."""
    import threading
    import episode_logger as el
    import thread_context as tc
    import write_ledger as wl

    db_path, original_db = _tmp_db(tmp_path)
    original_ledger = wl._LEDGER_PATH
    wl._LEDGER_PATH = tmp_path / "write_ledger.jsonl"
    box = {}
    try:
        with el.trajectory_scope(task_id="task_hop") as trace:
            snap = tc.snapshot()
            outside_snap = None

            def _worker():
                tc.restore(snap)
                box["ev"] = el.record_trajectory_event("probe.hop")
                wl.log_write(tmp_path / "data" / "hop.txt", gate="test", size=3)
                # 풀 스레드 재사용 시뮬레이션 — trace 없는 스냅샷 복원이 잔류를 청소한다
                tc.restore(outside_snap)
                box["stale"] = el.current_trajectory_identity()

            outside_snap = {k: v for k, v in snap.items() if k != "_trajectory_trace"}
            t = threading.Thread(target=_worker)
            t.start()
            t.join(5)

        assert box["ev"] and box["ev"]["run_id"] == trace.run_id
        assert box["stale"]["run_id"] == ""  # 잔류 청소 (남의 run 에 실리지 않는다)
        ledger = json.loads(wl._LEDGER_PATH.read_text(encoding="utf-8").strip())
        assert ledger["run"] == trace.run_id  # 워커의 쓰기가 부모 run 에 실렸다
        assert ledger["event_seq"] == box["ev"]["event_seq"] + 1
    finally:
        wl._LEDGER_PATH = original_ledger
        el._get_db = original_db


def test_routing_timeout_thread_inherits_trajectory(tmp_path):
    """핸들러 타임아웃 스레드(ibl_routing._run_sync_with_timeout)가 실제로 척추를 잇는다."""
    import episode_logger as el
    from ibl_routing import _run_sync_with_timeout

    db_path, original_db = _tmp_db(tmp_path)
    try:
        with el.trajectory_scope(task_id="task_timeout_hop") as trace:
            ev = _run_sync_with_timeout(
                lambda: el.record_trajectory_event("probe.timeout_hop"),
                (), 5.0, "probe")
        assert ev and ev["run_id"] == trace.run_id
    finally:
        el._get_db = original_db


def test_trajectory_scope_adopts_reentry_identity(tmp_path):
    """재진입 봉투가 복원한 episode/parent run 이 자식 run 의 사건 행에 실린다."""
    import episode_logger as el

    db_path, original_db = _tmp_db(tmp_path)
    try:
        with el.trajectory_scope(task_id="task_reentry_ident",
                                 parent_run_id="run_parent_probe",
                                 episode_id=77) as trace:
            ev = el.record_trajectory_event("probe.reentry")
            assert ev["episode_id"] == 77

        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT episode_id, parent_run_id FROM trajectory_event "
            "WHERE run_id=? AND event_seq=?", (trace.run_id, ev["event_seq"])).fetchone()
        conn.close()
        assert row == (77, "run_parent_probe")
    finally:
        el._get_db = original_db


def test_ibl_finished_lifts_honesty_markers(tmp_path, monkeypatch):
    """봉투의 정직 표지가 ibl.finished 에 집계로 실린다 — success:true 한 줄 증발 방지."""
    import episode_logger as el
    import system_tools_ibl as sti

    db_path, original_db = _tmp_db(tmp_path)
    # 표지는 엔진이 봉투 최상위로 승격시킨다(HONESTY_KEYS 한 벌) — 여기는 그 최상위를 읽는다.
    envelope = {
        "success": True,
        "_fallback_used": True,           # 플래그 → 1
        "error_count": 2,                 # 수량 → 값
        "skipped_steps": ["a", "b"],      # 목록 → 길이 (원문은 싣지 않는다)
        "halted": False,                  # falsy → 미탑재
    }
    monkeypatch.setattr(sti, "_execute_ibl_unified_impl", lambda *a, **k: envelope)
    try:
        raw = sti._execute_ibl_unified({"code": "[sense:probe]{}"}, str(tmp_path),
                                       agent_id="probe")
        out = raw if isinstance(raw, dict) else json.loads(raw)
        assert out["success"] is True

        conn = sqlite3.connect(db_path)
        data = json.loads(conn.execute(
            "SELECT data FROM trajectory_event WHERE kind='ibl.finished' "
            "ORDER BY ts DESC LIMIT 1").fetchone()[0])
        conn.close()
        assert data["markers"] == {"_fallback_used": 1, "error_count": 2,
                                   "skipped_steps": 2}
        assert "halted" not in data["markers"]
    finally:
        el._get_db = original_db


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
