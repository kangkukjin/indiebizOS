import json,time,urllib.request,os,sys,asyncio
from pathlib import Path
ROOT=Path('/Users/kangkukjin/Desktop/AI/indiebizOS')
BASE=ROOT/'outputs/long_sentence_imagination/2026-10-28_102회차'
def request(path,payload=None):
 if path=='/ibl/execute' and os.environ.get('LS102_LOCAL')=='1':
  sys.path.insert(0,str(ROOT/'backend'))
  import boot_paths
  from api_ibl import execute_ibl_code,IBLRequest
  return asyncio.run(execute_ibl_code(IBLRequest(**payload)))
 req=urllib.request.Request('http://127.0.0.1:8765'+path,data=None if payload is None else json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=120) as r:return json.load(r)
def ibl(label,code='',**kw):
 p={'code':code,'edition':2,'origin':'training','project_path':str(ROOT),**kw}
 t=time.time();r=request('/ibl/execute',p)
 (BASE/'harness'/f'{label}.json').write_text(json.dumps({'request':p,'elapsed':time.time()-t,'response':r},ensure_ascii=False,indent=2))
 return r
if __name__=='__main__':
 for label,names in [('contracts1',['self:read','self:write','self:script','self:workflow']),('contracts2',['table:join','table:groupby','table:dedup','table:sort'])]:
  r=ibl(label,describe=names);print(label,json.dumps(r,ensure_ascii=False)[:22000])
