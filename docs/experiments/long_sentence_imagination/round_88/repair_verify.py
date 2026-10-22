"""Independent checks against fixture facts, never AI's own checker."""
import csv
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
BASE=ROOT/'outputs/long_sentence_imagination/2026-10-22_88회차'
OUT=BASE.with_name(BASE.name+'_repair2')
checks=[]
def check(name, ok, detail=None):
    checks.append({'check':name,'pass':bool(ok),'detail':detail})

base=json.loads((OUT/'reference/initial_inputs/records.json').read_text())['items']
source_tasks=json.loads((OUT/'reference/initial_inputs/tasks.json').read_text())['items']
base_index={r['id']:r for r in base}
expected=json.loads((OUT/'reference/expected.json').read_text())
for n in range(1,9):
    f=OUT/'trainer'/f'T{n}'/'state.json'
    if not f.exists():continue
    s=json.loads(f.read_text());d=s['data'];t=s['tasks']
    observed=1799 if n==7 else 1800
    eligible=1616 if n<=4 else 1798 if n==7 else 1799
    check(f'trainer T{n} coverage',d['observed']==observed and d['eligible']==eligible and d['missing']==(['D1800'] if n==7 else []))
    check(f'trainer T{n} task states',t['required_done']==(0 if n<3 else 9) and len(t['cancelled'])==(0 if n==1 else 12))
    check(f'trainer T{n} decision',s['launch_ready'] is False and s['review_complete'] is True)
    if n>=2:check(f'trainer T{n} policy',s['policy']=={'budget':4200000,'deadline':'2026-11-20','cancel_optional':True,'external_saas':False,'face':False})
    check(f'trainer T{n} report', (f.parent/'report.txt').is_file())
    raw=base if n<=4 else json.loads((OUT/'staged'/('records_partial.json' if n==7 else 'records_v2.json')).read_text())['items']
    oracle=[{'id':r['id'],'consent':r['consent']!='yes','checksum':r['checksum']!='pass','search':not r['searchable'],'access':not r['accessible']} for r in raw if r['consent']!='yes' or r['checksum']!='pass' or not r['searchable'] or not r['accessible']]
    check(f'trainer T{n} every blocked record',d['blocked']==oracle)
    expected_states={r['id']:('cancelled' if n>=2 and r['optional'] else 'verified_done' if n>=3 and int(r['id'][3:])<=2 and not r['optional'] and r['id']!='W4-02' else 'unverified' if n>=3 and r['id']=='W4-02' else 'planned') for r in source_tasks}
    check(f'trainer T{n} every task state',{r['id']:r['status'] for r in t['items']}==expected_states)


for p in (BASE/'reference/initial_inputs').iterdir():
    check('identical initial bytes '+p.name,p.read_bytes()==(OUT/'reference/initial_inputs'/p.name).read_bytes())
frozen_end=OUT/'runs/repair_source_end_hashes.json'
end=json.loads(frozen_end.read_text()) if frozen_end.exists() else None
for name,digest in json.loads((OUT/'runs/repair_source_hashes.json').read_text()).items():
    check('production source frozen '+name,(end[name] if end else hashlib.sha256((ROOT/name).read_bytes()).hexdigest())==digest)
for n in range(1,9):
    p=OUT/'runs'/f'T{n}_result.json'
    if p.exists():
        r=json.loads(p.read_text())
        check(f'AI T{n} terminal without children',r['state']=='succeeded' and r['pending_children']==0)
for snap in sorted((OUT/'snapshots').glob('T*')):
    changed=[]
    for p in snap.rglob('*'):
        if not p.is_file():continue
        rel=p.relative_to(snap);live=OUT/'ai'/rel
        if not live.exists() or p.read_bytes()!=live.read_bytes():changed.append(str(rel))
    check(f'{snap.name} prior artifacts preserved',not changed,changed)
