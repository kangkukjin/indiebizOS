"""Read-only accounting and execution evidence for the exact round 38 task IDs."""
import collections
import json
import sqlite3
from pathlib import Path

from transport import ROOT, DOC, OUT

def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))


def collect():
    con = sqlite3.connect(f'file:{ROOT}/data/world_pulse.db?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    metrics, traces = {}, {}
    for stage in ('base', 'variant'):
        submitted = OUT / 'runs' / f'ai_{stage}.json'
        if not submitted.exists():
            continue
        task = json.loads(submitted.read_text())['response']['task_id']
        row = con.execute('select id,started_at,ended_at,total_ms,source,task_id from episode_log where task_id=?', (task,)).fetchone()
        if not row:
            continue
        episodes = dict(row)
        events = [(r['kind'], json.loads(r['data']), r['source']) for r in con.execute(
            'select kind,data,source from trajectory_event where episode_id=? order by event_seq', (row['id'],))]
        roles, totals = {}, collections.Counter()
        tool_calls, finished, recalls = [], [], []
        for kind, data, source in events:
            if kind == 'model.usage' and data.get('accounting') == 'billable_usage':
                role = data.get('role', 'unknown') + ':' + data.get('phase', '')
                values = {k: int(data.get(k, 0) or 0) for k in ('input', 'output', 'cache_read', 'cache_create')}
                totals.update(values)
                roles.setdefault(role, collections.Counter()).update(values)
            elif kind == 'supervision.tool.started':
                saved = data.get('input', {})
                path = Path(data['store']) / (saved.get('id', '') + '.txt')
                raw = path.read_text() if path.is_file() else saved.get('excerpt', '')
                try:
                    request = json.loads(raw)
                except json.JSONDecodeError:
                    request = {'unparsed_excerpt': raw}
                tool_calls.append(dict(id=data.get('id'), name=data.get('name'), request=request,
                                       source=source, ts=data.get('time')))
            elif kind == 'supervision.tool.finished':
                finished.append({k: data.get(k) for k in ('check_rejected', 'success', 'elapsed_s', 'evidence')})
            elif kind in ('recall.presented', 'recall.used'):
                recalls.append(dict(kind=kind, data=data))
        metrics[stage] = dict(episode=episodes, totals=dict(totals), roles={k: dict(v) for k, v in roles.items()},
            tools=len(tool_calls), check_rejections=sum(bool(d.get('check_rejected')) for d in finished),
            compressed=sum(kind == 'context.compacted' for kind, _, _ in events),
            evaluations=sum(kind == 'supervision.evaluation.finished' for kind, _, _ in events),
            event_sources=sorted({source for _, _, source in events}),
            models=sorted({d.get('provider','')+'/'+d.get('model','') for k,d,_ in events if k=='model.usage'}))
        traces[stage] = dict(task_id=task, episode_id=row['id'], tools=tool_calls, results=finished, recall=recalls)
    trainer = {}
    for label in sorted(p.stem for p in (OUT / 'runs').glob('*.json') if not p.stem.startswith('ai_')):
        path = OUT / 'runs' / (label + '.json')
        if not path.exists():
            continue
        raw = json.loads(path.read_text())
        result = raw['response']
        actions = [e for e in result.get('evidence', []) if e.get('kind') == 'invoke' and 'action' in e]
        trainer[label] = dict(wall_s=raw['ended']-raw['started'],
            ok=result.get('success', result.get('ok')), run_status=result.get('run_status'),
            resume=result.get('resume'), usage={k: result.get('usage', {}).get(k)
                for k in ('steps', 'rows', 'elapsed_ms', 'limits', 'model')}, issues=result.get('issues', []),
            actions=[dict(action=e['action'], targets=e.get('targets')) for e in actions],
            recording_count=len(result.get('recordings', [])), error=result.get('error'), diagnostic=result.get('diagnostic'))
    dump(OUT / 'evidence' / 'ai_metrics.json', metrics)
    dump(OUT / 'evidence' / 'ai_trace.json', traces)
    dump(OUT / 'evidence' / 'trainer_runs.json', trainer)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    collect()
