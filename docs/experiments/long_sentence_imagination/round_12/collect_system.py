"""Read-only episode accounting; never adds cumulative cost summaries twice."""
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
number,episode=map(int,sys.argv[1:3])
c=sqlite3.connect(f'file:{ROOT}/data/world_pulse.db?mode=ro',uri=True)
c.row_factory=sqlite3.Row
row=dict(c.execute('select id,started_at,ended_at,total_ms,source,run_id from episode_log where id=?',(episode,)).fetchone())
assert row['ended_at'], 'Training still running; do not apply repairs'
counts=Counter();usage=Counter();errors=[];cost={};models=set()
for e in c.execute('select kind,data from trajectory_event where episode_id=? order by event_seq',(episode,)):
    kind=e['kind'];d=json.loads(e['data']);counts[kind]+=1
    if kind=='model.usage' and d.get('accounting')=='billable_usage':
        usage.update({k:d.get(k,0) or 0 for k in ('input','output','cache_read','cache_create')})
        models.add(d.get('model','unknown'))
    if kind=='supervision.cost.summary':
        cost={k:v for k,v in d.get('cost',{}).items() if k not in ('events_path',)}
    if kind=='supervision.tool.finished' and (d.get('check_rejected') or d.get('is_error')):
        errors.append({k:d.get(k) for k in ('tool_name','check_rejected','is_error','elapsed_s')})
row.update(usage=dict(usage),models=sorted(models),event_counts=dict(counts),cost=cost,errors=errors,
           token_scope='billable_usage events only; cache is part of input; author tokens unmeasured')
path=ROOT/f'docs/experiments/long_sentence_imagination/round_{number}/system_evidence.json'
path.write_text(json.dumps(row,ensure_ascii=False,indent=2));print(json.dumps(row,ensure_ascii=False))
