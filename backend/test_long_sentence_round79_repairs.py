"""긴문장 79회차 L79-1: HTTP /system-ai/chat 턴의 대화 소유권 — REFLEX 적격·영수증·동시성 보존."""
import inspect
from types import SimpleNamespace as NS

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


def _short_history():
    return [{"role": "user", "content": "삼성1에서 음악 틀어"},
            {"role": "assistant", "content": "삼성1에서 재생했습니다."}]


def _runner():
    return NS(ai=NS(agent_id="system_ai", _provider=NS(model="opus")), config={"name": "system_ai"})


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


def test_reflex_becomes_eligible_only_inside_owned_turn(memory_db):
    import api_system_ai as S
    from reflex_execution import ReflexTurn
    outside = ReflexTurn(_runner(), "음악 꺼", _short_history())
    assert not outside.eligible and outside.reason == "missing_conversation_binding"
    with S._owned_turn("system_ai", "task_r79_reflex"):
        inside = ReflexTurn(_runner(), "음악 꺼", _short_history())
        assert inside.eligible, inside.reason


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


def test_busy_session_falls_back_to_unowned_turn_without_error(memory_db):
    import api_system_ai as S
    store = sessions.SessionStore(memory_db, "conversations", "system_ai")
    with sessions.connection(memory_db) as conn:
        sid = sessions.resolve(conn, str(memory_db), "system_ai", "conversations")
    running = store.begin(sid)  # 동시 요청이 이미 턴을 쥐고 있다
    try:
        with S._owned_turn("system_ai", "task_busy") as binding:
            assert binding is None and sessions.current() is None
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
    assert "_owned_turn(conv_thread, task_id)" in src and "turn_hold(task_id)" in src
    assert "sessions.owned_turn(" in inspect.getsource(S._owned_turn)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__]))
