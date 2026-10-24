import importlib.util,json,time,urllib.request,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'outputs/phone-fast-control'
OUT.mkdir(parents=True, exist_ok=True)
spec=importlib.util.spec_from_file_location('driver',ROOT/'data/scripts/android_control.py')
driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
source=(ROOT/'data/instruments/phone_control.py').read_text()
def api(path,body=None):
 req=urllib.request.Request('http://127.0.0.1:8765/'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=100) as r: return json.load(r)
def ibl(code):
 v=api('ibl/execute',{'code':code,'edition':2,'origin':'user','project_id':'하드웨어'})
 if not v.get('success'): raise RuntimeError(str(v)[:1200])
 return v['value']
report={'trials':[]}
for d in api('remote-pcs')['items']:
 caps=(d.get('env') or {}).get('android_control') or {}
 if not d.get('connected') or caps.get('contract')!=1 or (d.get('phone_update') or {}).get('current_version') != 24: continue
 if len(sys.argv)>1 and d['alias']!=sys.argv[1]: continue
 for i in range(3):
  for mode in (['python','control'] if i%2==0 else ['control','python']):
   plan=driver.prepare({'request':{'action':'volume_status','stream':'music'},'source':source,'native_control':caps if mode=='control' else {}})
   assert plan['transport']==mode, 'installed hashes do not match'
   command={'limb':d['device_id'],'op':mode,'timeout':20,'background':True,'request_id':plan['request_id']}
   command['inputs' if mode=='control' else 'code']=plan['inputs' if mode=='control' else 'code']
   start=time.monotonic()
   accepted=ibl('return [limbs:guestpc]'+json.dumps(command,ensure_ascii=False));ref=accepted.get('task_ref')
   if not ref: raise RuntimeError(str(accepted)[:1000])
   observed=ibl('return [self:task]'+json.dumps({'op':'wait','ref':ref,'timeout':60}));elapsed=time.monotonic()-start
   result=observed.get('result') or {};value=result.get('value') or {}
   row={'alias':d['alias'],'mode':mode,'round':i+1,'wall_seconds':round(elapsed,3),'elapsed_ms':result.get('elapsed_ms'),'state':observed.get('state'),'verified':value.get('verified'),'execution_mode':result.get('execution_mode'),'task_ref':ref}
   report['trials'].append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
   (OUT/('acceptance-'+(sys.argv[1] if len(sys.argv)>1 else 'all')+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
   if observed.get('state')!='succeeded' or value.get('verified') is not True:
    (OUT/'acceptance-unexpected.json').write_text(json.dumps(observed,ensure_ascii=False,indent=2));raise RuntimeError('verification failed; no resubmission')
 start=time.monotonic()
 public=ibl('return [fn:Android제어]'+json.dumps({'대상':d['device_id'],'요청':{'action':'volume_status','stream':'music'}},ensure_ascii=False))
 (OUT/('public-'+d['device_id']+'.json')).write_text(json.dumps(public,ensure_ascii=False,indent=2))
 print(json.dumps({'alias':d['alias'],'public_status':public.get('status'),'verified':public.get('verified'),'wall_seconds':round(time.monotonic()-start,3)},ensure_ascii=False),flush=True)
 if not public.get('verified'): raise RuntimeError('public verification failed')
if not report['trials']: print('No connected updated devices; no commands submitted',flush=True)