# AI schema adapters decode output only; expected values are the fixed fixture facts.
f=OUT/'ai/T1/record_summary.json'
if f.exists():
    d=json.loads(f.read_text())
    check('AI T1 records summary',d['processed_count']==1800 and d['all_four_pass']==1616 and d['not_all_pass']==184)
    check('AI T1 per gate counts',[d['gate_results'][g]['fail'] for g in ['동의 확인','체크섬 일치','검색 가능','접근성 통과']]==[90,40,60,72])
    rows=list(csv.DictReader((f.parent/'record_ledger.csv').open(encoding='utf-8-sig')))
    check('AI T1 all row identities',len(rows)==1800 and {r['id'] for r in rows}==set(base_index))
    check('AI T1 all row judgments',all((r['all_four_pass'].lower()=='true')==(base_index[r['id']]['consent']=='yes' and base_index[r['id']]['checksum']=='pass' and base_index[r['id']]['searchable'] and base_index[r['id']]['accessible']) for r in rows))
    tasks=json.loads((f.parent/'task_ledger.json').read_text())['items']
    check('AI T1 all tasks present',len(tasks)==72 and {t['id'] for t in tasks}=={t['id'] for t in source_tasks})
    check('AI T1 completion and readiness',all(t['evidence_status']=='미완(완료 보고·검증 영수증 없음)' for t in tasks) and {t['id'] for t in tasks if t['executable']=='실행 가능'}=={f'W{i}-01' for i in range(1,7)})
    gate=json.loads((f.parent/'launch_gate.json').read_text())
    check('AI T1 launch not ready',gate['conditions'][0]['met'] is False and gate['conditions'][1]['met'] is False)

f=OUT/'ai/T2/task_ledger.json'
if f.exists():
    d=json.loads(f.read_text());rows=d['items']
    check('AI T2 every task scope',len(rows)==72 and all((r['scope']=='in_scope')==(not base_task['optional']) for r,base_task in zip(rows,source_tasks)) and {r['id'] for r in rows if r['scope']!='in_scope'}=={f'W6-{i:02}' for i in range(1,13)})
    check('AI T2 ready required tasks',{r['id'] for r in rows if r['executable']=='실행 가능'}=={f'W{i}-01' for i in range(1,6)})
    budget=json.loads((f.parent/'budget.json').read_text())
    check('AI T2 budget',budget['budget']==4200000 and budget['in_scope_cost']==3390000 and budget['remaining']==810000 and budget['in_scope_count']==60 and budget['cancelled_count']==12)
    decisions=json.loads((f.parent/'raid_ledger.json').read_text())
    check('AI T2 settled choices removed from open list',{r['id'] for r in decisions['open_decisions']}=={'Q3','Q4','Q5'} and {r['id'] for r in decisions['resolved_decisions']}=={'Q1','Q2'})
    gate=json.loads((f.parent/'launch_gate.json').read_text())
    check('AI T2 launch not ready',gate['conditions'][0]['met'] is False and gate['conditions'][1]['met'] is False)

f=OUT/'ai/T3/task_ledger.json'
if f.exists():
    rows=json.loads(f.read_text())['items']
    expected_status={t['id']:('cancelled_with_receipt' if t['optional'] and int(t['id'][3:])<=2 else 'cancelled' if t['optional'] else 'reported_unverified' if t['id']=='W4-02' else 'verified_done' if int(t['id'][3:])<=2 else 'no_report') for t in source_tasks}
    check('AI T3 every task state',{r['id']:r['t3_status'] for r in rows}==expected_status)
    done={k for k,v in expected_status.items() if v=='verified_done'}
    check('AI T3 only verified progress',{r['id'] for r in rows if r['counts_toward_progress']}==done)
    check('AI T3 ready tasks',{r['id'] for r in rows if r['executable'].startswith('실행 가능')}=={'W1-03','W2-03','W3-03','W4-02','W5-03'})
    gate=json.loads((f.parent/'launch_gate.json').read_text())
    check('AI T3 evidence and launch',gate['conditions'][1]['observed']=='9/60' and gate['conditions'][0]['met'] is False and gate['conditions'][1]['met'] is False)

f=OUT/'ai/T4/handoff.json'
if f.exists():
    d=json.loads(f.read_text());e=d['completion_evidence'];g=d['launch_gate']
    check('AI T4 completion evidence',e['verified_done']==9 and e['in_scope_required']==60 and len(e['tasks'])==9 and e['excluded'][0]['task']=='W4-02')
    check('AI T4 kept policy and budget',g['budget']['budget']==4200000 and g['budget']['in_scope_cost']==3390000 and len(d['confirmed_decisions'])==6 and d['resolved_questions']==['Q1','Q2'])
    check('AI T4 next tasks',{r['task'] for r in d['next_actions']['executable_now']}=={'W1-03','W2-03','W3-03','W4-02','W5-03'} and d['next_actions']['waiting_on_predecessors']==46)
    check('AI T4 no new analysis claim',d['new_analysis'] is False)

