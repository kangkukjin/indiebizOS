"""Read-only episode evidence collection, restricted to this round's task IDs."""
import collections
import hashlib
import json
import sqlite3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'outputs/long_sentence_imagination/2026-10-22_88회차'
db=sqlite3.connect(f'file:{ROOT/"data/world_pulse.db"}?mode=ro',uri=True);db.row_factory=sqlite3.Row
summary=[]
for f in sorted((OUT/'runs').glob('T*_accepted.json')):
    turn=f.name.split('_')[0];ticket=json.loads(f.read_text());tid=ticket.get('task_id')
    eps=[dict(r) for r in db.execute('select id,source,task_id,run_id,total_ms,ended_at from episode_log where task_id=?',(tid,))]
    events=[];usage=collections.defaultdict(collections.Counter);kinds=collections.Counter();tools=[];sessions=[]
    for ep in eps:
        log=db.execute('select log from episode_log where id=?',(ep['id'],)).fetchone()[0] or ''
        sessions += [{'episode':ep['id'],'line':line} for line in log.splitlines() if 'call: session=' in line or '압축' in line or 'compact' in line.lower()]
        for row in db.execute('select event_seq,kind,data from trajectory_event where episode_id=? order by event_seq',(ep['id'],)):
            d=json.loads(row['data']);k=row['kind'];kinds[k]+=1
            if k=='model.usage' and d.get('accounting')=='billable_usage':
                role=d.get('role','unknown')
                for key in ['input','output','cache_read','cache_create']:
                    if isinstance(d.get(key),(int,float)):usage[role][key]+=d[key]
            if k=='supervision.tool.started':
                tools.append({'episode':ep['id'],'seq':row['event_seq'],**d})
            if k in ('supervision.tool.started','supervision.tool.finished','supervision.evaluation.finished','model.usage','model.input','context.compacted','recall.presented','recall.used') or 'session' in k:
                events.append({'episode':ep['id'],'seq':row['event_seq'],'kind':k,'data':d})
    (OUT/'runs'/f'{turn}_events.json').write_text(json.dumps(events,ensure_ascii=False,indent=2))
    summary.append({'turn':turn,'task_id':tid,'episodes':eps,'usage':dict(usage),'event_kinds':dict(kinds),'tool_count':len(tools),'session_observations':sessions,
      'tool_previews':[{'episode':t['episode'],'seq':t['seq'],'tool':t.get('tool') or t.get('name'),'input':str(t.get('input'))[:1300]} for t in tools]})
(OUT/'runs/episode_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
files={str(p.relative_to(OUT/'ai')):hashlib.sha256(p.read_bytes()).hexdigest() for p in (OUT/'ai').rglob('*') if p.is_file()}
(OUT/'runs/ai_file_hashes.json').write_text(json.dumps(files,ensure_ascii=False,indent=2))
for s in summary:
    print(json.dumps({k:v for k,v in s.items() if k not in ('tool_previews','event_kinds')},ensure_ascii=False))
    print('context.compacted:',s['event_kinds'].get('context.compacted',0))
