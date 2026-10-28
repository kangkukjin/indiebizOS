import sys,json,hashlib
from pathlib import Path
ROOT=Path('/Users/kangkukjin/Desktop/AI/indiebizOS');B1=ROOT/'outputs/long_sentence_imagination/2026-10-28_102회차';B2=ROOT/'outputs/long_sentence_imagination/2026-10-28_103회차'
sys.path.insert(0,str(B1/'harness'));import api
api.BASE=B2
ibl=api.ibl
inputs={'root':str(B1/'source'),'vendor':str(B2/'source/new_vendor.json'),'previous':str(B1/'trainer/final_report.json')}
code=(B2/'trainer/region_v0.ibl').read_text()
mode=sys.argv[1] if len(sys.argv)>1 else ''
if mode=='register':
 contract={'version':1,'params':{'items':'List<Record>'},'required':['items'],'result':'List<Record>','effects':['pure'],'adapter':{'protocol':'registered-json/1'}}
 r=ibl('register_normalizer','return [self:script]{op:"register",id:"LS103Normalize",path:$path,description:"103회차 공급업체 포장가격과 배송비 단위 정규화",callable_contract:$contract}',inputs={'path':str(ROOT/'data/scripts/ls103_normalize.py'),'contract':contract});print(r.get('success'),r.get('error'));assert r['success']
elif mode=='base':
 r=ibl('check_v0',code,inputs=inputs,check=True);print('check',r.get('ok'),r.get('issues'));assert not r.get('issues')
 before=(B1/'trainer/dispatch.jsonl').read_bytes()
 r=ibl('base_v0',code,inputs=inputs);print('run',r.get('success'),r.get('error'));assert r['success']
 (B2/'trainer/base_value.json').write_text(json.dumps(r['value'],ensure_ascii=False,indent=2));assert before==(B1/'trainer/dispatch.jsonl').read_bytes()
elif mode=='save':
 pieces=code.split('[def:')[1:]
 for part in pieces:
  name=part.split(']')[0];body='[def:'+part
  if name=='LS103Region':body=body[:body.rfind('\nreturn [fn:LS103Region]')]
  r=ibl('save_'+name,'return [self:workflow]{op:"save",code:$code,description:$description}',inputs={'code':body,'description':'103회차 재조합 검증: '+name});assert r['success'],r.get('error');print('saved',name,flush=True)
 r=ibl('rediscover',describe=['fn:LS103Region']);print('rediscovered',r['actions'][0]['definition']['function_ref'],flush=True)
 code='''[def:LS103Recommendation]($plan){
 $best=$plan.with_transfer.budget
 return {scenario:"budget_with_transfer",total:$best.total_cost+$plan.transfer_cost,change_from_no_transfer:$plan.base.budget.total_cost-($best.total_cost+$plan.transfer_cost),over_budget_libraries:map(filter($best.libraries,($x)=>$x.over_budget),($x)=>$x.library),plan:$plan}
}
return [fn:LS103Recommendation]{plan:[fn:LS103Region]{root:$root,vendor:$vendor,previous:$previous}}'''
 (B2/'trainer/recalled_composition.ibl').write_text(code)
 r=ibl('recall_check',code,inputs=inputs,check=True);assert not r.get('issues'),r.get('issues')
 r=ibl('recalled_composition',code,inputs=inputs);assert r['success'],r.get('error');(B2/'trainer/recalled_value.json').write_text(json.dumps(r['value'],ensure_ascii=False,indent=2));print('recalled composition PASS')
