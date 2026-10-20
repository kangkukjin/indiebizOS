"""Local browser transport, owner boundary, driver pinning, and uncertain writes."""
import boot_paths  # noqa: F401
import asyncio
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'data/packages/installed/tools/browser-action'


@pytest.fixture
def driver(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location('embedded_test_driver', PACKAGE / 'browser_embedded.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv('INDIEBIZ_RUNTIME_STATE_DIR', str(tmp_path))
    return module


def test_member_cannot_reach_owner_browser(driver, monkeypatch):
    def forbidden():
        pytest.fail('non-owner read connection credentials')
    monkeypatch.setattr(driver, 'connection', forbidden)
    _, result = asyncio.run(driver.route({'driver': 'embedded', 'op': 'content'}, 'browser_op', 'a' * 64, False, False))
    assert result['error_code'] == 'FORBIDDEN'


def test_no_bridge_uses_legacy_and_pins_until_close(driver, monkeypatch):
    async def run():
        owner = 'b' * 64
        assert (await driver.route({}, 'browser_navigate', owner, True, False))[0] == 'playwright'
        monkeypatch.setattr(driver, 'connection', lambda: {'instance_id': 'new'})
        assert (await driver.route({}, 'browser_op', owner, True, True))[0] == 'playwright'
        _, result = await driver.route({'driver': 'embedded'}, 'browser_op', owner, True, False)
        assert result['error_code'] == 'DRIVER_PINNED'
        await driver.route({'op': 'close'}, 'browser_op', owner, True, False)
        assert owner not in driver._choices
    asyncio.run(run())


def test_initial_unsupported_modes_keep_legacy(driver, monkeypatch):
    monkeypatch.setattr(driver, 'connection', lambda: {'instance_id': 'available'})
    async def run():
        for index, args in enumerate(({'op': 'content', 'mode': 'html'},
                                      {'op': 'click', 'mode': 'right'},
                                      {'op': 'wait', 'selector': '#ready'},
                                      {'op': 'navigate', 'headless': True})):
            selected, result = await driver.route(args, 'browser_op', str(index) * 64, True, False)
            assert selected == 'playwright' and result is None
    asyncio.run(run())


def test_chrome_connect_does_not_pin_playwright(driver):
    async def run():
        owner = 'e' * 64
        selected, result = await driver.route({'op': 'chrome', 'mode': 'connect'}, 'browser_op', owner, True, False)
        assert selected == 'chrome' and result is None and owner not in driver._choices
        selected, _ = await driver.route({'op': 'navigate'}, 'browser_op', owner, True, True)
        assert selected == 'chrome'
    asyncio.run(run())


def test_explicit_unsupported_embedded_fails_before_transport(driver, monkeypatch):
    monkeypatch.setattr(driver, 'connection', lambda: {'instance_id': 'available'})
    _, result = asyncio.run(driver.route({'driver': 'embedded', 'op': 'evaluate'}, 'browser_op', 'f' * 64, True, False))
    assert result['error_code'] == 'UNSUPPORTED_OPERATION'


def test_bridge_wire_and_restart(driver, monkeypatch, tmp_path):
    async def run():
        # AF_UNIX limits paths to ~104 bytes on macOS.
        import tempfile
        with tempfile.TemporaryDirectory(prefix='ib-eb-', dir='/tmp') as folder:
            path = Path(folder) / 's'
            seen = []
            async def serve(reader, writer):
                message = json.loads(await reader.readline())
                seen.append(message)
                writer.write((json.dumps({'id': message['id'], 'result': {'success': True, 'content': 'hello'}}) + '\n').encode())
                await writer.drain()
                writer.close()
            server = await asyncio.start_unix_server(serve, path)
            os.chmod(path, 0o600)
            info = {'version': 1, 'socket': str(path), 'instance_id': 'first', 'token': 'a' * 64}
            state = driver.state_path()
            state.write_text(json.dumps(info)); state.chmod(0o600)
            try:
                assert driver.connection()['instance_id'] == 'first'
                selected, result = await driver.route({'op': 'content'}, 'browser_op', 'c' * 64, True, False)
                assert selected == 'embedded' and result['content'] == 'hello'
                assert seen[0]['owner'] == 'c' * 64 and seen[0]['token'] == info['token']
                assert 'token' not in result
                info['instance_id'] = 'second'; state.write_text(json.dumps(info))
                _, result = await driver.route({'op': 'click', 'ref': 'e1'}, 'browser_op', 'c' * 64, True, False)
                assert result['error_code'] == 'BROWSER_RESTARTED'
                assert len(seen) == 1
                state.chmod(0o644)
                assert driver.connection() is None
            finally:
                server.close(); await server.wait_closed()
    asyncio.run(run())


def test_disconnected_submission_is_not_retried(driver, tmp_path):
    async def run():
        import tempfile
        with tempfile.TemporaryDirectory(prefix='ib-eb-', dir='/tmp') as folder:
            path = Path(folder) / 's'; seen = []
            async def drop(reader, writer):
                seen.append(await reader.readline()); writer.close()
            server = await asyncio.start_unix_server(drop, path)
            try:
                result = await driver.request({'op': 'auth', 'mode': 'login'}, 'd' * 64,
                                              {'socket': str(path), 'instance_id': 'one', 'token': 'x' * 64})
                assert result['outcome_unknown'] is True and len(seen) == 1
            finally:
                server.close(); await server.wait_closed()
    asyncio.run(run())


def test_handler_captures_principal_before_async_route(monkeypatch, tmp_path):
    from principal import ANONYMOUS, set_transport, reset_transport
    spec = importlib.util.spec_from_file_location('embedded_boundary_handler', PACKAGE / 'handler.py')
    handler = importlib.util.module_from_spec(spec); spec.loader.exec_module(handler)
    context = SimpleNamespace(project_path=str(tmp_path), agent_id='system_ai', task_id='external', tool_name='browser_op')
    token = set_transport(ANONYMOUS)
    try:
        call = handler.execute({'driver': 'embedded', 'op': 'snapshot'}, context)
    finally:
        reset_transport(token)
    result = json.loads(asyncio.run(call))
    assert result['error_code'] == 'FORBIDDEN'


@pytest.mark.parametrize('change', [
    {'op': 'navigate', 'url': 'https://example.test'},
    {'op': 'click', 'ref': 'e1'},
    {'op': 'type', 'ref': 'e1', 'text': 'hello'},
    {'op': 'tab', 'mode': 'switch', 'index': 1},
    {'op': 'evaluate', 'script': 'document.title'},
])
def test_handler_blocks_background_mutation_after_real_router_pins_chrome(monkeypatch, tmp_path, change):
    """execute → 실제 route/작업 결속 → owned_execute. Chrome 통신 끝단만 대체."""
    import thread_context
    from tool_loader import load_tool_handler
    from tool_context import ToolContext
    handler = load_tool_handler('browser_op')
    embedded = handler.load_singleton(handler.__file__, 'browser_embedded')
    monkeypatch.setattr(embedded, '_choices', {})
    monkeypatch.setattr(embedded, 'connection', lambda: None)
    monkeypatch.setattr(handler, '_is_chrome_connected', lambda: True)
    monkeypatch.setattr(thread_context, 'get_task_origin', lambda: 'scheduler')
    calls = []

    async def transport(params, context):
        calls.append(dict(params))
        return json.dumps({'success': True, 'driver': params['driver']})

    monkeypatch.setattr(handler, '_execute', transport)
    context = ToolContext(str(tmp_path), 'browser_op')

    async def run():
        first = json.loads(await handler.execute({'op': 'snapshot'}, context))
        assert first['success'] and first['driver'] == 'chrome'
        assert any(choice[0] == 'chrome' for choice in embedded._choices.values())
        refused = json.loads(await handler.execute(change, context))
        assert not refused['success'] and refused['error_code'] == 'SCREEN_CONTEXT_UNAVAILABLE'
        assert [call['op'] for call in calls] == ['snapshot']
        # 거절이 기존 탭이나 작업 결속을 바꾸지 않는다. 입회 턴에서는 같은 작업으로 실행 가능.
        monkeypatch.setattr(thread_context, 'get_task_origin', lambda: 'user')
        allowed = json.loads(await handler.execute(change, context))
        assert allowed['success'] and calls[-1]['driver'] == 'chrome'

    asyncio.run(run())


def test_background_snapshot_then_click_through_ibl_entry(monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api_ibl import router
    from tool_loader import load_tool_handler
    import thread_context
    handler = load_tool_handler('browser_op')
    embedded = handler.load_singleton(handler.__file__, 'browser_embedded')
    monkeypatch.setattr(embedded, '_choices', {})
    monkeypatch.setattr(embedded, 'connection', lambda: None)
    monkeypatch.setattr(handler, '_is_chrome_connected', lambda: True)
    monkeypatch.setattr(thread_context, 'get_task_origin', lambda: 'scheduler')
    calls = []

    async def transport(params, context):
        calls.append(dict(params))
        return json.dumps({'success': True, 'driver': params['driver']})

    monkeypatch.setattr(handler, '_execute', transport)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        response = client.post('/ibl/execute', json={
            'edition': 2, 'project_path': str(tmp_path), 'origin': 'scheduler', 'code': (
                '[limbs:browser]{op:"snapshot"}\n'
                'return [limbs:browser]{op:"click",ref:"e1"}')})
    assert response.status_code == 200, response.text
    result = response.json()
    assert not result['success'], result
    assert [call['op'] for call in calls] == ['snapshot']
    assert calls[0]['driver'] == 'chrome'
    assert '화면 없는 문맥' in json.dumps(result, ensure_ascii=False)


@pytest.mark.parametrize('driver_name', ['embedded', 'chrome'])
def test_snapshot_observation_without_guide_through_handler(monkeypatch, tmp_path, driver_name):
    import control_observations as obs
    import guide_registry
    import thread_context
    from tool_loader import load_tool_handler
    from tool_context import ToolContext
    handler = load_tool_handler('browser_op')
    embedded = handler.load_singleton(handler.__file__, 'browser_embedded')
    monkeypatch.setattr(embedded, '_choices', {})
    monkeypatch.setattr(obs, 'STORE_PATH', tmp_path / 'observations.json')
    monkeypatch.setattr(guide_registry, 'surface_control_guide', lambda *args: None)
    monkeypatch.setattr(thread_context, 'get_task_origin', lambda: 'user')
    monkeypatch.setattr(embedded, 'connection', lambda: {'instance_id': 'test'})
    obs.record('site:example.test', [{
        'observed_at': '2026-10-20T10:00:00+09:00', 'environment': {'site': 'example.test'},
        'fact': '로그인 화면으로 이동함',
    }])

    async def transport(*args):
        return json.dumps({'success': True, 'url': 'https://example.test/path'})

    async def bridge(*args):
        return json.loads(await transport())

    monkeypatch.setattr(handler, '_execute', transport)
    monkeypatch.setattr(embedded, 'request', bridge)
    result = json.loads(asyncio.run(handler.execute(
        {'op': 'snapshot', 'driver': driver_name}, ToolContext(str(tmp_path), 'browser_op'))))
    assert result['success'] and 'control_guide' not in result
    assert result['driver_surface']['surface'] == 'site:example.test'
    assert result['driver_surface']['observations'] == 1
    assert 'target:"site:example.test"' in result['driver_surface']['note']


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
