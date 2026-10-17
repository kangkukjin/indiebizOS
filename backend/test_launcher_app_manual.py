"""Remote cockpit footer information on the real assembled browser surface."""
import boot_paths  # noqa: F401
import json
from urllib.parse import urlsplit

import pytest

from surface_assets import source_build


@pytest.fixture(scope='module')
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        instance = pw.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.fixture(params=['source', 'localized'])
def cockpit(request, browser):
    from launcher_surface_remote import launcher_html
    with source_build():
        if request.param == 'source':
            # Import again under source_build: dynamic modules deliberately use snapshots.
            from launcher_web_shell import LAUNCHER_SHELL_HTML
            from launcher_web_app import LAUNCHER_APP_JS
            from launcher_web_render import LAUNCHER_RENDER_JS
            html = LAUNCHER_SHELL_HTML + LAUNCHER_APP_JS + LAUNCHER_RENDER_JS
        else:
            html = launcher_html(display=False)
            assert 'window.__ui=' in html, 'Build the UI catalog before acceptance tests'
    page = browser.new_page(viewport={'width': 390, 'height': 844})
    page.add_init_script("localStorage.setItem('indiebiz_ui_locale','ko');window.WebSocket=class {close(){}};")
    calls, errors = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    attack = '''기록 "'<img src=x onerror="window.cockpitXSS=1">'''
    state = {'fail_limbs': False, 'expired': False}

    def respond(route):
        path = urlsplit(route.request.url).path
        if path == '/launcher/app':
            route.fulfill(content_type='text/html', body=html)
            return
        calls.append((path, route.request.method, route.request.post_data))
        result = {}
        status = 200
        if path == '/launcher/config':
            result = {'has_password': False, 'host': 'desktop'}
        elif path == '/projects':
            result = {'projects': []}
        elif path == '/launcher/instruments':
            result = {'instruments': []}
        elif path == '/world-pulse/dashboard':
            result = {'ibl_health': {'healthy': False, 'stale': False, 'checked_at': '2026-10-17T12:00:00',
                      'action_count': 178, 'items': [{'key': 'fixture', 'label': '통화 점검', 'ok': False,
                                                    'detail': attack}]},
                      'disk_free_gb': 123, 'services': {'scheduler': True, 'channel_poller': False}}
            status = 401 if state['expired'] else 200
        elif path == '/remote-pcs':
            result = {'usb': {'ready': True, 'folder': '/work/helper'}, 'items': [
                {'alias': attack, 'connected': True, 'registration': {'state': 'active', 'kind': 'phone'},
                 'phone_update': state.get('phone_update', {'state': 'awaiting_confirmation', 'current_version': 4, 'latest_version': 5})}]}
            status = 503 if state['fail_limbs'] else 200
        route.fulfill(status=status, content_type='application/json', body=json.dumps(result))

    page.route('**/*', respond)
    page.goto('http://cockpit.test/launcher/app')
    yield page, calls, errors, attack, state
    page.close()


def test_information_panels_mobile_and_desktop(cockpit, tmp_path):
    from playwright.sync_api import expect
    page, calls, errors, attack, _ = cockpit
    expect(page.locator('#app')).to_have_class('app on')
    assert not any(path == '/nodes/active-work' for path, _, _ in calls)
    page.locator('#t-manual').click()
    expect(page.locator('#cpHealthSummary')).to_have_text('IBL 주의')
    assert page.locator('#p-manual .wrap').evaluate("el=>el.firstElementChild.classList.contains('dash-head')")
    assert page.locator('#p-manual .wrap').evaluate("el=>Array.from(el.children).slice(-2).map(x=>x.id)") == ['cpLimbs', 'cpStatus']
    assert page.locator('#p-manual .cockpit-info').count() == 2
    for removed in ('cpActive', 'cpStructure', 'cpLogs', 'cpBody', 'cpPursuits', 'cpRecall', 'cpHistory'):
        expect(page.locator('#'+removed)).to_have_count(0)
    expect(page.locator('#gearLever')).to_be_attached()
    expect(page.locator('#mJournal')).to_be_visible()
    expect(page.locator('#mIntent')).to_be_visible()
    assert not any(path == '/remote-pcs' for path, _, _ in calls)
    for panel in ['cpStatus', 'cpLimbs']:
        page.locator('#'+panel+' > summary').click()
    expect(page.locator('#cpStatusBody')).to_contain_text('디스크 123GB')
    expect(page.locator('#cpStatusBody')).to_contain_text('채널 폴러 · 중지')
    expect(page.locator('#cpLimbsBody')).to_contain_text('폰에서 Android 설치 확인 필요')
    expect(page.locator('#cpLimbsBody')).to_contain_text(attack)
    removed_paths = {'/nodes/active-work', '/system-logs', '/ibl/pursuits', '/ibl/execute',
                     '/system-ai/recall-preview', '/xray/doc/anatomy/raw'}
    assert not any(path in removed_paths for path, _, _ in calls)
    assert page.evaluate('window.cockpitXSS') is None
    assert page.locator('.cockpit-info img').count() == 0
    detail = page.locator('#cpStatusBody .cp-entry [data-ui-system]').last
    assert detail.get_attribute('data-ui-system') == attack
    assert detail.evaluate('el=>el.attributes.length') == 1
    for width in (320, 390, 1280):
        page.set_viewport_size({'width': width, 'height': 900})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert page.locator('#p-manual').evaluate('el=>el.scrollWidth<=el.clientWidth')
    page.screenshot(path=str(tmp_path / 'cockpit.png'), full_page=True)
    assert not errors


def test_newer_installed_apk_is_not_shown_as_a_downgrade(cockpit):
    from playwright.sync_api import expect
    page, _, errors, _, state = cockpit
    state['phone_update'] = {'state': 'ahead', 'current_version': 6, 'latest_version': 5,
                            'current_version_name': '0.6', 'latest_version_name': '0.5'}
    page.locator('#t-manual').click()
    page.locator('#cpLimbs > summary').click()
    panel = page.locator('#cpLimbsBody')
    expect(panel).to_contain_text('중앙 배포본보다 새 버전 설치됨')
    expect(panel).to_contain_text('설치 0.6 · 중앙 배포 0.5')
    expect(panel).not_to_contain_text('→')
    expect(panel).not_to_contain_text('APK 호환 확인 필요')
    assert not errors


def test_error_retry_and_polling_lifetime(cockpit):
    from playwright.sync_api import expect
    page, calls, errors, _, state = cockpit
    page.locator('#t-manual').click()
    expect(page.locator('#cpHealthSummary')).to_have_text('IBL 주의')
    state['fail_limbs'] = True
    page.locator('#cpLimbs > summary').click()
    expect(page.locator('#cpLimbsBody')).to_contain_text('503')
    state['fail_limbs'] = False
    page.locator('#cpLimbsBody button').click()
    expect(page.locator('#cpLimbsBody')).to_contain_text('폰에서 Android 설치 확인 필요')
    page.locator('#t-autopilot').click()
    page.evaluate('cpSync()')
    assert page.evaluate('cpTimer') is None
    before = len(calls)
    page.evaluate("cpLoad('status')")
    assert len(calls) == before
    page.locator('#t-manual').click()
    state['expired'] = True
    page.evaluate("cpLoad('status')")
    expect(page.locator('#login')).to_be_visible()
    expect(page.locator('#app')).not_to_be_visible()
    assert page.evaluate('cpTimer') is None
    assert not errors


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
