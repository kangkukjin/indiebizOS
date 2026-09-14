"""회원 기본 기능·앱 주체·기기 산출물 전달의 회귀 검사."""
import boot_paths  # noqa: F401
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest
import principal as P


def test_default_open_still_hides_owner_functions_and_unsupported_hardware(monkeypatch):
    import vocabulary_state as vs
    import member_profile as mp
    import member_bridge
    import limb_keys
    monkeypatch.setattr(vs, 'read_state', lambda root=None: {'active': {'pkg': True}})
    monkeypatch.setattr(vs, 'action_owner', lambda *args: 'pkg')
    monkeypatch.setattr(member_bridge, 'connected', lambda d: True)
    monkeypatch.setattr(limb_keys, 'get_by_device', lambda d: {'env': {'client': 'web'}})
    monkeypatch.setattr(mp, 'manifest', lambda root=None: {'actions': {
        'self:write': {'package': 'pkg', 'lands_on': 'body', 'limb_op': {'op': 'write'}},
        'limbs:android': {'package': 'pkg', 'lands_on': 'body', 'limb_op': {'op': 'accessibility'}},
    }})
    token = P.set_transport(P.OWNER)
    try:
        with P.narrow(P.member('a', 4, 'd')):
            assert mp.visible('self', 'write', {})
            assert mp.gate('self', 'write', {}) is None
            for node, action in [('others', 'delegate'), ('self', 'config'), ('limbs', 'android')]:
                assert not mp.visible(node, action, {})
                assert mp.gate(node, action, {})
    finally:
        P.reset_transport(token)


def test_report_has_member_request_and_no_owner_paths(monkeypatch):
    import member_apps
    import limb_keys
    monkeypatch.setattr(limb_keys, 'get_by_device', lambda d: {'env': {'client': 'web'}})
    monkeypatch.setattr(member_apps, 'visible', lambda *args: True)
    report = next(i for i in member_apps.catalogue()['instruments'] if i['id'] == 'report')
    create = report['modes'][0]
    assert create['request']['output'] == 'reports/report.md'
    assert create['request']['workflow'] == 'research_report'
    assert create['client_action_id'] == 'report:create'
    serialized = json.dumps(report)
    for forbidden in ['others:delegate', '@hub', '~workspace', '/Users/', '/switches/']:
        assert forbidden not in serialized


def test_catalogue_drops_owner_targets_and_empty_modes(monkeypatch, tmp_path):
    import member_apps
    import api_launcher_web
    import runtime_utils
    monkeypatch.setattr(runtime_utils, 'get_base_path', lambda: str(tmp_path))
    monkeypatch.setattr(member_apps, 'visible', lambda *args: True)
    monkeypatch.setattr(member_apps, 'load_nodes_installed', lambda: {'nodes': {'self': {
        'actions': {'read': {'app': {'instrument': 'files'}}}}}})
    monkeypatch.setattr(api_launcher_web, '_derive_instruments', lambda **kw: {'instruments': [{
        'id': 'files', 'modes': [
            {'name': 'owner', 'action': '[self:read]{path:"~workspace/private"}'},
            {'name': 'hub', 'action': '[self:read]{path:"notes"}@hub'},
            {'name': 'empty', 'buttons': [{'action': '[others:delegate]{}'}]},
            {'name': 'mine', 'action': '[self:read]{path:"notes"}'},
        ]}]})
    assert [m['name'] for m in member_apps.catalogue()['instruments'][0]['modes']] == ['mine']


def test_browser_has_two_surfaces_and_no_owner_controls():
    from member_browser import browser_html
    html = browser_html()
    nav = re.search(r'<nav id="memberNav">(.*?)</nav>', html).group(1)
    assert re.findall(r'data-view="(.*?)"', nav) == ['drive', 'apps']
    assert 'id="openMemberFiles"' in html and 'id="memberArtifacts"' in html
    assert 'id="gearLever"' not in html and 'data-view="settings"' not in html


def test_real_member_ibl_write_uses_member_device_even_with_hub_target(tmp_path, monkeypatch):
    import member_session
    import member_bridge
    import vocabulary_state
    from member_session import MemberSession, MemberSessionManager
    monkeypatch.setattr(member_session, '_base', lambda: tmp_path)
    monkeypatch.setattr(vocabulary_state, 'read_state', lambda root=None: {
        'version': 1, 'revision': 1, 'active': {'system_essentials': True}})
    monkeypatch.setattr(member_bridge, 'connected', lambda device: True)
    monkeypatch.setattr(MemberSession, '_ensure_runner', lambda self: pytest.fail('시스템/회원 모델 불필요'))
    files = {}
    def exchange(command, **kwargs):
        assert P.current() == P.member('member-a', 4, 'device-a')
        if command['op'] == 'memory_recall':
            return {'success': True, 'history': [], 'javascript_available': True}
        if command['op'] == 'write':
            files[command['path']] = command['content']
            return {'success': True, 'saved': True, 'path': command['path']}
        return {'success': True, 'saved': True}
    monkeypatch.setattr(member_bridge, 'request', exchange)
    token = P.set_transport(P.OWNER)
    try:
        out = MemberSessionManager(tmp_path).turn('member-a', 'device-a', 4, '회원', '보고서 저장',
            local_task_id='local-task', code='[self:write]{path:"reports/mine.md",content:"회원 보고서"}@hub')
    finally:
        P.reset_transport(token)
    assert out['success'], out
    assert files == {'reports/mine.md': '회원 보고서'}
    assert not list(tmp_path.rglob('mine.md'))
    assert not (tmp_path / 'outputs').exists()


