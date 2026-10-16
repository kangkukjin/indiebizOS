"""ES5 경량 표면도 공통 세션을 생성·전환·재개한다."""
import json
from urllib.parse import urlsplit

import boot_paths  # noqa: F401
from playwright.sync_api import sync_playwright, expect
from launcher_lite import LAUNCHER_LITE_HTML


def test_lite_session_history_and_new_conversation(tmp_path):
    items = [{'id': 'old', 'title': '이전 회의', 'updated_at': '2026-10-14T01:00:00Z'}]
    rows = {'old': [{'id': '1', 'role': 'user', 'content': '과거 요청'}]}
    sent = []

    def route(r):
        path = urlsplit(r.request.url).path
        if path == '/launcher/lite':
            r.fulfill(content_type='text/html', body=LAUNCHER_LITE_HTML)
            return
        data = {}
        if path == '/chat-sessions':
            if r.request.method == 'POST':
                data = {'id': 'new', 'title': '새 세션', 'updated_at': '2026-10-15T00:00:00Z'}
                items.insert(0, data); rows['new'] = []
            else:
                data = {'sessions': items}
        elif path.startswith('/chat-sessions/'):
            sid = path.split('/')[2]
            if path.endswith('/messages'):
                body = r.request.post_data_json
                sent.append((sid, body['message']))
                rows[sid] += [{'id': '2', 'role': 'user', 'content': body['message']}, {'id': '3', 'role': 'assistant', 'content': '새 답변'}]
            else:
                data = {'messages': rows[sid], 'has_older': False, 'turn': None}
        elif path == '/launcher/auth/login':
            data = {'session_id': 'test', 'success': True}
        r.fulfill(content_type='application/json', body=json.dumps(data))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 390, 'height': 844})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.route('**/*', route)
        page.goto('http://fixture.test/launcher/lite')
        expect(page.locator('#chatlog')).to_contain_text('과거 요청')
        page.locator('#chatNew').click()
        expect(page.locator('#chatlog')).not_to_contain_text('과거 요청')
        page.locator('#cmsg').fill('새 요청'); page.locator('#csend').click()
        expect(page.locator('#chatlog')).to_contain_text('새 답변')
        assert sent == [('new', '새 요청')]
        page.locator('#chatHistoryOpen').click()
        page.get_by_role('button', name='이전 회의', exact=True).click()
        expect(page.locator('#chatHistory')).not_to_be_visible()
        expect(page.locator('#chatlog')).to_contain_text('과거 요청')
        expect(page.locator('#chatlog')).not_to_contain_text('새 요청')
        page.reload()
        expect(page.locator('#chatlog')).to_contain_text('과거 요청')
        from launcher_lite import lite_display
        payload = lite_display()
        payload['code'] = payload['code'].replace('히스토리', '기록 보기')
        payload['version'] = 'lite-next'
        page.locator('#cmsg').fill('계속 작성 중')
        page.evaluate("window.savedInput=document.getElementById('cmsg')")
        page.evaluate("value => new Promise((resolve,reject)=>IndieLite.apply(value,error=>error?reject(error):resolve()))", payload)
        expect(page.locator('#chatHistoryOpen')).to_have_text('기록 보기')
        assert page.evaluate("savedInput===document.getElementById('cmsg')")
        expect(page.locator('#cmsg')).to_have_value('계속 작성 중')
        assert sent == [('new', '새 요청')]
        page.screenshot(path=str(tmp_path/'lite-sessions.png'))
        assert not errors
        browser.close()


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
