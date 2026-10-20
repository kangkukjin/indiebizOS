"""Capture only this rehearsal's evidence; raw payloads stay outside Git."""
import collections,json,sqlite3,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5];OUT=ROOT/'outputs/long_sentence_imagination/2026-10-20_83회차';DOC=ROOT/'docs/experiments/long_sentence_imagination/round_83'
c=sqlite3.connect(f'file:{ROOT}/data/world_pulse.db?mode=ro',uri=True);c.row_factory=sqlite3.Row
accepted={json.loads(p.read_text())['task_id']:p.stem.removesuffix('_accepted') for p in (OUT/'runs').glob('*_accepted.json')}
summary=[]
for task,label in accepted.items():
 ep=c.execute('select * from episode_log where task_id=?',(task,)).fetchone()
 if not ep:continue
 ep=dict(ep);folder=OUT/'evidence'/label;folder.mkdir(parents=True,exist_ok=True)
 events=[dict(r) for r in c.execute('select * from trajectory_event where episode_id=? order by ts,event_seq',(ep['id'],))]
 for e in events:e['data']=json.loads(e['data'])
 (folder/'events.json').write_text(json.dumps(events,ensure_ascii=False,indent=2))
 (folder/'episode.json').write_text(json.dumps(ep,ensure_ascii=False,indent=2))
 cost=collections.defaultdict(lambda:collections.Counter());calls=[];stores=set()
 for event in events:
  d=event['data'];kind=event['kind']
  if kind=='model.usage' and d.get('accounting')=='billable_usage':
   for key in ['input','output','cache_read','cache_create']:cost[d.get('role','unknown')][key]+=d.get(key,0) or 0
   cost[d.get('role','unknown')]['usage_events']+=1
  if kind=='supervision.tool.started':
   payload=d.get('input',{});text=payload.get('excerpt','');p=Path(d.get('store',''))/(payload.get('id','')+'.txt')
   if p.is_file():text=p.read_text()
   calls.append({'name':d.get('name'),'input':text,'time':d.get('time')})
  if d.get('store'):stores.add(d['store'])
 for i,store in enumerate(sorted(stores)):
  source=Path(store)
  if source.is_dir():shutil.copytree(source,folder/f'store_{i}',dirs_exist_ok=True)
 (folder/'calls.json').write_text(json.dumps(calls,ensure_ascii=False,indent=2))
 forbidden=[]
 for call in calls:
  text=call['input']
  if any(s in text for s in ['/trainer/','/harness/','round_83/task.md','LONG_SENTENCE_PURCHASE_FOLLOWUP']):forbidden.append(call)
 summary.append({'label':label,'episode':ep['id'],'task_id':task,'total_ms':ep['total_ms'],'agent':ep['agent'],'started_at':ep['started_at'],'ended_at':ep['ended_at'],'cost':dict(cost),'tool_calls':len(calls),'model_round_events':sum(e['kind']=='model.round' for e in events),'forbidden_access_candidates':len(forbidden)})
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False,indent=2))
p=sqlite3.connect(f'file:{ROOT}/projects/L83_training/conversations.db?mode=ro',uri=True);p.row_factory=sqlite3.Row
for t in ['conversation_turns','conversation_sessions','conversation_task_links','messages']:
 (OUT/(t+'.json')).write_text(json.dumps([dict(r) for r in p.execute('select * from '+t)],ensure_ascii=False,indent=2))
