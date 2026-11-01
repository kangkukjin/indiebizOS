"""Compact evidence from retained receipts, with raw model usage kept separate."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[4]/'backend'))
import boot_paths
import harness as h
import json,hashlib,re
from fixtures import main_inputs

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
summary={'outputs':str(h.OUT),'models':{},'validation':{},'executions':{},'source_checks':{}}
for label in ['ai_fault','ai_main','ai_variant','ai_transfer','ai_script','ai_action']:
    p=h.OUT/(label+'.model.json')
    if p.exists():
        obj=json.loads(p.read_text());timing=json.loads((h.OUT/(label+'.timing.json')).read_text())
        summary['models'][label]={'session_id':obj.get('session_id'),'turns':obj.get('num_turns'),'usage':obj.get('usage'),'modelUsage':obj.get('modelUsage'),'wall_seconds':timing['ended']-timing['started'],'returncode':timing['returncode'],'model_file_sha256':sha(p)}
        (h.DOC/(label+'_response.md')).write_text(obj.get('result',''))
for p in sorted(h.OUT.glob('*validation.json')):summary['validation'][p.stem]=json.loads(p.read_text())
for bodyname in ['trainer','ai_fixture_fault','ai','ai_transfer','action']:
    body=h.OUT/bodyname;p=body/'calls.jsonl'
    if not p.exists():continue
    rows=[json.loads(l) for l in p.read_text().splitlines()]
    requests=[];events=[]
    for i,r in enumerate(rows):
        q=r['request'];v=r['result']
        ev={'index':i,'at':r['at'],'seconds':r['seconds'],'code_sha256':hashlib.sha256(q.get('code','').encode()).hexdigest(),'check':bool(q.get('check')),'describe':q.get('describe'),'success':v.get('success'),'issues':v.get('issues',[]),'error':v.get('error'),'diagnostic_code':v.get('diagnostic',{}).get('code'),'run_id':v.get('resume',{}).get('run_id'),'usage':{k:v.get('usage',{}).get(k) for k in ['steps','rows','elapsed_ms']}}
        ev['actor'] = 'operator_postcheck' if bodyname == 'action' and i >= 34 else 'experiment_call'
        events.append(ev);requests.append({'index':i,'request':q})
    (h.DOC/(bodyname+'_programs.jsonl')).write_text(''.join(json.dumps(x,ensure_ascii=False,default=str)+'\n' for x in requests))
    (h.DOC/(bodyname+'_events.jsonl')).write_text(''.join(json.dumps(x,ensure_ascii=False,default=str)+'\n' for x in events))
    summary['executions'][bodyname]={'calls':len(rows),'failed':sum(r['result'].get('success') is False for r in rows),'events_file':bodyname+'_events.jsonl','raw_sha256':sha(p)}
for bodyname in ['trainer','ai']:
    body=h.OUT/bodyname
    summary['source_checks'][bodyname]={'initial_inputs_equal':all((body/'inputs'/name).read_bytes()==json.dumps(value,ensure_ascii=False,indent=2).encode() for name,value in main_inputs().items()),'initial_report_unchanged':sha(body/'outputs/report.json')==sha(h.OUT/(bodyname+'_main_report.json'))}
summary['execution_count_note'] = 'Counts include preflights and operator diagnostics; not model turn counts. Action indices 34 and 35 are operator postchecks.'
summary['action'] = json.loads((h.OUT/'action/outputs/action_report.json').read_text())
summary['action_operator_check'] = {'contract': json.loads((h.OUT/'action_fresh_contract.json').read_text()), 'call_succeeded': False, 'call_issue': 'UNSUPPORTED_ADAPTER', 'selector': json.loads((h.OUT/'action_selector_canonical.json').read_text()), 'interpretation': 'The fixture lives under outputs, which select_tests excludes. Canonical read-only selection found 76/837 tests; no tests were run against the canonical tree for the absent candidate. Formal apply was not reached.'}
summary['isolation']=json.loads((h.OUT/'isolation_preflight.json').read_text())
summary['recovery']=json.loads((h.OUT/'trainer_recovery_assertions.json').read_text())
h.dump(h.DOC/'evidence.json',summary)
print('models',list(summary['models']))
print('validation',{k:v['passed'] for k,v in summary['validation'].items()})
print('source_checks',summary['source_checks'])
for k,v in summary['models'].items():
 u=v['usage'];print(k,round(v['wall_seconds'],2),v['turns'],*[u.get(n) for n in ['input_tokens','cache_creation_input_tokens','cache_read_input_tokens','output_tokens']])
