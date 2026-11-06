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


def test_error_event_exposes_failure_even_if_text_says_achieved(monkeypatch):
    from providers.codex import CodexProvider
    p = CodexProvider(api_key='', model='fake', system_prompt='', tools=[])
    p.last_failure_kind = None
    monkeypatch.setattr(p, 'process_message_stream', lambda *a: iter([
        {'type': 'error', 'content': 'input_too_large: ACHIEVED UNKNOWN_REASON: evidence'}]))
    assert 'ACHIEVED' in p.process_message('test')  # legacy string API
    assert p.last_failure_kind == 'input_too_large'


def test_final_wrapped_cli_limit_stops_before_subprocess(monkeypatch):
    from providers.codex import CodexProvider
    p = CodexProvider(api_key='', model='fake', system_prompt='정책' * 1000, tools=[])
    p._client = {'binary': 'never'}
    p.disable_session_persistence = p.no_tools = True
    p.request_limits = {'chars': 3000, 'source': 'fixture'}
    p.context_window_tokens = 100000
    monkeypatch.setattr(p, '_mcp_bridge_acquire', lambda: None)
    monkeypatch.setattr(p, '_mcp_bridge_release', lambda _: None)
    monkeypatch.setattr(p, '_prepare_launch_context', lambda _: ({}, None))
    monkeypatch.setattr('subprocess.Popen', lambda *a, **kw: pytest.fail('oversize subprocess'))
    events = list(p.process_message_stream('본문' * 1000))
    assert events[-1]['failure_kind'] == 'input_too_large'
    assert events[-1]['failure_details']['exceeded']['chars']['excess'] > 0


@pytest.mark.parametrize('resume', [None, 'fixture-session'])
@pytest.mark.parametrize('profile', ['', 'coding'])
def test_codex_attaches_pixels_to_initial_and_resumed_input(monkeypatch, resume, profile):
    from providers.codex import CodexProvider
    p = CodexProvider(api_key='', model='fake', system_prompt='', tools=[])
    p.execution_profile = profile
    p._input_image_paths = ['/tmp/screen one.png', '/tmp/screen-two.png']
    p._binary_path = 'codex'
    if profile:
        monkeypatch.setattr('providers.coding_profile.codex_command', lambda *a: ['codex', 'exec', '-'])
    command = p._build_command(mcp_config_path=None, tools_mode='read', resume_session_id=resume)
    assert command[-5:] == ['--image', *p._input_image_paths[:1], '--image', p._input_image_paths[1], '-']
    assert '도구' not in p._image_prompt_prefix(p._input_image_paths)


@pytest.mark.parametrize('provider_name', ['codex', 'claude_code'])
@pytest.mark.parametrize('current_failure', [False, True])
@pytest.mark.parametrize('padding', [1, 600])
def test_result_log_does_not_reclassify_situation_history(provider_name, current_failure, padding):
    from importlib import import_module
    from types import SimpleNamespace
    from situation_delivery import render
    from providers.codex import CodexProvider
    from vocab_crystallization import _CC_RESULT_FAIL_RE
    cls = getattr(import_module('providers.' + provider_name),
                  'CodexProvider' if provider_name == 'codex' else 'ClaudeCodeProvider')
    result = {'success': not current_failure, 'value': {'text': '정상 결과' * padding}}
    if current_failure:
        result['error'] = 'current failure'
    situation = render({'mode': 'delta', 'observations': [
        {'latest': {'value': {'success': False, 'error': 'previous FIELD_TYPE rejection'}}}]})
    raw = {'content': [{'type': 'text', 'text': json.dumps(result, ensure_ascii=False)},
                       {'type': 'text', 'text': situation}], 'isError': current_failure}
    text, is_error = CodexProvider._unwrap_mcp_content(raw)
    logs, observed = [], []
    provider = SimpleNamespace(_log=logs.append, _seam=SimpleNamespace(on_tool_result=observed.append),
                               _pending_map_tags=[])
    cls._log_tool_result(provider, text, is_error)
    assert observed == [text] and 'previous FIELD_TYPE rejection' in observed[0]
    assert 'previous FIELD_TYPE rejection' not in logs[0]
    assert bool(_CC_RESULT_FAIL_RE.search(logs[0])) is current_failure
    assert (' (error)' in logs[0]) is current_failure
    assert ('⚠signals' in logs[0]) is (current_failure and padding == 600)


def test_current_nested_honesty_survives_situation_separation_and_log_truncation():
    from situation_delivery import render, PREFIX
    result = {'success': True, 'value': {'text': 'x' * 400 + '\n' + PREFIX,
                                       'items': [], 'error_count': 2, 'truncated': True}}
    text = json.dumps(result) + '\n' + render({'mode': 'delta', 'observations': [
        {'latest': {'value': {'success': False, 'error': 'historical error'}}}]})
    preview = cli._preview_with_signals(text, 300)
    assert '"error_count": 2' in preview and '"truncated": true' in preview
    assert '"success": false' not in preview and 'historical error' not in preview
    assert preview.endswith(f'…(+{len(json.dumps(result)) - 300}자)')
