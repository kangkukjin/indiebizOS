import json,sys,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5];DOC=ROOT/'docs/experiments/long_sentence_imagination/round_83';OUT=ROOT/'outputs/long_sentence_imagination/2026-10-20_83회차'
mode=sys.argv[1];turn=sys.argv[2] if len(sys.argv)>2 else '1';version=sys.argv[3] if len(sys.argv)>3 else '0'
body={'code':(DOC/f'base_v{version}.ibl').read_text(),'edition':2,'project_id':'L83_training','origin':'training','inputs':{'folder':str(OUT/'inputs'),'dialogue':str(OUT/f'dialogue_t{turn}.txt'),'out':str(OUT/'trainer'/f't{turn}_v{version}.json')}}
(OUT/'trainer').mkdir(exist_ok=True)
if mode=='check':body['check']=True
if turn!='1' and mode!='check':
 prev=json.loads((OUT/'trainer_t1_v1_run.json').read_text())
 print('reuse keys',list(prev))
 run_id=prev.get('continuation',{}).get('reuse_args',{}).get('reuse',{}).get('run_id')
 if run_id:body['reuse']={'run_id':run_id}
start=time.monotonic();req=urllib.request.Request('http://localhost:8765/ibl/execute',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
try:
 result=json.load(urllib.request.urlopen(req,timeout=600))
except urllib.error.HTTPError as e: result={'http_error':e.code,'body':e.read().decode()}
(OUT/f'trainer_t{turn}_v{version}_{mode}_request.json').write_text(json.dumps(body,ensure_ascii=False,indent=2))
(OUT/f'trainer_t{turn}_v{version}_{mode}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print('SECONDS',time.monotonic()-start);print(json.dumps({k:result.get(k) for k in ['success','ok','status','issues','error','run_status']},ensure_ascii=False));print(json.dumps(result.get('value',{}).get('advice',{}),ensure_ascii=False))
