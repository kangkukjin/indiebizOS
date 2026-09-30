import json, random
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict, Counter
ROOT = Path(__file__).resolve().parents[4]
LOCAL = ROOT / 'outputs/long_sentence_imagination/2026-09-30_11회차'
HERE = Path(__file__).resolve().parent

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def oracle(rows, meters, tariffs):
    slots = defaultdict(list)
    for r in rows: slots[r['meter'],r['date']].append(r)
    canonical = {}
    anomalies = []
    for key, rr in slots.items():
        vals = {r['reading'] for r in rr if r['reading'] is not None}
        status = 'unreadable' if not vals else 'conflict' if len(vals)>1 else 'ok'
        canonical[key] = (status, next(iter(vals)) if status=='ok' else None)
        if status != 'ok': anomalies.extend(rr)
    intervals=[]
    rates={r['zone']:r['rate'] for r in tariffs}
    for m in meters:
        dates=sorted(k[1] for k in canonical if k[0]==m['meter'])
        for a,b in zip(dates, dates[1:]):
            sa,va=canonical[m['meter'],a]; sb,vb=canonical[m['meter'],b]
            delta=(date.fromisoformat(b)-date.fromisoformat(a)).days
            status='gap' if delta!=1 else 'conflict' if 'conflict' in (sa,sb) else 'unreadable' if 'unreadable' in (sa,sb) else 'ok'
            usage=None; roll=False
            if status=='ok':
                usage=vb-va
                if usage<0:
                    if m['modulus'] is None: status='decrease';usage=None
                    else: usage+=m['modulus'];roll=True
            rate=rates.get(m['zone']); charge=usage*rate if usage is not None and rate is not None else None
            intervals.append(dict(meter=m['meter'],start=a,end=b,zone=m['zone'],status=status,usage=usage,rollover=roll,rate=rate,charge=charge))
    by=[]
    for m in meters:
        rr=[r for r in intervals if r['meter']==m['meter']]
        charges=[r['charge'] for r in rr if r['charge'] is not None]
        usages=[r['usage'] for r in rr if r['usage'] is not None]
        by.append(dict(meter=m['meter'],usage=sum(usages) if usages else None,known_charge=sum(charges) if charges else None,unpriced_intervals=sum(r['usage'] is not None and r['rate'] is None for r in rr)))
    counts=Counter(r['status'] for r in intervals)
    summary=dict(input_rows=len(rows),canonical_slots=len(slots),extra_rows=sum(n-1 for n in Counter((r['meter'],r['date'],r['reading']) for r in rows if r['reading'] is not None).values()),conflict_slots=sum(v[0]=='conflict' for v in canonical.values()),unreadable_slots=sum(v[0]=='unreadable' for v in canonical.values()),interval_count=len(intervals),status_counts=dict(counts),rollover_intervals=sum(r['rollover'] for r in intervals),unpriced_intervals=sum(r['usage'] is not None and r['rate'] is None for r in intervals),total_usage=sum(r['usage'] for r in intervals if r['usage'] is not None),known_charge=sum(r['charge'] for r in intervals if r['charge'] is not None),by_meter=by)
    return dict(summary=summary,intervals=intervals,anomalies=anomalies)

meters=[dict(meter=f'M{i:03}',zone='X' if i==95 else 'ABC'[i%3],modulus=10000 if i<4 else None) for i in range(96)]
tariffs=[dict(zone=z,rate=r) for z,r in zip('ABC',[2,3,4])]
rows=[]
for i,m in enumerate(meters):
    for d in range(31):
        if i<8 and d==10: continue
        reading=(9800+(10+i%7)*d)%10000 if i<4 else 1000+i*100+(10+i%7)*d
        if 14<=i<19 and d==20: reading=None
        rows.append(dict(source_id=f'R{i:03}-{d:02}',meter=m['meter'],date=(date(2026,8,1)+timedelta(days=d)).isoformat(),reading=reading))
        if 8<=i<14 and d==15: rows.append(dict(source_id=f'C{i:03}',meter=m['meter'],date=rows[-1]['date'],reading=reading+7))
for r in list(rows[:100]): rows.append(dict(r,source_id='D'+r['source_id']))
random.Random(1130).shuffle(rows)
a,b=rows[::2],rows[1::2]
for folder in [LOCAL/'inputs',LOCAL/'system_inputs']:
    for name,data in [('meters',meters),('readings_a',a),('readings_b',b),('tariffs',tariffs)]:save(folder/(name+'.json'),dict(rows=data))
variant=[dict(r,rate=5 if r['zone']=='B' else r['rate']) for r in tariffs]
save(LOCAL/'tariffs_variant.json',dict(rows=variant))
save(LOCAL/'expected.json',oracle(rows,meters,tariffs))
save(LOCAL/'expected_variant.json',oracle(rows,meters,variant))
save(LOCAL/'expected_empty_b.json',oracle(a,meters,tariffs))
print(json.dumps({'local':str(LOCAL),'input_rows':len(rows),'expected':oracle(rows,meters,tariffs)['summary']},ensure_ascii=False))
