"""Read-only trajectory accounting; aggregate billable usage without double counting."""
import collections
import json
import sqlite3
from prepare import HERE,ROOT,OUT

db=sqlite3.connect(f'file:{ROOT}/data/world_pulse.db?mode=ro',uri=True);db.row_factory=sqlite3.Row
report={'token_note':'Input includes cache where provider reports it; cache_read/create shown separately, never added to input. Trainer author tokens unmeasured.', 'ai':[],'trainer':[]}
for task in ('task_sysai_87f75841','task_sysai_f5fc67c3','task_sysai_90394faa','task_sysai_e918dbb8'):
    episode=db.execute('SELECT id,source,total_ms,started_at,ended_at FROM episode_log WHERE task_id=?',(task,)).fetchone()
    events=[(r['kind'],json.loads(r['data'])) for r in db.execute('SELECT kind,data FROM trajectory_event WHERE episode_id=? ORDER BY event_seq',(episode['id'],))]
    roles={};seen=set();tools=collections.Counter();usage_total=collections.Counter()
    for kind,data in events:
        if kind=='supervision.tool.started':tools[data.get('name','unknown')]+=1
        if kind!='model.usage' or data.get('accounting')!='billable_usage':continue
        key=(data.get('call_id'),data.get('round_index'),data.get('role'))
        if key in seen:continue
        seen.add(key);role=data.get('role','unknown');r=roles.setdefault(role,collections.Counter())
        for field in ('input','output','cache_read','cache_create'):
            r[field]+=data.get(field,0) or 0;usage_total[field]+=data.get(field,0) or 0
    report['ai'].append({**dict(episode),'task_id':task,'tools':dict(tools),'usage':dict(usage_total),
        'roles':{k:dict(v) for k,v in roles.items()},
        'recall_presented':sum(k=='recall.presented' for k,_ in events),
        'recall_used':sum(k=='recall.used' for k,_ in events),
        'compactions':sum(k=='context.compacted' for k,_ in events),
        'cost':[d for k,d in events if k=='supervision.cost.summary']})
for p in sorted((OUT/'runs').glob('*.json')):
    d=json.loads(p.read_text());r=d.get('response',{})
    if 'run_status' not in r:continue
    report['trainer'].append({'label':p.stem,'wall_s':d.get('ended',0)-d.get('started',0),
        'success':r.get('success'),'run_status':r['run_status'],'run_id':r.get('resume',{}).get('run_id'),
        'usage':{k:r.get('usage',{}).get(k) for k in ('steps','rows','elapsed_ms')},'result':r.get('value')})
(HERE/'evidence/metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
for a in report['ai']:print(a['id'],a['total_ms'],a['tools'],a['usage'])
