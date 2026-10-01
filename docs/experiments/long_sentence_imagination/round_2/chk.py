import json,sys;x=json.load(open(f'runs/{sys.argv[1]}.json'))['response']
print('total chars',len(json.dumps(x,ensure_ascii=False)), x.get('status'), 'guards',len(json.dumps(x.get('guards'),ensure_ascii=False)), x.get('guards_total'), x.get('guards_ref'))
for i in x.get('issues',[]): print(i['code'],i.get('severity'),i.get('location',{}).get('line'),i['message'][:220], '|', (i.get('hint') or '')[:160], '| exp',i.get('expected'),'act',str(i.get('actual'))[:100])
for w in x.get('warnings',[]): print('WARN',w.get('code'),w.get('location',{}).get('line'),w.get('message','')[:200])
print('result_type', x.get('result_type'))
