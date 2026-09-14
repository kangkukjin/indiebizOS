"""설치 없는 회원 웹앱의 실행·연결·재실행 경계."""
import boot_paths
import asyncio
import json
from pathlib import Path
import re
import shutil
import subprocess
import threading

import pytest
import principal as P
import member_runtime as MR


def test_browser_entry_is_executable_without_helper():
    from member_entry import entry_html
    html = entry_html()
    assert 'memberLogin' in html and 'MemberBrowserRuntime' in html
    assert '브라우저의 내 작업 공간' in html
    assert 'PC 연결 프로그램 다운로드' not in html
    assert "connect-src 'none'" in html
    if not shutil.which('node'):
        pytest.skip('node required')
    for script in re.findall(r'<script[^>]*>(.*?)</script>', html, re.S):
        subprocess.run(['node', '--check'], input=script, text=True, capture_output=True, check=True)


def test_javascript_requires_browser_capability_and_local_task(tmp_path, monkeypatch):
    from member_runner import MemberRunner
    import member_bridge
    sent = []
    monkeypatch.setattr(member_bridge, 'request', lambda command, **kw: sent.append(command) or {'success': True})
    runner = MemberRunner.__new__(MemberRunner)
    token = P.set_transport(P.OWNER)
    try:
        with P.narrow(P.member('a', 4, 'd')), MR.turn_scope(tmp_path, 'd', 'hub-task', threading.Event(), {}):
            assert not json.loads(runner._member_tool('run_javascript', {'code': 'return 1'}))['success']
            MR.current().update(javascript_available=True, local_task_id='local-task')
            assert json.loads(runner._member_tool('run_javascript', {'code': 'return input*2', 'input': 21}))['success']
            assert 'run_command' not in runner._get_available_tools()
    finally:
        P.reset_transport(token)
    assert sent == [{'op': 'javascript', 'code': 'return input*2', 'input': 21}]


def test_stale_browser_cannot_cancel_or_submit_new_work(monkeypatch):
    import api_member
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    monkeypatch.setattr(api_member, '_member_of', lambda key: (({'session': 'new', 'device_id': 'd'}, 'a', 4), None))
    app = FastAPI(); app.include_router(api_member.router)
    with TestClient(app) as client:
        for path in ['/m/session/close', '/m/run']:
            result = client.post(path, json={'key': 'synthetic', 'body_session': 'old', 'task_id': 'local-task', 'message': 'test'}).json()
            assert result == {'success': False, 'error': 'stale_browser_session'}


def test_stale_browser_result_is_not_written(monkeypatch):
    import api_limb
    monkeypatch.setattr(api_limb.limb_keys, 'validate', lambda key: {'session': 'new', 'device_id': 'd'})
    monkeypatch.setattr(api_limb.phone_jobs, 'set_result', lambda *args: pytest.fail('stale result written'))
    result = asyncio.run(api_limb.limb_result(api_limb.ResultRequest(key='synthetic', session='old', job_id='job', result={})))
    assert not result['success']


def test_bridge_does_not_dispatch_to_replacement_browser(tmp_path, monkeypatch):
    import member_bridge, limb_keys
    monkeypatch.setattr(limb_keys, 'get_by_device', lambda d: {'session': 'new'})
    monkeypatch.setattr(member_bridge.phone_jobs, 'enqueue', lambda *args: pytest.fail('stale command enqueued'))
    token = P.set_transport(P.OWNER)
    try:
        with P.narrow(P.member('a', 4, 'd')), MR.turn_scope(tmp_path, 'd', 'hub-task', threading.Event(), {}):
            MR.current()['body_session'] = 'old'
            assert not member_bridge.request({'op': 'write'})['success']
    finally:
        P.reset_transport(token)


def test_browser_runtime_receipts_and_path_boundaries():
    if not shutil.which('node'):
        pytest.skip('node required')
    root = Path(__file__).parent / 'static'
    source = '\n'.join((root / f'member_browser_{name}.js').read_text() for name in ['store', 'files', 'runtime'])
    checks = r'''
const assert=require('node:assert/strict');
globalThis.crypto=require('node:crypto').webcrypto;
class Store {
 constructor(){this.tables=new Map()}
 async get(t,id){return this.tables.get(t+':'+id)}
 async put(t,id,v){this.tables.set(t+':'+id,v);return v}
 async all(t){return [...this.tables].filter(([k])=>k.startsWith(t+':')).map(([,v])=>v)}
 async change(t,id,f){return this.put(t,id,f(await this.get(t,id)))}
}
(async()=>{
 const store=new Store(),r=new MemberBrowserRuntime('synthetic',store);r.session='epoch';
 await store.put('tasks','task',{id:'task',events:[]});let effects=0;r.approve=async()=>true;
 r.execute=async()=>{effects++;return {success:true}};
 const c={member:true,body_session:'epoch',request_key:'receipt',task_id:'task',op:'write',path:'a',content:'test'};
 assert.equal((await r.run({...c,body_session:'old'})).success,false);
 assert.equal((await r.run({...c,task_id:'other'})).success,false);
 assert.equal((await r.run(c)).success,true);assert.deepEqual(await r.run(c),(await store.get('jobs','receipt')).result);assert.equal(effects,1);
 await assert.rejects(r.run({...c,content:'different'}));
 await store.put('jobs','unknown',{fingerprint:await memberDigest(JSON.stringify({...c,request_key:'unknown'})),state:'running'});
 assert.equal((await r.run({...c,request_key:'unknown'})).error,'result_unknown');assert.equal(effects,1);
 r.approve=async()=>false;assert.equal((await r.run({...c,request_key:'denied'})).success,false);assert.equal(effects,1);
 const files=new MemberBrowserFiles(store);
 for(const path of ['../secret','/etc/passwd','C:\\secret'])await assert.rejects(files.execute({op:'write',path,content:'x'}));
 await files.execute({op:'write',path:'notes/one.txt',content:'회원 파일'});
 assert.equal((await files.execute({op:'read',path:'notes/one.txt'})).content,'회원 파일');
 assert.equal((await files.execute({op:'list',path:'.'})).items[0].name,'notes');
 await assert.rejects(files.execute({op:'mkdir',path:'notes/one.txt'}));
 assert.equal((await files.execute({op:'read',path:'notes/one.txt'})).content,'회원 파일');
 await assert.rejects(files.execute({op:'write',path:'notes/one.txt/child',content:'x'}));
 const other=new MemberBrowserFiles(new Store());await assert.rejects(other.execute({op:'read',path:'notes/one.txt'}));
 console.log('browser boundaries passed');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    subprocess.run(['node'], input=source + '\n' + checks, text=True, capture_output=True, check=True)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
