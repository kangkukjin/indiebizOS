"""원격 런처에서 연구 프로젝트를 열면 에이전트가 아니라 주제별 대화가 보인다."""
import json
from urllib.parse import urlsplit

import boot_paths  # noqa: F401
from playwright.sync_api import expect, sync_playwright


def test_research_project_shows_topics_and_chats_by_topic():
    from launcher_surface_remote import launcher_html

    threads = [{'id': 't1', 'title': '우크라이나', 'updated_label': '2026-10-11 19:09', 'mode_label': '자료 + 추가 조사'},
               {'id': 't2', 'title': '교육', 'updated_label': '2026-10-10 12:21'}]
    messages = {'t1': [{'id': 1, 'role': 'user', 'content': '전쟁은 언제 끝날까', 'status': 'complete', 'status_label': ''},
                       {'id': 2, 'role': 'assistant', 'content': '네 가지 시나리오', 'status': 'complete', 'status_label': ''}]}
    calls, errors, agent_requests = [], [], []
    state = {'running': False}

    def route(r):
        path = urlsplit(r.request.url).path
        if path == '/launcher/app':
            r.fulfill(content_type='text/html', body=launcher_html())
            return
        data = {}
        if path == '/projects':
            data = {'projects': [{'id': '연구1', 'name': '연구1', 'project_kind': 'research', 'project_uid': 'u1'},
                                 {'id': 'p', 'name': '일반'}]}
        elif '/agents' in path:
            agent_requests.append(path)
            data = {'agents': []}
        elif path == '/ibl/execute':
            body = r.request.post_data_json
            assert body['code'].startswith('[self:project]{') and body['edition'] == 2
            inputs = body['inputs']
            calls.append(inputs)
            assert inputs['project_ref'] == 'u1'
            op = inputs['op']
            if op == 'thread_list':
                data = {'success': True, 'items': [] if inputs['archived'] else threads, 'next_cursor': None}
            elif op == 'thread_messages':
                items = messages.get(inputs['thread_ref'], [])
                if state['running']:  # 접수 다음 조회에서 실행을 끝낸다
                    state['running'] = False
                    items.append({'id': 4, 'role': 'assistant', 'content': '새 답변', 'status': 'complete', 'status_label': ''})
                data = {'success': True, 'items': items, 'next_cursor': None, 'active_run': None}
            elif op == 'thread_send':
                messages['t1'].append({'id': 3, 'role': 'user', 'content': inputs['message'], 'status': 'complete', 'status_label': ''})
                state['running'] = True
                data = {'success': True, 'items': []}
            elif op == 'thread_create':
                threads.append({'id': 't3', 'title': inputs['title'], 'updated_label': '방금'})
                data = {'success': True, 'items': [threads[-1]]}
        r.fulfill(content_type='application/json', body=json.dumps(data))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 390, 'height': 844})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('**/*', route)
        page.goto('http://repair.test/launcher/app')
        browse = page.locator('#apBrowse')
        expect(browse).to_contain_text('주제별 대화')
        browse.get_by_text('연구1', exact=True).click()
        # 에이전트 목록이나 '에이전트가 없습니다' 경고 대신 주제가 보인다
        expect(browse).to_contain_text('주제 2')
        expect(browse.get_by_text('우크라이나', exact=True)).to_be_visible()
        expect(browse.get_by_text('교육', exact=True)).to_be_visible()
        assert agent_requests == []
        browse.get_by_text('우크라이나', exact=True).click()
        expect(page.locator('#apTitle')).to_contain_text('우크라이나')
        expect(page.locator('#apMsgs')).to_contain_text('네 가지 시나리오')
        page.locator('#apInput').fill('다음 질문')
        page.locator('#apSend').click()
        expect(page.locator('#apMsgs')).to_contain_text('새 답변', timeout=15000)
        sent = [c for c in calls if c['op'] == 'thread_send']
        assert len(sent) == 1 and sent[0]['thread_ref'] == 't1' and sent[0]['message'] == '다음 질문'
        # 뒤로 가면 같은 프로젝트의 주제 목록으로 돌아오고 새 주제를 만들 수 있다
        page.evaluate('apExitChat()')
        expect(browse).to_contain_text('주제 2')
        page.once('dialog', lambda d: d.accept('경제'))
        browse.get_by_text('＋ 새 주제').click()
        expect(browse).to_contain_text('주제 3')
        expect(browse.get_by_text('경제', exact=True)).to_be_visible()
        assert errors == []
        browser.close()


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
