"""Check semantic results without imposing trainer-specific JSON naming."""
import json
import sys
from prepare import HERE,OUT
from verify import expected

cases=[(sys.argv[1],sys.argv[2])] if len(sys.argv)>2 else [('ai-base','base'),('ai-variant','variant')]
for label,phase in cases:
    p=OUT/label;d=json.loads((p/'decisions.json').read_text());md=(p/'newsletter.md').read_text()
    want=expected(phase,'ai');got={r.get('id',r.get('event_id')):r for r in d['decisions']};errors=[]
    for w in want:
        r=got.get(w['event_id'],{});actual=r.get('verdict','').replace(' ','')
        category='추천' if w['reason']=='included' else '확인필요' if w['reason'] in ('conflict','undated') else '과거정보' if w['reason']=='unverified' else '제외'
        if not actual.startswith(category):errors.append([w['event_id'],'verdict',actual,category])
        if w['reason']!='conflict':
            for key in ('title','region','date','status'):
                if r.get(key)!=w[key]:errors.append([w['event_id'],key])
        if sorted(s['url'] for s in r.get('sources',[]))!=sorted(s['url'] for s in w['sources']):
            errors.append([w['event_id'],'sources'])
        for source in w['sources']:
            if source['url'] not in md:errors.append([w['event_id'],'markdown_source'])
        if w['event_id'] not in md:errors.append([w['event_id'],'markdown_id'])
    if len(got)!=36:errors.append(['event_count',len(got)])
    result={'label':label,'phase':phase,'events':len(got),'errors':errors,'passed':not errors,
            'editorial_issue':'base E06 repost label is inaccurate; variant labels revision correctly' if label=='ai-base' else None}
    (HERE/'evidence'/f'verify-{label}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False))
    if errors:raise SystemExit(1)
