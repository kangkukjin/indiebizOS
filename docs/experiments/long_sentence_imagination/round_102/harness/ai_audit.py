from api import *
import sqlite3,collections
expected=json.loads((BASE/'harness/expected.json').read_text());a=json.loads((BASE/'ai/report.json').read_text())
assert a['total_cost']==expected['total_cost'] and a['hold_count']==expected['hold_count']
checks=0
for x,y in zip(a['libraries'],expected['libraries']):
 assert x['library']==y['library'] and x['ready']==y['ready'] and x['total_cost']==y['total_cost']
 rows={z['item']:z for z in x['lines']}
 for z in y['lines']:
  for k,v in z.items():
   got=rows[z['item']][k]
   if k=='status' and got=='confirmed':got='ready'
   assert got==v,(y['library'],z['item'],k,got,v)
   checks+=1
ledger=[json.loads(s) for s in (BASE/'ai/dispatch.jsonl').read_text().splitlines()];assert len(ledger)==2
c=sqlite3.connect('file:'+str(ROOT/'data/world_pulse.db')+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
rows=[dict(r) for r in c.execute('select * from trajectory_event where episode_id=5576 order by event_seq')]
for r in rows:
 try:r['data']=json.loads(r['data'])
 except Exception:pass
(BASE/'harness/ai_trajectory.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
usage=[r for r in rows if r['kind']=='model.usage'];print('usage sample',str(usage[:1])[:1300])
counts=collections.Counter(r['kind'] for r in rows)
# Preserve observed accesses for manual isolation review; do not infer absence from missing logs.
selected=[r for r in rows if r['kind'] in ['supervision.tool.started','supervision.tool.finished','recall.presented','recall.used','context.compacted','model.usage','supervision.cost.summary']]
(BASE/'harness/ai_selected_events.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2))
audit={'checks':checks,'line_count':600,'dispatch_count':2,'total_cost':a['total_cost'],'hold_count':a['hold_count'],'episode':5576,'counts':dict(counts)}
(BASE/'harness/ai_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2));print(audit)
