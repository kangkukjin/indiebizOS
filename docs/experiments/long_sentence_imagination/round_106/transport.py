"""HTTP 운송만 수행하며 연구 조합은 저장한 IBL 프로그램이 소유한다."""
import json,sys,time,uuid,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'outputs/long_sentence_imagination/2026-11-01_106회차'
def call(label,body,timeout=600):
 body={'edition':2,'origin':'training','project_path':str(ROOT),'ticket':uuid.uuid4().hex,**body}
 p=OUT/'runs'/f'{label}.json';rec={'request':body,'started':time.time()};p.write_text(json.dumps(rec,ensure_ascii=False,indent=2))
 req=urllib.request.Request('http://127.0.0.1:8765/ibl/execute',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(req,timeout=timeout) as r:res=json.load(r)
 except urllib.error.HTTPError as e:res={'http_error':e.code,'body':e.read().decode()}
 except Exception as e:res={'transport_unknown':True,'error':str(e)}
 rec.update(response=res,ended=time.time(),seconds=time.time()-rec['started']);p.write_text(json.dumps(rec,ensure_ascii=False,indent=2))
 print(json.dumps({'label':label,'seconds':rec['seconds'],**{k:res.get(k) for k in ['success','issues','error','diagnostic','run_id','value','http_error','transport_unknown'] if k in res}},ensure_ascii=False)[:3500],flush=True)
 return res
if __name__=='__main__':
 label=sys.argv[1];body=json.loads(Path(sys.argv[2]).read_text());call(label,body)
