"""세션 매핑의 실제 전후 상태와 실패 보고. 사용자 라이브 세션은 변경하지 않는다."""
import json
import boot_paths  # noqa: F401
import pytest
from providers import cli_provider as cli
from test_conversation_sessions import project  # noqa: F401


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_SESSION_STORES", [])
    monkeypatch.setattr(cli, "_data_dir", lambda: tmp_path)
    return cli.CliSessionStore("fixture", "fixture")


def test_reset_removes_only_selected_session_and_derivatives(store):
    key = "system:system_ai@session:a"
    original = {key: "first", key + "#policy": "second", "system:system_ai@session:b": "keep", "other": "keep"}
    store.save_map(original); store.save_sizes({k: 100 for k in original})
    result = cli.clear_sessions_for_agent(key)
    assert result["ok"] and result["removed"] == 2
    assert store.load_map() == {k: v for k, v in original.items() if k not in (key, key + "#policy")}
    assert set(store.load_sizes()) == set(store.load_map())
    assert cli.clear_sessions_for_agent(key)["removed"] == 0


@pytest.mark.parametrize("failure", ["write", "decode"])
def test_reset_reports_real_storage_failure(store, monkeypatch, failure):
    store.save_map({"agent": "kept"})
    if failure == "write":
        def deny(*args): raise OSError("fixture read-only")
        monkeypatch.setattr("restart_protocol.atomic_json", deny)
    else:
        store.map_path().write_text("broken json")
    result = cli.clear_sessions_for_agent("agent")
    assert result["ok"] is False and result["error"] and result["removed"] == 0
    if failure == "write":
        assert store.load_map() == {"agent": "kept"}


def test_natural_handler_reports_failure_without_success_claim(monkeypatch):
    from cognitive_consciousness import handle_session_reset
    monkeypatch.setattr("thread_context.get_current_registry_key", lambda: "agent")
    monkeypatch.setattr("providers.clear_cli_sessions_for_agent", lambda key: {"ok": False, "error": "write failed"})
    result = handle_session_reset()
    assert "실패" in result and "시작했습니다" not in result


def test_explicit_api_and_natural_handler_use_the_same_owned_session(project, store, monkeypatch):
    import conversation_sessions as sessions
    import chat_session_service as service
    from cognitive_consciousness import handle_session_reset
    db, user, agent, conversation_store = project
    sid = conversation_store.create("selected")["id"]
    other = conversation_store.create("other")["id"]
    monkeypatch.setattr(service, "store_for", lambda *a: (conversation_store, {"id": "agent"}))
    monkeypatch.setattr("thread_context.get_current_registry_key", lambda: "project:agent")
    key = "project:agent@session:" + sid
    mapping = {key + "#policy": "reset", "project:agent@session:" + other: "keep"}
    with sessions.scope(sessions.Binding(conversation_store.path, sid, conversation_store.owner)):
        store.save_map(mapping)
        result = service.reset_cli_session("agent", "project", "agent")
        assert result["ok"] and result["key"] == key and result["removed"] == 1
        after_api = store.load_map()
        store.save_map(mapping)
        assert "매핑을 제거했습니다" in handle_session_reset()
        assert store.load_map() == after_api
    assert len(conversation_store.list()) == 3  # 대화와 영속 기록은 삭제하지 않는다.


def test_reset_apis_preserve_failure_result(monkeypatch):
    import asyncio
    import api_agents
    import api_system_ai
    result = {"ok": False, "error": "fixture write failed", "removed": 0}
    calls = []
    def reset(*args):
        calls.append(args)
        return result
    monkeypatch.setattr("chat_session_service.reset_cli_session", reset)
    assert asyncio.run(api_agents.reset_agent_session("p", "a")) == result
    assert asyncio.run(api_system_ai.reset_system_ai_session()) == result
    assert calls == [("agent", "p", "a"), ("system_ai",)]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
