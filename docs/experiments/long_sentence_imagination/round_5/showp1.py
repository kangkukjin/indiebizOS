import json,sys
from rr import rr_all
n=sys.argv[1]
r=json.load(open(f'runs/{n}.json'))['response']
print('ok',r.get('success'),'sc',r.get('source_complete'),'elapsed',json.load(open(f'runs/{n}.json'))['elapsed_s'])
if r.get('success'):
    v=json.loads(rr_all(r['result_ref']['id'],['value'])); json.dump(v,open(f'runs/{n}_value.json','w'),ensure_ascii=False,indent=1)
    print([ (x['id'],x['상태']) for x in v['영수증'] if x['상태']!='읽음'])
    for x in v['추출']: print(x['id'],x['가맹점'],x['날짜'],x['합계'],x['원문확인'])
    print(json.dumps(r['result_ref'].get('input_args'),ensure_ascii=False))
else:
    d=dict(r.get('diagnostic') or {}); d.pop('partial',None); print(json.dumps(d,ensure_ascii=False)[:2000])
m=r.get('usage',{}).get('model') or {}; print('model',m.get('requests'),m.get('input'),m.get('output'))
