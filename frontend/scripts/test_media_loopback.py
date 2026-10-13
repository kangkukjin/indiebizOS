"""Real-browser proof for the WebRTC engine: two engines in one Chromium page, fake camera, remote frames decoded."""
import functools
import os
import subprocess
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def harness_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp('media-harness')
    env = {**os.environ, 'MEDIA_HARNESS_OUT': str(out)}
    subprocess.run(['npx', 'vite', 'build', '--config', 'vite.harness.config.ts'], cwd=ROOT, env=env, check=True, timeout=300)
    assert (out / 'index.html').exists()
    return out


@pytest.fixture(scope='module')
def served(harness_dir):
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(SimpleHTTPRequestHandler, directory=str(harness_dir)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/'
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


@pytest.mark.parametrize('trickle', [True, False], ids=['trickle', 'non-trickle'])
def test_loopback_decodes_remote_video(served, trickle):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream', '--allow-loopback-in-peer-connection'])
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(served)
        page.wait_for_function("window.harness && document.getElementById('status').textContent === 'ready'")
        try:
            result = page.evaluate('o => window.harness.run(o)', {'trickle': trickle, 'profile': {'maxBitrateKbps': 800, 'maxFramerate': 15}})
        except Exception:
            diagnostics = page.evaluate("""() => { const p = window.harness.pair; if (!p) return null; const peer = e => [e.pc.signalingState, e.pc.iceConnectionState, e.pc.iceGatheringState, e.state, e.generation];
              return { status: document.getElementById('status').textContent, log: p.log, a: peer(p.a), b: peer(p.b) }; }""")
            print('loopback diagnostics:', diagnostics)
            raise
        assert result['width'] > 0, result
        assert result['framesDecoded'] > 0, result
        assert result['generation'] == 0
        assert result['path'] == 'direct', result
        assert result['quality']['width'] > 0 and result['quality']['fps'] >= 0, result
        assert 'a:active' in result['states'] and 'b:active' in result['states'], result
        assert result['peerAlive'] == [True, True], result  # DTLS DataChannel liveness: what the call keepalive reports as peer_alive
        log = page.evaluate('window.harness.pair.log')
        offers = [line for line in log if ' offer ' in line]
        answers = [line for line in log if ' answer ' in line]
        candidates = [line for line in log if ' candidate ' in line]
        assert len(offers) == 1 and len(answers) == 1, log
        if trickle:
            assert candidates, log
        else:
            assert not candidates, log  # non-trickle: candidates live inside the complete SDP
            assert 'a=candidate' in page.evaluate("window.harness.pair.frames.find(f => f.type === 'offer').payload.sdp")
        fingerprint = page.evaluate("window.harness.pair.frames.find(f => f.type === 'offer').payload.fingerprint")
        assert fingerprint.startswith('sha-256 '), fingerprint
        if trickle:
            restarted = page.evaluate('window.harness.restart()')
            assert restarted['generation'] == 1 and restarted['state'] == 'active', restarted
            assert 1 in restarted['frameGenerations'], restarted
        # the sender honoured the bitrate cap from the quality profile
        params = page.evaluate("window.harness.pair.a.pc.getSenders().map(s => s.getParameters().encodings?.[0]?.maxBitrate)")
        assert 800000 in params, params
        page.evaluate('window.harness.close()')
        assert not errors, errors
        browser.close()
