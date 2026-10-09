"""Read-only, task-scoped telemetry collection; no unrelated conversations."""
import collections
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent.parent


def main():
    db = sqlite3.connect(f'file:{ROOT}/data/world_pulse.db?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    for label, task in [('base', 'task_sysai_4dcfd1fe'),
                        ('variant', 'task_sysai_564bc324')]:
        episode = dict(db.execute(
            'select id,total_ms,source,run_id from episode_log where task_id=?',
            (task,)).fetchone())
        events = [{'kind': row['kind'], 'data': json.loads(row['data'])}
                  for row in db.execute(
                      'select kind,data from trajectory_event where episode_id=? order by event_seq',
                      (episode['id'],))]
        usage = [e['data'] for e in events if e['kind'] == 'model.usage'
                 and e['data'].get('accounting') == 'billable_usage']
        totals = {key: sum(u.get(key, 0) or 0 for u in usage)
                  for key in ['input', 'output', 'cache_read', 'cache_create']}
        roles = {}
        for u in usage:
            bucket = roles.setdefault(u.get('role', 'unknown'), {k: 0 for k in totals})
            for k in totals:
                bucket[k] += u.get(k, 0) or 0
        metrics = {'episode': episode, 'usage': totals, 'roles': roles,
                   'events': dict(collections.Counter(e['kind'] for e in events)),
                   'tool_names': dict(collections.Counter(
                       e['data'].get('name') for e in events
                       if e['kind'] == 'supervision.tool.started'))}
        selected = [e for e in events if e['kind'] in {
            'model.usage', 'supervision.tool.started', 'supervision.tool.finished',
            'recall.presented', 'recall.used', 'context.compacted', 'supervision.cost.summary'}]
        for suffix, value in [('metrics', metrics), ('events', selected)]:
            (HERE / 'evidence' / f'ai_{label}_{suffix}.json').write_text(
                json.dumps(value, ensure_ascii=False, indent=2))
        print(label, episode, totals)


if __name__ == '__main__':
    main()
