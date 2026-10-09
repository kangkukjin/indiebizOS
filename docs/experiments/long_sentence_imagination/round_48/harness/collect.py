"""Read-only, task-scoped telemetry collection. 사용: collect.py <label>=<task_id> [...]"""
import collections, json, sqlite3, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent.parent

def main():
    db = sqlite3.connect(f'file:{ROOT}/data/world_pulse.db?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    for arg in sys.argv[1:]:
        label, task = arg.split('=', 1)
        row = db.execute('select id,total_ms,source,run_id from episode_log where task_id=?', (task,)).fetchone()
        if row is None:
            print(label, 'no episode for', task); continue
        episode = dict(row)
        events = [{'kind': r['kind'], 'data': json.loads(r['data'])} for r in db.execute(
            'select kind,data from trajectory_event where episode_id=? order by event_seq', (episode['id'],))]
        usage = [e['data'] for e in events if e['kind'] == 'model.usage' and e['data'].get('accounting') == 'billable_usage']
        totals = {k: sum(u.get(k, 0) or 0 for u in usage) for k in ['input', 'output', 'cache_read', 'cache_create']}
        roles = {}
        for u in usage:
            b = roles.setdefault(u.get('role', 'unknown'), {k: 0 for k in totals})
            for k in totals: b[k] += u.get(k, 0) or 0
        tools = [e['data'] for e in events if e['kind'] == 'supervision.tool.started']
        fin = [e['data'] for e in events if e['kind'] == 'supervision.tool.finished']
        metrics = {'episode': episode, 'usage': totals, 'roles': roles,
                   'events': dict(collections.Counter(e['kind'] for e in events)),
                   'tool_names': dict(collections.Counter(t.get('name') for t in tools)),
                   'tool_failures': sum(1 for f in fin if f.get('ok') is False or f.get('status') in ('error', 'failed')),
                   'recall_used': [e['data'] for e in events if e['kind'] == 'recall.used'][:10],
                   'compacted': sum(1 for e in events if e['kind'] == 'context.compacted')}
        selected = [e for e in events if e['kind'] in {'model.usage', 'supervision.tool.started', 'supervision.tool.finished',
                    'recall.presented', 'recall.used', 'context.compacted', 'supervision.cost.summary'}]
        (HERE / 'evidence' / f'ai_{label}_metrics.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=2))
        (HERE / 'evidence' / f'ai_{label}_events.json').write_text(json.dumps(selected, ensure_ascii=False, indent=2))
        print(label, episode, totals, 'tools', sum(metrics['tool_names'].values()), metrics['tool_names'], 'fail', metrics['tool_failures'], 'compacted', metrics['compacted'])

if __name__ == '__main__':
    main()
