"""Round 88 repair replay: transport only; preserved baseline fixtures/programs."""
import argparse
import datetime
import importlib.util
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path('/Users/kangkukjin/Desktop/AI/indiebizOS')
HERE = ROOT/'docs/experiments/long_sentence_imagination/round_88'
BASE = ROOT/'outputs/long_sentence_imagination/2026-10-22_88회차'
OUT = ROOT/'outputs/long_sentence_imagination/2026-10-22_88회차_repair'
PROJECT = 'L88_repair'
API = 'http://127.0.0.1:8765'

def save(name, value):
    (OUT/'runs'/f'{name}.json').write_text(json.dumps(value,ensure_ascii=False,indent=2))

def api(path, body=None, timeout=55):
    req=urllib.request.Request(API+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('action');ap.add_argument('label',nargs='?',default='1');ap.add_argument('--attempt',type=int,default=1);a=ap.parse_args()
    global OUT,PROJECT
    if a.attempt != 1:
        OUT=ROOT/f'outputs/long_sentence_imagination/2026-10-22_88회차_repair{a.attempt}'
        PROJECT=f'L88_repair{a.attempt}'
    if a.action=='prepare':
        spec=importlib.util.spec_from_file_location('fixture88',HERE/'setup.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        m.OUT=OUT;m.main()
        # Replay identical bytes, including serializer choices, rather than only equal JSON.
        for source in (BASE/'reference/initial_inputs').iterdir():
            shutil.copyfile(source, OUT/'inputs'/source.name)
            shutil.copyfile(source, OUT/'reference/initial_inputs'/source.name)
        for source in (BASE/'staged').iterdir():
            shutil.copyfile(source, OUT/'staged'/source.name)
        requests=(BASE/'reference/requests.json').read_text().replace(str(BASE),str(OUT))
        (OUT/'reference/requests.json').write_text(requests)
        now=datetime.datetime.now().astimezone()
        (OUT/'start.json').write_text(json.dumps({'start':now.isoformat(),'deadline':(now+datetime.timedelta(minutes=60)).isoformat(),'head':'35c36b31+repair','synthetic':True},indent=2))
        return
    if a.action=='continue':
        def invoke(action, label):
            p=subprocess.run([sys.executable,__file__,action,str(label),'--attempt',str(a.attempt)],capture_output=True,text=True)
            if p.returncode:
                raise RuntimeError(p.stdout+p.stderr)
            return p.stdout
        for n in range(int(a.label),4 if a.attempt==3 else 9):
            if not (OUT/'runs'/f'T{n}_accepted.json').exists():
                print(invoke('submit',n),flush=True)
            if a.attempt!=3 and not (OUT/'runs'/f'trainer_T{n}.json').exists():
                print(invoke('trainer',n),flush=True)
            while not (OUT/'runs'/f'T{n}_result.json').exists():
                invoke('poll',n)
                if not (OUT/'runs'/f'T{n}_result.json').exists():
                    time.sleep(5)
            result=json.loads((OUT/'runs'/f'T{n}_result.json').read_text())
            print(json.dumps({'turn':n,'state':result['state'],'completed_at':result.get('completed_at')},ensure_ascii=False),flush=True)
            assert result['state']=='succeeded' and result['pending_children']==0,result
            if n==4:
                print(invoke('stop','T4'),flush=True)
                print(invoke('start','T5'),flush=True)
        return
    if a.action in ('submit','trainer','create'):
        deadline=datetime.datetime.fromisoformat(json.loads((OUT/'start.json').read_text())['deadline'])
        if datetime.datetime.now().astimezone()>=deadline:raise SystemExit('Experiment budget expired')
    if a.action=='create':
        assert not (OUT/'runs/agent.json').exists()
        save('project',api('/projects',{'name':PROJECT}))
        body=json.loads((BASE/'runs/create_agent.json').read_text())
        result=api(f'/projects/{PROJECT}/agents',body);save('agent',result)
        agent=result['agent']['id'];save('agent_start',api(f'/projects/{PROJECT}/agents/{agent}/start',{}))
        print(json.dumps({'project':PROJECT,'agent':agent}));return
    if a.action=='health':print(json.dumps(api('/health')));return
    agent=json.loads((OUT/'runs/agent.json').read_text())['agent']['id'];route=f'/projects/{PROJECT}/agents/{agent}'
    if a.action in ('stop','start'):
        r=api(route+'/'+a.action,{});save('agent_'+a.action+'_'+a.label,r);print(json.dumps(r));return
    if a.action=='submit':
        n=int(a.label)
        assert not (OUT/'runs'/f'T{n}_accepted.json').exists()
        if n>1:assert json.loads((OUT/'runs'/f'T{n-1}_result.json').read_text())['state']=='succeeded'
        reveal={3:[('receipts.json','receipts.json')],5:[('records_v2.json','records.json'),('old_memo.txt','old_memo.txt')],7:[('records_partial.json','records.json')],8:[('records_v4.json','records.json')]}
        reveal[9]=[(f'repair_variant/{name}',name) for name in ('handover_message.txt','site_access_notice.txt')]
        if a.attempt==3:
            reveal={3:reveal[9]}
        for src,dst in reveal.get(n,[]):shutil.copyfile(OUT/'staged'/src,OUT/'inputs'/dst)
        request=json.loads((OUT/'reference/requests.json').read_text())['turns'][n-1]
        body={'command':request,'origin':'training','background':True};save(f'T{n}_request',{'body':body,'at':datetime.datetime.now().astimezone().isoformat()})
        result=api(route+'/command',body);save(f'T{n}_accepted',result);print(json.dumps(result));return
    if a.action=='poll':
        n=int(a.label);ticket=json.loads((OUT/'runs'/f'T{n}_accepted.json').read_text())
        r=api(ticket['status_url']+'?wait=20');r['polled_at']=datetime.datetime.now().astimezone().isoformat()
        terminal=r.get('state') in ('succeeded','failed','cancelled');save(f'T{n}_'+('result' if terminal else 'latest'),r)
        if terminal and not (OUT/'snapshots'/f'T{n}').exists():shutil.copytree(OUT/'ai',OUT/'snapshots'/f'T{n}')
        print(json.dumps({k:r.get(k) for k in ['state','pending_children','completed_at','result','error']},ensure_ascii=False)[:6500]);return
    if a.action=='trainer':
        n=int(a.label);(OUT/'trainer'/f'T{n}').mkdir(exist_ok=True)
        name='trainer_T1_v2_check_request.json' if n==1 else f'trainer_T{n}_check_request.json'
        body=json.loads((BASE/'runs'/name).read_text().replace(str(BASE),str(OUT)))
        body.update(origin='training',edition=2,project_id=PROJECT)
        check=api('/ibl/execute',body);save(f'trainer_T{n}_check',{'request':body,'response':check})
        assert check.get('ok'),check
        body=check['execute_args'];body.update(origin='training',edition=2,project_id=PROJECT)
        start=time.time();result=api('/ibl/execute',body);save(f'trainer_T{n}',{'request':body,'response':result,'seconds':time.time()-start})
        print(json.dumps({k:result.get(k) for k in ('success','value','error')},ensure_ascii=False));return

if __name__=='__main__':main()
