import json,sys,time,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[5]
n,label,inp=sys.argv[1:4]; d=root/f'docs/experiments/long_sentence_imagination/round_{n}'; o=root/f'outputs/long_sentence_imagination/2026-10-06_{n}회차'
code=(d/('drafts/'+sys.argv[4] if len(sys.argv)>4 else 'drafts/main_v0.ibl')).read_text()
payload=dict(code=code,inputs=json.loads((o/f'{inp}_inputs.json').read_text()),origin='training',project_path=str(root),agent_id=f'LSI{n}_trainer',task_id=f'LSI{n}',check='check' in label)
start=time.monotonic(); req=urllib.request.Request('http://127.0.0.1:8765/ibl/execute',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
with urllib.request.urlopen(req,timeout=120) as r:result=json.load(r)
record=dict(response=result,elapsed=time.monotonic()-start); (o/f'{label}_run.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in result.items() if k not in ['execute_args','revise_args','functions','dependencies','canonical_code','results','runtime_checks','value_wire']},ensure_ascii=False)[:12000]); print('elapsed',record['elapsed'])
