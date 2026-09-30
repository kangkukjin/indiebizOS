"""Compare every marker with literal lines from the immutable synthetic drafts."""
import hashlib
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
LOCAL=HERE.parents[3]/'outputs/long_sentence_imagination/2026-09-30_14회차'
checks={};receipts=[]
for label,mode in [('after_main','inputs'),('after_variant','variant'),('after_uppercase','uppercase')]:
    output=LOCAL/label/'report.json'
    if not output.exists():continue
    result=json.loads(output.read_text());expected=[];failed=[]
    manifest=json.loads((LOCAL/mode/'manifest.json').read_text())
    for entry in manifest['files']:
        path=LOCAL/mode/entry['name']
        if not path.exists():failed.append(entry['id']);continue
        for line,text in enumerate(path.read_text().split('\n'),1):
            for marker in ('TODO','FIXME'):
                if marker in text:expected.append({'id':entry['id'],'line':line,'marker':marker,'text':text})
    assert result['findings']==expected
    assert result['failed']==len(failed) and result['read']==6-len(failed)
    assert [r['id'] for r in result['files'] if not r['read']]==failed
    assert result['status']==('partial' if failed else 'complete')
    assert {r['marker']:r['count'] for r in result['summary']}=={m:sum(x['marker']==m for x in expected) for m in ('TODO','FIXME')}
    assert json.loads((LOCAL/label/'report.txt').read_text())==result
    checks[label]={'read':result['read'],'failed':len(failed),'markers':len(expected),'status':result['status'],'all_lines_exact':True}
for path in sorted(LOCAL.glob('*.json')):
    d=json.loads(path.read_text());r=d.get('response')
    if not isinstance(r,dict):continue
    receipts.append({'label':path.stem,'elapsed_seconds':d.get('elapsed_seconds'),
                     'success':r.get('success'),'check_ok':r.get('ok'),
                     'run_id':r.get('continuation',{}).get('reuse_args',{}).get('reuse',{}).get('run_id'),
                     'source_complete':r.get('source_complete'),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
(HERE/'evidence.json').write_text(json.dumps({'checks':checks,'receipts':receipts},ensure_ascii=False,indent=2))
print(json.dumps(checks,ensure_ascii=False))
