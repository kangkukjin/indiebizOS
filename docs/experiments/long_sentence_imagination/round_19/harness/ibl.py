"""HTTP harness: input transport and receipt capture only, no task computation."""
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT/'outputs/long_sentence_imagination/2026-10-05_19회차'
label, source = sys.argv[1:3]
extra = json.loads(sys.argv[3]) if len(sys.argv)>3 else {}
payload = dict(code=Path(source).read_text() if source!='-' else '',edition=2,
               origin='training',project_id='컨텐츠',agent_id='LSI19_trainer',
               task_id='LSI19',budget={'steps':1000000,'rows':100000})
payload.update(extra)
if 'inputs_file' in payload:
    payload['inputs']=json.loads(Path(payload.pop('inputs_file')).read_text())
start=time.monotonic()
req=urllib.request.Request('http://127.0.0.1:8765/ibl/execute',
    data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
with urllib.request.urlopen(req,timeout=400) as r:
    result=json.load(r)
elapsed=time.monotonic()-start
(OUT/'runs'/f'{label}.json').write_text(json.dumps(dict(request=payload,response=result,elapsed=elapsed),ensure_ascii=False,indent=1))
print(json.dumps({'label':label,'elapsed':elapsed,**{k:v for k,v in result.items() if k not in ['results','final_result','execute_args','revise_args','functions','descriptions','canonical_code','code','value','dependencies','preflight','guards_ref','runtime_checks']}},ensure_ascii=False)[:7500])
