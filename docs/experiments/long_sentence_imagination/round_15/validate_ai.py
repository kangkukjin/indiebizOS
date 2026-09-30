import csv,json,math
from pathlib import Path
from collections import Counter,defaultdict
import sys
P=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parent
report=P/'out_ai/report.md'; result=P/'out_ai/issues.json'
if not report.exists() or not result.exists():
    print('final artifacts pending');raise SystemExit(0)
x=json.loads(result.read_text()); expected=json.loads((P.parents[2]/'docs/experiments/long_sentence_imagination/round_10/expected_09.json').read_text())
names={'low_attendance':'출석률미달','consecutive_absences':'연속결석','score_drop':'성적하락','untested':'미응시','no_payment':'미납','multiple_payments':'중복납부','underpayment':'금액부족','withdrawn_attendance':'퇴원생출석'}
groups={g['type']:g for g in x['issues']}
checks={};details={}
for key,ekey in names.items():
    got=sorted({r['id'] for r in groups[key]['items']});want=expected[ekey]
    checks[key]=got==want
    details[key]={'got':got,'expected':want,'records':len(groups[key]['items'])}
students=list(csv.DictReader((P/'input_09/students.csv').open()));student={s['학번']:s for s in students};active={s['학번'] for s in students if s['상태']=='재원'}
classes=defaultdict(lambda:defaultdict(int))
for s in students:
    cls=classes[s['반']];cls['students']+=1
    if s['학번'] in active:cls['active']+=1
for f in (P/'input_09/attendance').glob('*.csv'):
    for a in csv.DictReader(f.open()):
        if a['학번'] in active:
            cls=classes[student[a['학번']]['반']];cls['sessions']+=1;cls['present']+=a['상태']!='결석'
for s in json.loads((P/'input_09/scores.json').read_text())['scores']:
    if s['id'] in active and s['cur'] is not None:
        cls=classes[student[s['id']]['반']];cls['score_n']+=1;cls['score_sum']+=s['cur']
checks['classes']=len(x['classes'])==len(classes)
for r in x['classes']:
    e=classes[r['class']]
    checks['classes'] &= all(r[k]==e[k] for k in ['students','active','sessions','present','score_n','score_sum'])
    checks['classes'] &= abs(r['attendance_pct']-100*e['present']/e['sessions'])<=0.0051
    checks['classes'] &= abs(r['score_avg']-e['score_sum']/e['score_n'])<=0.0051
orig=list(csv.DictReader((P/'input_09/notes.csv').open()))
notes=x['notes']['items'];nc=Counter(r['category'] for r in notes)
checks['notes_count']=len(notes)==60
checks['notes_originals']=Counter((r['id'],r['date'],r['memo']) for r in notes)==Counter((r['학번'],r['일자'],r['메모']) for r in orig)
checks['notes_classified']=dict(nc)==expected['메모유형_심은것'] and x['notes']['ai_classified']
checks['actions']=Counter(r['id'] for r in x['notes']['action_required'])==Counter(r['id'] for r in notes if r['category']=='조치 필요')
checks['source_rows']=x['validation']['source_attendance_rows']==6656 and x['validation']['source_payment_rows']==294 and x['validation']['source_score_rows']==302 and x['validation']['source_note_rows']==60
checks['source_errors']=not any(x['data_quality'][k] for k in ['read_errors','parse_errors','uninterpretable_rows'])
md=report.read_text();checks['md_names']=all(i in md for ids in expected.values() if isinstance(ids,list) for i in ids)
checks['md_classes']=all(c in md for c in classes)
checks['md_ai_label']='AI' in md
answer={'checks':checks,'details':details,'note_counts':dict(nc),'class_expected':dict(classes),'all_deterministic_checks':all(checks.values()),'note':'Artifact readback by AI itself must also be checked from its tool trace; this verifier is the trainer check.'}
(P/'ai_validation.json').write_text(json.dumps(answer,ensure_ascii=False,indent=2));print(json.dumps(answer,ensure_ascii=False,indent=1))
