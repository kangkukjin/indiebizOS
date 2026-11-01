import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[4]/'backend'))
import boot_paths
import harness as h
import json,shutil
b=h.OUT/'trainer';shutil.copytree(h.OUT/'variant_inputs',b/'inputs_variant',dirs_exist_ok=True)
original=json.loads((h.OUT/'trainer_request_v0.json').read_text())['inputs']
script=original['script_request'];script['operation']='update'
raw={'invoice_id':'p1','machine':'A','fee':'KRW 1,000','source':'probe'}
script['probes']=[{'code':'[self:script]{id:"LS105Normalize",args:$args}','inputs':{'args':{'rows':[raw]}},'expected':[{'invoice_id':'p1','asset_id':'A','amount':1000,'raw':raw}]}]
report=original['report_request'];report.update(operation='update',code=report['code'].replace('$tolerance=0','$tolerance=500'))
report['probes']=[{'code':'[fn:LS105Report]{input_root:"inputs_variant",output:"outputs/probe_variant.json"}','expected':{'path':'outputs/probe_variant.json','total_actual':9088100,'duplicates':24,'missing_checks':54,'mismatches':0,'rows':600,'unmatched':12}}]
source=original['normalizer'].replace(".replace('₩','')", ".replace('₩','').replace('KRW','')")
(h.DOC/'normalize_v1.py.txt').write_text(source)
code='''$w=[self:write]{path:"data/scripts/ls105_normalize.py",content:$source}
$s=[fn:능력변경완료]{요청:$script}
assert $s.behavior_verified,"스크립트 검사"
$r=[fn:능력변경완료]{요청:$report}
assert $r.complete,"관용구 검사"
$out=[self:workflow]{op:"run",edition:2,pipeline:"[fn:LS105Report]{input_root:\\"inputs_variant\\",output:\\"outputs/report_variant.json\\"}"}
return {script:$s,report:$r,business:$out.value}'''
(h.DOC/'trainer_variant.ibl').write_text(code)
request={'code':code,'inputs':{'source':source,'script':script,'report':report}}
h.dump(h.OUT/'trainer_variant_request.json',request)
check=h.child(b,{**request,'check':True});h.dump(h.OUT/'trainer_variant_check.json',check);print('check',check.get('issues'))
if not check.get('issues'):
 r=h.child(b,request);h.dump(h.OUT/'trainer_variant_result.json',r);print('run',r.get('success'),r.get('error'),str(r.get('value'))[-450:])
