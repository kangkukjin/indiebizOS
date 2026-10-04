"""Japanese release acceptance on built UI; fixture APIs, no live writes."""
import importlib.util
import json
import re
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from launcher_browser import prepare_launcher, select_locale, settled_style
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
    errors = prepare_launcher(page, launcher + surface)
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
    select_locale(page, picker, 'en', keyboard=True)
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


def test_desktop_picker_toolbar_states(launcher, browser, tmp_path):
    context = browser.new_context(viewport={'width': 1280, 'height': 800})
    page = context.new_page()
    errors = prepare_launcher(page, launcher)
    page.goto(launcher)
    picker = page.get_by_label('Language / 언어').filter(visible=True).first
    picker.wait_for()
    neighbour = page.get_by_title('화면 모드 선택', exact=True)
    fields = ['height', 'borderRadius', 'backgroundColor', 'color']
    assert settled_style(picker, fields) == settled_style(neighbour, fields)
    neighbour.hover()
    hover = settled_style(neighbour, ['backgroundColor'])
    picker.hover()
    assert settled_style(picker, ['backgroundColor']) == hover
    page.keyboard.press('Tab')
    picker.focus()
    assert picker.evaluate("el => el.matches(':focus-visible')")
    style = settled_style(picker, ['outlineStyle', 'boxShadow'])
    assert style['outlineStyle'] != 'none' or style['boxShadow'] != 'none'
    page.screenshot(path=str(tmp_path / 'desktop-picker-focus.png'))
    select_locale(page, picker, 'en', keyboard=True)
    assert not errors, errors
    context.close()
