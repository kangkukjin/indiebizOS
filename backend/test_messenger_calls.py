"""Messenger call entry: saved contact only, matching PC/phone cards, no row misrouting."""
import boot_paths  # noqa: F401
import json
from types import SimpleNamespace

import pytest
import yaml
from playwright.sync_api import sync_playwright

from test_imagination_round77_81_repairs import module, ROOT
from test_media_browser import browser_assets, servers  # noqa: F401
from test_media_two_hubs import hubs  # noqa: F401
from test_render_core import _assembled_script

TARGET = 'ab' * 32
OTHER = 'cd' * 32


def instrument():
    data = yaml.safe_load((ROOT / 'data/packages/installed/tools/business/ibl_actions.yaml').read_text())
    def find(value):
        if isinstance(value, dict):
            if value.get('instrument') == 'messenger':
                return value
            for child in value.values():
                found = find(child)
                if found:
                    return found
        if isinstance(value, list):
            for child in value:
                found = find(child)
                if found:
                    return found
    return {**find(data), 'id': 'messenger'}


@pytest.mark.parametrize('contacts,expected', [
    ([], ''), ([('email', TARGET)], ''), ([('phone', TARGET)], ''),
    ([('email', 'a@example.com'), ('nostr', ' ' + TARGET + ' ')], TARGET),
    ([('nostr', ''), ('nostr', OTHER)], OTHER),
])
def test_inbox_call_target_uses_nostr_contact_only(monkeypatch, contacts, expected):
    mod = module('business')
    monkeypatch.setattr(mod, '_indienet', lambda: None)
    bm = SimpleNamespace(get_inbox_summary=lambda **kw: [
        {'id': 1, 'name': '이웃', '_channel_contacts': contacts}])
    assert json.loads(mod._msg_inbox(bm, {}))['items'][0]['nostr_target'] == expected


def rows():
    return [{'id': 1, 'name': '첫 이웃', 'nostr_target': TARGET},
            {'id': 2, 'name': '이메일 이웃', 'nostr_target': '', 'to': TARGET},
            {'id': 3, 'name': '둘째 이웃', 'nostr_target': OTHER},
            {'id': 4, 'name': '잘못된 주소', 'nostr_target': '\"><script>alert(1)</script>'}]


def test_phone_buttons_keep_selected_contact_after_detail_changes():
    # Run the actual assembled phone/remote renderer, not a reimplementation of its markup.
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={'width': 390, 'height': 844})
        page.route('http://messenger.test/**', lambda r: r.fulfill(body='<main id="cards"></main>', content_type='text/html'))
        page.goto('http://messenger.test/')
        page.evaluate("window.fetch=async()=>({ok:true,json:async()=>({})});")
        page.add_script_tag(content=_assembled_script())
        page.evaluate('''({prim,items}) => {
            document.getElementById('cards').innerHTML=renderView([prim],{items});
            window.rowDrill=()=>{window.drilled=true};
            window.actualMessengerCall=window.messengerCall;
            window.__calls=[];
            window.messengerCall=b=>window.__calls.push({...b.dataset});
        }''', {'prim': instrument()['view'][0], 'items': rows()})
        assert page.get_by_role('button', name='음성 통화', exact=True).count() == 2
        assert page.get_by_role('button', name='영상 통화', exact=True).count() == 2
        page.get_by_role('button', name='영상 통화', exact=True).nth(1).click()
        assert page.evaluate('window.__calls') == [{'callTarget': OTHER, 'callPurpose': 'video_call'}]
        assert not page.evaluate('!!window.drilled')
        # Field deletion removes controls immediately on refresh; other contact types never substitute.
        page.evaluate('''prim => {document.getElementById('cards').innerHTML=renderView([prim],
            {items:[{name:'삭제된 연락처',nostr_target:'',to:'a'.repeat(64)}]});}''', instrument()['view'][0])
        assert page.get_by_role('button', name='영상 통화', exact=True).count() == 0
        page.evaluate('''({prim,items}) => {
            document.getElementById('cards').innerHTML=renderView([prim],{items});
            IS_PHONE=true; window.messengerCall=window.actualMessengerCall;
        }''', {'prim': instrument()['view'][0], 'items': rows()})
        with page.expect_request('**/launcher/native-call?*') as native:
            page.get_by_role('button', name='음성 통화', exact=True).nth(1).click()
        from urllib.parse import urlparse, parse_qs
        assert parse_qs(urlparse(native.value.url).query) == {'target': [OTHER], 'purpose': ['voice_call']}
        browser.close()


def test_pc_messenger_click_sends_saved_contact_and_does_not_open_thread(servers):
    _, _, urls = servers
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.add_init_script('window.messengerFixture=' + json.dumps(instrument()) + ';')
        page.add_init_script('window.open=()=>null;')
        requests = []
        def api(route):
            if route.request.method == 'OPTIONS':
                route.fulfill(headers={'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*'}, body='')
                return
            payload = route.request.post_data_json
            requests.append((route.request.url, payload))
            result = {'items': rows()} if '/ibl/execute' in route.request.url else {'success': True, 'session': {'session_id': 'fixture'}}
            route.fulfill(json=result, headers={'Access-Control-Allow-Origin': '*'})
        page.route('**/ibl/execute', api)
        page.route('**/media/sessions', api)
        page.goto(urls[0] + '/?messenger')
        page.get_by_role('button', name='영상 통화', exact=True).nth(1).wait_for()
        assert page.get_by_role('button', name='음성 통화', exact=True).count() == 2
        before = len([r for r in requests if '/ibl/execute' in r[0]])
        page.get_by_role('button', name='영상 통화', exact=True).nth(1).click()
        page.wait_for_function("!Array.from(document.querySelectorAll('button')).some(b=>b.disabled && b.getAttribute('aria-label')==='영상 통화')")
        calls = [body for url, body in requests if '/media/sessions' in url]
        assert len(calls) == 1
        assert calls[0]['target'] == OTHER
        assert calls[0]['purpose'] == 'video_call'
        assert len([r for r in requests if '/ibl/execute' in r[0]]) == before
        browser.close()


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
