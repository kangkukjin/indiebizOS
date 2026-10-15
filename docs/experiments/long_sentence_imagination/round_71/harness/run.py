"""Isolated hub, real signed Go clients; business logic remains in the IBL file."""
import boot_paths  # noqa: F401; invoke with PYTHONPATH=backend
import base64
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
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-15_71회차'
DOC = ROOT / 'docs/experiments/long_sentence_imagination/round_71'

def seed(folder, member):
    folder.mkdir(parents=True, exist_ok=True)
    files = []
    for i in range(6):
        name = f'batch{i+1:02d}.json'; files.append(name)
        rows = [{'id':f'{member}-{i}-{j}', 'qty':j+1, 'price':(i+1)*100+(0 if member=='A' else 7), 'cancelled':j%4==0} for j in range(8)]
        (folder/name).write_text(json.dumps(rows))
    (folder/'manifest.json').write_text(json.dumps({'files':files}))
    (folder/'source.txt').write_bytes('첫 줄\r\n둘째 줄 🐣\r\n'.encode())


def main():
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env')
    import api_limb, api_member_desktop, member_session, limb_keys, device_registry
    from contextlib import ExitStack
    label = sys.argv[1]; codefile = sys.argv[2] if len(sys.argv)>2 else 'draft_v0.ibl'
    root = OUT / label; root.mkdir(parents=True, exist_ok=True)
    hub = root/'hub'; hub.mkdir(exist_ok=True)
    evidence = []; processes=[]
    if codefile == 'AI':
        import faulthandler
        trace = (root/'threads.txt').open('w')
        faulthandler.dump_traceback_later(45, file=trace)
    else:
        from system_tools import _execute_ibl_unified
        checked = _execute_ibl_unified({'code':(DOC/codefile).read_text(),'check':True,'origin':'training'},str(root),agent_id='training71')
        (root/'check.json').write_text(checked if isinstance(checked,str) else json.dumps(checked,ensure_ascii=False))
    with ExitStack() as stack:
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
                proc=subprocess.Popen(['/tmp/indiebiz-member-l71','--member-desktop'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True);processes.append(proc)
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
                if variant=='broken':(folder/'batch03.json').write_text('{broken')
                if variant=='recovered':
                    seed(folder,name)
                    (folder/'manifest.json').write_text(json.dumps({'files':list(reversed(json.loads((folder/'manifest.json').read_text())['files']))}))
                payload={'message':(DOC/'task.md').read_text().split('## 자연어 요청 원문\n')[1].split('\n\n##')[0]} if codefile=='AI' else {'message':'긴문장71 '+variant,'code':(DOC/codefile).read_text()}
                if variant=='broken' and codefile=='AI':
                    payload['message'] += '\n조건 변경: batch03.json을 읽지 못하게 되었다. 네 직전 결과는 재사용해도 되지만 다른 실행자의 결과나 정답은 참조하지 마. 기존 보고서를 갱신해 줘.'
                    payload['task_id']=evidence[-1]['task_id']
                queued=local('task/start',payload);tid=queued.get('task_id');approvals=[]
                deadline=time.monotonic()+(int(os.environ.get('L71_AI_TIMEOUT', '120')) if codefile=='AI' else 160)
                while time.monotonic()<deadline:
                    for a in local('approvals'):
                        approvals.append(a['command'])
                        if variant=='concurrent' and a['command'].get('op')=='write' and a['command'].get('path','').endswith('/copy.txt'):
                            (folder/'copy.txt').write_text('human intervened')
                        local('approve',{'key':a['key'],'allow':True})
                    result=local('task?id='+tid)
                    if result['state']!='running':break
                    time.sleep(.1)
                else:
                    local('close',{})
                    for _ in range(100):
                        result=local('task?id='+tid)
                        if result['state']!='running':break
                        time.sleep(.1)
                row={'member':name,'variant':variant,'task_id':tid,'seconds':time.time()-start,'result':result,'commands':approvals}
                row['artifacts']={p.name:base64.b64encode(p.read_bytes()).decode() for p in folder.iterdir() if p.name in ('summary.json','summary.txt','copy.txt')}
                evidence.append(row);(root/'evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
                print(json.dumps({'member':name,'variant':variant,'state':result['state'],'error':result.get('result',{}).get('error'),'seconds':row['seconds']},ensure_ascii=False),flush=True)
            for variant in (('base',) if codefile=='AI' else ('base','broken','recovered','concurrent') if label.startswith('repair') else ('base','broken')):
                for c in clients:run(*c,variant)
            # UI conditional writes: a stale digest must never replace a human edit.
            name,local,folder=clients[0]
            rd=local('file',{'op':'read','path':'source.txt'});(folder/'source.txt').write_text('human edit')
            conflict=local('file',{'op':'write','path':'source.txt','content':'stale','expected_hash':rd['sha256']})
            (root/'conflict.json').write_text(json.dumps({'response':conflict,'preserved':(folder/'source.txt').read_text()=='human edit'}))
        finally:
            for proc in processes:
                proc.stdin.close()
                try:proc.wait(timeout=8)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()
            server.should_exit=True;thread.join(timeout=5);sock.close()
            if codefile=='AI':
                faulthandler.cancel_dump_traceback_later();trace.close()

if __name__=='__main__':main()
