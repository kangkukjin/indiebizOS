"""Transport the authored IBL and preserve the exact request/response; no task logic."""
import json,sys,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]
OUT=ROOT/'outputs/long_sentence_imagination/2026-10-05_21회차'
label,source,inputs=sys.argv[1:4]
payload=dict(code=Path(source).read_text(),inputs=json.loads(Path(inputs).read_text()),origin='training',project_path=str(ROOT),agent_id='LSI21_trainer',task_id='LSI21',check='check' in label,budget={'steps':1000000,'rows':100000})
start=time.monotonic()
req=urllib.request.Request('http://127.0.0.1:8765/ibl/execute',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
with urllib.request.urlopen(req,timeout=120) as r:result=json.load(r)
record=dict(request=payload,response=result,elapsed=time.monotonic()-start)
(OUT/'runs'/f'{label}.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in result.items() if k not in ['execute_args','revise_args','functions','dependencies','canonical_code','results','value','final_result','runtime_checks']},ensure_ascii=False)[:12000])
print('elapsed',record['elapsed'])
