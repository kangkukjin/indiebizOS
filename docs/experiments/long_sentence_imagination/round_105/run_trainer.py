import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[4]/'backend'))
import boot_paths
import harness as h
import json
body=h.OUT/'trainer'
raw={'invoice_id':'p1','machine':'A','fee':'₩1,000','source':'probe'}
normalized=[{'invoice_id':'p1','asset_id':'A','amount':1000,'raw':raw}]
contract={'version':1,'params':{'rows':'List<Record>'},'required':['rows'],'result':'List<Record>','effects':['pure'],'adapter':{'protocol':'registered-json/1'}}
script_request={'kind':'script','operation':'add','target':'LS105Normalize','source':'data/scripts/ls105_normalize.py','description':'청구 원행을 보존하며 장비 식별번호와 원 단위 정수 금액 정규화','registration':{'callable_contract':contract},'probes':[{'code':'[self:script]{id:"LS105Normalize",args:$args}','inputs':{'args':{'rows':[raw]}},'expected':normalized}]}
a=[{'asset_id':'A','branch':'B1','expected_cost':900}]
expected={'rows':[{'asset_id':'A','branch':'B1','expected_cost':900,'actual_cost':1000,'difference':100,'missing_check':False,'duplicate_count':0}],'unmatched':[],'total_actual':1000,'duplicates':0,'missing_checks':0,'mismatches':1}
reconcile_request={'kind':'idiom','operation':'add','target':'LS105Reconcile','code':(h.DOC/'reconcile_v0.ibl').read_text(),'description':'장비·차량 등 대상대장과 점검·청구를 대사하고 누락·재접수·차액·미연결을 보존한다','probes':[{'code':'[fn:LS105Reconcile]{assets:$a,checks:$c,bills:$b}','inputs':{'a':a,'c':[{'asset_id':'A'}],'b':normalized},'expected':expected}]}
report_request={'kind':'idiom','operation':'add','target':'LS105Report','code':(h.DOC/'report_v0.ibl').read_text(),'description':'대장·점검·청구 JSON 자료에서 대사 보고서를 만들고 저장 결과를 재독한다','probes':[{'code':'[fn:LS105Report]{input_root:"inputs",output:"outputs/probe_report.json"}','expected':{'path':'outputs/probe_report.json','total_actual':sum(10000+i*17+(500 if i%13==0 else 0) for i in range(1,601)),'duplicates':24,'missing_checks':60,'mismatches':46,'rows':600,'unmatched':12}}]}
inputs={'normalizer':(h.DOC/'normalize_v0.py.txt').read_text(),'script_request':script_request,'reconcile_request':reconcile_request,'report_request':report_request}
code=(h.DOC/'trainer_v0.ibl').read_text()
request={'code':code,'inputs':inputs}
h.dump(h.OUT/'trainer_request_v0.json',request)
check=h.child(body,{**request,'check':True});h.dump(h.OUT/'trainer_check_v0.json',check)
print('CHECK',json.dumps({k:check.get(k) for k in ['success','issues','warnings']},ensure_ascii=False)[:2500])
if not check.get('issues'):
 result=h.child(body,request);h.dump(h.OUT/'trainer_result_v0.json',result)
 print('RUN',json.dumps({k:result.get(k) for k in ['success','value','error','diagnostic']},ensure_ascii=False)[:5000])
