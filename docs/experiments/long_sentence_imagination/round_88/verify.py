"""Independent checks against fixture facts, never AI's own checker."""
import csv
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'outputs/long_sentence_imagination/2026-10-22_88회차'
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

f=OUT/'ai/T1/records_validation.csv'
if f.exists():
    rows=list(csv.DictReader(f.open(encoding='utf-8-sig')))
    check('AI T1 record IDs',len(rows)==1800 and {r['id'] for r in rows}==set(base_index))
    preserved=True
    for row in rows:
        original=base_index[row['id']]
        for key in ['collection','consent','checksum','searchable','accessible']:
            preserved=preserved and str(original[key]).lower()==str(row.get(key)).lower()
    check('AI T1 source fields all rows',preserved)
    valid_flags=True
    for row in rows:
        r=base_index[row['id']]
        actual=[r['consent']=='yes',r['checksum']=='pass',r['searchable'],r['accessible']]
        valid_flags=valid_flags and row['all_pass'].lower()==str(all(actual)).lower()
        valid_flags=valid_flags and int(row['fail_count'])==sum(not x for x in actual)
    check('AI T1 all row judgments',valid_flags)
    s=json.loads((f.parent/'analysis_summary.json').read_text())['records']
    check('AI T1 summary counts',s['records']==1800 and s['all_pass']==1616 and s['unique_fail']==184 and s['per_gate_fail']=={'consent':90,'checksum':40,'searchable':60,'accessible':72})
    tasks=json.loads((f.parent/'tasks_tracking.json').read_text())['items']
    check('AI T1 task IDs',len(tasks)==72 and {r['id'] for r in tasks}=={r['id'] for r in source_tasks})
    check('AI T1 no false completion',all(r['tracked_status']=='미완료(planned)' for r in tasks))

f=OUT/'ai/T2/analysis_summary.json'
if f.exists():
    s=json.loads(f.read_text())
    check('AI T2 scope and cost',s['scope']['in_scope']==60 and set(s['scope']['cancelled'])==set(expected['tasks']['cancelled']) and s['cost']['budget_t2']==4200000 and s['cost']['t2_in_scope_total']==3390000)
    check('AI T2 prior analysis retained',s['records']['all_pass']==1616 and s['launch']['launchable'] is False and s['dependency']['deadline']=='2026-11-20')
    check('AI T2 withdrawn options',set(s['scope']['options_excluded'])=={'O2','O3'})

f=OUT/'ai/T3/analysis_summary.json'
if f.exists():
    s=json.loads(f.read_text());r=s['receipts']
    done={f'W{i}-{j:02d}' for i in range(1,6) for j in (1,2)}-{'W4-02'}
    check('AI T3 completed evidence IDs',set(r['verified_done'])==done and r['reported_unverified']==['W4-02'])
    check('AI T3 cancelled receipts retained',set(r['cancelled_with_report'])=={'W6-01','W6-02'})
    check('AI T3 dependency readiness',set(s['ready_now'])=={'W1-03','W2-03','W3-03','W4-02','W5-03'} and s['blocked_by_unverified']==['W4-03'])
    check('AI T3 no false record repair',s['launch']['record_gate']['all_four_pass']==1616 and s['launch']['launchable'] is False)
    check('AI T3 policy and remaining',s['cost']['budget']==4200000 and s['progress']['planned']==50 and s['progress']['reported_unverified']==1 and s['deadline']=='2026-11-20')

f=OUT/'ai/T4/handoff.json'
if f.exists():
    s=json.loads(f.read_text());c=s['goal']['conditions'];e=s['completion_evidence']
    check('AI T4 handoff policy',c['budget_won']==4200000 and c['deadline']=='2026-11-20' and c['publication'].startswith('draft_only'))
    check('AI T4 handoff completion evidence',e['verified_done_count']==9 and {r['task'] for r in e['verified_done']}==done and e['reported_unverified'][0]['task']=='W4-02')
    check('AI T4 decision provenance',next(d for d in s['decisions_in_force'] if d['id']=='D-01')['basis']=='user_derived')

f=OUT/'ai/T5/analysis_summary.json'
if f.exists():
    s=json.loads(f.read_text());r=s['records']
    check('AI T5 corrected source',r['records']==1800 and r['all_pass']==1799 and r['unique_fail']==1 and [x['id'] for x in r['failed_records']]==['D1777'])
    check('AI T5 progress retained',s['progress']['verified_done']==9 and s['progress']['planned']==50 and s['cost']['budget']==4200000 and s['launch']['launchable'] is False)
    memo=json.loads((f.parent/'memo_reconciliation.json').read_text())
    check('AI T5 old proposal not adopted',memo['adopted']==[] and len(memo['claims'])==4)
    rows=list(csv.DictReader((f.parent/'records_validation.csv').open(encoding='utf-8-sig')))
    original={r['id']:r for r in json.loads((OUT/'staged/records_v2.json').read_text())['items']}
    check('AI T5 all record IDs',len(rows)==1800 and {r['id'] for r in rows}==set(original))
    fields_ok=True;flags_ok=True
    for row in rows:
        r=original[row['id']]
        fields_ok=fields_ok and all(str(row[k]).lower()==str(r[k]).lower() for k in ['collection','consent','checksum','searchable','accessible'])
        flags_ok=flags_ok and (row['all_pass'].lower()=='true')==(r['id']!='D1777')
    check('AI T5 all source fields',fields_ok);check('AI T5 all row judgments',flags_ok)

