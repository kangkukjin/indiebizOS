"""원격 채팅 대상 전환 시 작성문·주행 분석 초안의 수신자 경계."""
import json
from urllib.parse import urlsplit

import boot_paths  # noqa: F401
import pytest
from playwright.sync_api import expect, sync_playwright


@pytest.fixture
def browser_chat():
    from launcher_surface_remote import launcher_html

    sent = []
    errors = []
    prompt = '#EXECUTE\n지난 주행 분석 요청\n=== 실행 로그 ===\n내부 실행 기록'

    def route(r):
        path = urlsplit(r.request.url).path
        if path == '/launcher/app':
            r.fulfill(content_type='text/html', body=launcher_html())
            return
        if path.endswith('/analysis-prompt'):
            data = {'prompt': prompt}
        elif path == '/projects':
            data = {'projects': [{'id': 'p', 'name': '프로젝트'}]}
        elif path == '/projects/p/agents':
            data = {'agents': [{'id': 'a', 'name': '에이전트 A'},
                               {'id': 'b', 'name': '에이전트 B'}]}
        elif path.endswith('/command') or path == '/system-ai/chat':
            sent.append((path, r.request.post_data_json))
            data = {'status_url': '/test-task'}
        elif path == '/test-task':
            data = {'state': 'succeeded', 'result': '응답 완료'}
        else:
            data = {}
        r.fulfill(content_type='application/json', body=json.dumps(data))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 390, 'height': 844})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('**/*', route)
        page.goto('http://repair.test/launcher/app')
        expect(page.locator('#apBrowse')).to_contain_text('프로젝트')
        page.evaluate("async()=>{await apBrowseProject('p'); apPickAgent(0);}")
        yield page, sent, prompt
        assert errors == []
        browser.close()


@pytest.mark.parametrize('source,target', [('system', 'a'), ('a', 'system'), ('a', 'b')])
def test_draft_does_not_cross_chat_targets(browser_chat, source, target):
    page, sent, _ = browser_chat
    pick = {'system': 'apPickSystem()', 'a': 'apPickAgent(0)', 'b': 'apPickAgent(1)'}
    page.evaluate(pick[source])
    page.locator('#apInput').fill('이전 상대에게 작성하던 내용\n\n')
    page.evaluate('apExitChat()')
    page.evaluate(pick[target])
    expect(page.locator('#apInput')).to_have_value('')
    page.locator('#apInput').press_sequentially('현재 사용자 메시지')
    page.locator('#apSend').click()
    expect(page.locator('#apMsgs')).to_contain_text('응답 완료')
    path, body = sent.pop()
    assert path == ('/system-ai/chat' if target == 'system'
                    else f'/projects/p/agents/{target}/command')
    assert body.get('message', body.get('command')) == '현재 사용자 메시지'
    assert not sent


def test_analysis_draft_cannot_leak_to_agent(browser_chat):
    page, sent, prompt = browser_chat
    page.evaluate('jAnalyze(123)')
    expect(page.locator('#apInput')).to_have_value(prompt)
    page.evaluate('apExitChat(); apPickAgent(0)')
    expect(page.locator('#apInput')).to_have_value('')
    page.locator('#apInput').press_sequentially('현재 사용자 메시지')
    page.locator('#apSend').click()
    expect(page.locator('#apMsgs')).to_contain_text('응답 완료')
    assert sent == [('/projects/p/agents/a/command',
                     {'command': '현재 사용자 메시지', 'background': True})]


def test_analysis_has_no_delayed_write_into_next_chat(browser_chat):
    page, _, _ = browser_chat
    page.evaluate("async()=>{await jAnalyze(123); apPickAgent(0); document.getElementById('apInput').value='새 초안';}")
    # 기존 80ms 지연 콜백이 다른 상대의 새 초안을 덮어쓰던 경로.
    page.wait_for_timeout(150)
    expect(page.locator('#apInput')).to_have_value('새 초안')


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
