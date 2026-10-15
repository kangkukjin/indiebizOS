"""Independent output oracle; does not execute the trainer's IBL."""
import base64
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[5]
OUT=ROOT/'outputs/long_sentence_imagination/2026-10-15_72회차'
label=sys.argv[1]
rows=json.loads((OUT/label/'evidence.json').read_text())
checks=[]
for run in rows:
    recovered=label.startswith('repair') and run['variant'] in ('recovered','burst','fault')
    missing=[] if run['variant']=='base' or recovered else ['part2.json']
    expected=[]
    order=list(range(24))
    if recovered:order.reverse()
    for i in order:
        qty=0 if recovered and i==0 else 10+i
        shipped=sum((i+p)%7+(run['member']=='B') for p in range(4) if f'part{p+1}.json' not in missing)
        expected.append({'sku':f'K{i:02d}','ordered':qty,'shipped':shipped,
                         'shortage':None if missing else max(0,qty-shipped),
                         'status':'unknown' if missing else 'shortage' if shipped<qty else 'fulfilled'})
    value={'rows':expected,'total_ordered':sum(x['ordered'] for x in expected),
           'total_shipped':sum(x['shipped'] for x in expected),'missing_files':missing}
    actual=json.loads(base64.b64decode(run['artifacts']['reconciliation.json']))
    assert actual==value,(run['member'],run['variant'],actual,value)
    summary=base64.b64decode(run['artifacts']['summary.txt']).decode()
    assert summary==f"총 주문 {value['total_ordered']} / 확인된 출하 {value['total_shipped']} / 미확인 {len(missing)}파일"
    assert run['reexecuted']==0,run
    assert run['replay']['state']==run['hub_status']['state'],run['replay']
    if 'inputs_unchanged' in run: assert run['inputs_unchanged']
    hub=run['hub_status'];events=hub['events']
    if label.startswith('repair'):
        if run['variant']=='fault': assert run['result']['state']=='unknown'
        if run['variant']=='burst':
            assert hub['events_gap']=={'from':1,'to':events[0]['seq']-1}
            assert any('보관 범위' in str(e['value']) for e in run['result']['events'] if e['kind']=='assistant')
    checks.append({'member':run['member'],'variant':run['variant'],'state':run['result']['state'],
        'seconds':round(run['seconds'],3),'artifacts_correct':True,'reexecuted':run['reexecuted'],
        'events_first':events[0]['seq'] if events else None,'cursor':hub['cursor'],
        'events_gap':hub.get('events_gap'),'totals':[value['total_ordered'],value['total_shipped']],
        'request_id':hub['request_id'],'task_id':run['task_id']})
(OUT/label/'verification.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2))
print(json.dumps(checks,ensure_ascii=False,indent=2))
