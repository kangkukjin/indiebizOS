"""빌드된 관리 화면의 메뉴 진입·등록·수정·중지·재발급·해제. 업무 API는 대역이다."""
import functools
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright
from launcher_browser import prepare_launcher

ROOT = Path(__file__).resolve().parents[1]


def test_member_pc_management(tmp_path):
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(ROOT / 'dist'))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}/'
    pcs = []
    calls = []
    address = {'url': 'https://hub.example/m/app', 'warning': ''}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1360, 'height': 1000})
            errors = prepare_launcher(page, url)
            page.add_init_script("localStorage.setItem('indiebiz_ui_locale','ko');")
            def api(route):
                path = urlsplit(route.request.url).path
                method = route.request.method
                body = route.request.post_data_json if route.request.post_data else {}
                calls.append((method, path, body))
                result = {'success': True}
                if method == 'GET':
                    result = {'address': address, 'pcs': pcs, 'daily_limit': 40, 'global_daily_limit': 400}
                elif method == 'POST' and path == '/member-pcs':
                    assert 'neighbor_id' not in body
                    pcs.append({'device_id': 'memberpc-test', 'name': body['name'], 'user_label': body['user_label'],
                                'note': body['note'], 'enabled': True, 'status': 'pending', 'created_at': 1,
                                'expires_at': None, 'last_seen': None, 'host': '', 'os': '', 'client': '',
                                'turns_today': 0, 'tokens_today': 0, 'active_tasks': 0, 'daily_limit': 40})
                    result = {'key': 'synthetic-only-key', 'alias': body['name'], 'device_id': 'memberpc-test', 'address': address}
                elif method == 'PATCH':
                    pcs[0].update(body)
                    if 'enabled' in body:
                        pcs[0]['status'] = 'offline' if body['enabled'] else 'disabled'
                elif path.endswith('/key'):
                    result = {'key': 'synthetic-rotated', 'alias': pcs[0]['name'], 'device_id': 'memberpc-test', 'address': address}
                elif method == 'DELETE':
                    pcs[0]['status'] = 'revoked'
                route.fulfill(status=200, content_type='application/json', body=json.dumps(result), headers={'Access-Control-Allow-Origin': '*'})
            page.route('**/member-pcs**', api)
            page.goto(url)
            page.get_by_title('메뉴', exact=True).click()
            page.get_by_role('button', name='회원 PC 관리', exact=True).click()
            expect(page.get_by_text('등록된 회원 PC가 없습니다.', exact=True)).to_be_visible()
            page.get_by_role('button', name='PC 등록', exact=True).click()
            page.get_by_label('PC 이름', exact=True).fill('연구실 노트북')
            page.get_by_label('사용자 표시명 (선택)').fill('연구 담당')
            page.get_by_label('메모 (선택)').fill('문서와 분석 작업')
            page.get_by_role('button', name='등록하고 키 발급').click()
            expect(page.get_by_label('회원 PC 등록 키')).to_have_value('synthetic-only-key')
            expect(page.get_by_label('회원 PC 등록 키')).to_have_attribute('type', 'password')
            expect(page.get_by_role('cell', name='연결 대기')).to_be_visible()
            page.get_by_role('button', name='수정', exact=True).click()
            page.get_by_label('PC 이름', exact=True).fill('연구실 PC')
            page.get_by_role('button', name='변경 저장').click()
            expect(page.get_by_role('cell', name='연구실 PC')).to_be_visible()
            page.get_by_role('button', name='사용 중지', exact=True).click()
            expect(page.get_by_role('dialog')).to_be_visible()
            page.get_by_role('dialog').get_by_role('button', name='취소', exact=True).click()
            assert not any(body.get('enabled') is False for _, _, body in calls)
            page.get_by_role('button', name='사용 중지', exact=True).click()
            page.get_by_role('dialog').get_by_role('button', name='확인', exact=True).click()
            expect(page.get_by_role('button', name='사용 재개', exact=True)).to_be_visible()
            page.get_by_role('button', name='사용 재개', exact=True).click()
            page.get_by_role('button', name='키 재발급', exact=True).click()
            page.get_by_role('dialog').get_by_role('button', name='확인', exact=True).click()
            expect(page.get_by_label('회원 PC 등록 키')).to_have_value('synthetic-rotated')
            page.get_by_label('발급 정보 닫기').click()
            page.screenshot(path=str(tmp_path / 'member-pcs-desktop.png'), full_page=True)
            page.set_viewport_size({'width': 760, 'height': 900})
            expect(page.get_by_role('button', name='수정', exact=True)).to_be_visible()
            page.get_by_role('button', name='등록 해제', exact=True).click()
            page.get_by_role('dialog').get_by_role('button', name='확인', exact=True).click()
            expect(page.get_by_text('등록된 회원 PC가 없습니다.', exact=True)).to_be_visible()
            page.get_by_label('해제한 PC 포함').check()
            expect(page.get_by_role('cell').get_by_text('등록 해제', exact=True)).to_be_visible()
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
