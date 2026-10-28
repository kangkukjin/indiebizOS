from run_region import ROOT,B1,B2,ibl
import json,sys
expected=json.loads((B1/'harness/variant_expected.json').read_text());actual=json.loads((B2/'trainer/base_value.json').read_text());checks=0
for mode in ['base','with_transfer']:
 for policy in ['deadline','budget']:
  a=actual[mode][policy];e=expected[mode][policy];assert a['total_cost']==e['total_cost']
  for x,y in zip(a['libraries'],e['libraries']):
   assert x['library']==y['library'] and x['total_cost']==y['total_cost'] and x['over_budget']==y['over_budget']
   xx={r['item']:r for r in x['lines']}
   for row in y['lines']:
    for k,v in row.items():assert xx[row['item']][k]==v,(mode,policy,y['library'],row['item'],k,xx[row['item']][k],v);checks+=1
assert actual['transfer_cost']==expected['transfer_cost']
assert [{k:t[k] for k in ['item','from','to','quantity','cost']} for t in actual['transfers']]==expected['transfers']
assert actual['previous_total']==276251
r=ibl('write_final','[self:write]{path:$path,content:json($report)}; return [self:read]{path:$path}',inputs={'path':str(B2/'trainer/regional_report.json'),'report':actual});assert r['success'];assert json.loads((B2/'trainer/regional_report.json').read_text())==actual
if (B2/'trainer/recalled_value.json').exists():
 recalled=json.loads((B2/'trainer/recalled_value.json').read_text());assert recalled['plan']==actual;assert recalled['total']==459330;assert recalled['change_from_no_transfer']==31316
 r=ibl('write_proposal','[self:write]{path:$path,content:json($proposal)}; return [self:read]{path:$path}',inputs={'path':str(B2/'trainer/proposal.json'),'proposal':recalled});assert r['success']
(B2/'harness/verification.json').write_text(json.dumps({'checks':checks,'line_count':2400,'transfer_items':40,'transfer_qty':147,'transfer_cost':1029,'base_deadline':717400,'base_budget':490646,'transfer_deadline':684329,'transfer_budget':459330,'pass':True},indent=2));print('PASS',checks,'fields across 2400 planned lines')
