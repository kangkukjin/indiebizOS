import json,sys
r=json.load(open(f'runs/{sys.argv[1]}.json'))['response']
print('status',r.get('status'),'success',r.get('success'),'chars',len(json.dumps(r,ensure_ascii=False)), 'guards',len(json.dumps(r.get('guards',[]),ensure_ascii=False)))
for i in r.get('issues',[]) or ([r['diagnostic']] if r.get('diagnostic') else []):
    loc=i.get('location') or {}
    print('E',i.get('code'),'L',loc.get('line'),i.get('message','')[:400],'| hint:',(i.get('hint') or '')[:300], '| cp', i.get('call_path'))
for w in r.get('warnings',[]): print('W', w.get('code'), (w.get('location') or {}).get('line'), str(w.get('message'))[:300])
