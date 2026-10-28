from api import *
import sqlite3,copy
p=json.loads((BASE/'trainer/probe_request.json').read_text());failed=json.loads((BASE/'harness/probe_failed.json').read_text())['response'];assert not failed['success'];rid=failed['resume']['run_id']
ledger=BASE/'trainer/probe_dispatch.jsonl';before=[json.loads(s) for s in ledger.read_text().splitlines()];assert len(before)==2
(BASE/'harness/probe_ledger_before.json').write_text(json.dumps(before,ensure_ascii=False,indent=2))
old=json.loads((BASE/'harness/save_LS102ReportProbe.json').read_text())['response']['value']['function_ref']
defs=json.loads((BASE/'harness/probe_defs.json').read_text())
fixed=defs['LS102ReportProbe'].replace('upper($lib.label)','($lib.label==null ? $lib.id : upper($lib.label))')
r=ibl('probe_save_fixed','return [self:workflow]{op:"save",code:$code,expected_revision:$revision,description:"102회차 복구 탐침: nullable 표시 수리"}',inputs={'code':fixed,'revision':old['revision']});assert r['success'],r.get('error')
desc=ibl('probe_describe_fixed',describe=['fn:LS102PlanProbe']);definition=desc['actions'][0]['definition'];refs=definition['function_refs']
# Unsafe dispatch request mutation: check only, never run.
unsafe=defs['LS102LibraryProbe'].replace('total_cost:$cost','total_cost:$cost+1')+'\n'+p['code']
r=ibl('probe_unsafe_check',unsafe,inputs=p['inputs'],function_refs=refs,check=True,repair={'run_id':rid});print('unsafe',r.get('ok'),str(r.get('issues'))[:800]);assert r.get('issues'),r
r=ibl('probe_repair_check',p['code'],inputs=p['inputs'],function_refs=refs,check=True,repair={'run_id':rid});print('repair check',r.get('ok'),r.get('repair'),str(r.get('issues'))[:1600])
assert not r.get('issues'),r.get('issues')
plan=r['repair']['plan_hash'];r=ibl('probe_repaired',p['code'],inputs=p['inputs'],function_refs=refs,repair={'run_id':rid,'plan_hash':plan});print('repaired',r.get('success'),r.get('error'),r.get('resume'));assert r['success'],r.get('error')
actual=r['value'];(BASE/'trainer/probe_repaired_report.json').write_text(json.dumps(actual,ensure_ascii=False,indent=2))
after=[json.loads(s) for s in ledger.read_text().splitlines()];assert after==before
r=ibl('probe_resumed',p['code'],inputs=p['inputs'],resume={'run_id':rid});assert r['success'];assert [json.loads(s) for s in ledger.read_text().splitlines()]==before
expected=json.loads((BASE/'harness/expected.json').read_text());assert actual['total_cost']==expected['total_cost'];assert actual['hold_count']==expected['hold_count'];assert len(actual['libraries'])==3
for lib,exp in zip(actual['libraries'],expected['libraries']):
 assert lib['total_cost']==exp['total_cost'];rows={x['item']:x for x in lib['lines']}
 for row in exp['lines']:
  for key,value in row.items():assert rows[row['item']][key]==value
r=ibl('probe_write_final','[self:write]{path:$path,content:json($report)}; return [self:read]{path:$path}',inputs={'path':str(BASE/'trainer/probe_final.json'),'report':actual});assert r['success'];assert json.loads((BASE/'trainer/probe_final.json').read_text())==actual
# Snapshot durable receipts only after terminal calls, with SQLite backup semantics.
paths=list((ROOT/'data/ibl_runs').rglob(rid+'.sqlite'));assert len(paths)==1
with sqlite3.connect('file:'+str(paths[0])+'?mode=ro',uri=True) as src,sqlite3.connect(BASE/'harness/probe_journal.sqlite') as dst:src.backup(dst)
print('PASS original 2 dispatch effects preserved through repair and resume; all 3 libraries completed',rid)
