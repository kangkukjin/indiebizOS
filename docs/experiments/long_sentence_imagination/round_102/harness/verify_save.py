from api import *
actual=json.loads((BASE/'trainer/local_base_v2_value.json').read_text());expected=json.loads((BASE/'harness/expected.json').read_text())
def verify(a,e):
 assert a['total_cost']==e['total_cost'];assert a['hold_count']==e['hold_count']
 for x,y in zip(a['libraries'],e['libraries']):
  assert x['library']==y['library'] and x['ready']==y['ready'] and x['total_cost']==y['total_cost']
  xx={z['item']:z for z in x['lines']}
  assert len(xx)==len(y['lines'])
  for z in y['lines']:
   for k,v in z.items():assert xx[z['item']][k]==v,(x['library'],z['item'],k,xx[z['item']][k],v)
verify(actual,expected)
ledger=[json.loads(x) for x in (BASE/'trainer/dispatch.jsonl').read_text().splitlines()]
assert len(ledger)==2 and [x['request']['library'] for x in ledger]==['L1','L2']
for x in ledger:
 lib=next(l for l in actual['libraries'] if l['library']==x['request']['library']);assert x['request']['lines']==lib['lines'] and x['receipt']==lib['receipt']['receipt']
r=ibl('write_final','[self:write]{path:$path,content:json($report)}; return [self:read]{path:$path}',inputs={'path':str(BASE/'trainer/final_report.json'),'report':actual});assert r['success'];assert json.loads((BASE/'trainer/final_report.json').read_text())==actual
print('600 lines/total/holds/2 append receipts/final file PASS',actual['total_cost'],actual['hold_count'])
source=(BASE/'trainer/main_v2.ibl').read_text();parts=source.split('[def:')[1:];defs={}
for part in parts:
 name=part.split(']')[0];code='[def:'+part
 if name=='LS102Plan':code=code[:code.rfind('\nreturn [fn:LS102Plan]')]
 defs[name]=code.strip()
before={'ledger':(BASE/'trainer/dispatch.jsonl').read_bytes().hex(),'logs':sorted(str(x) for x in (ROOT/'data/script_runs').glob('LS102*'))}
for name,code in defs.items():
 r=ibl('save_'+name,'return [self:workflow]{op:"save",code:$code,description:$description}',inputs={'code':code,'description':'102회차 교육키트 훈련 검증 능력: '+name});assert r['success'],r.get('error')
 print(name,r['value'].get('revision'),r['value'].get('function_id'))
after={'ledger':(BASE/'trainer/dispatch.jsonl').read_bytes().hex(),'logs':sorted(str(x) for x in (ROOT/'data/script_runs').glob('LS102*'))}
assert before==after
(BASE/'harness/save_no_business_execution.json').write_text(json.dumps({'before':before,'after':after,'equal':True},indent=2))
(BASE/'harness/defs.json').write_text(json.dumps(defs,ensure_ascii=False,indent=2))
# The defect is a separate probe, never the successful main execution.
probe={}
for name in ['LS102Report','LS102Library','LS102Plan']:
 code=defs[name]
 for n in ['LS102Report','LS102Library','LS102Plan']:code=code.replace(n,n+'Probe')
 if name=='LS102Report':code=code.replace('($lib.label==null ? $lib.id : $lib.label)','upper($lib.label)')
 probe[name+'Probe']=code
 r=ibl('save_'+name+'Probe','return [self:workflow]{op:"save",code:$code,description:"102회차 의도적 복구 탐침"}',inputs={'code':code});assert r['success'],r.get('error')
(BASE/'harness/probe_defs.json').write_text(json.dumps(probe,ensure_ascii=False,indent=2))
code='return [fn:LS102PlanProbe]{root:$root,ledger:$ledger}'
inputs={'root':str(BASE/'source'),'ledger':str(BASE/'trainer/probe_dispatch.jsonl')}
r=ibl('probe_check',code,inputs=inputs,check=True);assert not r.get('issues'),r.get('issues')
r=ibl('probe_failed',code,inputs=inputs);print('probe',r.get('success'),r.get('error'),r.get('resume'))
(BASE/'trainer/probe_request.json').write_text(json.dumps({'code':code,'inputs':inputs},ensure_ascii=False,indent=2))
