"""HTTP 작업 완료는 답변 저장과 대화 턴 해제 뒤에 공개한다."""
import threading
import sqlite3
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
import api_system_ai as api
import conversation_sessions as sessions
import system_ai_memory as memory
import thread_context as tc


@pytest.fixture
def http_chat(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "MEMORY_DB_PATH", tmp_path / "memory.db")
    monkeypatch.setattr(memory, "DATA_PATH", tmp_path)
    monkeypatch.setattr(memory, "_ckpt_schedule", None)
    monkeypatch.setattr(memory, "_ckpt_apply", None)
    monkeypatch.setattr(api, "_docs_initialized", True)
    monkeypatch.setattr(api, "load_system_ai_config", lambda: {
        "enabled": True, "provider": "ollama", "model": "fixture"})
    monkeypatch.setattr(api, "_images_from_response_paths", lambda *a: [])
    monkeypatch.setattr("episode_logger.EpisodeLogger", SimpleNamespace(
        start_episode=lambda *a: None, end_episode=lambda *a: None))
    memory.init_memory_db()
    calls = []

    def respond(**kwargs):
        calls.append({"binding": sessions.current(), "history": kwargs["history"]})
        sessions.record_event({"type": "test.result", "actor": "system_ai",
                               "response": "저장 확인", "completed": True})
        return "저장 확인", []

    monkeypatch.setattr(api, "process_system_ai_message", respond)
    previous = tc.snapshot()
    tc.clear_all_context()
    yield calls
    tc.restore(previous)


@pytest.mark.parametrize("gate", ["save", "finish"])
def test_background_completion_waits_for_saved_reply_and_released_turn(http_chat, monkeypatch, gate):
    entered, release = threading.Event(), threading.Event()
    original_save, original_finish = api.save_conversation, sessions.SessionStore.finish

    def save(role, *args, **kwargs):
        if gate == "save" and role == "assistant":
            entered.set()
            assert release.wait(5)
        return original_save(role, *args, **kwargs)

    def finish(store, binding, *args, **kwargs):
        if gate == "finish":
            entered.set()
            assert release.wait(5)
        return original_finish(store, binding, *args, **kwargs)

    monkeypatch.setattr(api, "save_conversation", save)
    monkeypatch.setattr(sessions.SessionStore, "finish", finish)
    receipt = api.chat_with_system_ai(api.ChatMessage(
        message="파일을 저장해", origin="training", background=True))
    try:
        assert entered.wait(5)
        observed = api.get_system_ai_task(receipt.task_id)
    finally:
        release.set()
    # 실패해도 작업자를 회수하고 임시 DB/monkeypatch 수명 밖으로 내보내지 않는다.
    final = api.get_system_ai_task(receipt.task_id, wait=5)
    assert observed["state"] not in {"succeeded", "failed", "cancelled"}
    assert final["state"] == "succeeded"
    binding = http_chat[0]["binding"]
    with sessions.connection(memory.MEMORY_DB_PATH) as conn:
        assert conn.execute("SELECT state FROM conversation_turns WHERE id=?",
                            (binding.turn_id,)).fetchone()[0] == "completed"
        assert conn.execute("SELECT content FROM conversations WHERE session_id=? AND role='assistant'",
                            (binding.session_id,)).fetchone()[0] == "저장 확인"
    # 완료를 본 즉시 후속을 보내도 소유권과 직전 답변이 함께 있어야 한다.
    api.chat_with_system_ai(api.ChatMessage(message="방금 결과를 확인해", origin="training"))
    assert http_chat[1]["binding"] is not None
    assert http_chat[1]["binding"].session_id == binding.session_id
    assert any(row["content"] == "저장 확인" for row in http_chat[1]["history"])


