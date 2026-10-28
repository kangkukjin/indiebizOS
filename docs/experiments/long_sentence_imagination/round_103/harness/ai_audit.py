from run_region import ROOT,B1,B2
import json,hashlib,sqlite3,collections
expected=json.loads((B1/'harness/variant_expected.json').read_text());raw=json.loads((B2/'ai/plan.json').read_text());actual=raw['scenarios'];checks=0
for mode in ['base','with_transfer']:
 for policy in ['deadline','budget']:
  a=actual[mode][policy];e=expected[mode][policy];assert a['total_cost']==e['total_cost']
  libs={r['library']:r for r in a['libraries']}
  for y in e['libraries']:
   x=libs[y['library']];assert x['total_cost']==y['total_cost'] and x['over_budget']==y['over_budget']
   rows={r['item']:r for r in x['lines']};assert len(rows)==len(y['lines'])
   for row in y['lines']:
    for k,v in row.items():
     got=rows[row['item']][k]
     if k=='status' and got=='selected':got='ready'  # documented proposal label
     if k=='status' and got=='transfer':
      assert rows[row['item']]['shortage']==0 and rows[row['item']]['transfer_in']>0
      got='stock'  # inventory after allowed transfer covers demand
     assert got==v,(mode,policy,y['library'],row['item'],k,got,v)
     checks+=1
assert raw['transfer_cost']==expected['transfer_cost'];assert [{k:r[k] for k in ['item','from','to','quantity','cost']} for r in raw['transfers']]==expected['transfers']
assert raw['recommendation']['grand_total']==459330
for p in (B2/'harness').glob('prior_*_ledger.json'):
 old=json.loads(p.read_text());assert hashlib.sha256(__import__('pathlib').Path(old['path']).read_bytes()).hexdigest()==old['sha256']
with sqlite3.connect('file:'+str(ROOT/'data/world_pulse.db')+'?mode=ro',uri=True) as c:
 c.row_factory=sqlite3.Row;events=[dict(r) for r in c.execute('select * from trajectory_event where episode_id=5577 order by event_seq')]
for e in events:
 try:e['data']=json.loads(e['data'])
 except (TypeError,ValueError):pass
(B2/'harness/ai_trajectory.json').write_text(json.dumps(events,ensure_ascii=False,indent=2))
usage=[e for e in events if e['kind']=='model.usage'];(B2/'harness/ai_usage.json').write_text(json.dumps(usage,ensure_ascii=False,indent=2))
selected=[e for e in events if e['kind'] in ['supervision.tool.started','supervision.tool.finished','recall.presented','recall.used','context.compacted','supervision.cost.summary']];(B2/'harness/ai_selected_events.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2))
audit={'checks':checks,'line_count':2400,'ledgers_unchanged':True,'total':459330,'episode':5577,'counts':dict(collections.Counter(e['kind'] for e in events))};(B2/'harness/ai_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2));print(audit)
