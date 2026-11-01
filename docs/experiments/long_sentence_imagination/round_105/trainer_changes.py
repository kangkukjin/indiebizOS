import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[4]/'backend'))
import boot_paths
import harness as h
import json,shutil
b=h.OUT/'trainer'
def run(label,code,inputs=None):
    result=h.child(b,{'code':code,'inputs':inputs or {}})
    h.dump(h.OUT/(label+'.json'),result)
    print(label,result.get('success'),str(result.get('error',''))[:240],str(result.get('value',''))[:300])
    return result
# Original program and its business output are frozen before any changed conditions.
shutil.copyfile(b/'outputs/report.json',h.OUT/'trainer_main_report.json')
for kind,target in [('script','LS105Normalize'),('idiom','LS105Reconcile')]:
    run('trainer_remove_protected_'+kind,'[fn:능력변경완료]{요청:$r}',{'r':{'kind':kind,'operation':'remove','target':target}})
request=json.loads((h.OUT/'trainer_request_v0.json').read_text())['inputs']['reconcile_request']
request.update(operation='update',code=request['code'].replace('$tolerance=0','$tolerance=500'))
# Deliberately stale expected value: real publication succeeds, post-publication probe fails.
p=run('trainer_change_plan','[self:script]{id:"능력변경",args:{op:"plan",request:$r}}',{'r':request})
plan=p['value']['plan']; program=p['value']['program']
failed=run('trainer_postsave_failure',program)
status=run('trainer_postsave_status','[self:script]{id:"능력변경",args:{op:"status",plan:$p}}',{'p':plan})
probe=request['probes'][0];probe['expected']['mismatches']=0
verified=run('trainer_verify_plan','[self:script]{id:"능력변경",args:{op:"verify",plan:$p,probes:$probes}}',{'p':plan,'probes':[probe]})
if verified.get('success'):
    finish=run('trainer_verify_only',verified['value']['program'])
    after=run('trainer_verify_status','[self:script]{id:"능력변경",args:{op:"status",plan:$p}}',{'p':plan})
    h.dump(h.OUT/'trainer_recovery_assertions.json',{'postsave_failed':failed.get('success') is False,'published_matches':status.get('value',{}).get('matches'),'verify_complete':finish.get('value',{}).get('complete'),'same_revision':status.get('value',{}).get('revision')==after.get('value',{}).get('revision')})
