import json,sys
d=json.load(open(f'runs/{sys.argv[1]}.json')); r=d['response']
print('elapsed',d['elapsed_s'],'success',r.get('success'),'status',r.get('run_status'),'sc',r.get('source_complete'),'chars',len(json.dumps(r,ensure_ascii=False)))
print(json.dumps(r.get('value'),ensure_ascii=False)[:int(sys.argv[2]) if len(sys.argv)>2 else 3000])
if not r.get('success'):
    dg=dict(r.get('diagnostic') or {}); dg.pop('partial',None); print('DIAG',json.dumps(dg,ensure_ascii=False)[:2500])
print('usage',r.get('usage')); print('resume',r.get('resume'), 'cont', (r.get('continuation') or {}).get('read_calls')); print('ref',(r.get('result_ref') or {}).get('chars')); print('evsum',r.get('evidence_summary')); print('reuse',r.get('reuse'))