def test_reply_save_failure_never_publishes_success(http_chat, monkeypatch):
    original = api.save_conversation

    def save(role, content, **kwargs):
        if role == "assistant" and not content.startswith("[실패]"):
            raise OSError("reply storage failed")
        return original(role, content, **kwargs)

    monkeypatch.setattr(api, "save_conversation", save)
    monkeypatch.setattr(api.threading, "Thread", lambda target, **kw: SimpleNamespace(start=target))
    receipt = api.chat_with_system_ai(api.ChatMessage(message="저장", origin="training", background=True))
    view = api.get_system_ai_task(receipt.task_id)
    assert view["state"] == "failed"
    assert "reply storage failed" in view["error"]


def test_turn_close_failure_never_publishes_success(http_chat, monkeypatch):
    def fail_finish(*args, **kwargs):
        raise sqlite3.OperationalError("turn storage failed")

    monkeypatch.setattr(sessions.SessionStore, "finish", fail_finish)
    monkeypatch.setattr(api.threading, "Thread", lambda target, **kw: SimpleNamespace(start=target))
    receipt = api.chat_with_system_ai(api.ChatMessage(message="저장", origin="training", background=True))
    view = api.get_system_ai_task(receipt.task_id)
    assert view["state"] == "failed"
    assert "turn storage failed" in view["error"]


def test_pending_delegation_is_not_completed_by_http_wrapper(http_chat, monkeypatch):
    def delegated(**kwargs):
        memory.update_task_delegation(tc.get_current_task_id(), "{}", increment_pending=True)
        tc.set_called_agent()
        return "자식 대기", []

    monkeypatch.setattr(api, "process_system_ai_message", delegated)
    response = api.chat_with_system_ai(api.ChatMessage(message="위임", origin="training"))
    assert "위임 중" in response.response
    assert api.get_system_ai_task(response.task_id)["state"] == "waiting_children"


@pytest.mark.parametrize('fail', [False, True])
def test_http_route_progress_is_visible_during_turn_and_cleared_after(http_chat, monkeypatch, fail):
    import json
    import ibl_progress
    import supervision_bus
    observed = {}

    def respond(**kwargs):
        binding = sessions.current()
        task_id = tc.get_current_task_id()
        ibl_progress.report_step(None, 3, 0, 'self:read', reused=True)
        ibl_progress.beat({'row': 2, 'rows': 5, 'phase': 'compute'})
        with sessions.connection(binding.db_path) as conn:
            progress = json.loads(conn.execute('SELECT progress FROM conversation_turns WHERE id=?',
                                               (binding.turn_id,)).fetchone()[0])
        observed.update(binding=binding, task=task_id, progress=progress)
        if fail:
            raise RuntimeError('controlled failure')
        return 'done', []

    monkeypatch.setattr(api, 'process_system_ai_message', respond)
    monkeypatch.setattr(api.threading, 'Thread', lambda target, **kw: SimpleNamespace(start=target))
    receipt = api.chat_with_system_ai(api.ChatMessage(message='progress', origin='training', background=True))
    view = api.get_system_ai_task(receipt.task_id)
    assert view['state'] == ('failed' if fail else 'succeeded')
    assert observed['progress']['step'] == 3 and observed['progress']['reused']
    assert observed['progress']['detail'] == {'row': 2, 'rows': 5, 'phase': 'compute'}
    assert observed['task'] not in supervision_bus._progress_sinks
    with sessions.connection(observed['binding'].db_path) as conn:
        assert conn.execute('SELECT progress FROM conversation_turns WHERE id=?',
                            (observed['binding'].turn_id,)).fetchone()[0] == ''


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))


# ── 대화 턴을 열지 못한 요청은 실행하지 않는다(무소유 실행 없음, 2026-11-11) ──

def _running_turn(owner="rehearsal"):
    store = sessions.SessionStore(memory.MEMORY_DB_PATH, "conversations", owner)
    with sessions.connection(store.path) as conn:
        sid = sessions.resolve(conn, store.path, owner, "conversations")
    return store, store.begin(sid)


