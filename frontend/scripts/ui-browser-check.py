"""Browser integration of the built desktop and actual server-generated remote shell.
Run after vite build, with a Python that provides playwright. API data is synthetic;
translation catalogs are the real generated artifact, not mocked translations.
"""
import json
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / 'dist'), **kwargs)

    def do_GET(self):
        if self.path == '/launcher/app':
            html = json.loads((ROOT / 'i18n/remote.json').read_text())['html'].encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html)
        else:
            super().do_GET()

    def log_message(self, *args):
        pass


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f'http://127.0.0.1:{server.server_port}'
    reports = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for surface, url in [('desktop', '/'), ('remote', '/launcher/app')]:
            context = browser.new_context(viewport={'width': 1280, 'height': 900})
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            def api(route):
                path = urlsplit(route.request.url).path
                if route.request.url.startswith(origin) and (path in ['/', '/launcher/app'] or path.startswith('/assets/')):
                    route.continue_()
                    return
                payload = {}
                if path == '/launcher/config': payload = {'has_password': False, 'host': 'desktop'}
                elif path == '/projects': payload = {'projects': []}
                elif path == '/switches': payload = {'switches': []}
                elif path == '/folders': payload = {'folders': []}
                elif path == '/health': payload = {'status': 'ok'}
                elif path == '/model-gear': payload = {'gear': 'balanced', 'presets': {}}
                route.fulfill(status=200, content_type='application/json', body=json.dumps(payload), headers={'Access-Control-Allow-Origin':'*'})
            page.route('**/*', api)
            page.goto(origin + url)
            picker = page.get_by_label('Language / 언어').filter(visible=True)
            picker.first.wait_for(timeout=30000)
            korean = page.locator('body').inner_text()
            picker.first.select_option('en')
            page.wait_for_timeout(300)
            english = page.locator('body').inner_text()
            if surface == 'desktop':
                catalog = json.loads((ROOT / 'i18n/catalog.json').read_text())
                changed = next(m for m in catalog['messages'].values() if m['source'] == '화면 모드 선택')
                assert changed['translations']['en'] != changed['source']
                assert page.get_by_title(changed['translations']['en'], exact=True).count() == 1
            assert english != korean, (surface, english[:500])
            assert page.locator('html').get_attribute('lang') == 'en'
            assert page.evaluate("localStorage.getItem('indiebiz.ui.locale')") == 'en'
            # Content entered or returned by users remains byte-for-byte intact on switches.
            page.evaluate("""() => {const p=document.createElement('p');p.id='user-content';p.textContent='사용자 대화·파일명 비밀값 $& <b>';document.body.append(p);const i=document.createElement('input');i.id='draft';i.value='입력 중인 한국어';document.body.append(i)}""")
            picker.first.select_option('ko')
            assert page.locator('#user-content').inner_text() == '사용자 대화·파일명 비밀값 $& <b>'
            assert page.locator('#draft').input_value() == '입력 중인 한국어'
            picker.first.select_option('en')
            page.reload()
            picker.first.wait_for()
            assert picker.first.input_value() == 'en'
            assert page.locator('html').get_attribute('lang') == 'en'
            picker.first.select_option('ko')
            assert page.locator('html').get_attribute('lang') == 'ko'
            # Return to the same user-visible source labels after a full English cycle.
            assert '자율주행' in page.locator('body').inner_text()
            if surface == 'remote':
                page.evaluate("apBrowseRoot()")
                picker.first.select_option('en')
                assert page.locator('#apBrowse').get_by_text('시스템 AI', exact=True).count() == 0
            assert not errors, (surface, errors)
            reports.append({'surface': surface, 'switchPersistRestore': True, 'userContentPreserved': True, 'pageErrors': errors, 'englishSample': english[:400]})
            context.close()
        browser.close()
    server.shutdown()
    print(json.dumps(reports, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
