"""Collect bounded, non-sensitive evidence for round 63; never runs a training task."""
import json,collections,sqlite3,shutil,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]
OUT=Path(os.environ.get('R63_OUT',str(ROOT/'outputs/long_sentence_imagination/2026-10-13_63회차'))).resolve()
DOC=ROOT/'docs/experiments/long_sentence_imagination/round_63';EV=DOC/'evidence';EV.mkdir(exist_ok=True)
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=1,default=str))
runs=[]
for label in ['record_check','record_check2','record_check3','record_base','record_base_v3','resume_base','change_variant']:
    p=OUT/'runs'/f'{label}.json'
    if not p.exists():continue
    r=json.loads(p.read_text());u=r.get('usage') or {};m=u.get('model') or {}
    runs.append({'label':label,'mode':r.get('mode'),'status':r.get('status'),'success':r.get('success'),'executed':r.get('executed'),'error':(r.get('error') or '')[:300],'issues':[(i['code'],i['location']['line']) for i in r.get('issues',[])],'usage':{k:u.get(k) for k in ('steps','rows','elapsed_ms')},'model':{k:m.get(k) for k in ('requests','input','output','cache_read','cache_create')},'run_id':(r.get('resume') or {}).get('run_id'),'response_bytes':p.stat().st_size})
write(EV/'trainer_runs.json',runs)
c=sqlite3.connect('file:'+str(ROOT/'data/world_pulse.db')+'?mode=ro',uri=True)
agents=[]
for label,status_file in [('feedback56_base','feedback56/status_a348e83f.json'),('feedback56_variant','feedback56/status_c5d40358.json'),('agent_base','agent/status_base.json'),('agent_resume','agent/status_resume.json'),('agent_change','agent/status_change.json'),('agent_change_post_repair','agent/status_change2.json')]:
    p=OUT/status_file
    if not p.exists():continue
    st=json.loads(p.read_text());rid=st.get('run_id')
    ep=c.execute('select id,started_at,ended_at,total_ms,source from episode_log where run_id=?',(rid,)).fetchone()
    usage=[];started=[];finished=[];cost=None
    for kind,raw in c.execute('select kind,data from trajectory_event where run_id=? order by event_seq',(rid,)):
        d=json.loads(raw)
        if kind=='model.usage' and d.get('accounting')=='billable_usage':usage.append(d)
        elif kind=='supervision.tool.started':started.append(d)
        elif kind=='supervision.tool.finished':finished.append(d)
        elif kind=='supervision.cost.summary':cost={k:v for k,v in d['cost'].items() if not k.endswith('_path')}
    agents.append({'case':label,'task_id':(st.get('task_ref') or {}).get('task_id'),'state':st.get('state'),'pending_children':st.get('pending_children'),'run_id':rid,'episode':ep,'model_calls':len(usage),'totals':{k:sum(r.get(k,0) for r in usage) for k in ('input','output','cache_read','cache_create')},'tools':dict(collections.Counter(x['name'] for x in finished)),'tool_ids':len(finished),'failed_tools':[{'name':x['name'],'check_rejected':x.get('check_rejected'),'excerpt':(x.get('evidence',{}).get('excerpt','') or '')[:400]} for x in finished if x.get('is_error') or x.get('check_rejected')],'cost':cost})
write(EV/'agent_runs.json',agents)
for src,dst in [('start.json','start.json'),('papers/pdf_index.json','pdf_index.json'),('trainer/out/record.json','trainer_record.json'),('trainer/out/record.md','trainer_record.md'),('trainer/out/resume.json','trainer_resume.json'),('trainer/out/change.json','trainer_change.json'),('runs/history.json','question_history.json'),('runs/op_close_q2.json','operator_close_q2.json'),('runs/obsC_send.json','observation_c_send.json'),('runs/obsC_result.json','observation_c_result.json'),('feedback56/evidence.json','feedback56_evidence.json'),('runs/post_attach.json','post_repair_attach_send.json'),('runs/post_checks2.json','post_repair_checks.json'),('runs/training_ended.time','training_ended.time')]:
    p=OUT/src
    if p.exists():shutil.copy2(p,EV/dst)
for name in ['resume.md','change.md','record.md','report.md']:
    p=OUT/'agent/out'/name
    if p.exists():shutil.copy2(p,EV/f'agent_{name}')
print({'trainer_runs':len(runs),'agent_runs':len(agents)})
