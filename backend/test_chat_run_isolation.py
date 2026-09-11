"""실행·연결 교체 경쟁을 실제 asyncio 경계에서 재현한다. 모델/외부 송신/실 DB 없음."""
import boot_paths  # noqa: F401
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from chat_runs import ChatRuns
from websocket_manager import WebSocketManager


def test_replaced_run_keeps_own_cancel_and_cannot_send_to_new_socket():
    async def scenario():
        from execution_workers import bind_context
        registry, manager = ChatRuns(), WebSocketManager()
        a, b = SimpleNamespace(send_json=AsyncMock()), SimpleNamespace(send_json=AsyncMock())
        manager.active_connections['same'] = a
        started, finish = asyncio.Event(), asyncio.Event()
        observations = []

        async def old(client, data):
            read_cancel = bind_context(lambda: registry.is_cancelled(client))
            started.set()
            await finish.wait()
            observations.append(await asyncio.to_thread(read_cancel))
            observations.append(await manager.send_message(client, {'old': True}))

        task = registry.start(old, 'same', {}, a, manager)
        await started.wait()
        registry.detach('same', a)
        assert task in registry.background and not task.done()
        manager.active_connections['same'] = b
        new = registry.begin('same', b)
        registry.cancel('same', a)
        assert not new.cancelled.is_set()
        registry.cancel('same', b)
        finish.set()
        await task
        await asyncio.sleep(0)
        assert observations == [False, False]
        assert registry.active['same'] is new and new.cancelled.is_set()
        assert task not in registry.background
        a.send_json.assert_not_called()
        b.send_json.assert_not_called()
    asyncio.run(scenario())


def test_cancel_before_handler_starts_is_not_reset_and_next_run_is_clean():
    async def scenario():
        registry, manager, connection = ChatRuns(), WebSocketManager(), object()
        observed = []

        async def handler(client, data):
            observed.append(registry.is_cancelled(client))

        task = registry.start(handler, 'same', {}, connection, manager)
        registry.cancel('same', connection)
        await task
        await registry.call(handler, 'same', {}, manager)
        assert observed == [True, False]
        assert registry.current('same') is None
    asyncio.run(scenario())


def test_failed_direct_run_restores_context_and_removes_control_target():
    async def scenario():
        registry, manager = ChatRuns(), WebSocketManager()

        async def broken(client, data):
            assert registry.current(client) is not None
            raise ValueError('execution failed')

        with pytest.raises(ValueError, match='execution failed'):
            await registry.call(broken, 'probe', {}, manager)
        assert registry.current('probe') is None and registry.active == {}
    asyncio.run(scenario())


@pytest.mark.parametrize('route', ['send', 'broadcast', 'agent', 'system', 'launcher'])
def test_late_send_failure_and_disconnect_preserve_replacement(route, monkeypatch):
    async def scenario():
        import websocket_manager as hub
        manager = WebSocketManager()
        client = 'system_ai_probe' if route == 'system' else 'project-agent-probe'
        new = SimpleNamespace(send_json=AsyncMock())

        async def fail_after_replace(payload):
            if route == 'launcher':
                hub.set_launcher_ws(new, asyncio.get_running_loop())
            else:
                manager.active_connections[client] = new
                manager.active_connections['new-recipient'] = new
            raise RuntimeError('connection closed')

        old = SimpleNamespace(send_json=fail_after_replace)
        manager.active_connections[client] = old
        if route == 'launcher':
            monkeypatch.setattr(hub, '_launcher_ws', old)
            monkeypatch.setattr(hub, '_launcher_loop', asyncio.get_running_loop())
            assert not await hub.send_launcher_command('probe')
            hub.clear_launcher_ws(old)
            assert hub.get_launcher_ws() is new
        else:
            if route == 'send':
                assert not await manager.send_message(client, {})
            elif route == 'broadcast':
                await manager.broadcast({})
            elif route == 'agent':
                await manager.send_to_agent_chat('project', 'agent', {})
            else:
                await manager.send_to_system_ai_chat({})
            manager.disconnect(client, old)
            assert manager.active_connections[client] is new
        new.send_json.assert_not_called()
    asyncio.run(scenario())


@pytest.mark.parametrize('provider,key,runner_error', [
    ('openai', 'fixture-env-key', False), ('ollama', '', False),
    ('openai', '', False), ('openai', 'fixture-env-key', True),
])
def test_system_chat_uses_resolved_model_before_creating_task(monkeypatch, provider, key, runner_error):
    import chat_runs
    import chat_streams as streams
    import episode_logger as episodes
    import model_resolver
    import system_ai_core as core
    import system_ai_memory as memory
    import thread_context as tc
    from execution_workers import create_executor
    messages, created, saved, calls = [], [], [], []
    manager = WebSocketManager()

    async def send(client, payload):
        messages.append(payload)

    def runner():
        if runner_error:
            raise ValueError('provider initialization failed')

        def stream(*args, **kwargs):
            calls.append((tc.get_current_task_id(), kwargs['cancel_check']()))
            yield {'type': 'final', 'content': 'fixture result'}
        return SimpleNamespace(cognitive_stream=stream)

    monkeypatch.setattr(chat_runs, 'registry', ChatRuns())
    monkeypatch.setattr(streams, 'manager', manager)
    monkeypatch.setattr(manager, 'send_message', send)
    monkeypatch.setattr(episodes.EpisodeLogger, 'start_episode', lambda *a, **k: None)
    monkeypatch.setattr(episodes.EpisodeLogger, 'end_episode', lambda: None)
    monkeypatch.setattr(model_resolver, 'resolve', lambda role: {
        'provider': provider, 'model': 'gear-fixture-model', 'api_key': key})
    # 기어가 유효하면 이 옛 파일을 읽거나 키 검사에 쓰지 않는다.
    monkeypatch.setattr(core, 'load_system_ai_config', lambda: pytest.fail('raw config preflight'))
    monkeypatch.setattr(core, 'get_system_ai_runner', runner)
    monkeypatch.setattr(memory, 'create_task', lambda **kw: created.append(kw))
    monkeypatch.setattr(memory, 'delete_task', lambda *a: None)
    monkeypatch.setattr(memory, 'get_task', lambda *a: None)
    monkeypatch.setattr(memory, 'save_conversation', lambda *a, **kw: saved.append(a))
    monkeypatch.setattr(memory, 'get_history_for_ai', lambda **kw: [])
    before = tc.snapshot()
    try:
        tc.restore({'future_loop_identity': 'must remain'})
        loop_before = tc.snapshot()
        with create_executor('test-chat', max_workers=1) as pool:
            monkeypatch.setattr(streams, 'executor', pool)

            async def scenario():
                await asyncio.wait_for(streams.handle_system_ai_chat_stream('probe', {'message': 'test'}), 3)
            asyncio.run(scenario())
        assert tc.snapshot() == loop_before
    finally:
        tc.restore(before)
    if provider == 'openai' and not key:
        assert created == saved == calls == []
        assert messages[-1]['type'] == 'error'
    elif runner_error:
        assert any(m.get('message') == 'provider initialization failed' for m in messages)
        assert messages[-1]['type'] == 'end'
    else:
        assert calls == [(created[0]['task_id'], False)]
        assert ('assistant', 'fixture result') in saved
        assert messages[-1]['type'] == 'end'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