def test_report_is_saved_on_client_before_completion_and_survives_failed_delivery():
    if not shutil.which('node'):
        pytest.skip('node required')
    root = Path(__file__).parent / 'static'
    source = '\n'.join((root / f'member_browser_{name}.js').read_text() for name in ['store', 'files', 'runtime'])
    checks = r'''
const assert=require('node:assert/strict');
globalThis.crypto=require('node:crypto').webcrypto;
globalThis.document={getElementById:()=>({textContent:''})};
class Store {
 constructor(){this.tables=new Map()}
 async get(t,id){return this.tables.get(t+':'+id)}
 async put(t,id,v){this.tables.set(t+':'+id,v);return v}
 async all(t){return [...this.tables].filter(([k])=>k.startsWith(t+':')).map(([,v])=>v)}
 async change(t,id,f){return this.put(t,id,f(await this.get(t,id)))}
}
(async()=>{
 const store=new Store(),r=new MemberBrowserRuntime('test-only',store);r.active=true;r.session='epoch';
 let sent;
 const content='# 내 보고서\n자료에 근거한 본문',artifact={id:'a'.repeat(32),name:'report.md',mime:'text/markdown',size:new TextEncoder().encode(content).length,sha256:await memberDigest(content),data:memberBase64(new TextEncoder().encode(content))};
 globalThis.fetch=async(url,options)=>{if(url==='/m/receipts')return new Response(JSON.stringify({success:true,type:'delivered'}));assert.equal(url,'/m/run');sent=JSON.parse(options.body);
   return new Response(JSON.stringify({type:'result',result:{success:true,request_id:'request-a',epoch:'epoch',response:content,artifacts:[artifact]}})+'\n',
     {headers:{'content-type':'application/x-ndjson'}})};
 await store.put('tasks','a',{id:'a',events:[],state:'running'});
 const write=r.files.execute.bind(r.files);let checked=false;
 r.files.execute=async c=>{assert.equal((await store.get('tasks','a')).state,'running');checked=true;return write(c)};
 await r.runTask('a',{message:'보고서 작성',output:'reports/report.md'});
 const task=await store.get('tasks','a');assert.equal(task.state,'completed');assert.equal(task.result.saved,true);assert(checked);
 assert.equal(sent.output,undefined);assert.equal(sent.code,undefined);assert.equal(sent.message,'보고서 작성');
 assert.equal(task.result.files[0].on,'body');assert.equal(task.result.files[0].path,'reports/'+artifact.id+'-report.md');
 const reopened=new MemberBrowserRuntime('test-only',store);
 assert.equal((await reopened.files.execute({op:'read',path:task.result.files[0].path})).content,'# 내 보고서\n자료에 근거한 본문');
 const other=new MemberBrowserFiles(new Store());await assert.rejects(other.execute({op:'read',path:task.result.files[0].path}));
 await assert.rejects(r.start({message:'bad',output:'/Users/owner/report.md'}));
 await store.put('tasks','b',{id:'b',events:[],state:'running'});
 artifact.id='b'.repeat(32);r.files.execute=async()=>{throw Error('storage full')};
 await r.runTask('b',{message:'보고서 작성',output:'reports/report.md'});
 const failed=await store.get('tasks','b');assert.equal(failed.state,'failed');assert.equal(failed.result.success,false);assert.equal(failed.result.saved,false);
 assert.equal(await store.get('files','reports/'+artifact.id+'-report.md'),undefined);
 for(const op of ['write','mkdir','file_move','javascript','memory_save','script'])assert.equal(await r.approve({op}),true);
 await store.put('jobs','echo',{id:'echo',command:{op:'memory_recall',task_id:'a'},result:{history:'PRIVATE_ECHO'.repeat(10000)}});
 await store.put('jobs','binary',{id:'binary',command:{op:'read',task_id:'a'},result:{content:'BINARY_CONTENT'.repeat(10000),success:true}});
 const recall=await r.execute({op:'memory_recall',task_id:'a'});assert(JSON.stringify(recall).length<3000);assert(!JSON.stringify(recall).includes('PRIVATE_ECHO'));assert(!JSON.stringify(recall).includes('BINARY_CONTENT'));
 console.log('member artifact delivery passed');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    subprocess.run(['node'], input=source + '\n' + checks, text=True, capture_output=True, check=True)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
