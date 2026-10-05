"""Native container checks, shared writer fencing and actual local RHWP UI."""
import io
import socket
import struct
import threading
import time
import zipfile
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

import document_hwp
import api_documents
from document_workspace import DocumentWorkspace, DocumentConflict, DocumentUnsupported

FIXTURES = Path(__file__).parent / 'fixtures/hwp'
ROOT = Path(__file__).resolve().parents[1]


def args(d, s):
    return dict(document_id=d['id'], session_id=s['id'], client_id=s['client_id'],
                epoch=s['engine_epoch'], expected=s['session_revision'])


@pytest.mark.parametrize('format', ['hwp', 'hwpx'])
def test_native_draft_save_copy_restore_and_fencing(tmp_path, monkeypatch, format):
    monkeypatch.setattr(document_hwp, 'available', lambda: True)
    path = tmp_path / ('sample.' + format)
    original = (FIXTURES / path.name).read_bytes()
    path.write_bytes(original)
    app = DocumentWorkspace(tmp_path / 'workspace')
    detail = app.open(path); d = detail['document']
    assert detail['capabilities']['engine'] == 'rhwp'
    s = app.acquire(d['id'], 'window')['session']
    assert document_hwp.content(app, **args(d, s)) == original
    edited = (FIXTURES / ('edited.' + format)).read_bytes()
    initial_session = s
    result = document_hwp.draft(app, **args(d, s), operation_id='first', data=edited)
    assert document_hwp.draft(app, **args(d, s), operation_id='first', data=edited) == result
    s = result['session']
    assert s['session_revision'] == initial_session['session_revision'] + 1
    with pytest.raises(DocumentConflict):
        document_hwp.draft(app, **args(d, initial_session), operation_id='stale-revision', data=original)
    assert path.read_bytes() == original
    with pytest.raises(ValueError):
        document_hwp.draft(app, **args(d, s), operation_id='invalid', data=b'not a document')
    assert app.detail(d['id'])['session']['blob'] == s['blob']
    copy = app.export_copy(**args(d, s), operation_id='copy', filename='copy.' + format)
    assert Path(copy['path']).read_bytes() == edited
    saved = app.save(**args(d, s), operation_id='save', expected_revision=d['revision_id'])
    assert path.read_bytes() == edited
    restored = app.restore(**args(d, s), operation_id='restore', revision_id=d['revision_id'])['session']
    assert app.store.bytes(restored['blob']) == original
    assert restored['engine_epoch'] != s['engine_epoch']
    assert path.read_bytes() == edited
    s = restored
    new = app.reclaim(d['id'], 'new-window', s['engine_epoch'])['session']
    with pytest.raises(DocumentConflict):
        document_hwp.draft(app, **args(d, s), operation_id='stale', data=original)
    path.write_bytes(b'external writer')
    with pytest.raises(DocumentConflict):
        app.save(**args(d, new), operation_id='external', expected_revision=saved['revision_id'])
    assert path.read_bytes() == b'external writer'


@pytest.mark.parametrize('protected_flag', [2, 4, 16, 256, 1024])
def test_invalid_and_protected_hwp_rejected(tmp_path, protected_flag):
    import olefile
    data = io.BytesIO((FIXTURES / 'sample.hwp').read_bytes())
    with olefile.OleFileIO(data, write_mode=True) as doc:
        header = bytearray(doc.openstream('FileHeader').read())
        struct.pack_into('<I', header, 36, struct.unpack_from('<I', header, 36)[0] | protected_flag)
        doc.write_stream('FileHeader', bytes(header))
    with pytest.raises(DocumentUnsupported):
        document_hwp.validate(data.getvalue(), 'hwp')
    for format in ('hwp', 'hwpx'):
        path = tmp_path / ('invalid.' + format); path.write_bytes(b'bad')
        with pytest.raises(ValueError):
            DocumentWorkspace(tmp_path / 'ws').open(path)


