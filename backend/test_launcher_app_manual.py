"""Remote cockpit information parity on the real assembled browser surface."""
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
    state = {'fail_logs': False, 'expired': False}

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
        elif path == '/nodes/active-work':
            result = {'items': [{'kind': 'system_ai', 'project_name': attack, 'project_id': '',
                                  'agents': ['담당 AI'], 'busy': True, 'elapsed_sec': 12}]}
            status = 401 if state['expired'] else 200
        elif path == '/world-pulse/dashboard':
            result = {'ibl_health': {'healthy': False, 'stale': False, 'checked_at': '2026-10-17T12:00:00',
                      'action_count': 178, 'items': [{'key': 'fixture', 'label': '통화 점검', 'ok': False,
                                                    'detail': attack}]},
                      'disk_free_gb': 123, 'services': {'scheduler': True, 'channel_poller': False}}
        elif path == '/xray/doc/anatomy/raw':
            result = {'content': '# 구조\n\n인지 외골격 ' + attack}
        elif path == '/remote-pcs':
            result = {'usb': {'ready': True, 'folder': '/work/helper'}, 'items': [
                {'alias': attack, 'connected': True, 'registration': {'state': 'active', 'kind': 'phone'},
                 'phone_update': {'state': 'awaiting_confirmation', 'current_version': 4, 'latest_version': 5}}]}
        elif path == '/system-logs':
            result = {'lines': ['ERROR ' + attack], 'note': '최근 300줄'}
            status = 503 if state['fail_logs'] else 200
        elif path == '/ibl/execute':
            args = json.loads(route.request.post_data)
            assert args['project_id'] == '수동모드' and args['surface'] == 'web'
            assert args['code'].startswith('[self:body]')
            result = {'result': {'items': [{'파일': attack, '상태': '수정', '요지': '원장 검증'}], 'text': '변화 1건'}}
        elif path == '/ibl/pursuits':
            result = {'items': [{'id': attack, 'title': attack, 'status': 'active', 'agent_key': 'system', 'next': '다음 관측'}], 'total': 21}
        elif path.startswith('/ibl/pursuits/'):
            result = {'pursuit': {'title': attack, 'status': 'active', 'goal_criteria': '전체 목표',
                       'framing': '현재 규정', 'progress': '확보한 결과', 'next': '다음 할 일',
                       'assumptions': [{'status': 'broken', 'text': '이전 전제', 'evidence': attack}]},
                      'pending_turns': [{}], 'events': [{'kind': 'updated', 'payload': {'note': attack}}]}
        elif path == '/system-ai/recall-preview':
            assert json.loads(route.request.post_data) == {'message': '회상 검증'}
            result = {'top_score': .9, 'top_code': '[self:body]{}', 'total_chars': 300,
                      'sections': [{'label': '해마', 'present': True, 'content': attack},
                                   {'label': '심층 기억', 'present': False, 'content': ''}]}
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
    expect(page.locator('#cpActive')).to_contain_text(attack)
    expect(page.locator('#cpHealthSummary')).to_have_text('IBL 주의')
    assert not any(path in {'/remote-pcs', '/system-logs', '/ibl/pursuits', '/ibl/execute'} for path, _, _ in calls)
    for panel in ['cpStructure', 'cpStatus', 'cpLimbs', 'cpLogs', 'cpBody', 'cpPursuits', 'cpRecall']:
        page.locator('#'+panel+' > summary').click()
    expect(page.locator('#cpStructureBody')).to_contain_text('인지 외골격')
    expect(page.locator('#cpStatusBody')).to_contain_text('디스크 123GB')
    expect(page.locator('#cpStatusBody')).to_contain_text('채널 폴러 · 중지')
    expect(page.locator('#cpLimbsBody')).to_contain_text('폰에서 Android 설치 확인 필요')
    expect(page.locator('#cpLogsBody')).to_contain_text('ERROR '+attack)
    expect(page.locator('#cpBodyBody')).to_contain_text('변화 1건')
    page.locator('#cpBodyBody button').click()
    expect(page.locator('#cpBodyBody > p').first).to_have_text(attack)
    assert json.loads([body for path, _, body in calls if path == '/ibl/execute'][-1])['code'].find(json.dumps(attack, ensure_ascii=False)) >= 0
    page.locator('#cpPursuitsBody button').first.click()
    expect(page.locator('#cpPursuitsBody article')).to_contain_text('전체 목표')
    expect(page.locator('#cpPursuitsBody article')).to_contain_text('깨진 전제')
    page.locator('#cpPursuitsBody article summary').click()
    assert json.loads(page.locator('#cpPursuitsBody article pre').last.inner_text())['note'] == attack
    page.locator('#cpRecallQuery').fill('회상 검증')
    page.locator('#cpRecallButton').click()
    expect(page.locator('#cpRecallBody')).to_contain_text('90.0%')
    expect(page.locator('#cpRecallBody')).to_contain_text('심층 기억 — 회상 없음')
    expect(page.locator('#cpRecallBody')).to_contain_text(attack)
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


def test_error_retry_and_polling_lifetime(cockpit):
    from playwright.sync_api import expect
    page, calls, errors, _, state = cockpit
    page.locator('#t-manual').click()
    expect(page.locator('#cpActive')).to_contain_text('담당 AI')
    state['fail_logs'] = True
    page.locator('#cpLogs > summary').click()
    expect(page.locator('#cpLogsBody')).to_contain_text('503')
    state['fail_logs'] = False
    page.locator('#cpLogsBody button').click()
    expect(page.locator('#cpLogsBody')).to_contain_text('ERROR')
    page.locator('#t-autopilot').click()
    page.evaluate('cpSync()')
    assert page.evaluate('cpTimer') is None
    before = len(calls)
    page.evaluate("cpLoad('active')")
    assert len(calls) == before
    page.locator('#t-manual').click()
    state['expired'] = True
    page.evaluate("cpLoad('active')")
    expect(page.locator('#login')).to_be_visible()
    expect(page.locator('#app')).not_to_be_visible()
    assert page.evaluate('cpTimer') is None
    assert not errors


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
