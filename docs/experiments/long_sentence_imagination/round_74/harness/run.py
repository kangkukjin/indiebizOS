"""Isolated hub, real signed Go clients; business logic remains in the IBL file."""
import boot_paths  # noqa: F401; invoke with PYTHONPATH=backend
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
import sys
from unittest.mock import patch
import requests
import uvicorn
from fastapi import FastAPI
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption, PublicFormat

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-15_74회차'
DOC = ROOT / 'docs/experiments/long_sentence_imagination/round_74'

def seed(folder, member):
    folder.mkdir(parents=True, exist_ok=True)
    sections = []
    for i in range(1, 13):
        name = f'doc{i:02d}.txt'
        ending = ('\n', '\r\n', '\r')[(i-1)%3]
        lines = [f'비공개 {member} 내부{i}', ('배포 제외 표지\u2028비공개 구분자\v표지 계속' if os.environ.get('L74_UNICODE') and i==1 else '배포 제외 표지'),
                 f'{member} 절차{i} 첫 줄  ', f'  한글 🧭 "인용"\t{i}',
                 f'마지막 공개 줄 {i}  ', '비공개 부록', '내부 연락처 가상', '끝']
        (folder/name).write_bytes((ending.join(lines)+ending).encode())
        sections.append({'id':f'S{i:02d}', 'path':name, 'start_line':3, 'end_line':5})
    (folder/'manifest.json').write_text(json.dumps({'sections':sections}))


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env')
    import api_limb, api_member_desktop, member_session, limb_keys, device_registry
    import client_agent, member_desktop_requests as service
    from contextlib import ExitStack
    label = sys.argv[1]; codefile = sys.argv[2] if len(sys.argv)>2 else 'draft_v0.ibl'
    root = OUT / label; root.mkdir(parents=True, exist_ok=True)
    hub = root/'hub'; hub.mkdir(exist_ok=True)
    (hub/'data').mkdir(exist_ok=True)
    (hub/'data/member_role.md').write_bytes((ROOT/'data/member_role.md').read_bytes())
    (hub/'data/member_policy.json').write_bytes((ROOT/'data/member_policy.json').read_bytes())
    evidence = []; processes=[]; envelopes={}; calls={}
    original_run=client_agent.run
    def traced(envelope, resolved, **kwargs):
        rid=envelope['request_id']; envelopes[rid]=dict(envelope); calls[rid]=calls.get(rid,0)+1
        value=original_run(envelope,resolved,**kwargs)
        return value
    if codefile == 'AI':
        import faulthandler
        trace = (root/'threads.txt').open('w')
        faulthandler.dump_traceback_later(45, file=trace)
    else:
        from system_tools import _execute_ibl_unified
        checked = _execute_ibl_unified({'code':(DOC/codefile).read_text(),'check':True,'origin':'training'},str(root),agent_id='training74')
        (root/'check.json').write_text(checked if isinstance(checked,str) else json.dumps(checked,ensure_ascii=False))
    original_init=member_session.MemberSession._ensure_runner
    def init(session):
        original_init(session)
        provider=session.runner.ai._provider
        (root/'model.json').write_text(json.dumps({'provider':getattr(provider,'provider_name',type(provider).__name__),'model':getattr(provider,'model',None)}))
    with ExitStack() as stack:
        stack.enter_context(patch.object(member_session.MemberSession,'_ensure_runner',init))
        stack.enter_context(patch.object(client_agent,'run',traced))
        stack.enter_context(patch.object(limb_keys,'_store_path',lambda:hub/'data/limb_keys.json'))
        stack.enter_context(patch.object(device_registry,'_store_path',lambda:hub/'data/device_registry.json'))
        stack.enter_context(patch.object(limb_keys,'_cache',None))
        stack.enter_context(patch.object(device_registry,'_cache',None))
        stack.enter_context(patch.object(api_limb,'_notify_new_limb',lambda *a:None))
        stack.enter_context(patch.object(api_limb,'_notify_host_change',lambda *a:None))
        stack.enter_context(patch.object(member_session,'_base',lambda:hub))
        stack.enter_context(patch.object(member_session.MemberSessionManager,'_instance',None))
        app=FastAPI();app.include_router(api_limb.router);app.include_router(api_member_desktop.router)
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='off'))
        thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
        try:
            clients=[]
            for name in (('A',) if codefile=='AI' else ('A','B')):
                issued=limb_keys.mint('training-'+name,member_pc={})
                private=Ed25519PrivateKey.generate()
                public=base64.b64encode(private.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode()
                with limb_keys._lock:
                    limb_keys._load()['keys'][issued['key']]['desktop']={'installation_id':name,'public_key':public};limb_keys._save()
                config={'mode':'member','desktop':True,'base':f'http://127.0.0.1:{port}','key':issued['key'],
                    'private_key':base64.b64encode(private.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption())).decode(),'data_dir':str(root/name)}
                log=(root/f'{name}-executor.log').open('w');stack.callback(log.close)
                proc=subprocess.Popen(['/tmp/indiebiz-member-l74','--member-desktop'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True);processes.append(proc)
                proc.stdin.write(json.dumps(config)+'\n');proc.stdin.flush();ready=json.loads(proc.stdout.readline())
                def local(path,body=None,ready=ready):
                    r=requests.request('GET' if body is None else 'POST',ready['origin']+'/member/'+path,json=body,headers={'X-Member-Token':ready['token']},timeout=10);r.raise_for_status();return r.json()
                deadline=time.monotonic()+15
                while not limb_keys.get_by_device(issued['device_id']).get('session'):
                    if time.monotonic()>deadline:raise RuntimeError('connect timeout')
                    time.sleep(.1)
                folder=root/name/'workspace';seed(folder,name);clients.append((name,local,folder))
            def run(name,local,folder,variant):
                start=time.time()
                if variant=='broken':(folder/'doc04.txt').unlink()
                if variant=='recovered':
                    seed(folder,name)
                    manifest=json.loads((folder/'manifest.json').read_text())
                    manifest['sections'].reverse(); manifest['sections'][0].update(start_line=1,end_line=1)
                    (folder/'manifest.json').write_text(json.dumps(manifest))
                payload={'message':(DOC/'task.md').read_text().split('## 자연어 요청 원문\n')[1].split('\n\n##')[0]} if codefile=='AI' else {'message':'긴문장74 '+variant,'code':(DOC/codefile).read_text()}
                if variant=='broken' and codefile=='AI':
                    payload['message'] += '\n조건 변경: doc04.txt를 읽지 못하게 되었다. 네 직전 결과는 재사용해도 되지만 다른 실행자의 결과나 정답은 참조하지 마. 기존 보고서를 갱신해 줘.'
                    payload['task_id']=evidence[-1]['task_id']
                sources=[folder/'manifest.json',*sorted(folder.glob('doc*.txt'))]
                before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
                queued=local('task/start',payload);tid=queued.get('task_id');approvals=[]
                deadline=time.monotonic()+(int(os.environ.get('L74_AI_TIMEOUT', '240')) if codefile=='AI' else 40)
                while time.monotonic()<deadline:
                    for a in local('approvals'):
                        approvals.append(a['command'])
                        if variant=='cancel' and a['command'].get('op')=='write':
                            local('close',{})
                        else:
                            local('approve',{'key':a['key'],'allow':True})
                    result=local('task?id='+tid)
                    if result['state']!='running':break
                    time.sleep(.1)
                else:
                    (root/f'{name}-{variant}-before-cancel.json').write_text(json.dumps(result,ensure_ascii=False))
                    local('close',{})
                    for _ in range(100):
                        result=local('task?id='+tid)
                        if result['state']!='running':break
                        time.sleep(.1)
                row={'member':name,'variant':variant,'task_id':tid,'seconds':time.time()-start,'result':result,'commands':approvals}
                row['inputs_unchanged']=before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
                row['input_hashes']=before
                row['artifacts']={p.name:base64.b64encode(p.read_bytes()).decode() for p in folder.iterdir() if p.name in ('excerpts.json','handbook.txt')}
                # Read central state directly for diagnostics, never use it as a business result.
                rid=next((r for r,e in envelopes.items() if e['conversation_id']==tid),None)
                if rid:
                    rec=next(r for r in limb_keys._load()['keys'].values() if r['device_id'] in [k[0] for k in service.LIVE if k[1]==rid])
                    before_calls=calls[rid]
                    row['hub_status']=service.status(rec,rid)
                    replay={**envelopes[rid],'version':2}
                    row['replay']=service.submit(rec,replay,{})
                    row['reexecuted']=calls[rid]-before_calls
                evidence.append(row);(root/'evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
                print(json.dumps({'member':name,'variant':variant,'state':result['state'],'error':result.get('result',{}).get('error'),'seconds':row['seconds']},ensure_ascii=False),flush=True)
            for variant in (('base','broken') if codefile=='AI' else ('base','broken','recovered') if label.startswith('repair') else ('cancel',) if label.startswith('cancel') else ('base','broken')):
                for c in clients:
                    if codefile=='AI' and variant=='broken' and evidence[-1]['result']['state']!='completed': continue
                    run(*c,variant)
        finally:
            for proc in processes:
                proc.stdin.close()
                try:proc.wait(timeout=8)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()
            server.should_exit=True;thread.join(timeout=5);sock.close()
            if codefile=='AI':
                faulthandler.cancel_dump_traceback_later();trace.close()

if __name__=='__main__':main()