f=OUT/'ai/T5/record_summary.json'
if f.exists():
    d=json.loads(f.read_text())
    check('AI T5 coverage and counts',d['input_count']==1800 and d['all_four_pass']==1799 and d['not_all_pass']==1 and d['missing_ids']==[])
    rows=list(csv.DictReader((f.parent/'record_ledger.csv').open(encoding='utf-8-sig')))
    check('AI T5 every row judgment',len(rows)==1800 and {r['id'] for r in rows}==set(base_index) and {r['id'] for r in rows if r['all_four_pass'].lower()!='true'}=={'D1777'})
    diff=json.loads((f.parent/'record_diff.json').read_text())
    check('AI T5 changed records',diff['changed_records']==185 and diff['by_change']=={'newly_pass':184,'newly_fail':1})
    gate=json.loads((f.parent/'launch_gate.json').read_text())
    check('AI T5 task state reused',gate['conditions'][1]['observed']=='9/60' and gate['conditions'][0]['met'] is False)

f=OUT/'ai/T6/action_table.json'
if f.exists():
    d=json.loads(f.read_text())
    rows=list(csv.DictReader((f.parent/'task_actions.csv').open(encoding='utf-8-sig')))
    done={t['id'] for t in source_tasks if not t['optional'] and int(t['id'][3:])<=2 and t['id']!='W4-02'}
    remaining={t['id'] for t in source_tasks if not t['optional']}-done
    check('AI T6 no completed or cancelled reassignment',len(rows)==51 and {r['task_id'] for r in rows}==remaining)
    check('AI T6 counts',d['counts']['task_actions']==51 and d['counts']['startable_new']==4 and d['counts']['recheck']==1 and d['counts']['waiting']==46)
    check('AI T6 exclusions',set(d['excluded']['verified_done_not_reassigned'])==done and set(d['excluded']['cancelled_W6_not_reassigned'])=={f'W6-{i:02}' for i in range(1,13)})
    check('AI T6 linked conditions',all(set(i['conditions'])<={g['id'] for g in d['conditions']} for i in d['issues']) and any(len(i['conditions'])>1 for i in d['issues']))

f=OUT/'ai/T7/record_summary.json'
if f.exists():
    d=json.loads(f.read_text())
    check('AI T7 missing distinguished',d['file_count']==1799 and d['population']==1800 and d['missing_ids']==['D1800'] and d['fail_ids']==['D1777'] and d['population_status']=={'pass':1798,'fail':1,'unconfirmed_missing':1})
    check('AI T7 retained rows unchanged',d['value_changed_records']==0 and d['removed_vs_t5']==['D1800'] and d['added_vs_t5']==[])
    gate=json.loads((f.parent/'launch_gate.json').read_text())
    check('AI T7 tasks and launch',gate['conditions'][1]['observed']=='9/60' and gate['conditions'][0]['met'] is False)

f=OUT/'ai/T8/record_summary.json'
if f.exists():
    d=json.loads(f.read_text())
    check('AI T8 restored record',d['file_count']==1800 and d['missing_ids']==[] and d['fail_ids']==['D1777'] and d['population_status']=={'pass':1799,'fail':1} and d['D1800']['same_as_t5'] is True)
    check('AI T8 no silent retained changes',d['vs_t7']=={'added':['D1800'],'removed':[],'value_changed':[]} and d['vs_t5']=={'added':[],'removed':[],'value_changed':[]})
    gate=json.loads((f.parent/'launch_gate.json').read_text())
    check('AI T8 review separate from launch',gate['review_work']['status']=='완료' and gate['project_launch']['ready'] is False and gate['conditions'][1]['observed']=='9/60')


report={'checks':checks,'passed':sum(c['pass'] for c in checks),'failed':sum(not c['pass'] for c in checks)}
(OUT/'runs/repair_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'passed':report['passed'],'failed':report['failed'],'failures':[c for c in checks if not c['pass']]},ensure_ascii=False))