def test_hwp_api_binary_and_asset_boundaries(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    monkeypatch.setattr(document_hwp, 'available', lambda: True)
    workspace = DocumentWorkspace(tmp_path / 'workspace')
    monkeypatch.setattr(api_documents, 'service', lambda: workspace)
    app = FastAPI(); app.include_router(api_documents.router)
    client = TestClient(app)
    path = tmp_path / 'sample.hwpx'; data = (FIXTURES / path.name).read_bytes(); path.write_bytes(data)
    d = workspace.open(path)['document']; s = workspace.acquire(d['id'], 'window')['session']
    params = args(d, s); params.pop('document_id')
    url = '/documents/' + d['id']
    assert client.get(url + '/hwp-content', params=params).content == data
    assert client.post(url + '/hwp-draft', params={**params, 'operation_id': 'draft'}, content=data).status_code == 200
    assert client.post(url + '/hwp-draft', params={**params, 'operation_id': 'cross'}, content=data,
                       headers={'origin': 'https://evil.example'}).status_code == 403
    assert client.get('/documents/hwp-assets/%2e%2e/document_hwp/host.js').status_code == 404
    monkeypatch.setattr(document_hwp, 'available', lambda: False)
    assert workspace.capabilities(d['id'])['edit_native'] is False


@pytest.mark.system
@pytest.mark.skipif(not document_hwp.available(), reason='로컬 RHWP 번들 준비 필요')
@pytest.mark.parametrize('format', ['hwp', 'hwpx'])
def test_local_hwp_browser_roundtrip(tmp_path, monkeypatch, format):
    import uvicorn
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
    from fastapi.staticfiles import StaticFiles
    from playwright.sync_api import sync_playwright, expect
    assert document_hwp.available(), 'Prepare local RHWP assets first'
    workspace = DocumentWorkspace(tmp_path / 'workspace')
    monkeypatch.setattr(api_documents, 'service', lambda: workspace)
    app = FastAPI(); app.include_router(api_documents.router)
    from test_document_app_support import mount_document_app, open_document
    mount_document_app(app, workspace)
    @app.get('/launcher/auth/session')
    def auth():
        return {'authenticated': True, 'external': False}
    @app.get('/health')
    def health():
        return {'status': 'ok'}
    html = (ROOT / 'frontend/dist/index.html').read_text().replace('<html', '<html data-indiebiz-surface="remote"', 1)
    @app.get('/')
    def index():
        return HTMLResponse(html)
    app.mount('/assets', StaticFiles(directory=ROOT / 'frontend/dist/assets'))
    sock = socket.socket(); sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True); thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(.02)
        assert server.started
        source = tmp_path / ('sample.' + format)
        original = (FIXTURES / source.name).read_bytes(); source.write_bytes(original)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1600, 'height': 1100})
            failures, remote = [], []
            page.on('pageerror', lambda error: failures.append(str(error)))
            page.on('request', lambda req: remote.append(req.url) if req.url.startswith('http') and not req.url.startswith(f'http://127.0.0.1:{port}/') else None)
            open_document(page, port, source)
            ui = page.get_by_role('region', name='한글 문서 편집기', exact=True)
            try:
                expect(ui.get_by_role('button', name='원본 저장', exact=True)).to_be_enabled(timeout=60000)
                host = page.frame_locator('iframe[title="로컬 HWP 편집 화면"]')
                studio = host.frame_locator('iframe')
                # Human typing into the native editor's actual input surface.
                studio.locator('#scroll-content canvas').first.click(position={'x': 420, 'y': 180})
                page.keyboard.press('Control+Home')
                page.keyboard.insert_text('수정 완료 ')
                ui.get_by_role('button', name='작업 저장', exact=True).click()
                expect(ui.get_by_role('status')).to_contain_text('작업 초안 저장됨', timeout=20000)
                assert source.read_bytes() == original
                ui.get_by_role('button', name='원본 저장', exact=True).click()
                expect(ui.get_by_role('status')).to_contain_text('원본 저장됨', timeout=20000)
                assert source.read_bytes() != original
                document_hwp.validate(source.read_bytes(), format)
                page.screenshot(path=str(tmp_path / ('hwp-editor-' + format + '.png')), full_page=True)
                # Fresh WASM instance reads published bytes, not editor state.
                import json
                import subprocess
                parsed = json.loads(subprocess.check_output(['node', str(ROOT / 'scripts/verify_document_hwp.mjs'), str(source)], text=True))
                assert '수정 완료 ' in parsed['text'], parsed
                assert '한글 문서 시험 · 원본 보존' in parsed['text'], parsed
                if format == 'hwpx':
                    with zipfile.ZipFile(source) as archive:
                        assert b'<hp:tbl' in archive.read('Contents/section0.xml')
                # Reload the app and reopen the same native saved document.
                open_document(page, port, source, fresh=True)
                expect(ui.get_by_role('button', name='원본 저장', exact=True)).to_be_enabled(timeout=30000)
                assert not remote, remote
                # Electron's packaged frontend has an opaque file: origin. The
                # HTTP bridge must still negotiate with the local Studio SDK.
                shell = tmp_path / 'file-origin.html'
                shell.write_text('<iframe id="host" src="http://127.0.0.1:' + str(port) + '/documents/hwp-assets/host.html?channel=file-test"></iframe><output></output><script>'
                    + 'const target="http://127.0.0.1:' + str(port) + '";const frame=document.querySelector("iframe");'
                    + 'frame.onload=()=>frame.contentWindow.postMessage({channel:"file-test",id:"load",op:"load",args:{filename:"sample.' + format + '",data:new Uint8Array(' + json.dumps(list(source.read_bytes())) + ')}},target);'
                    + 'addEventListener("message",event=>{if(event.source!==frame.contentWindow||event.origin!==target)return;'
                    + 'if(event.data.error){document.querySelector("output").textContent=event.data.error;return;}'
                    + 'if(event.data.id==="load")frame.contentWindow.postMessage({channel:"file-test",id:"state",op:"state",args:{}},target);'
                    + 'if(event.data.id==="state")document.querySelector("output").textContent=event.data.result.format;});</script>')
                page.goto(shell.as_uri())
                expect(page.locator('output')).to_have_text(format, timeout=30000)
            except Exception:
                page.screenshot(path=str(tmp_path / 'failure.png'), full_page=True)
                print({'errors': failures, 'remote': remote, 'body': page.locator('body').inner_text(), 'frames': [f.url for f in page.frames]})
                raise
            finally:
                browser.close()
    finally:
        server.should_exit = True; thread.join(10)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
