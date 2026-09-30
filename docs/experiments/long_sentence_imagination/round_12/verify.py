"""Independent all-row oracle for synthetic inventory, plus compact run receipts."""
import hashlib
import json
import sqlite3
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
LOCAL=ROOT/'outputs/long_sentence_imagination/2026-09-30_12회차'
expected=[dict(depot=f'D{i//48}',sku=f'S{i%48:02}',closing=100+i%7-i%11,
               shortage=max(97-(100+i%7-i%11),0)) for i in range(144)]
checks={}
for label in ('before_main','after_main'):
    path=LOCAL/label/'result.json'
    if path.exists():
        data=json.loads(path.read_text())
        assert data['rows']==expected
        assert sum(row['closing'] for row in data['summary'])==14111
        assert sum(row['shortage'] for row in data['summary'])==161
        checks[label]='144 rows and depot totals exact'
for label in ('after_variant','after_short','after_duplicate'):
    path=LOCAL/label/'result.json'
    if path.exists():
        data=json.loads(path.read_text())
        assert data['status']=='blocked' and 'received.csv' in data['error']
        assert '레코드' in data['error'] or '열' in data['error']
        checks[label]=data['error']
receipts=[]
for path in sorted(LOCAL.glob('*.json')):
    data=json.loads(path.read_text());r=data.get('response')
    if not isinstance(r,dict): continue
    receipts.append({'label':path.stem,'elapsed_seconds':data.get('elapsed_seconds'),
                     'success':r.get('success'),'check_ok':r.get('ok'),
                     'run_id':r.get('resume',{}).get('run_id') or r.get('continuation',{}).get('reuse_args',{}).get('reuse',{}).get('run_id'),
                     'source_complete':r.get('source_complete'),
                     'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
(HERE/'evidence.json').write_text(json.dumps({'checks':checks,'receipts':receipts},ensure_ascii=False,indent=2))
print(json.dumps(checks,ensure_ascii=False))
