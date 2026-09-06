"""에피소드 태스크 명시 바인딩 회귀 (2026-09-06, ep2904/ep2905)

재현한 결함: WebSocket 핸들러는 이벤트 루프 *한 스레드*에서 여러 턴을 동시에 연다.
threading.local 의 task_id 는 그 스레드 안에서 전역이라, 새 턴이 시작 시점에 상속한 값은
*아직 도는 이웃 턴의* 태스크였다 — 15:00 시스템 AI 턴(ep2905)이 14:45 설계 에이전트 턴(ep2904)의
task_e64c9313 을 물려받아 run 을 공유하고, 15:08 에 그 run 을 종료 처리했다(설계는 15:21 까지 계속
그 run 에 썼다). trajectory 30일 12건·에이전트 쌍 8가지.

처방: start_episode(task_id=…) 명시 바인딩 — 자기 태스크를 아는 진입점은 넘기고, None 일 때만 상속.

실행: .venv/bin/python -m pytest backend/test_episode_task_binding_2026_09_06.py -q
"""
import ast
import os
import sqlite3
import sys

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401

BACKEND = os.path.dirname(os.path.abspath(__file__))


def _tmp_db(tmp_path):
    import episode_logger as EL
    path = str(tmp_path / "world_pulse.db")

    def _get_db():
        conn = sqlite3.connect(path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    orig = EL._get_db
    EL._get_db = _get_db
    EL._ensure_episode_tables()
    return path, orig


def test_explicit_task_wins_over_stale_thread_local(tmp_path):
    import episode_logger as EL
    from thread_context import set_current_task_id, clear_current_task_id
    path, orig = _tmp_db(tmp_path)
    try:
        set_current_task_id("task_neighbor1")          # 이웃 턴이 같은 스레드에 남긴 값
        EL.EpisodeLogger.start_episode("system_ai", "바인딩 시험", task_id="task_mine0001")
        ep = EL._current_episode.get(None)
        assert ep is not None
        assert ep.task_id == "task_mine0001"
        assert ep.trajectory.run_id == EL.trajectory_run_id("task_mine0001")
        assert ep.trajectory.run_id != EL.trajectory_run_id("task_neighbor1")
        EL.EpisodeLogger.end_episode()
        conn = sqlite3.connect(path)
        row = conn.execute("SELECT task_id, run_id FROM episode_log ORDER BY id DESC LIMIT 1").fetchone()
        assert row[0] == "task_mine0001" and row[1] == EL.trajectory_run_id("task_mine0001")
    finally:
        clear_current_task_id()
        EL._get_db = orig


def test_none_still_inherits_for_sync_entrypoints(tmp_path):
    """동기 워커 스레드 진입점(HTTP /system-ai/chat 등)은 한 턴 = 한 스레드라 상속이 옳다 — 유지."""
    import episode_logger as EL
    from thread_context import set_current_task_id, clear_current_task_id
    path, orig = _tmp_db(tmp_path)
    try:
        set_current_task_id("task_worker001")
        EL.EpisodeLogger.start_episode("system_ai", "상속 시험")
        ep = EL._current_episode.get(None)
        assert ep.task_id == "task_worker001"
        EL.EpisodeLogger.end_episode()
    finally:
        clear_current_task_id()
        EL._get_db = orig


def test_ws_handlers_bind_task_before_episode():
    """관문: 이벤트 루프 스레드의 두 스트림 핸들러는 start_episode 에 task_id= 를 넘긴다 (AST)."""
    src = open(os.path.join(BACKEND, "surface", "api_websocket.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    seen = {}
    for fn in tree.body:
        if isinstance(fn, ast.AsyncFunctionDef) and fn.name in ("handle_chat_message_stream", "handle_system_ai_chat_stream"):
            for c in ast.walk(fn):
                if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == "start_episode":
                    seen[fn.name] = {k.arg for k in c.keywords}
    assert set(seen) == {"handle_chat_message_stream", "handle_system_ai_chat_stream"}, seen
    for name, kws in seen.items():
        assert "task_id" in kws, f"{name}: start_episode 가 task_id 명시 바인딩 없이 열린다 — 이웃 턴의 태스크를 상속한다"


if __name__ == "__main__":                      # 러너는 하나 — pytest
    import sys as _sys
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__] + _sys.argv[1:]))
