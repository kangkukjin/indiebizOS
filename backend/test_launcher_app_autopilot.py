"""원격 채팅 대상 전환 시 작성문·주행 분석 초안의 수신자 경계."""
import json
from urllib.parse import urlsplit, parse_qs

import boot_paths  # noqa: F401
import pytest
from playwright.sync_api import expect, sync_playwright


@pytest.fixture
def browser_chat():
    from launcher_surface_remote import launcher_html

    sent = []
    errors = []
    sessions = {}
    messages = {}
    turns = {}
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
        elif path == '/chat-sessions':
            body = r.request.post_data_json if r.request.method == 'POST' else {k:v[0] for k,v in parse_qs(urlsplit(r.request.url).query).items()}
            key=body.get('agent_id','system')
            if key not in sessions:
                sessions[key]=[{'id':key,'title':'기존 대화','archived':0,'updated_at':'2026-10-15T00:00:00Z'}]
                messages[key]=[]
            if r.request.method == 'POST':
                row={'id':key+str(len(sessions[key])),'title':'새 세션','archived':0,'updated_at':'2026-10-16T00:00:00Z'}
                sessions[key].insert(0,row);messages[row['id']]=[];data=row
            else: data={'sessions':sessions[key]}
        elif path.startswith('/chat-sessions/'):
            sid=path.split('/')[2]
            if path.endswith('/messages'):
                body=r.request.post_data_json;sent.append((path,body))
                messages[sid]+=[{'id':str(len(messages[sid])+1),'role':'user','content':body['message'],'timestamp':'2026-10-15T00:00:00Z','images':[]},
                               {'id':str(len(messages[sid])+2),'role':'assistant','content':'응답 완료','timestamp':'2026-10-15T00:01:00Z','images':[]}]
                if body['message']=='계속 실행':turns[sid]={'id':'running-'+sid,'state':'running','stream_content':'진행 중인 답변'}
                data={'session_id':sid,'turn_id':'turn'}
            elif path.endswith('/cancel'):
                turns[sid]={'id':'running-'+sid,'state':'cancelled'};data={'cancelled':True}
            else: data={'messages':messages.get(sid,[]),'has_older':False,'turn':turns.get(sid),'events':[]}
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
    assert path == f'/chat-sessions/{target}/messages'
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
    assert sent == [('/chat-sessions/a/messages',
                     {'target':'agent','project_id':'p','agent_id':'a','message':'현재 사용자 메시지','images':[]})]


def test_analysis_has_no_delayed_write_into_next_chat(browser_chat):
    page, _, _ = browser_chat
    page.evaluate("async()=>{await jAnalyze(123); apPickAgent(0); document.getElementById('apInput').value='새 초안';}")
    # 기존 80ms 지연 콜백이 다른 상대의 새 초안을 덮어쓰던 경로.
    page.wait_for_timeout(150)
    expect(page.locator('#apInput')).to_have_value('새 초안')



