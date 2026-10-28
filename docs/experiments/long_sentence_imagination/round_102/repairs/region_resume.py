from api import *
import urllib.request
ORIGINAL=BASE;BASE=ORIGINAL/'postrepair';import api;api.BASE=BASE
def http(path,payload=None):
 req=urllib.request.Request('http://127.0.0.1:8765'+path,data=None if payload is None else json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=600) as r:return json.load(r)
api.request=http;ibl=api.ibl
old=json.loads((BASE/'harness/region_after_demand.json').read_text());q=old['request'];r=old['response'];print('budget interruption',r.get('diagnostic',{}).get('code'),r.get('usage',{}).get('steps'),r.get('resume'),flush=True)
r=ibl('region_resumed',q['code'],inputs=q['inputs'],resume=r['resume'],budget={'steps':2000000});assert r['success'],r.get('error')
B2=ROOT/'outputs/long_sentence_imagination/2026-10-28_103회차';expected=json.loads((B2/'trainer/base_value.json').read_text());assert r['value']==expected
actual=r['value'];(BASE/'trainer/region_after.json').write_text(json.dumps(actual,ensure_ascii=False,indent=2));usage=r.get('usage');print('all regional output unchanged',str(usage)[:300],flush=True)
r=ibl('region_write_final','[self:write]{path:$path,content:json($report)};return [self:read]{path:$path}',inputs={'path':str(BASE/'trainer/regional_report.json'),'report':actual});assert r['success'],r.get('error');assert json.loads((BASE/'trainer/regional_report.json').read_text())==expected
(BASE/'harness/demand_verified.json').write_text(json.dumps({'distinct_dates_aggregate':True,'duplicate_request_counted_once':True,'stock_counted_once':True,'earliest_need_by':'2026-11-01','regional_2400_lines_equal':True,'budget':2000000,'usage':usage},ensure_ascii=False,indent=2));print('PASS revised demand + saved region + final file',flush=True)
