from api import *
import urllib.request
ORIGINAL=BASE;BASE=ORIGINAL/'postrepair';import api;api.BASE=BASE
# Live execution once the three implementation repairs are active.
def http(path,payload=None):
 req=urllib.request.Request('http://127.0.0.1:8765'+path,data=None if payload is None else json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=600) as r:return json.load(r)
api.request=http;ibl=api.ibl
source=json.loads((ORIGINAL/'harness/defs.json').read_text())['LS102Demand']
fixed=source.replace('$demand=$unique >> [table:groupby]{by:["library","item","need_by"],agg:{requested:["sum","quantity"]}}', '''$dated=map($unique,($r)=>{**$r,demand_key:json([$r.library,$r.item])})
  $earliest=[fn:중복빼고추리기]{목록:sorted($dated,"need_by"),키:"demand_key",개수:10000}
  $dates=from_entries(map($earliest,($r)=>[$r.demand_key,$r.need_by]))
  $demand=$unique >> [table:groupby]{by:["library","item"],agg:{requested:["sum","quantity"]}}
  $demand=map($demand.items,($r)=>{**$r,need_by:$dates[json([$r.library,$r.item])]})''')
assert fixed!=source;(BASE/'trainer/demand_fixed.ibl').write_text(fixed)
# Distinct dates, duplicate request, and stock counted once. Earlier date is second.
data={'requests':[{'request_id':'a','library':'L1','item':'K','need_by':'2026-11-10','quantity':2},{'request_id':'b','library':'L1','item':'K','need_by':'2026-11-01','quantity':3},{'request_id':'b','library':'L1','item':'K','need_by':'2026-11-01','quantity':3}], 'stock':[{'library':'L1','item':'K','available':4,'reserved':1}]}
for label,code in [('demand_original',source),('demand_fixed',fixed)]:
 r=ibl(label,code+'\nreturn [fn:LS102Demand]{data:$data}',inputs={'data':data});assert r['success'],r
 if label=='demand_original':assert len(r['value'])==2
 else:assert len(r['value'])==1 and r['value'][0]['requested']==5 and r['value'][0]['need_by']=='2026-11-01' and r['value'][0]['available']==3 and r['value'][0]['shortage']==2
ref=ibl('demand_describe',describe=['fn:LS102Demand'])['actions'][0]['definition']['function_ref']
r=ibl('demand_save','return [self:workflow]{op:"save",code:$code,expected_revision:$revision}',inputs={'code':fixed,'revision':ref['revision']});assert r['success'],r
# Reconsume the revised component from saved regional ability; no original effects.
B2=ROOT/'outputs/long_sentence_imagination/2026-10-28_103회차'
r=ibl('region_after_demand','return [fn:LS103Region]{root:$root,vendor:$vendor,previous:$previous}',inputs={'root':str(ORIGINAL/'source'),'vendor':str(B2/'source/new_vendor.json'),'previous':str(ORIGINAL/'trainer/final_report.json')});assert r['success'],r
expected=json.loads((B2/'trainer/base_value.json').read_text());assert r['value']==expected
(BASE/'trainer/region_after.json').write_text(json.dumps(r['value'],ensure_ascii=False,indent=2));print('earliest-date aggregation fixed; saved regional capability all outputs unchanged',flush=True)
