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


# Speaker-only device: actual sender UI, permission timing, and decoded WebRTC audio.
from test_media_sessions import hub, _device  # noqa: E402,F401
import media_sessions as ms  # noqa: E402
import api_resident_pcs  # noqa: E402


@pytest.fixture
def speaker_server(hub, browser_assets):
    app = FastAPI()
    app.include_router(api_media.router)
    app.include_router(api_resident_pcs.router)
    app.mount('/', StaticFiles(directory=browser_assets, html=True))
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    assert _wait(lambda: server.started)
    rec = _device('speaker-only', caps={'speaker': True})
    session = ms.create('extension', 'speaker', 'speaker-only')
    yield f'http://127.0.0.1:{sock.getsockname()[1]}', rec, session
    server.should_exit = True
    thread.join(5)
    sock.close()


_CAPTURE_PROBE = """window.captured = []; window.captureRequests = [];
const capture = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
navigator.mediaDevices.getUserMedia = async constraints => {
    window.captureRequests.push(constraints);
    if (window.denyCapture) throw new DOMException('denied', 'NotAllowedError');
    const stream = await capture(constraints);
    window.captured.push(stream);
    if (window.delayCapture) await new Promise(resolve => { window.releaseCapture = resolve; });
    return stream;
};"""


def test_speaker_sends_live_microphone_without_camera(speaker_server):
    url, rec, session = speaker_server
    sid = session['session_id']
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream',
                                          '--allow-loopback-in-peer-connection', '--autoplay-policy=no-user-gesture-required'])
        sender, receiver = browser.new_page(), browser.new_page()
        sender.add_init_script(_CAPTURE_PROBE)
        receiver.goto(url)
        receiver.evaluate("""async ({sid, auth}) => {
          window.received = [];
          const pc = window.audioPeer = new RTCPeerConnection();
          pc.ontrack = e => window.received.push(e.track);
          pc.ondatachannel = e => { e.channel.onmessage = m => { if (m.data === 'ping') e.channel.send('pong'); }; };
          const ws = new WebSocket(`${location.origin.replace('http', 'ws')}/limb/resident/media/${sid}`);
          let seq = 0;
          const send = (type, payload) => ws.send(JSON.stringify({v:1, session_id:sid,
            msg_id:crypto.randomUUID(), from:'device', to:'hub', generation:0, seq:++seq,
            expires_at:Date.now()/1000+60, type, payload}));
          pc.onicecandidate = e => { if (e.candidate) send('candidate', e.candidate.toJSON()); };
          let chain = Promise.resolve();
          ws.onmessage = e => { const f = JSON.parse(e.data); chain = chain.then(async () => {
            if (f.type === 'offer') {
              await pc.setRemoteDescription({type:'offer', sdp:f.payload.sdp});
              await pc.setLocalDescription(await pc.createAnswer());
              send('answer', {sdp:pc.localDescription.sdp});
            } else if (f.type === 'candidate') await pc.addIceCandidate(f.payload);
            else if (f.type === 'end') pc.close();
          }); };
          await new Promise(resolve => { ws.onopen = resolve; }); ws.send(JSON.stringify(auth));
        }""", {'sid': sid, 'auth': {'key': rec['key'], 'installation_id': rec['registration']['installation_id'],
                                    'grant': ms.get(sid).grants['device']}})
        sender.goto(f'{url}/?session={sid}&ui=1')
        sender.get_by_role('button', name='마이크 입력', exact=True).click()
        assert sender.evaluate('window.captureRequests.length') == 0
        sender.get_by_role('button', name='마이크 소리 보내기', exact=True).click()
        receiver.wait_for_function("window.audioPeer.connectionState === 'connected'")
        receiver.wait_for_function("async () => [...(await window.audioPeer.getStats()).values()].some(s => s.type === 'inbound-rtp' && s.kind === 'audio' && s.totalSamplesReceived > 0)")
        assert receiver.evaluate('window.received.map(t => t.kind)') == ['audio']
        assert sender.evaluate('window.captureRequests[0].video') is False
        assert ms.get(sid).consent['inputs'] == ['mic']
        sender.get_by_role('button', name='마이크 끄기', exact=True).click()
        assert sender.evaluate('window.captured[0].getAudioTracks()[0].enabled') is False
        sender.get_by_role('button', name='마이크 켜기', exact=True).click()
        assert sender.evaluate('window.captured[0].getAudioTracks()[0].enabled') is True
        sender.get_by_role('button', name='종료', exact=True).click()
        sender.wait_for_function("window.captured.every(s => s.getTracks().every(t => t.readyState === 'ended'))")
        assert ms.get(sid).state == 'ended'
        browser.close()


@pytest.mark.parametrize('case', ['denied', 'end-during-permission'])
def test_speaker_capture_failure_and_late_result(speaker_server, case):
    url, _, session = speaker_server
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'])
        page = browser.new_page()
        page.add_init_script(_CAPTURE_PROBE)
        page.goto(f"{url}/?session={session['session_id']}&ui=1")
        page.get_by_role('button', name='마이크 입력', exact=True).click()
        page.evaluate('window.denyCapture = true' if case == 'denied' else 'window.delayCapture = true')
        page.get_by_role('button', name='마이크 소리 보내기', exact=True).click()
        if case == 'denied':
            page.get_by_text('카메라·마이크 권한이 거부됐습니다.', exact=False).wait_for()
            assert page.evaluate('window.captured.length') == 0
            page.evaluate('window.denyCapture = false')
            page.get_by_role('button', name='마이크 소리 보내기', exact=True).click()
            page.wait_for_function('window.captured.length === 1')
            page.get_by_role('button', name='종료', exact=True).click()
        else:
            page.wait_for_function('!!window.releaseCapture')
            page.get_by_role('button', name='종료', exact=True).click()
            page.evaluate('window.releaseCapture()')
        page.wait_for_function("window.captured.every(s => s.getTracks().every(t => t.readyState === 'ended'))")
        assert page.get_by_role('button', name='마이크 소리 보내기', exact=True).is_disabled()
        browser.close()
