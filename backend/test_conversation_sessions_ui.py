"""실제 React 화면: 세션 전환·진행 중 새 대화·재접속·기존 연구 연결 유지."""
import json
import os
from pathlib import Path
import socket
import subprocess
import time
from urllib.parse import urlparse, parse_qs
from urllib.request import urlopen

import pytest


@pytest.mark.system
def test_session_workspace_in_browser(tmp_path):
    from playwright.sync_api import sync_playwright, expect
    root = Path(__file__).resolve().parents[1]
    vite = root / 'frontend/node_modules/.bin/vite'
    if not vite.exists():
        pytest.skip('frontend dependencies are not installed')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    log = (tmp_path/'vite.log').open('w')
    server = subprocess.Popen([str(vite), '--host', '127.0.0.1', '--port', str(port)],
                              cwd=root/'frontend', stdout=log, stderr=subprocess.STDOUT)
    items = [{'id':'old','title':'회의 준비','archived':0,'running':False,'updated_at':'2026-10-15T01:00:01Z'}]
    records = {'old':[{'id':'51','role':'user','content':'지난 회의의 결정은 보존해줘.', 'timestamp':'2026-10-14T17:00:00Z','images':[]},
                      {'id':'52','role':'assistant','content':'**결정 사항**을 보존했습니다.', 'timestamp':'2026-10-15T01:00:01Z','images':[]}]}
    records['old'] = [{'id':str(i),'role':'user','content':f'오래된 대화 {i}',
        'timestamp':f'2026-10-{13 if i <= 2 else 14}T01:00:00Z','images':[]} for i in range(1,51)] + records['old']
    turns, sent = {}, []
    def api(route):
        request = route.request
        path = urlparse(request.url).path
        body = request.post_data_json if request.post_data else {}
        result = {}
        if path == '/chat-sessions':
            if request.method == 'POST':
                item = {'id':f'new{len(items)}','title':'새 세션','archived':0,'running':False,'updated_at':'2026-10-16T01:00:00Z'}
                items.insert(0,item); records[item['id']] = []; result = item
            else: result = {'sessions':items}
        elif path.startswith('/chat-sessions/'):
            sid = path.split('/')[2]
            if path.endswith('/messages'):
                sent.append((sid,body['message']))
                records[sid].append({'id':str(10+len(sent)),'role':'user','content':body['message'], 'timestamp':'2026-10-15T02:00:00Z','images':[]})
                turns[sid]={'id':'turn-'+sid,'state':'running','stream_content':'진행 중인 답변'}
                next(i for i in items if i['id']==sid).update(running=True,title=body['message'])
                result={'session_id':sid,'turn_id':'turn-'+sid}
            elif path.endswith('/cancel'):
                turns[sid]['state']='cancelled';next(i for i in items if i['id']==sid)['running']=False
                result={'cancelled':True}
            elif request.method == 'PATCH':
                item=next(i for i in items if i['id']==sid); item.update({k:v for k,v in body.items() if k in ('title','archived')});result=item
            else:
                before=int(parse_qs(urlparse(request.url).query).get('before',['999999'])[0])
                rows=[r for r in records[sid] if int(r['id']) < before]
                result={'messages':rows[-50:],'has_older':len(rows)>50,'events':[], 'turn':turns.get(sid),'panels':{}}
        route.fulfill(status=200,content_type='application/json',body=json.dumps(result),headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*'})
    try:
        for _ in range(100):
            try:
                with urlopen(url,timeout=1): break
            except Exception:
                if server.poll() is not None: pytest.fail((tmp_path/'vite.log').read_text())
                time.sleep(.1)
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True)
            try:
                page=browser.new_page(viewport={'width':1280,'height':900},timezone_id='Asia/Seoul')
                errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.route('http://127.0.0.1:8765/**',api)
                # Reproduce a long-lived Vite server serving the pre-session catalog.
                stale_catalog=json.loads((root/'frontend/i18n/catalog.json').read_text())
                stale_catalog['messages']={k:v for k,v in stale_catalog['messages'].items()
                    if not any(name in v.get('context','') for name in ('SessionWorkspace.tsx','SessionHistory.tsx'))}
                page.route('**/i18n/catalog.json*',lambda route:route.fulfill(
                    content_type='application/javascript',body='export default '+json.dumps(stale_catalog)))
                page.goto(url+'/#/system-ai')
                expect(page.get_by_text('지난 회의의 결정은 보존해줘.',exact=True)).to_be_visible()
                expect(page.get_by_role('complementary',name='대화 세션')).to_have_count(0)
                textbox=page.locator('textarea').last
                menu=page.get_by_label('대화 세션 메뉴').bounding_box()
                assert menu['y']+menu['height'] <= textbox.bounding_box()['y']
                page.get_by_role('button',name='새 세션',exact=True).click()
                expect(page.get_by_text('지난 회의의 결정은 보존해줘.',exact=True)).not_to_be_visible()
                textbox.fill('새 주제 조사');textbox.press('Enter')
                expect(page.get_by_text('진행 중인 답변',exact=False)).to_be_visible()
                assert sent == [('new1','새 주제 조사')]
                page.get_by_role('button',name='새 세션',exact=True).click()
                expect(page.get_by_text('진행 중인 답변',exact=False)).not_to_be_visible()
                assert turns['new1']['state']=='running'
                page.get_by_role('button',name='히스토리',exact=True).click()
                page.get_by_role('button',name='새 주제 조사 진행 중').click()
                expect(page.get_by_text('진행 중인 답변',exact=False)).to_be_visible()
                page.reload()
                expect(page.get_by_text('진행 중인 답변',exact=False)).to_be_visible()
                page.get_by_role('button',name='히스토리',exact=True).click()
                page.get_by_role('button',name='회의 준비',exact=True).click()
                expect(page.get_by_text('지난 회의의 결정은 보존해줘.',exact=True)).to_be_visible()
                expect(page.get_by_text('0',exact=True)).to_have_count(0)
                expect(page.locator('[data-message-day="2026-10-14"]')).to_be_visible()
                expect(page.locator('[data-message-day="2026-10-15"]:visible')).to_have_count(1)
                expect(page.locator('[data-message-day="2026-10-13"]')).to_have_count(0)
                page.get_by_role('button',name='이전 대화 읽기',exact=True).click()
                expect(page.get_by_text('오래된 대화 1',exact=True)).to_be_visible()
                expect(page.locator('[data-message-day="2026-10-13"]')).to_be_visible()
                expect(page.get_by_role('button',name='이전 대화 읽기',exact=True)).to_have_count(0)
                items.append({'id':'archived','title':'과거 기록','archived':1,'updated_at':'2026-10-10T01:00:00Z'})
                records['archived']=[{'id':'100','role':'user','content':'보관한 대화 원문','timestamp':'2026-10-10T01:00:00Z','images':[]}]
                page.get_by_role('button',name='히스토리',exact=True).first.click()
                history=page.get_by_role('dialog',name='대화 히스토리')
                expect(history.locator('[data-session-day="2026-10-10"]')).to_be_visible()
                box=history.bounding_box()
                assert abs(box['x'] + box['width']/2 - 640) < 2
                expect(history.get_by_role('searchbox',name='세션 검색')).to_be_focused()
                page.screenshot(path=str(tmp_path/'session-history.png'))
                history.get_by_role('searchbox',name='세션 검색').fill('2026-10-10')
                expect(history.get_by_role('button',name='회의 준비')).to_have_count(0)
                history.get_by_role('button',name='과거 기록 보관됨').click()
                expect(history).to_have_count(0)
                expect(page.get_by_text('보관한 대화 원문',exact=True)).to_be_visible()
                expect(page.get_by_text('보관된 세션입니다. 복원 후 이어갈 수 있습니다.')).to_be_visible()
                page.get_by_role('button',name='히스토리',exact=True).first.click()
                history.get_by_role('button',name='회의 준비',exact=True).click()
                expect(page.get_by_text('지난 회의의 결정은 보존해줘.',exact=True)).to_be_visible()
                page.screenshot(path=str(tmp_path/'system-ai-sessions.png'))
                # Reuse the real React component with project/research adapters, not a copied UI.
                page.evaluate("""async () => {
                  const React = (await import('/node_modules/.vite/deps/react.js')).default;
                  const {createRoot} = (await import('/node_modules/.vite/deps/react-dom_client.js')).default;
                  const {ChatView} = await import('/src/components/chat/ChatView.tsx');
                  document.getElementById('root').style.display='none';
                  const mount=document.createElement('div'); document.body.append(mount);
                  window.fixtureRoot=createRoot(mount);window.fixtureReact=React;window.fixtureChat=ChatView;
                  fixtureRoot.render(React.createElement('div',{style:{display:'flex',height:'800px'}},
                    React.createElement('aside',{style:{width:'240px'}},'에이전트 목록',React.createElement('div',{id:'project-sessions',style:{height:'650px'}})),
                    React.createElement(ChatView,{chatTarget:{type:'agent',projectId:'fixture',agent:{id:'a',name:'자료 정리',ai:{model:'test'}}},layout:'fullpage'})));
                }""")
                expect(page.locator('#project-sessions')).to_be_empty()
                expect(page.get_by_role('button',name='새 세션',exact=True)).to_be_visible()
                page.screenshot(path=str(tmp_path/'project-agent-sessions.png'))
                page.evaluate("""() => {
                  fixtureRoot.render(fixtureReact.createElement(fixtureChat,{chatTarget:{type:'session',id:'research-topic',title:'연구 주제'},
                    session:{messages:[{id:'r1',role:'assistant',content:'이 주제의 자료와 분석',timestamp:new Date()}],loading:false,
                    loadOlder:async()=>{},send:async()=>true,cancel:async()=>{}}}));
                }""")
                expect(page.get_by_text('이 주제의 자료와 분석',exact=True)).to_be_visible()
                expect(page.get_by_role('complementary',name='대화 세션')).to_have_count(0)
                expect(page.get_by_role('button',name='새 세션',exact=True)).not_to_be_visible()
                # Real IndexedDB migration preserves old member records once and keeps members apart.
                page.add_script_tag(content=(root/'backend/static/member_browser_store.js').read_text())
                migration=page.evaluate("""async () => {
                  const store=await MemberBrowserStore.open('session-fixture');
                  await store.put('conversations','old',{id:'old',user:'기존 질문',assistant:'기존 응답',created:1});
                  const other=await MemberBrowserStore.open('another-member');
                  await other.put('conversations','old',{id:'old',user:'다른 회원',created:1});
                  await store.recover();await store.recover();
                  const result={task:await store.get('tasks','legacy-conversation'),record:await store.get('conversations','old'),
                    other:await other.get('conversations','old')};store.db.close();other.db.close();return result;
                }""")
                assert [e['value'] for e in migration['task']['events']]==['기존 질문','기존 응답']
                assert migration['record']['task_id']=='legacy-conversation'
                assert 'task_id' not in migration['other']
                assert not errors,errors
            finally: browser.close()
    finally:
        server.terminate()
        try: server.wait(timeout=10)
        except subprocess.TimeoutExpired: server.kill();server.wait()
        log.close()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
