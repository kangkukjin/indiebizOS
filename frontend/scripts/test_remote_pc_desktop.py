"""Built React screen sharing: one click, automatic route, and retry after failure."""
import functools
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright
from launcher_browser import prepare_launcher


ROOT = Path(__file__).resolve().parents[1]


def test_remote_pc_desktop(tmp_path):
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(ROOT / 'dist'))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}/'
    requests = []
    device = {'alias': '사무실 Mac', 'device_id': 'test-pc', 'connected': True,
              'registration': {'state': 'active', 'capabilities': {'os': 'darwin', 'desktop_stream': 1}}}
    phone = {'alias': '검증용 폰', 'device_id': 'test-phone', 'connected': True,
             'registration': {'state': 'active', 'kind': 'phone'},
             'phone_update': {'state': 'available', 'current_version': 2, 'latest_version': 3}}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1360, 'height': 900}, accept_downloads=True)
            errors = prepare_launcher(page, url)
            for pattern in ('**/ibl/**', '**/model-gear', '**/world-pulse/**'):
                page.route(pattern, lambda route: route.fulfill(status=503, content_type='application/json', body='{}'))
            page.add_init_script("localStorage.setItem('indiebiz_launcher_mode','manual');localStorage.setItem('indiebiz_ui_locale','ko');")
            page.add_init_script("window.desktopCalls=[];window.electron={openRemoteDesktop:async(device,route)=>{window.desktopCalls.push({device,route});if(window.desktopFailure)throw new Error('unavailable');return {route:route==='auto'?'direct':'tunnel'};}};")

            def api(route):
                path = urlsplit(route.request.url).path
                requests.append(path)
                if path == '/remote-pcs/phone-update':
                    assert route.request.post_data_json == {'target': 'test-phone'}
                    phone['phone_update']['state'] = 'awaiting_confirmation'
                result = {'items': [device, phone], 'usb': {'ready': True, 'folder': '/work/pc-helper'}} if path == '/remote-pcs' else {}
                route.fulfill(status=200, content_type='application/json', body=json.dumps(result), headers={'Access-Control-Allow-Origin': '*'})

            page.route('**/remote-pcs**', api)
            page.goto(url)
            page.get_by_role('button', name='손발 (USB)').click()
            panel = page.get_by_role('button', name='손발 (USB)').locator('..')
            page.get_by_role('button', name='앱 업데이트', exact=True).click()
            expect(panel).to_contain_text('폰에서 Android 설치 확인 필요')
            expect(page.get_by_role('button', name='앱 업데이트', exact=True)).to_have_count(0)
            assert requests.count('/remote-pcs/phone-update') == 1
            phone['phone_update'] = {'state': 'ahead', 'current_version': 6, 'latest_version': 5,
                                     'current_version_name': '0.6', 'latest_version_name': '0.5'}
            page.get_by_title('목록 새로고침').click()
            expect(panel).to_contain_text('중앙 배포본보다 새 버전 설치됨')
            expect(panel).to_contain_text('설치 0.6 · 중앙 배포 0.5')
            expect(panel).not_to_contain_text('APK 호환 확인 필요')
            expect(page.get_by_role('button', name='앱 업데이트', exact=True)).to_have_count(0)
            assert requests.count('/remote-pcs/phone-update') == 1
            requests.clear()
            page.get_by_role('button', name='화면 공유', exact=True).click()
            page.wait_for_function('window.desktopCalls.length === 1')
            assert page.evaluate('window.desktopCalls') == [{'device': 'test-pc', 'route': 'auto'}]
            expect(page.get_by_role('dialog', name='화면 공유', exact=True)).to_have_count(0)
            expect(page.get_by_role('button', name='외부 터널로 연결')).to_have_count(0)
            assert all(path == '/remote-pcs' for path in requests)
            page.evaluate('window.desktopFailure = true')
            page.get_by_role('button', name='화면 공유', exact=True).click()
            expect(panel.get_by_role('alert')).to_contain_text('unavailable')
            page.evaluate('window.desktopFailure = false')
            page.get_by_role('button', name='화면 공유', exact=True).click()
            page.wait_for_function('window.desktopCalls.length === 3')
            expect(panel.get_by_role('alert')).to_have_count(0)
            expect(page.get_by_role('button', name='화면 공유', exact=True)).to_be_enabled()
            expect(page.get_by_role('button', name='작업창', exact=True)).to_have_count(0)
            expect(page.get_by_role('dialog', name='원격 PC 작업창')).to_have_count(0)
            page.screenshot(path=str(tmp_path / 'remote-desktop.png'))
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
