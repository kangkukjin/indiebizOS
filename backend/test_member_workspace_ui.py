"""사용자가 선택한 작업을 앱 버튼과 비동기 대기열에서도 유지한다."""
import boot_paths  # noqa: F401
import json
import subprocess
import pytest
from member_workspace_ui import workspace_js


def test_app_action_keeps_selected_task_while_queue_waits():
    program = r'''
const vm=require('node:vm');let listener;const calls=[];
const frame={contentWindow:{postMessage:()=>{}}};
const c=vm.createContext({window:{addEventListener:(n,f)=>{listener=f}},document:{getElementById:()=>frame},memberRequest:async(p,b)=>{calls.push(b);return {success:false,error:'stop'};}});
vm.runInContext(SOURCE,c);vm.runInContext("currentTask='selected-task'",c);
listener({source:frame.contentWindow,data:{memberFrame:'request',action_id:'app:action',app_id:'app',args:{}}});
vm.runInContext("currentTask='other-task'",c);
vm.runInContext('memberAppQueue',c).then(()=>{if(calls.length!==1||calls[0].task_id!=='selected-task')throw Error(JSON.stringify(calls));});
'''.replace('SOURCE', json.dumps(workspace_js()))
    subprocess.run(['node', '-e', program], check=True, capture_output=True, text=True)


def test_desktop_bundled_ui_reaches_update_health_handshake(tmp_path):
    """Load the actual generated HTML/CSP and runtime script in a browser."""
    from pathlib import Path
    from playwright.sync_api import sync_playwright, expect
    from member_shell import member_html
    root = Path(__file__).resolve().parents[1]
    html = member_html().replace('<meta charset="utf-8">', '<meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src \'self\' \'unsafe-inline\'; style-src \'unsafe-inline\'; img-src data: blob:; media-src https: http:; frame-src about: blob:; connect-src \'none\'">', 1)
    html = html.replace('</html>', '<script src="workspace.cjs"></script></html>')
    (tmp_path / 'workspace.html').write_text(html)
    (tmp_path / 'workspace.cjs').write_text((root / 'member-desktop/workspace.cjs').read_text())
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.add_init_script('''window.DesktopMember={
                onDisconnected:()=>{},ready:async()=>{window.bootReady=true},
                settings:async()=>({name:'검증 PC',hub:'https://hub.example',startup:false}),
                request:async(path)=>{if(['tasks','approvals','results','media','changes'].includes(path))return [];
                    if(path==='workspace')return {success:true,workspace:'/selected'};
                    if(path==='apps')return {success:true,instruments:[{id:'sample',name:'검증 앱',modes:[]}]};return {success:true,screen:false};},
                updateStatus:async()=>({state:'unconfigured',configured:false,auto:false}),
                updateCheck:async()=>{},updateApply:async()=>{},updateAuto:async()=>{},
                startup:async()=>{},disconnect:async()=>{},importArchive:async()=>{},saveDiagnostics:async()=>{},
                chooseWorkspace:async()=>({cancelled:true}),openFile:async()=>{}
            };''')
            page.goto((tmp_path / 'workspace.html').as_uri())
            page.wait_for_function('window.bootReady===true')
            page.get_by_text('앱 업데이트', exact=True).click()
            expect(page.locator('#desktopUpdateStatus')).to_contain_text('업데이트 채널')
            expect(page.locator('#desktopUpdateCheck')).to_be_disabled()
            page.locator('[data-view="apps"]').click()
            expect(page.frame_locator('#appFrame').get_by_role('button', name='검증 앱')).to_be_visible()
            assert not errors, errors
        finally:
            browser.close()


