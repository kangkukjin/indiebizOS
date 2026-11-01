"""실제 의식·감독·계획 저장을 분리 호출한다. 결과 판정은 모델에 주지 않는다."""
import contextlib,hashlib,json,sys,time,traceback,os
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime
H=Path(__file__).resolve().parent;ROOT=H.parents[3]
OUT=ROOT/'outputs/long_sentence_imagination/2026-11-01_108회차'
sys.path.insert(0,str(ROOT/'backend'))
import boot_paths
from consciousness_agent import ConsciousnessAgent
from conscious_supervisor import Supervisor
from model_resolver import resolve
from model_call_context import capture_usage,summarize_usage
from episode_logger import EpisodeLogger
from thread_context import actor_context

CASES=json.loads((H/'cases.json').read_text())
META=json.loads((H/'start.json').read_text())
assert hashlib.sha256((H/'cases.json').read_bytes()).hexdigest()==META['cases_sha256']
DEADLINE=datetime.fromisoformat(META['deadline']).timestamp()
SELECT=sys.argv[1:] or [x['id'] for x in CASES]

def dump(path,value):
 path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def forbidden(name,args,**kw):
 raise RuntimeError('계획 단계 분리 시험: 실행자 도구가 연결되지 않았습니다')

for case in CASES:
 if case['id'] not in SELECT:continue
 directory=OUT/(case['id']+os.environ.get('LS108_ATTEMPT_SUFFIX',''));directory.mkdir(exist_ok=False)
 workspace=OUT/case['previous'] if case.get('previous') else directory
 if time.time()+150>DEADLINE:raise RuntimeError('회차 상한 잔여 부족: 새 모델 호출 중단')
 record={'id':case['id'],'started':time.time(),'status':'running','origin':'training','workspace':str(workspace),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
 dump(directory/'receipt.json',record)
 previous=None;history=[]
 if case.get('previous'):
  prior=next(c for c in CASES if c['id']==case['previous'])
  previous_result=json.loads((OUT/prior['id']/'framing.json').read_text())
  previous=previous_result.get('_research_plan')
  history=[{'role':'user','content':prior['request']},{'role':'assistant','content':json.dumps(previous_result,ensure_ascii=False)}]
 task='training_ls108_'+directory.name;agent_id='ls108_'+directory.name
 controller=None
 with (directory/'console.log').open('w') as log,contextlib.redirect_stdout(log),contextlib.redirect_stderr(log),actor_context(agent_id=agent_id,task_id=task,origin='training'),capture_usage() as usage:
  EpisodeLogger.start_episode('상상훈련108 '+case['id'],case['request'],task_id=task)
  record['episode_id']=EpisodeLogger.current().episode_id
  try:
   agent=ConsciousnessAgent()
   descriptor=resolve('consciousness')
   record['model']={k:descriptor.get(k) for k in ['provider','model','tier','source']}
   ai=SimpleNamespace(agent_id=agent_id,project_path=str(workspace),tools=[],_custom_execute_tool=forbidden)
   controller=Supervisor(SimpleNamespace(ai=ai),case['request'],history,agent_id,task,directory=directory/'supervision')
   real_plan=controller.plan
   calls=[]
   def observed_plan(prompt,system_prompt,revision=None,*,completion=False):
    i=len(calls);entry={'index':i,'phase':'plan_completion' if completion else 'plan','started':time.time(),'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'system_sha256':hashlib.sha256(system_prompt.encode()).hexdigest()};calls.append(entry)
    (directory/f'call_{i}_input.txt').write_text(prompt)
    (directory/f'call_{i}_system.txt').write_text(system_prompt)
    dump(directory/'calls.json',calls)
    raw=real_plan(prompt,system_prompt,revision,completion=completion)
    (directory/f'call_{i}_response.txt').write_text(raw)
    entry.update(ended=time.time(),response_sha256=hashlib.sha256(raw.encode()).hexdigest())
    dump(directory/'calls.json',calls)
    return raw
   controller.plan=observed_plan
   result=agent.process(case['request'],history,'',agent_name='연구계획 훈련',agent_role='사용자 요청에 맞게 문제·목적·연구계획을 구성한다.',supervisor=controller,project_path=str(workspace),previous_research_plan=previous)
   if result is None:raise RuntimeError('의식 결과 None')
   dump(directory/'framing.json',result)
   if result.get('_research_plan'):
    receipt=result['_research_plan'];body=Path(receipt['path']).read_text()
    assert body==receipt['body'] and hashlib.sha256(body.encode()).hexdigest()==receipt['sha256']
    (directory/'research_plan.md').write_text(body)
   record.update(status='completed',calls=len(calls),has_plan=bool(result.get('_research_plan')),deep_research=result.get('deep_research'),needs_clarification=result.get('needs_clarification'))
  except Exception as exc:
   record.update(status='failed',error=str(exc),traceback=traceback.format_exc())
  finally:
   if controller:
    record['controller_usage']=controller.usage
    controller.close()
   record['usage']=summarize_usage(usage)
   record['ended']=time.time();record['seconds']=record['ended']-record['started'];dump(directory/'receipt.json',record)
   EpisodeLogger.end_episode()
 print(json.dumps({k:record.get(k) for k in ['id','status','seconds','calls','has_plan','deep_research','needs_clarification','error']},ensure_ascii=False),flush=True)
