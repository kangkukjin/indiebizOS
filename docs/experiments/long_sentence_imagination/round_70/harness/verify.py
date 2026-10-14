"""Independent reference calculation and final artifact checks."""
import argparse
import collections
import json
from pathlib import Path
from prepare import HERE, OUT, BASE

def expected(phase, who='trainer'):
    data=json.loads((HERE/'fixtures/notices.json').read_text())
    grouped=collections.defaultdict(list)
    for wh in 'abc':
        stale=phase=='variant' and wh=='b'
        actual_phase='base' if stale else phase
        for row in data[actual_phase][wh]:
            grouped[row['event_id']].append({**row,'stale':stale,'warehouse':wh,
                'url':f'{BASE}/{who}/{actual_phase}/{wh}/f?path={row["event_id"]}.json'})
    answer=[]
    for eid,rows in grouped.items():
        fresh=[r for r in rows if not r['stale']]
        pool=fresh or rows
        newest=max(r['updated_at'] for r in pool)
        latest=[r for r in pool if r['updated_at']==newest]
        row=latest[0]
        forms={(r['title'],r['region'],r['date'],r['status']) for r in latest}
        if not fresh: reason='unverified'
        elif len(forms)>1: reason='conflict'
        elif row['status']=='cancelled': reason='cancelled'
        elif row['date'] is None: reason='undated'
        elif row['date']<'2026-10-15': reason='past'
        elif row['date']>'2026-10-21': reason='outside'
        else: reason='included'
        answer.append({'event_id':eid,'title':row['title'],'region':row['region'],
            'date':row['date'],'status':row['status'],'updated_at':newest,'reason':reason,
            'sources':[{'url':r['url'],'warehouse':r['warehouse'],'stale':r['stale']} for r in rows]})
    return sorted(answer,key=lambda r:(r['region'],r['date'] is None,r['date'] or '',r['event_id']))

def verify(label,phase):
    out=OUT/label; want=expected(phase)
    actual=json.loads((out/'decisions.json').read_text())
    collected=json.loads((out/'collected.json').read_text())
    md=(out/'newsletter.md').read_text()
    got=actual['decisions'];errors=[]
    if len(got)!=len(want):errors.append(f'events {len(got)} != {len(want)}')
    lookup={r['event_id']:r for r in got}
    for row in want:
        received=lookup.get(row['event_id'],{})
        for k in ('event_id','title','region','date','status','updated_at','reason','sources'):
            if ( [{key:s.get(key) for key in ('url','warehouse','stale')} for s in received.get(k,[])] if k=='sources' else received.get(k))!=row[k]:errors.append(f'{row["event_id"]}.{k}: {received.get(k)!r} != {row[k]!r}')
        if row['event_id'] not in md:errors.append(f'missing article {row["event_id"]}')
        for source in row['sources']:
            if source['url'] not in md:errors.append(f'missing link {source["url"]}')
    if [r['event_id'] for r in got]!=[r['event_id'] for r in want]:errors.append('region/date ordering')
    if len(collected['rows'])!=54:errors.append('notice coverage')
    if phase=='variant' and ('503' not in md or '過去' not in md and '과거자료' not in md):
        errors.append('failure or stale labels missing')
    expected_counts=collections.Counter(r['reason'] for r in want)
    result={'label':label,'phase':phase,'passed':not errors,'errors':errors,
            'counts':dict(expected_counts),'events':len(got),'notices':len(collected['rows']),
            'fresh_reused':sum(r['reused'] and not r['stale'] for r in collected['rows']),
            'stale_preserved':sum(r['stale'] for r in collected['rows'])}
    (HERE/'evidence'/f'verify-{label}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False))
    return not errors

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('label');p.add_argument('phase');a=p.parse_args()
    raise SystemExit(0 if verify(a.label,a.phase) else 1)
