"""Finite HTTP transport and evidence snapshots; no task computation here."""
import argparse
import datetime
import json
import shutil
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT/'outputs/long_sentence_imagination/2026-10-22_88회차'
API = 'http://127.0.0.1:8765'

def save(name, data):
    (OUT/'runs'/f'{name}.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))

def api(path, body=None, timeout=40):
    req=urllib.request.Request(API+path, data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r: return json.load(r)
    except urllib.error.HTTPError as e:
        return {'http_error':e.code,'body':e.read().decode()}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('action'); ap.add_argument('label',nargs='?',default='1'); a=ap.parse_args()
    agent=json.loads((OUT/'runs/agent.json').read_text())['agent']['id']
    base=f'/projects/L88_training/agents/{agent}'
    if a.action in ('submit','ibl','trainer'):
        deadline=datetime.datetime.fromisoformat(json.loads((OUT/'start.json').read_text())['deadline'])
        if datetime.datetime.now().astimezone()>=deadline:
            raise SystemExit('Round budget expired; only retrieval and cleanup are allowed.')
    if a.action=='start':
        result=api(base+'/start',{}); save('agent_start_'+a.label,result); print(json.dumps(result,ensure_ascii=False)); return
    if a.action=='stop':
        result=api(base+'/stop',{}); save('agent_stop_'+a.label,result); print(json.dumps(result,ensure_ascii=False)); return
    if a.action=='submit':
        n=int(a.label)
        if (OUT/'runs'/f'T{n}_accepted.json').exists():
            raise SystemExit('This turn was already submitted. Poll the existing task instead.')
        if n>1:
            previous=json.loads((OUT/'runs'/f'T{n-1}_result.json').read_text())
            assert previous.get('state') in ('succeeded','failed'),previous
        if n==3: shutil.copyfile(OUT/'staged/receipts.json',OUT/'inputs/receipts.json')
        if n==5:
            shutil.copyfile(OUT/'staged/records_v2.json',OUT/'inputs/records.json')
            shutil.copyfile(OUT/'staged/old_memo.txt',OUT/'inputs/old_memo.txt')
        if n==7: shutil.copyfile(OUT/'staged/records_partial.json',OUT/'inputs/records.json')
        if n==8: shutil.copyfile(OUT/'staged/records_v4.json',OUT/'inputs/records.json')
        text=json.loads((OUT/'reference/requests.json').read_text())['turns'][n-1]
        body={'command':text,'origin':'training','background':True}
        with sqlite3.connect(f'file:{ROOT/"data/world_pulse.db"}?mode=ro',uri=True) as db:
            ep=db.execute('select max(id) from episode_log').fetchone()[0]
        save(f'T{n}_request',{'body':body,'before_episode':ep,'at':datetime.datetime.now().astimezone().isoformat()})
        result=api(base+'/command',body); save(f'T{n}_accepted',result); print(json.dumps(result,ensure_ascii=False)); return
    if a.action=='poll':
        ticket=json.loads((OUT/'runs'/f'T{a.label}_accepted.json').read_text())
        result=api(ticket['status_url']+'?wait=20'); result['polled_at']=datetime.datetime.now().astimezone().isoformat()
        terminal=result.get('state') in ('succeeded','failed','cancelled')
        save(f'T{a.label}_'+('result' if terminal else 'latest'),result)
        if terminal:
            dest=OUT/'snapshots'/f'T{a.label}'
            if not dest.exists(): shutil.copytree(OUT/'ai',dest)
        print(json.dumps(result,ensure_ascii=False)[:9000]); return
    if a.action=='ibl':
        path=OUT/'runs'/f'{a.label}_request.json'
        body=json.loads(path.read_text()); body.update(origin='training',edition=2,project_id='study')
        started=time.time(); result=api('/ibl/execute',body,timeout=55)
        save(a.label,{'request':body,'response':result,'seconds':time.time()-started})
        summary={k:result.get(k) for k in ('ok','success','executed','status','value','error','issues','source_complete','reuse','stats') if k in result}
        print(json.dumps(summary,ensure_ascii=False)[:6000]); return
    if a.action=='trainer':
        n=int(a.label)
        for checking in [True,False]:
            cmd=['python3',str(Path(__file__).with_name('trainer.py')),str(n)]
            if not checking: cmd.append('--execute')
            subprocess.run(cmd,check=True,capture_output=True,text=True)
            label=f'trainer_T{n}'+('_check' if checking else '')
            body=json.loads((OUT/'runs'/f'{label}_request.json').read_text())
            body.update(origin='training',edition=2,project_id='study')
            started=time.time();result=api('/ibl/execute',body,timeout=55)
            save(label,{'request':body,'response':result,'seconds':time.time()-started})
            print(json.dumps({'label':label,'seconds':time.time()-started,**{k:result.get(k) for k in ('ok','success','value','issues','error') if k in result}},ensure_ascii=False))
            if checking and not result.get('ok'): break
        return
    if a.action=='health': print(json.dumps(api('/health')))

if __name__=='__main__': main()
