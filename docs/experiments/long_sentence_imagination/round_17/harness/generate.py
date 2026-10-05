import json, os
from pathlib import Path
from collections import defaultdict
rooms=[dict(room=f'R{i:03}',building='E' if i%2==0 else 'W',capacity=None if i in (0,1) else 12+i%5*4) for i in range(240)]
bookings=[]
for i in range(2400):
    room=i//10; slot=i%10; day='2026-10-12' if slot<5 else '2026-10-13'; s=540+(slot%5)*60
    bookings.append(dict(id=f'B{i:04}',room=f'R{room:03}',day=day,start=s,end=s+[45,60,75][i%3],people=10+i%25,status='cancelled' if i%37==0 else 'active',source='bookings_a.csv' if i<1200 else 'bookings_b.json',row=i+2 if i<1200 else i-1199))
for i in range(101,2400,211): bookings[i]['room']='RX'
for i in range(113,2400,223): bookings[i]['end']=bookings[i]['start']
maint=[dict(mid=f'M{i:03}_{d}',room=f'R{i:03}',day=f'2026-10-{12+d}',start=650+i%3*10,end=675+i%3*10) for i in range(240) for d in range(2)]
roommap={r['room']:r for r in rooms}
def expected(buffer):
    usable=[]; excluded=[]; over=[]; unknown=[]
    for x in bookings:
        reason='cancelled' if x['status']=='cancelled' else 'unknown_room' if x['room'] not in roommap else 'invalid_interval' if x['end']<=x['start'] else None
        if reason: excluded.append(dict(id=x['id'],reason=reason,source=x['source'],row=x['row'])); continue
        y=dict(x,**{k:v for k,v in roommap[x['room']].items() if k!='room'})
        y['effective_end']=y['end']+(buffer if y['building']=='E' else 0); usable.append(y)
        if y['capacity'] is None: unknown.append(y['id'])
        elif y['people']>y['capacity']: over.append(y['id'])
    by=defaultdict(list)
    for x in usable: by[(x['room'],x['day'])].append(x)
    pairs=[]
    for group in by.values():
        for idx,x in enumerate(group):
            for y in group[idx+1:]:
                if max(x['start'],y['start'])<min(x['effective_end'],y['effective_end']): pairs.append(dict(a=x['id'],b=y['id'],room=x['room'],day=x['day'],overlap=min(x['effective_end'],y['effective_end'])-max(x['start'],y['start'])))
    blocks=[]
    for m in maint:
        for x in by[(m['room'],m['day'])]:
            if max(x['start'],m['start'])<min(x['effective_end'],m['end']): blocks.append(dict(id=x['id'],mid=m['mid'],overlap=min(x['effective_end'],m['end'])-max(x['start'],m['start'])))
    impacted=set(over)|set(unknown)|{x['a'] for x in pairs}|{x['b'] for x in pairs}|{x['id'] for x in blocks}
    summary=dict(input_count=len(bookings),usable_count=len(usable),excluded_count=len(excluded),pair_count=len(pairs),maintenance_count=len(blocks),over_capacity_count=len(over),unknown_capacity_count=len(unknown),impacted_unique=len(impacted))
    perroom=[]
    for r in rooms:
        ids={x['id'] for x in usable if x['room']==r['room']}
        perroom.append(dict(room=r['room'],building=r['building'],usable_count=len(ids),impacted_unique=len(ids&impacted)))
    rank=sorted(perroom,key=lambda r:(-r['impacted_unique'],r['room']))[:10]
    return dict(summary=summary,excluded=excluded,pairs=pairs,maintenance=blocks,over_capacity=sorted(over),unknown_capacity=sorted(unknown),rooms=perroom,top10=rank)
base=expected(0); variant=expected(15)
result=dict(a=bookings[:1200],b=bookings[1200:],rooms=rooms,maintenance=maint,expected=dict(base=base,variant=variant,summaries=dict(base=base['summary'],variant=variant['summary'])),counts=dict(bookings=2400,rooms=240,maintenance=480))
Path(os.environ['INDIEBIZ_SCRIPT_RESULT']).write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
