"""Preserve repair outputs, terminal events and costs without model reasoning."""
import collections
import hashlib
import json
import re
import shutil
import sqlite3
from pathlib import Path
from transport import ROOT, DOC, OUT

REPAIR = OUT / 'repair'
DEST = DOC / 'repair'


def dump(name, value):
    path = DEST / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if name == 'evidence/runs.json':
        path.write_text('{\n' + ',\n'.join('  '+json.dumps(k)+': '+json.dumps(v,ensure_ascii=False)
                                             for k,v in value.items()) + '\n}\n')
    else:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2))


def collect():
    con = sqlite3.connect(f'file:{ROOT}/data/world_pulse.db?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    metrics = {}
    for stage in ('base', 'variant'):
        submitted = json.loads((OUT/'runs'/f'repair_ai_{stage}_start.json').read_text())
        task = submitted['response']['task_id']
        row = con.execute('select id,task_id,started_at,ended_at,total_ms from episode_log where task_id=?', (task,)).fetchone()
        if not row:
            continue
        totals, roles, tools, evaluations, cost, actions = collections.Counter(), {}, [], [], {}, []
        for event in con.execute('select kind,data from trajectory_event where episode_id=? order by event_seq', (row['id'],)):
            kind, data = event['kind'], json.loads(event['data'])
            if kind == 'model.usage' and data.get('accounting') == 'billable_usage':
                values = {k: int(data.get(k, 0) or 0) for k in ('input','output','cache_read','cache_create')}
                totals.update(values)
                roles.setdefault(data.get('role','')+':'+data.get('phase',''), collections.Counter()).update(values)
            elif kind == 'supervision.tool.started':
                tools.append(data.get('name'))
                ref = data.get('input', {}).get('id')
                path = Path(data['store'])/(str(ref)+'.txt')
                if path.is_file():
                    request = json.loads(path.read_text())
                    # Exact source code is enough to audit reuse; do not save full historical results.
                    actions.append({'name':data.get('name'), 'code':request.get('code'),
                                    'command':request.get('command') if data.get('name')=='Bash' else None})
            elif kind == 'supervision.evaluation.finished':
                evaluations.append({k:data[k] for k in ('decision','elapsed_s','seq') if k in data})
            elif kind == 'supervision.cost.summary':
                cost = data.get('cost', {})
        metrics[stage] = dict(episode=dict(row),totals=dict(totals),roles={k:dict(v) for k,v in roles.items()},
                              tools=tools,evaluations=evaluations,cost=cost)
        dump(f'evidence/{stage}_calls.json', actions)
    dump('evidence/ai_metrics.json', metrics)
    runs = {}
    for path in sorted((OUT/'runs').glob('repair_*.json')):
        raw=json.loads(path.read_text());response=raw['response']
        runs[path.stem] = {k:response.get(k) for k in ('success','run_status','resume','error','http_error','diagnostic','usage') if k in response}
        runs[path.stem]['wall_s']=raw['ended']-raw['started']
        runs[path.stem]['actions']=[e.get('action') for e in response.get('evidence',[]) if e.get('kind')=='invoke']
    dump('evidence/runs.json',runs)
    before=json.loads((REPAIR/'before_variant.json').read_text())
    preservation={}
    for name,expected in before.items():
        path=Path(name)
        current={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'mtime_ns':path.stat().st_mtime_ns}
        preservation[name]={'unchanged':current==expected, 'before':expected,'after':current}
    dump('evidence/preservation.json',preservation)
    for group in ('trainer/base','trainer/variant','trainer/base_v2','trainer/variant_v2','ai/base','ai/variant'):
        for name in ('research.md','source_notes.md','evidence.json','decision.md'):
            source=REPAIR/group/name
            if source.exists():
                target=DEST/'artifacts'/group/name
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,target)
                if target.suffix == '.md':
                    # 빈 줄의 들여쓰기만 제거한다. 문장·Markdown 줄바꿈은 보존.
                    target.write_text(re.sub(r'(?m)^[ \t]+$', '', target.read_text()))
    if (REPAIR/'semantic_evaluations.json').exists():
        dump('evidence/semantic_evaluations.json',json.loads((REPAIR/'semantic_evaluations.json').read_text()))
    print(json.dumps({k:{'episode':v['episode'],'evaluations':len(v['evaluations']),'totals':v['totals']} for k,v in metrics.items()},ensure_ascii=False))


if __name__ == '__main__':
    collect()
