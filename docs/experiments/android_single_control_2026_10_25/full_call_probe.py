import json,time,urllib.request,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'outputs/phone-fast-control'
OUT.mkdir(parents=True, exist_ok=True)
def api(path,body=None):
 req=urllib.request.Request('http://127.0.0.1:8765/'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=100) as r: return json.load(r)
base=(ROOT/'data/idioms/android_control.ibl').read_text().replace('[def:Android제어]', '[def:Android제어比較]')
rows=[]
for d in api('remote-pcs')['items']:
 if not d.get('connected') or (d.get('phone_update') or {}).get('current_version')!=24: continue
 if len(sys.argv)>1 and d['alias']!=sys.argv[1]: continue
 for i in range(3):
  for mode in (['python','control'] if i%2==0 else ['control','python']):
   body=base.replace('native_control:$선택.native_control','native_control:{}') if mode=='python' else base
   code=body+'\nreturn [fn:Android제어比較]'+json.dumps({'대상':d['device_id'],'요청':{'action':'volume_status','stream':'music'}},ensure_ascii=False)
   start=time.monotonic()
   result=api('ibl/execute',{'code':code,'edition':2,'origin':'user','project_id':'하드웨어'})
   v=result.get('value') or {}
   row={'alias':d['alias'],'mode':mode,'round':i+1,'wall_seconds':round(time.monotonic()-start,3),'status':v.get('status'),'verified':v.get('verified'),'task_ref':v.get('task_ref')}
   rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
   (OUT/('public-comparison-'+d['alias']+'.json')).write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
   if v.get('verified') is not True: raise RuntimeError(str(v.get('failure'))[:1500])
