"""긴문장 79회차 L79-1: HTTP /system-ai/chat 턴의 대화 소유권 — 영수증·동시성 보존."""
import inspect

import boot_paths  # noqa: F401
import pytest
import conversation_sessions as sessions


@pytest.fixture
def memory_db(tmp_path, monkeypatch):
    import system_ai_memory as memory
    path = tmp_path / "system_ai_memory.db"
    monkeypatch.setattr(memory, "MEMORY_DB_PATH", path)
    monkeypatch.setattr(memory, "DATA_PATH", tmp_path)
    memory.init_memory_db()
    return path


def test_http_turn_opens_owner_binding_and_links_task(memory_db):
    import api_system_ai as S
    assert sessions.current() is None
    with S._owned_turn("rehearsal", "task_r79") as binding:
        assert binding is not None and binding.owner == "rehearsal" and binding.turn_id
        assert sessions.current() is binding
        with sessions.connection(memory_db) as conn:
            link = conn.execute("SELECT session_id, turn_id FROM conversation_task_links WHERE task_id='task_r79'").fetchone()
            state = conn.execute("SELECT state FROM conversation_turns WHERE id=?", (binding.turn_id,)).fetchone()[0]
        assert tuple(link) == (binding.session_id, binding.turn_id) and state == "running"
    assert sessions.current() is None
    with sessions.connection(memory_db) as conn:
        assert conn.execute("SELECT state FROM conversation_turns WHERE id=?", (binding.turn_id,)).fetchone()[0] == "completed"


def test_owner_sessions_are_separate_and_match_history_resolution(memory_db):
    import api_system_ai as S
    sids = {}
    for owner in ("system_ai", "rehearsal"):
        with S._owned_turn(owner, f"task_{owner}") as b:
            with sessions.connection(memory_db) as conn:
                # 저장·히스토리가 쓰는 resolve 와 같은 세션이어야 한다(다른 세션이면 영수증이 엇갈린다).
                assert sessions.resolve(conn, str(memory_db), owner, "conversations") == b.session_id
            sids[owner] = b.session_id
    assert sids["system_ai"] != sids["rehearsal"]


def test_busy_session_is_refused_and_the_body_never_runs_unowned(memory_db):
    """2026-11-11: 옛 무소유 fallback 은 없다 — 같은 대화의 동시 요청은 실행하지 않고 명시 오류다."""
    import api_system_ai as S
    store = sessions.SessionStore(memory_db, "conversations", "system_ai")
    with sessions.connection(memory_db) as conn:
        sid = sessions.resolve(conn, str(memory_db), "system_ai", "conversations")
    running = store.begin(sid)  # 동시 요청이 이미 턴을 쥐고 있다
    ran = []
    try:
        with pytest.raises(sessions.TurnUnavailable) as refused:
            with S._owned_turn("system_ai", "task_busy"):
                ran.append(True)
        assert refused.value.kind == "busy" and refused.value.status_code == 409 and not ran
        assert sessions.current() is None
        with sessions.connection(memory_db) as conn:
            assert conn.execute("SELECT COUNT(*) FROM conversation_turns WHERE state='running'").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM conversation_task_links WHERE task_id='task_busy'").fetchone()[0] == 0
    finally:
        store.finish(running)


def test_failure_closes_turn_as_failed_and_propagates(memory_db):
    import api_system_ai as S
    with pytest.raises(RuntimeError):
        with S._owned_turn("system_ai", "task_fail") as binding:
            raise RuntimeError("boom")
    with sessions.connection(memory_db) as conn:
        row = conn.execute("SELECT state, error FROM conversation_turns WHERE id=?", (binding.turn_id,)).fetchone()
    assert tuple(row) == ("failed", "boom")
    assert sessions.current() is None


def test_chat_route_wires_owned_turn_around_processing():
    import api_system_ai as S
    src = inspect.getsource(S.chat_with_system_ai)
    assert "_owned_turn(conv_thread, task_id, opened)" in src and "turn_hold(task_id)" in src
    assert "sessions.owned_turn(" in inspect.getsource(S._owned_turn)
    # 턴은 작업 선발급·모델 호출보다 먼저 연다 — 못 열면 그 앞에서 409/503 으로 끝난다.
    assert src.index("opened = open_turn(") < src.index("create_system_ai_task(") < src.index("def _process()")


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__]))
