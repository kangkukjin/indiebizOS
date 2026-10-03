"""Japanese release acceptance on built UI; fixture APIs, no live writes."""
import importlib.util
import json
import re
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from test_xray_ui import browser, server, prepare, USER_TEXT  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / 'i18n/catalog.json').read_text())


def tr(source, locale='ja'):
    return next(m['translations'][locale] for m in CATALOG['messages'].values()
                if m['source'] == source)


@pytest.fixture(scope='module')
def launcher():
    spec = importlib.util.spec_from_file_location('ui_browser_check', ROOT / 'scripts/ui-browser-check.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), module.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{httpd.server_port}'
    httpd.shutdown()


@pytest.mark.parametrize('surface', ['/', '/launcher/app'])
def test_japanese_picker_persistence_and_restore(launcher, browser, surface):
    context = browser.new_context()
    page = context.new_page()
    errors = prepare(page)
    def api(route):
        path = urlsplit(route.request.url).path
        if route.request.url.startswith(launcher) and (path in ['/', '/launcher/app'] or path.startswith('/assets/')):
            route.continue_()
            return
        payload = {}
        if path == '/launcher/config':
            payload = {'has_password': False, 'host': 'desktop'}
        elif path in ['/projects', '/switches', '/folders']:
            payload = {path[1:]: []}
        elif path == '/launcher/instruments':
            payload = {'instruments': []}
        elif path == '/launcher/app-layout':
            payload = {'version': 1, 'positions': {}, 'folders': {}, 'membership': {}, 'removed': [], 'uninstalled': [], 'promoted': []}
        elif path == '/health':
            payload = {'status': 'ok'}
        route.fulfill(status=200, content_type='application/json', body=json.dumps(payload), headers={'Access-Control-Allow-Origin': '*'})
    page.route('**/*', api)
    page.goto(launcher + surface)
    picker = page.get_by_label('Language / 언어').filter(visible=True).first
    picker.wait_for()
    assert picker.locator('option[value="ja"]').inner_text() == '日本語'
    korean = page.locator('body').inner_text()
    picker.select_option('ja')
    page.wait_for_function("document.documentElement.lang==='ja'")
    japanese = page.locator('body').inner_text()
    assert japanese != korean
    assert re.search('[ぁ-んァ-ヶ]', japanese)
    if surface == '/':
        assert page.get_by_title(tr('화면 모드 선택'), exact=True).count() == 1
    page.reload()
    picker.wait_for()
    assert picker.input_value() == 'ja'
    assert page.locator('html').get_attribute('lang') == 'ja'
    picker.select_option('en')
    assert page.locator('html').get_attribute('lang') == 'en'
    picker.select_option('ko')
    assert page.locator('html').get_attribute('lang') == 'ko'
    assert not errors, errors
    context.close()


def test_japanese_xray_all_tabs_content_and_sibling_sync(server, browser):
    context = browser.new_context()
    page = context.new_page()
    errors = prepare(page)
    page.goto(server + '/xray/app?ui_locale=ja')
    page.wait_for_selector('.tab-bar')
    assert page.locator('html').get_attribute('lang') == 'ja'
    page.get_by_text(tr('새로고침'), exact=True).wait_for()
    assert page.locator('.proj-name').inner_text() == USER_TEXT
    for tab in ['bodymap', 'goals', 'tools', 'cognition', 'memory', 'dashboard', 'docs']:
        page.click(f'[data-tab="{tab}"]')
        page.wait_for_timeout(100)
        content = page.locator(f'#tab-{tab}').inner_text().replace(USER_TEXT, '')
        assert not re.search('[가-힣]', content), (tab, content)
    assert page.locator('.doc-text').inner_text() == USER_TEXT
    sibling = context.new_page()
    prepare(sibling)
    sibling.goto(server + '/xray/app')
    sibling.wait_for_selector('.tab-bar')
    assert sibling.locator('html').get_attribute('lang') == 'ja'
    sibling.evaluate("window.__ui.setLocale('en')")
    page.wait_for_function("document.documentElement.lang==='en'")
    sibling.evaluate("window.__ui.setLocale('ja')")
    page.wait_for_function("document.documentElement.lang==='ja'")
    assert page.locator('.doc-text').inner_text() == USER_TEXT
    page.reload()
    page.wait_for_selector('.tab-bar')
    assert page.locator('html').get_attribute('lang') == 'ja'
    assert not errors, errors
    context.close()