def test_sessions_create_resume_reload_and_responsive_layout(browser_chat, tmp_path):
    page,sent,_=browser_chat
    expect(page.locator('#apSessions')).to_be_visible()
    page.locator('#apInput').fill('이전 세션의 질문');page.locator('#apSend').click()
    expect(page.locator('#apMsgs')).to_contain_text('응답 완료')
    page.locator('#apSessionNew').click()
    expect(page.locator('#apSessionTitle')).to_have_text('새 세션')
    expect(page.locator('#apMsgs')).not_to_contain_text('이전 세션의 질문')
    page.locator('#apInput').fill('새 세션의 질문');page.locator('#apSend').click()
    expect(page.locator('#apMsgs')).to_contain_text('응답 완료')
    assert [path for path,_ in sent]==['/chat-sessions/a/messages','/chat-sessions/a1/messages']
    page.locator('#apSessionDetails summary').click()
    page.locator('#apSessionList').get_by_role('button',name='기존 대화',exact=True).click()
    expect(page.locator('#apMsgs')).to_contain_text('이전 세션의 질문')
    expect(page.locator('#apMsgs')).not_to_contain_text('새 세션의 질문')
    page.locator('#apSessionList').get_by_role('button',name='새 세션',exact=True).click()
    page.reload()
    expect(page.locator('#apBrowse')).to_contain_text('프로젝트')
    page.evaluate("async()=>{await apBrowseProject('p');apPickAgent(0)}")
    expect(page.locator('#apMsgs')).to_contain_text('새 세션의 질문')
    page.screenshot(path=str(tmp_path/'remote-mobile-sessions.png'))
    page.set_viewport_size({'width':1280,'height':850})
    page.evaluate('apPickAgent(0)')
    expect(page.locator('#apSessionList')).to_contain_text('2026-10-16')
    sidebar=page.locator('#apSessions').bounding_box();chat=page.locator('#apMsgs').bounding_box()
    assert sidebar['x']+sidebar['width']<=chat['x']+1
    page.screenshot(path=str(tmp_path/'remote-wide-sessions.png'))
    page.locator('#apSessionSearch').fill('2026-10-16')
    expect(page.locator('#apSessionList button')).to_have_count(1)


def test_late_snapshot_does_not_replace_new_session(browser_chat):
    page,_,_=browser_chat
    expect(page.locator('#apSend')).to_be_enabled()
    held=[]
    page.route('**/chat-sessions/a?*',lambda route:held.append(route))
    page.evaluate('void apSessionSnapshot(apSessionContext,apSessionContext.id)')
    page.locator('#apSessionNew').click()
    expect(page.locator('#apSessionTitle')).to_have_text('새 세션')
    assert held
    for route in held:
        route.fulfill(content_type='application/json',body=json.dumps({'messages':[{'id':'1','role':'assistant','content':'늦은 이전 응답','images':[]}],'has_older':False,'turn':None,'events':[]}))
    page.evaluate('void 0')
    expect(page.locator('#apMsgs')).not_to_contain_text('늦은 이전 응답')
    assert page.evaluate('apSessionContext.id')=='a1'

def test_switching_running_session_keeps_run_and_cancel_scoped(browser_chat):
    page,sent,_=browser_chat
    page.locator('#apInput').fill('계속 실행');page.locator('#apSend').click()
    expect(page.locator('#apSessionStop')).to_be_visible()
    expect(page.locator('#apSend')).to_be_disabled()
    page.locator('#apSessionNew').click()
    expect(page.locator('#apSessionTitle')).to_have_text('새 세션')
    expect(page.locator('#apSessionStop')).to_be_hidden()
    expect(page.locator('#apSend')).to_be_enabled()
    page.locator('#apSessionDetails summary').click()
    page.locator('#apSessionList').get_by_role('button',name='기존 대화',exact=True).click()
    expect(page.locator('#apMsgs')).to_contain_text('진행 중인 답변')
    page.locator('#apSessionStop').click()
    expect(page.locator('#apSessionStop')).to_be_hidden()
    expect(page.locator('#apSend')).to_be_enabled()
    assert len(sent)==1


def test_new_session_during_initial_list_load_keeps_user_selection(browser_chat):
    page,_,_=browser_chat
    expect(page.locator('#apSend')).to_be_enabled()
    held=[];created=[]
    page.route('**/chat-sessions?*',lambda route:held.append(route))
    page.route('**/chat-sessions',lambda route:created.append(route))
    page.evaluate('apPickAgent(0)')
    page.locator('#apSessionNew').click()
    assert held and created
    for route in held:
        route.fulfill(content_type='application/json',body=json.dumps({'sessions':[
            {'id':'a','title':'기존 대화','archived':0}]}))
    page.evaluate('void 0')
    for route in created:route.fallback()
    expect(page.locator('#apSessionTitle')).to_have_text('새 세션')
    assert page.evaluate('apSessionContext.id')=='a1'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