f=OUT/'ai/T6/action_table.json'
if f.exists():
    s=json.loads(f.read_text())
    order=json.loads((f.parent/'inspection_order.json').read_text())['steps']
    assigned=[r['item'] for r in order if r['kind'] in ('작업 검수','작업 재검증')]
    remaining={r['id'] for r in source_tasks if not r['optional']}-done
    check('AI T6 exactly 51 remaining tasks',len(assigned)==51 and set(assigned)==remaining)
    check('AI T6 done and cancelled excluded',set(s['excluded']['verified_done_not_reassigned'])==done and set(s['excluded']['cancelled_W6_out_of_scope'])==set(expected['tasks']['cancelled']))
    positions={task:i for i,task in enumerate(assigned)}
    ordered=all(positions[f'W{w}-{j:02d}']<positions[f'W{w}-{j+1:02d}'] for w in range(1,6) for j in range(3,12))
    check('AI T6 dependency order',ordered and positions['W4-02']<positions['W4-03'])
    check('AI T6 current record counts',s['numbers_from_t5']['records_pass']==1799 and s['numbers_from_t5']['fail_id']=='D1777' and s['launchable'] is False)

f=OUT/'ai/T7/recheck_summary.json'
if f.exists():
    s=json.loads(f.read_text())
    check('AI T7 missing separated from failure',s['population']['expected']==1800 and s['population']['present']==1799 and s['population']['missing_ids']==['D1800'] and s['population']['scope_complete'] is False and s['confirmed']['all_pass']==1798 and s['confirmed']['failed_ids']==['D1777'] and s['unverified']['records']==1)
    check('AI T7 no launch or false progress',s['launch']['launchable'] is False and s['task_status']['verified_done']==9 and s['task_status']['planned']==50 and s['cost']['budget']==4200000)
    check('AI T7 changed input isolated',s['changed_inputs']==['records.json'] and s['confirmed']['changed_values_vs_t5']==0)
    rows=list(csv.DictReader((f.parent/'records_validation.csv').open(encoding='utf-8-sig')))
    check('AI T7 full population IDs',len(rows)==1800 and {r['id'] for r in rows}==set(base_index))
    check('AI T7 every row three-valued',all(r['all_pass'].lower()==('' if r['id']=='D1800' else 'false' if r['id']=='D1777' else 'true') and r['present_v3'].lower()==str(r['id']!='D1800').lower() for r in rows))

f=OUT/'ai/T8/acceptance_review.json'
if f.exists():
    s=json.loads(f.read_text())
    check('AI T8 population restored',s['population']['present']==1800 and s['population']['scope_complete'] is True and s['population']['missing_ids']==[] and s['d1800']['all_pass'] is True)
    check('AI T8 failure retained',s['records']['pass']==1799 and s['records']['fail']==1 and s['records']['failed_ids']==['D1777'] and s['records']['unverified']==0)
    check('AI T8 task evidence retained',s['tasks']['required']==60 and set(s['tasks']['evidence_done'])==done and s['tasks']['reported_unverified']==['W4-02'] and s['tasks']['planned_count']==50)
    decisions={r['id']:r for r in s['decisions']['user_decided']}
    check('AI T8 policy retained',s['tasks']['cost']['budget_D08']==4200000 and '전체 취소' in decisions['D-03']['status'] and '제외' in decisions['D-02']['status'] and '2026-11-20' in decisions['D-09']['status'] and 'draft_only 유지'==decisions['draft_only']['status'])
    check('AI T8 launch remains blocked',s['launch']['launchable'] is False and '미완료' in s['completion']['project_launch'])
    check('AI T8 history compared',s['t1_vs_t8']['t1_fail_resolved']==184 and s['t1_vs_t8']['new_fail_vs_t1']==['D1777'])
    rows=list(csv.DictReader((f.parent/'records_validation.csv').open(encoding='utf-8-sig')))
    check('AI T8 full population IDs',len(rows)==1800 and {r['id'] for r in rows}==set(base_index))
    check('AI T8 every row judgment',all(r['all_pass'].lower()==('false' if r['id']=='D1777' else 'true') and r['present_v4'].lower()=='true' for r in rows))

for n in [1,2,3,5,7,8]:
    f=OUT/'ai'/f'T{n}'/'tasks_tracking.json'
    if not f.exists():continue
    rows=json.loads(f.read_text())['items']
    actual={r['id']:str(r.get(f'status_t{n}') or r.get('status_t3') or r.get('tracked_status')) for r in rows}
    canonical={k:('cancelled' if 'cancelled' in v else 'verified_done' if 'verified_done' in v else 'unverified' if 'unverified' in v else 'planned' if 'planned' in v else v) for k,v in actual.items()}
    exp={r['id']:('cancelled' if n>=2 and r['optional'] else 'verified_done' if n>=3 and int(r['id'][3:])<=2 and not r['optional'] and r['id']!='W4-02' else 'unverified' if n>=3 and r['id']=='W4-02' else 'planned') for r in source_tasks}
    check(f'AI T{n} every task status',len(rows)==72 and canonical==exp)

for snap in sorted((OUT/'snapshots').glob('T*')):
    changed=[]
    for p in snap.rglob('*'):
        if not p.is_file():continue
        relative=p.relative_to(snap);live=OUT/'ai'/relative
        if not live.exists() or hashlib.sha256(p.read_bytes()).digest()!=hashlib.sha256(live.read_bytes()).digest():changed.append(str(relative))
    check(f'{snap.name} prior artifacts preserved',not changed,changed)

report={'checks':checks,'passed':sum(c['pass'] for c in checks),'failed':sum(not c['pass'] for c in checks)}
(OUT/'runs/verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
