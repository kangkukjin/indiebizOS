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


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
