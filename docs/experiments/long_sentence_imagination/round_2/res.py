import json,sys;r=json.load(open(f'runs/{sys.argv[1]}.json'));x=r['response']
print('elapsed',r['elapsed_s'],'chars',len(json.dumps(x,ensure_ascii=False)),'keys',list(x)[:30])
for k in ['success','ok','status','source_complete','run_id','error']: print(k, x.get(k))
d=x.get('diagnostic')
if d: print('DIAG',d.get('code'),d.get('message','')[:400],'line',(d.get('location') or {}).get('line'),'frames',json.dumps(d.get('frames'),ensure_ascii=False)[:600], 'details', json.dumps(d.get('details'),ensure_ascii=False)[:600])
print('VALUE', json.dumps(x.get('value'),ensure_ascii=False)[:int(sys.argv[2]) if len(sys.argv)>2 else 3000])
