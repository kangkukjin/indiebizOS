from api import *
import hashlib,sqlite3,urllib.request
ORIGINAL=BASE;BASE=ORIGINAL/'postrepair';(BASE/'harness').mkdir(parents=True,exist_ok=True);(BASE/'trainer').mkdir(exist_ok=True)
import api
api.BASE=BASE
# HTTP to the actual running generation; no local runtime substitution.
def http(path,payload=None):
 req=urllib.request.Request('http://127.0.0.1:8765'+path,data=None if payload is None else json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=600) as r:return json.load(r)
api.request=http;ibl=api.ibl
for sid in ['LS102Normalize','LS102Append']:
 q=json.loads((ORIGINAL/'harness'/('register_'+sid+'.json')).read_text())['request']
 r=ibl('register_'+sid,**{k:v for k,v in q.items() if k not in ['edition','origin','project_path']});print('registered',sid,r.get('success'),r.get('error'),flush=True);assert r['success'],r
expected=json.loads((ORIGINAL/'harness/expected.json').read_text())
def verify(a):
 assert a['total_cost']==expected['total_cost'] and a['hold_count']==expected['hold_count']
 for x,y in zip(a['libraries'],expected['libraries']):
  assert x['library']==y['library'] and x['total_cost']==y['total_cost'] and x['ready']==y['ready']
  rows={r['item']:r for r in x['lines']}
  for row in y['lines']:
   for k,v in row.items():assert rows[row['item']][k]==v,(x['library'],row['item'],k)
inputs={'root':str(ORIGINAL/'source'),'ledger':str(BASE/'trainer/base_dispatch.jsonl')}
code=(ORIGINAL/'trainer/main_v2.ibl').read_text();r=ibl('base_check',code,inputs=inputs,check=True);assert r['ok'],r
r=ibl('base_run',code,inputs=inputs);assert r['success'],r.get('error');verify(r['value']);(BASE/'trainer/base_report.json').write_text(json.dumps(r['value'],ensure_ascii=False,indent=2));assert len((BASE/'trainer/base_dispatch.jsonl').read_text().splitlines())==2
print('HTTP original full program PASS',flush=True)
probe=json.loads((ORIGINAL/'harness/probe_defs.json').read_text());renamed={}
for name,body in probe.items():
 for old in probe:body=body.replace(old,old.replace('Probe','AfterProbe'))
 new=name.replace('Probe','AfterProbe');renamed[new]=body
 r=ibl('save_'+new,'return [self:workflow]{op:"save",code:$code,description:"102회차 공통 수리 후 별도 복구 검수"}',inputs={'code':body});assert r['success'],r.get('error')
 if 'Report' in new:old_ref=r['value']['function_ref']
 print('saved',new,flush=True)
code='return [fn:LS102PlanAfterProbe]{root:$root,ledger:$ledger}';inputs['ledger']=str(BASE/'trainer/probe_dispatch.jsonl')
r=ibl('probe_failed',code,inputs=inputs);assert not r['success'];rid=r['resume']['run_id'];ledger=Path(inputs['ledger']);before=ledger.read_bytes();assert len(before.splitlines())==2
fixed=renamed['LS102ReportAfterProbe'].replace('upper($lib.label)','($lib.label==null ? $lib.id : upper($lib.label))')
r=ibl('save_fixed','return [self:workflow]{op:"save",code:$code,expected_revision:$revision}',inputs={'code':fixed,'revision':old_ref['revision']});assert r['success'],r.get('error');print('fixed revision saved',flush=True)
d=ibl('describe_fixed',describe=['fn:LS102PlanAfterProbe']);refs=d['actions'][0]['definition']['function_refs']
unsafe=renamed['LS102LibraryAfterProbe'].replace('total_cost:$cost','total_cost:$cost+1')+'\n'+code
r=ibl('unsafe_check',unsafe,inputs=inputs,function_refs=refs,check=True,repair={'run_id':rid});assert not r.get('ok');assert ledger.read_bytes()==before
r=ibl('repair_check',code,inputs=inputs,function_refs=refs,check=True,repair={'run_id':rid});assert r.get('ok'),r
r=ibl('repaired',code,inputs=inputs,function_refs=refs,repair={'run_id':rid,'plan_hash':r['repair']['plan_hash']});assert r['success'],r;verify(r['value']);actual=r['value'];assert ledger.read_bytes()==before
r=ibl('resumed',code,inputs=inputs,resume={'run_id':rid});assert r['success'] and r['value']==actual;assert ledger.read_bytes()==before
r=ibl('write_final','[self:write]{path:$path,content:json($report)}; return [self:read]{path:$path}',inputs={'path':str(BASE/'trainer/final_report.json'),'report':actual});assert r['success'];assert json.loads((BASE/'trainer/final_report.json').read_text())==actual
p=next((ROOT/'data/ibl_runs').rglob(rid+'.sqlite'))
with sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True) as src,sqlite3.connect(BASE/'harness/probe_journal.sqlite') as dst:src.backup(dst)
(BASE/'harness/verified.json').write_text(json.dumps({'run_id':rid,'probe_dispatch':2,'base_dispatch':2,'safe_repair':True,'unsafe_rejected':True,'resume_same':True,'full_lines':600,'http_live':True},indent=2));print('HTTP repair/resume/full file PASS',rid,flush=True)
