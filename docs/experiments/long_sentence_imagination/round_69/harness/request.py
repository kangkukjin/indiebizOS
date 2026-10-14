"""Build a replay request; HTTP transport stays explicit and does not implement the task."""
import argparse
import json
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('input',type=Path)
p.add_argument('output',type=Path)
p.add_argument('request',type=Path)
p.add_argument('--reuse-response',type=Path)
p.add_argument('--check',action='store_true')
a=p.parse_args()
code=Path(__file__).resolve().parents[1]/'base_v2.ibl'
payload={'code':code.read_text(),'edition':2,'origin':'training','project_id':'study',
         'inputs':{'input':str(a.input.resolve()),'out':str(a.output.resolve())}}
if a.check:payload['check']=True
if a.reuse_response:
    previous=json.loads(a.reuse_response.read_text())
    if not previous.get('success'):raise SystemExit('reuse requires a successful response')
    payload.update(previous['continuation']['reuse_args'])
a.request.write_text(json.dumps(payload,ensure_ascii=False))
print(a.request)
