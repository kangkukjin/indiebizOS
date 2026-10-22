"""Read-only evidence audit for the repair replay, scoped to accepted task IDs."""
import collections
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/('outputs/long_sentence_imagination/2026-10-22_88회차_repair'+(sys.argv[1] if len(sys.argv)>1 and sys.argv[1]!='1' else ''))

def main():
    db=sqlite3.connect(f'file:{ROOT/"data/world_pulse.db"}?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    summaries=[]
    for accepted in sorted((OUT/'runs').glob('T*_accepted.json')):
        turn=accepted.name.split('_')[0]
        tid=json.loads(accepted.read_text())['task_id']
        episodes=[dict(r) for r in db.execute('select id,total_ms,ended_at from episode_log where task_id=?',(tid,))]
        usage=collections.defaultdict(collections.Counter);tools=[];planning=[];evaluations=[];sessions=[];events=[];models=set()
        for ep in episodes:
            log=db.execute('select log from episode_log where id=?',(ep['id'],)).fetchone()[0] or ''
            sessions += [line for line in log.splitlines() if 'call: session=' in line]
            for row in db.execute('select event_seq,kind,data from trajectory_event where episode_id=? order by event_seq',(ep['id'],)):
                d=json.loads(row['data']);kind=row['kind']
                if kind=='model.usage' and d.get('accounting')=='billable_usage':
                    models.add((d.get('role'),d.get('model'),d.get('provider'),d.get('source')))
                    for key in ('input','output','cache_read','cache_create'):
                        if isinstance(d.get(key),(int,float)):usage[d.get('role','unknown')][key]+=d[key]
                if kind=='supervision.tool.started':
                    ref=d.get('input',{});file=Path(d['store'])/(ref['id']+'.txt')
                    item={'id':d['id'],'name':d.get('name'),'episode':ep['id'],'seq':row['event_seq'],'input_ref':ref['id']}
                    if file.is_file():
                        raw=file.read_text();item['input']=json.loads(raw);item['full_input']=True
                        item['stored_bytes_sha256']=hashlib.sha256(file.read_bytes()).hexdigest()
                    else:item['input']=ref.get('excerpt');item['full_input']=False
                    tools.append(item)
                if kind=='supervision.tool.supervisor':
                    ref=d.get('input',{});file=Path(d['store'])/(ref['id']+'.txt')
                    item={'episode':ep['id'],'seq':row['event_seq'],'role':d.get('role'),'operation':d.get('operation'),'input_ref':ref['id']}
                    if file.is_file():
                        item.update(input=json.loads(file.read_text()),full_input=True,stored_bytes_sha256=hashlib.sha256(file.read_bytes()).hexdigest())
                    else:item.update(input=ref.get('excerpt'),full_input=False)
                    planning.append(item)
                if kind=='supervision.evaluation.finished':evaluations.append(d['decision'])
                if kind in ('supervision.framing','supervision.tool.started','supervision.tool.finished','supervision.tool.supervisor','supervision.evaluation.finished','model.usage','context.compacted'):
                    events.append({'episode':ep['id'],'seq':row['event_seq'],'kind':kind,'data':d})
        (OUT/'runs'/f'{turn}_events.json').write_text(json.dumps(events,ensure_ascii=False,indent=2))
        (OUT/'runs'/f'{turn}_tool_inputs.json').write_text(json.dumps(tools,ensure_ascii=False,indent=2))
        (OUT/'runs'/f'{turn}_planning_tool_inputs.json').write_text(json.dumps(planning,ensure_ascii=False,indent=2))
        assert len(tools)==len({x['id'] for x in tools})
        summaries.append({'turn':turn,'task_id':tid,'episodes':episodes,'usage':dict(usage),'tool_count':len(tools),
            'full_tool_inputs':sum(x['full_input'] for x in tools),'sessions':sessions,'evaluations':evaluations,
            'planning_tool_count':len(planning),'full_planning_inputs':sum(x['full_input'] for x in planning),
            'models':[dict(zip(('role','model','provider','source'),m)) for m in sorted(models,key=str)],
            'context_compacted':sum(x['kind']=='context.compacted' for x in events)})
    preservation=[]
    for snap in sorted((OUT/'snapshots').glob('T*')):
        changed=[];count=0
        for p in snap.rglob('*'):
            if not p.is_file():continue
            count+=1;rel=p.relative_to(snap);current=OUT/'ai'/rel
            if not current.is_file() or p.read_bytes()!=current.read_bytes():changed.append(str(rel))
        preservation.append({'turn':snap.name,'files':count,'changed':changed})
    report={'turns':summaries,'preservation':preservation}
    (OUT/'runs/repair_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    for s in summaries:
        print(s['turn'],[e['id'] for e in s['episodes']],s['tool_count'],sum(u['input'] for u in s['usage'].values()),sum(u['output'] for u in s['usage'].values()))
    print('changed prior files',sum(len(x['changed']) for x in preservation))

if __name__=='__main__':main()
