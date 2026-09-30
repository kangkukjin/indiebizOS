"""Independent oracle for every synthetic sensor observation."""
import hashlib
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
LOCAL=HERE.parents[3]/'outputs/long_sentence_imagination/2026-09-30_13회차'
checks={};receipts=[]
for label in ('before_main','after_main'):
    path=LOCAL/label/'result.json'
    if path.exists():
        result=json.loads(path.read_text());assert result['status']=='ok'
        rows=result['rows'];assert len(rows)==120
        for i,row in enumerate(rows):
            value=2*(i%17)+(i%12)%3
            assert row=={'sensor':f'S{i%12:02}','sample':i,'value':value,'exceeded':value>25}
        assert result['total']==2024 and result['exceeded']==30
        for row in result['summary']:
            subset=[r for r in rows if r['sensor']==row['sensor']]
            assert row['count']==len(subset)==10
            assert row['sum']==sum(r['value'] for r in subset)
            assert row['mean']==row['sum']/10
            assert row['exceeded']==sum(r['exceeded'] for r in subset)
        assert json.loads((LOCAL/label/'report.txt').read_text())==result
        checks[label]='120 rows, 12 sensor summaries and both files exact'
for label in ('after_variant','after_nested'):
    path=LOCAL/label/'result.json'
    if path.exists():
        result=json.loads(path.read_text());assert result['status']=='blocked'
        assert '중복' in result['error'] and '.json' in result['error']
        checks[label]=result['error']
for path in sorted(LOCAL.glob('*.json')):
    data=json.loads(path.read_text());r=data.get('response') if isinstance(data,dict) else None
    if not isinstance(r,dict):continue
    receipts.append({'label':path.stem,'elapsed_seconds':data.get('elapsed_seconds'),
                     'success':r.get('success'),'check_ok':r.get('ok'),
                     'run_id':r.get('continuation',{}).get('reuse_args',{}).get('reuse',{}).get('run_id'),
                     'source_complete':r.get('source_complete'),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
(HERE/'evidence.json').write_text(json.dumps({'checks':checks,'receipts':receipts},ensure_ascii=False,indent=2))
print(json.dumps(checks,ensure_ascii=False))