@pytest.mark.parametrize('bridge', ['desktop', 'native'])
def test_sessions_preserve_history_and_switch_surfaces(tmp_path, bridge):
    """Exercise real DOM/layout with a deterministic local task transport."""
    from playwright.sync_api import sync_playwright, expect
    from member_shell import member_html

    (tmp_path / 'workspace.html').write_text(member_html())
    stub = r'''
    window.fixtureTasks=[{id:'old',title:'회의 준비',state:'completed',workspace:'/selected',
      events:[{kind:'user',value:'회의에서 확인할 내용을 정리해줘.'},
      {kind:'assistant',value:'다음 세 가지를 확인해 보세요.\n\n- **일정**과 참석자\n- 논의할 안건\n- 필요한 자료'}]}];
    window.fixtureRequests=[];
    window.fixtureRequest=async(path,body)=>{
      fixtureRequests.push({path,body});
      if(path==='tasks')return fixtureTasks;
      if(path.startsWith('task?id=')){
        const result=structuredClone(fixtureTasks.find(t=>t.id===decodeURIComponent(path.slice(8))));
        if(window.delayTask)await new Promise(resolve=>window.releaseTask=resolve);
        return result;
      }
      if(path==='task/start'){
        const id=body.task_id||('new-'+fixtureTasks.length);let t=fixtureTasks.find(t=>t.id===id);
        if(!t){t={id,title:body.create_only?'새 세션':body.message,state:'completed',workspace:'/selected',events:[]};fixtureTasks.unshift(t)}
        if(body.create_only)return {success:true,task_id:id};
        if(t.title==='새 세션')t.title=body.message;
        t.events.push({kind:'user',value:body.message},{kind:'assistant',value:'새 세션에서 답변합니다.'});
        if(window.delayStart)await new Promise(resolve=>window.releaseStart=resolve);
        return {success:true,task_id:id};
      }
      if(['approvals','results','media'].includes(path))return [];
      if(path==='apps')return {success:true,instruments:[{id:'sample',name:'검증 앱',modes:[]}]};
      if(path==='workspace')return {success:true,workspace:'/selected'};
      return {success:true};
    };
    '''
    if bridge == 'desktop':
        stub += 'window.DesktopMember={request:fixtureRequest};'
    else:
        stub += '''window.MemberBridge={request:async(id,path,body)=>{
          window.memberNativeResult(id,await fixtureRequest(path,JSON.parse(body)));
        }};'''
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.add_init_script(stub)
            page.goto((tmp_path / 'workspace.html').as_uri())
            expect(page.locator('#chat .bubble')).to_have_count(2)
            expect(page.locator('#taskTitle')).to_have_text('회의 준비')
            expect(page.locator('#chatEmpty')).to_be_hidden()
            expect(page.locator('#chat .assistant b')).to_have_text('일정')
            expect(page.locator('#taskSidebar')).to_have_count(0)
            menu = page.locator('#taskSessionMenu').bounding_box()
            title = page.locator('#taskTitle').bounding_box()
            assert menu['y'] <= title['y'] < menu['y'] + menu['height']
            chat = page.locator('#chat').bounding_box()
            assert menu['y'] + menu['height'] < chat['y']
            assert chat['width'] > 1000
            expect(page.locator('#taskHistory')).not_to_be_visible()
            composer = page.locator('#send').bounding_box()
            assert composer['y'] + composer['height'] <= 900
            page.screenshot(path=str(tmp_path / 'sessions.png'))

            page.locator('[data-view="apps"]').click()
            expect(page.frame_locator('#appFrame').get_by_role('button', name='검증 앱')).to_be_visible()
            expect(page.locator('#send')).to_be_hidden()
            expect(page.locator('#drivePanel')).to_be_hidden()
            page.screenshot(path=str(tmp_path / 'apps.png'))
            page.locator('#openMemberFiles').click()
            expect(page.locator('#filesPanel')).to_be_visible()
            page.locator('#backToApps').click()
            expect(page.locator('#appsPanel')).to_be_visible()

            page.locator('#newTask').click()
            expect(page.locator('#chat .bubble')).to_have_count(0)
            expect(page.locator('#chatEmpty')).to_be_visible()
            expect(page.locator('#send')).to_be_visible()
            expect(page.locator('#taskList button')).to_have_count(2)
            page.screenshot(path=str(tmp_path / 'new-session.png'))
            page.locator('#message').fill('새 대화의 질문')
            page.locator('#sendButton').click()
            expect(page.locator('#taskTitle')).to_have_text('새 대화의 질문')
            expect(page.locator('#chat')).not_to_contain_text('회의에서')
            expect(page.locator('#chat .bubble')).to_have_count(2)
            expect(page.locator('#taskList button')).to_have_count(2)
            page.locator('#taskHistoryOpen').click()
            page.get_by_role('button', name='회의 준비 완료').click()
            expect(page.locator('#taskHistory')).not_to_be_visible()
            expect(page.locator('#chat')).to_contain_text('회의에서')
            assert page.evaluate('fixtureTasks.find(t=>t.id==="old").events.length') == 2

            # A response to an earlier selection must not refill the new session.
            page.evaluate('delayTask=true; taskSignature=""; void refreshTasks()')
            page.wait_for_function('!!window.releaseTask')
            page.locator('#newTask').click()
            page.evaluate('delayTask=false; releaseTask()')
            page.wait_for_function('!taskBusy')
            expect(page.locator('#chat .bubble')).to_have_count(0)
            expect(page.locator('#taskTitle')).to_have_text('새 세션')

            # Starting a request and immediately starting a new session is also safe.
            page.evaluate('delayStart=true')
            page.locator('#message').fill('늦게 접수되는 요청')
            page.locator('#sendButton').click()
            page.wait_for_function('!!window.releaseStart')
            page.locator('#newTask').click()
            page.evaluate('delayStart=false; releaseStart()')
            page.wait_for_function('!taskSubmitting')
            expect(page.locator('#chat .bubble')).to_have_count(0)
            expect(page.locator('#message')).to_have_value('')

            page.evaluate("fixtureTasks[0].state='running'; refreshTasks()")
            expect(page.get_by_role('button', name='작업 중단', exact=True)).to_be_visible()
            page.locator('[data-view="apps"]').click()
            expect(page.get_by_role('button', name='작업 중단', exact=True)).to_be_visible()
            assert not errors, errors
        finally:
            browser.close()


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