@pytest.mark.parametrize("background", [False, True])
def test_concurrent_request_on_the_same_conversation_is_409_before_any_work(http_chat, monkeypatch, background):
    store, running = _running_turn()
    monkeypatch.setattr(api.threading, "Thread", lambda target, **kw: SimpleNamespace(start=target))
    try:
        with pytest.raises(api.HTTPException) as refused:
            api.chat_with_system_ai(api.ChatMessage(message="동시에 하나 더", origin="training", background=background))
    finally:
        store.finish(running)
    assert refused.value.status_code == 409 and "이미 실행 중" in refused.value.detail
    assert http_chat == []  # 모델 호출 0
    with sqlite3.connect(memory.MEMORY_DB_PATH) as conn:
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0  # 미리 만든 작업도 없다
        assert conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 0  # 진행 중인 대화에 글을 끼우지 않는다
        assert conn.execute("SELECT COUNT(*) FROM conversation_turns WHERE state='running'").fetchone()[0] == 0
    # 앞선 턴이 끝나면 같은 대화의 다음 요청은 정상 소유로 실행된다.
    api.chat_with_system_ai(api.ChatMessage(message="이어서", origin="training"))
    assert http_chat[0]["binding"].session_id == running.session_id and http_chat[0]["binding"].turn_id != running.turn_id


def test_conversation_store_failure_is_a_retryable_503_not_an_unowned_run(http_chat, monkeypatch):
    def broken(self, sid):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(sessions.SessionStore, "begin", broken)
    with pytest.raises(api.HTTPException) as refused:
        api.chat_with_system_ai(api.ChatMessage(message="저장소 장애", origin="training"))
    assert refused.value.status_code == 503 and refused.value.headers == {"Retry-After": "5"}
    assert http_chat == []
    with sqlite3.connect(memory.MEMORY_DB_PATH) as conn:
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0


def test_failure_before_the_turn_scope_leaves_no_running_turn(http_chat, monkeypatch):
    def broken(**kwargs):
        raise RuntimeError("작업 원장 쓰기 실패")
    monkeypatch.setattr(api, "create_system_ai_task", broken, raising=False)
    monkeypatch.setattr(memory, "create_task", broken)
    with pytest.raises(RuntimeError):
        api.chat_with_system_ai(api.ChatMessage(message="접수 실패", origin="training"))
    with sqlite3.connect(memory.MEMORY_DB_PATH) as conn:
        rows = conn.execute("SELECT state,error FROM conversation_turns").fetchall()
    assert rows == [("failed", "작업 원장 쓰기 실패")]


def test_tool_reentry_adopts_the_parent_turn_instead_of_opening_a_conversation_turn(http_chat, monkeypatch):
    """내부 IBL 재진입은 부모의 활성 binding 을 채택할 뿐 새 턴을 열지 않는다 — busy 로 막히면 안 된다."""
    import execution_turn
    import principal
    import resident_pcs
    seen = []

    def respond(**kwargs):
        conversation = sessions.current()
        binding = execution_turn.Binding(None, "system_ai", tc.get_current_task_id(), aliases={"system_ai"},
                                         context={}, conversation=conversation, principal=principal.current())
        with execution_turn._lock:
            execution_turn._sessions[binding.task] = binding
        try:
            def reenter():  # MCP→HTTP 재진입은 다른 스레드다
                with execution_turn.adopt_session("system_ai", binding.task) as adopted:
                    seen.append((adopted is binding, resident_pcs.attribution()))
            worker = threading.Thread(target=reenter)
            worker.start()
            worker.join(5)
        finally:
            with execution_turn._lock:
                execution_turn._sessions.pop(binding.task, None)
        return "재진입 확인", []

    monkeypatch.setattr(api, "process_system_ai_message", respond)
    api.chat_with_system_ai(api.ChatMessage(message="도구를 쓰는 턴", origin="training"))
    adopted, origin = seen[0]
    assert adopted and origin["basis"] == "execution_turn" and origin["conversation"]["owner"] == "rehearsal"
    assert origin["conversation"]["turn_id"]
