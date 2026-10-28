from api import *
for ident,file,params,result,effects,extra in [
 ('LS102Normalize','normalize.py',{'kind':'Text','payload':'Unknown','aliases':'Record'},'List<Record>',['pure'],{}),
 ('LS102Append','append.py',{'path':'Text','request':'Record'},{'receipt':'Text','path':'Text'},['write_external'],{'write_resources':{'file':'path'}})]:
 contract={'version':1,'params':params,'required':list(params),'result':result,'effects':effects,'adapter':{'protocol':'registered-json/1'},**extra}
 r=ibl('register_'+ident,'return [self:script]{op:"register",id:$id,path:$path,description:$description,callable_contract:$contract}',inputs={'id':ident,'path':str(ROOT/'data/scripts'/('ls102_'+file)),'description':'102회차 훈련 전용 '+ident,'contract':contract})
 print(ident,json.dumps(r.get('value',r),ensure_ascii=False)[:1500])
r=ibl('existing_contract',describe=['fn:중복빼고추리기']);print(json.dumps(r,ensure_ascii=False)[:4000])
