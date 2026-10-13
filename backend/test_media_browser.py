"""Two independent hubs + real React session hooks + Chromium camera and decoded video."""
import boot_paths  # noqa: F401
import importlib.util
import os
import socket
import subprocess
import threading
from pathlib import Path

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from playwright.sync_api import sync_playwright

import api_media
from test_media_two_hubs import hubs, _wait  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def browser_assets(tmp_path_factory):
    out = tmp_path_factory.mktemp('media-browser')
    subprocess.run(['npx', 'vite', 'build', '--config', 'vite.harness.config.ts'],
                   cwd=ROOT / 'frontend', env={**os.environ, 'MEDIA_HARNESS_OUT': str(out)}, check=True)
    return out


@pytest.fixture
def servers(hubs, browser_assets):
    a, b, _ = hubs
    running = []
    urls = []
    for i, hub in enumerate((a, b)):
        spec = importlib.util.spec_from_file_location(f'api_media_browser_{i}', api_media.__file__)
        surface = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(surface)
        surface.ms = hub
        app = FastAPI()
        app.include_router(surface.router)
        app.mount('/', StaticFiles(directory=browser_assets, html=True))
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
        thread = threading.Thread(target=lambda s=server, sk=sock: s.run(sockets=[sk]), daemon=True)
        thread.start()
        assert _wait(lambda: server.started)
        running.append((server, thread, sock))
        urls.append(f'http://127.0.0.1:{sock.getsockname()[1]}')
    yield a, b, urls
    for server, thread, sock in running:
        server.should_exit = True
        thread.join(5)
        sock.close()


@pytest.mark.parametrize('delay_capture', [0, 900], ids=['bundled', 'late-offer'])
def test_call_accepts_before_capture_and_decodes_on_both_hubs(servers, delay_capture):
    a, b, urls = servers
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream',
                                          '--allow-loopback-in-peer-connection', '--autoplay-policy=no-user-gesture-required'])
        caller, callee = browser.new_page(), browser.new_page()
        if delay_capture:
            caller.add_init_script(f'''const capture = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
                navigator.mediaDevices.getUserMedia = async c => {{await new Promise(r => setTimeout(r, {delay_capture})); return capture(c);}};''')
        sid = a.create('call', 'video_call', '친구')['session_id']
        caller.goto(f'{urls[0]}/?session={sid}')
        assert _wait(lambda: sid in b._sessions)
        callee.goto(f'{urls[1]}/?session={sid}')
        callee.get_by_role('button', name='수락').wait_for()
        assert callee.get_by_test_id('session').get_attribute('data-capturing') == 'false'
        assert callee.get_by_test_id('session').get_attribute('data-role') == 'callee'
        callee.get_by_role('button', name='수락').click()
        for page in (caller, callee):
            page.wait_for_function("document.getElementById('remote').videoWidth > 0", timeout=20000)
            assert page.get_by_test_id('session').get_attribute('data-error') == ''
        caller.get_by_role('button', name='종료').click()
        callee.wait_for_function("document.querySelector('[data-testid=session]').dataset.state === 'ended'")
        browser.close()



def test_recorded_video_element_stream_decodes_at_receiver(servers):
    _, _, urls = servers
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream',
                                          '--allow-loopback-in-peer-connection', '--autoplay-policy=no-user-gesture-required'])
        page = browser.new_page()
        page.goto(urls[0])
        page.wait_for_function('window.harness != null')
        result = page.evaluate('window.harness.run({trickle: true, playback: true})')
        assert result['framesDecoded'] > 0 and result['width'] > 0
        assert result['peerAlive'] == [True, True]
        page.evaluate('window.harness.close()')
        browser.close()

if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
