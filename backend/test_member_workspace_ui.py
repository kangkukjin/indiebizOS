"""사용자가 선택한 작업을 앱 버튼과 비동기 대기열에서도 유지한다."""
import boot_paths  # noqa: F401
import json
import subprocess
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


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
