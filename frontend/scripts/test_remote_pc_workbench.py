"""Built React owner workbench: keyboard, navigation, binary transfer and close.

All API responses are isolated fixtures; native PTY transport is tested separately.
"""
import base64
import functools
import hashlib
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright
from launcher_browser import prepare_launcher


ROOT = Path(__file__).resolve().parents[1]


def test_remote_pc_workbench(tmp_path):
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(ROOT / 'dist'))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}/'
    sessions, inputs, jobs, transfers, cancels = {}, [], {}, {}, []
    payload = b'hello binary\x00\xff'
    device = {'alias': '사무실 Mac', 'device_id': 'test-pc', 'connected': True,
              'registration': {'state': 'active', 'capabilities': {'os': 'darwin', 'terminal': True}}}
    entries = [{'name': 'notes.txt', 'path': '/work/notes.txt', 'dir': False, 'bytes': len(payload)},
               {'name': 'project', 'path': '/work/project', 'dir': True, 'bytes': 0}]
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1360, 'height': 900}, accept_downloads=True)
            errors = prepare_launcher(page, url)
            for pattern in ('**/ibl/**', '**/model-gear', '**/world-pulse/**'):
                page.route(pattern, lambda route: route.fulfill(status=503, content_type='application/json', body='{}'))
            page.add_init_script("localStorage.setItem('indiebiz_launcher_mode','manual');localStorage.setItem('indiebiz_ui_locale','ko');")

            def api(route):
                parsed = urlsplit(route.request.url)
                path, method = parsed.path, route.request.method
                data = route.request.post_data_json if route.request.post_data else {}
                result = {}
                if path == '/remote-pcs':
                    result = {'items': [device], 'usb': {'ready': True, 'folder': '/work/pc-helper'}}
                elif path == '/remote-pcs/terminals':
                    sessions[data['id']] = {'closed': False}
                    result = {'id': data['id'], 'job_id': 'terminal', 'state': 'starting'}
                elif path.startswith('/remote-pcs/terminals/'):
                    sid = path.rsplit('/', 1)[1]
                    if method == 'DELETE':
                        sessions.setdefault(sid, {})['closed'] = True
                    elif method == 'POST':
                        if data['type'] == 'input':
                            inputs.append(data)
                    else:
                        cursor = int(parse_qs(parsed.query).get('cursor', ['0'])[0])
                        raw = 'remote-mac ~ % 한글 출력\r\n'.encode()
                        result = {'state': 'running', 'reason': '', 'gap': False,
                                  'data': base64.b64encode(raw[cursor:]).decode(), 'cursor': len(raw)}
                elif path == '/remote-pcs/command':
                    command = data['command']
                    op = command['op']
                    value = {'info': {'home': '/work'}, 'list': {'path': command.get('path'), 'files': entries},
                             'read': {'content': 'preview text', 'truncated': False}, 'transfer': {'verified': True}}[op]
                    jid = f'job-{len(jobs)}'
                    jobs[jid] = {'id': jid, 'state': 'succeeded', 'created': 1, 'summary': command, 'result': value}
                    result = {'job_id': jid}
                elif path == '/remote-pcs/history':
                    jid = parse_qs(parsed.query).get('job', [''])[0]
                    busy = {'id': 'busy-job', 'state': 'running', 'created': 1, 'summary': {'op': 'shell', 'cmd': 'build project'}, 'result': None}
                    rows = [jobs[jid]] if jid in jobs else [busy] if jid else [busy, *jobs.values()]
                    cursor = int(parse_qs(parsed.query).get('cursor', ['0'])[0])
                    events = [{'cursor': 1, 'kind': 'log', 'payload': {'text': 'Building project…'}}] if jid == 'busy-job' and cursor == 0 else []
                    result = {'tasks': rows, 'events': events, 'cursor': 1 if jid == 'busy-job' else 0}
                elif path == '/remote-pcs/cancel':
                    cancels.append(data['job_id'])
                elif path == '/remote-pcs/transfers':
                    tid = f'transfer-{len(transfers)}'
                    transfers[tid] = {**data, 'id': tid, 'size': data.get('size', len(payload)), 'sha256': data.get('sha256', hashlib.sha256(payload).hexdigest()), 'bytes': bytearray()}
                    result = {k: v for k, v in transfers[tid].items() if k != 'bytes'}
                elif path.startswith('/remote-pcs/transfers/'):
                    row = transfers[path.rsplit('/', 1)[1]]
                    action = data['action']
                    if action == 'write':
                        row['bytes'].extend(base64.b64decode(data['data']))
                    elif action == 'commit':
                        assert hashlib.sha256(row['bytes']).hexdigest() == row['sha256']
                    elif action == 'info':
                        result = {k: v for k, v in row.items() if k != 'bytes'}
                    elif action == 'read':
                        result = {'data': base64.b64encode(payload).decode(), 'offset': len(payload)}
                route.fulfill(status=200, content_type='application/json', body=json.dumps(result), headers={'Access-Control-Allow-Origin': '*'})

            page.route('**/remote-pcs**', api)
            page.goto(url)
            page.get_by_role('button', name='손발 (USB)').click()
            page.get_by_role('button', name='작업창', exact=True).click()
            dialog = page.get_by_role('dialog', name='원격 PC 작업창')
            expect(dialog.get_by_role('status')).to_have_text('연결됨')
            page.locator('.xterm-helper-textarea').focus()
            page.keyboard.type('pwd')
            page.keyboard.press('Enter')
            page.wait_for_function('document.querySelector(".xterm") !== null')
            page.screenshot(path=str(tmp_path / 'remote-terminal.png'))
            dialog.get_by_role('button', name='파일', exact=True).click()
            expect(dialog.get_by_role('button', name='📄 notes.txt')).to_be_visible()
            dialog.get_by_role('button', name='📄 notes.txt').click()
            expect(dialog.get_by_text('preview text', exact=True)).to_be_visible()
            with page.expect_download() as event:
                dialog.get_by_role('button', name='가져오기', exact=True).click()
            assert Path(event.value.path()).read_bytes() == payload
            dialog.locator('input[type=file]').set_input_files({'name': 'upload.bin', 'mimeType': 'application/octet-stream', 'buffer': payload})
            expect(dialog.get_by_role('button', name='파일 보내기')).to_be_enabled()
            assert any(bytes(t['bytes']) == payload for t in transfers.values())
            page.screenshot(path=str(tmp_path / 'remote-files.png'))
            dialog.get_by_role('button', name='작업·로그').click()
            dialog.get_by_role('button', name='shell build project').click()
            expect(dialog.get_by_text('Building project…', exact=True)).to_be_visible()
            dialog.get_by_role('button', name='중지', exact=True).click()
            assert cancels == ['busy-job']
            page.screenshot(path=str(tmp_path / 'remote-tasks.png'))
            dialog.get_by_role('button', name='작업창 닫기').click()
            expect(dialog).not_to_be_visible()
            page.wait_for_timeout(250)
            assert any(s['closed'] for s in sessions.values())
            assert ''.join(i['data'] for i in inputs) == 'pwd\r', inputs
            assert [i['sequence'] for i in inputs] == list(range(1, len(inputs) + 1))
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
