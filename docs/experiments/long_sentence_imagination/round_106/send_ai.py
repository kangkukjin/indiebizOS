"""106회차 운송: 요청·접수증을 즉시 보존하고 같은 작업을 회수한다."""
import json,sys,time,urllib.request,urllib.error,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'outputs/long_sentence_imagination/2026-11-01_106회차'
label=sys.argv[1];message=(OUT/f'{label}_request.txt').read_text()
def call(method,path,body=None):
 req=urllib.request.Request('http://127.0.0.1:8765'+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'},method=method)
 with urllib.request.urlopen(req,timeout=45) as r:return json.load(r)
con=sqlite3.connect(f'file:{ROOT}/data/world_pulse.db?mode=ro',uri=True)
record={'label':label,'started':time.time(),'episode_before':con.execute('select max(id) from episode_log').fetchone()[0]}
p=OUT/f'{label}_run.json'
def save():p.write_text(json.dumps(record,ensure_ascii=False,indent=2))
save()
record['accepted']=call('POST','/system-ai/chat',{'message':message,'origin':'training','background':True});save()
url=record['accepted'].get('status_url');print(json.dumps(record['accepted'],ensure_ascii=False),flush=True)
while url and time.time()-record['started']<1800:
 try:
  state=call('GET',url+'?wait=20');record['latest']=state;record['seconds']=time.time()-record['started'];save()
  status=state.get('status') or state.get('state')
  if status in ('succeeded','failed','cancelled','expired','completed'):
   record['ended']=time.time();save();print(json.dumps({'status':status,'seconds':record['seconds']},ensure_ascii=False),flush=True);break
 except Exception as e:
  record.setdefault('transport_errors',[]).append({'at':time.time(),'error':str(e)});save();time.sleep(2)
