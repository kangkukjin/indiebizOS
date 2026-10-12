"""Collect bounded, non-sensitive evidence; this never runs a training task."""
import collections,json,shutil,sqlite3
from pathlib import Path
from prepare import ROOT,OUT,DOC,write

evidence=DOC/'evidence';evidence.mkdir(exist_ok=True)
labels=['prepare','audit_base','audit_variant','audit_order','prepare_fixed','repair_base','repair_v2_base','repair_variant','repair_boundary','repair_order']
runs=[]
for label in labels:
    r=json.loads((OUT/'runs'/f'{label}.json').read_text())
    reuse=r.get('reuse',{});usage=r.get('usage',{})
    value=r.get('value',{})
    if label.startswith('prepare'):
        value={k:v for k,v in value.items() if k!='candidates'}
    runs.append({'label':label,'success':r.get('success'),'source_complete':r.get('source_complete'),'run_status':r.get('run_status'),'run_id':r.get('resume',{}).get('run_id'),'value':value,'usage':{k:usage[k] for k in ('steps','rows','elapsed_ms','model') if k in usage},'reuse':{'reused_calls':reuse.get('reused_calls',0),'model_calls':reuse.get('model_calls',0),'skipped_reasons':dict(collections.Counter(x['reason'] for x in reuse.get('skipped',[])))},'response_bytes':(OUT/'runs'/f'{label}.json').stat().st_size})
write(evidence/'trainer_runs.json',runs)
c=sqlite3.connect('file:'+str(ROOT/'data/world_pulse.db')+'?mode=ro',uri=True)
agents=[]
for label,rid in [('base','run_92907237cd57c4cead37'),('variant','run_22030ccec25f52845330')]:
    episode=c.execute('select id,started_at,ended_at,total_ms,task_id,source from episode_log where run_id=?',(rid,)).fetchone()
    usage=[];finished=[];started=[];cost=None
    for kind,raw in c.execute('select kind,data from trajectory_event where run_id=? order by event_seq',(rid,)):
        d=json.loads(raw)
        if kind=='model.usage' and d.get('accounting')=='billable_usage':usage.append(d)
        elif kind=='supervision.tool.finished':finished.append(d)
        elif kind=='supervision.tool.started':started.append(d)
        elif kind=='supervision.cost.summary':cost={k:v for k,v in d['cost'].items() if not k.endswith('_path')}
    assert {x['id'] for x in started}=={x['id'] for x in finished}
    status=json.loads((OUT/'runs'/f'agent_{label}_status.json').read_text())
    assert status['state']=='succeeded' and status['pending_children']==0
    agents.append({'case':label,'run_id':rid,'episode':dict(zip(['id','started_at','ended_at','total_ms','task_id','source'],episode)),'state':status['state'],'children':status['children'],'usage':usage,'totals':{k:sum(r.get(k,0) for r in usage) for k in ('input','output','cache_read','cache_create')},'tools':dict(collections.Counter(x['name'] for x in finished)),'tool_ids':[x['id'] for x in finished],'failed_tools':[{'id':x['id'],'name':x['name'],'check_rejected':x.get('check_rejected'),'excerpt':x.get('evidence',{}).get('excerpt','')[:1600]} for x in finished if x.get('is_error') or x.get('check_rejected')],'cost':cost})
write(evidence/'agent_runs.json',agents)
for name in ['start.json','input_hashes.json']:
    shutil.copy2(OUT/name,evidence/name)
for name in ['agent_base_status.json','agent_variant_status.json','training_ended_health.json']:
    shutil.copy2(OUT/'runs'/name,evidence/name)
for p in (OUT/'runs').glob('verify_*.json'):shutil.copy2(p,evidence/p.name)
for source,target in [('agent/base_snapshot/task.md','agent_task.md'),('agent/base_snapshot/report.md','agent_base_report.md'),('agent/out/report_variant.md','agent_variant_report.md')]:
    shutil.copy2(OUT/source,evidence/target)
write(evidence/'source_index.json',json.loads((OUT/'source/history/index.json').read_text()))
print({'trainer_runs':len(runs),'agent_runs':len(agents),'directory':str(evidence)})
