"""Capture task receipts and billable usage; raw device data stays in outputs/."""
from collections import Counter, defaultdict
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[4]
DOC = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-20_85회차'


def capture():
    db = sqlite3.connect(f'file:{ROOT}/data/world_pulse.db?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    summaries = []
    for path in sorted((OUT / 'runs').glob('ai_*_accepted.json')):
        label = path.stem.removeprefix('ai_').removesuffix('_accepted')
        task = json.loads(path.read_text())['task_id']
        row = db.execute('select * from episode_log where task_id=?', (task,)).fetchone()
        if row is None:
            continue
        episode = dict(row)
        events = [dict(r) for r in db.execute(
            'select * from trajectory_event where episode_id=? order by ts,event_seq',
            (episode['id'],))]
        costs = defaultdict(Counter)
        calls, models, ibl_runs = [], set(), []
        for event in events:
            event['data'] = d = json.loads(event['data'])
            kind = event['kind']
            if kind == 'model.usage' and d.get('accounting') == 'billable_usage':
                role = d.get('role', 'unknown')
                for key in ('input', 'output', 'cache_read', 'cache_create'):
                    costs[role][key] += d.get(key, 0) or 0
                costs[role]['billable_events'] += 1
                models.add(d.get('model', 'unknown'))
            if kind == 'supervision.tool.started':
                value = d.get('input', {})
                text = value.get('excerpt', '')
                stored = Path(d.get('store', '')) / (value.get('id', '') + '.txt')
                if stored.is_file():
                    text = stored.read_text()
                calls.append({'id': d.get('id'), 'name': d.get('name'),
                              'phase': d.get('phase'), 'input': text, 'ts': event['ts']})
            if kind == 'ibl.finished':
                ibl_runs.append({'ts': event['ts'], 'success': d.get('success'),
                                 'elapsed_ms': d.get('elapsed_ms')})
        folder = OUT / 'evidence' / label
        folder.mkdir(parents=True, exist_ok=True)
        for name, value in [('episode', episode), ('events', events), ('calls', calls)]:
            (folder / (name + '.json')).write_text(json.dumps(value, ensure_ascii=False, indent=2))
        forbidden = [c['id'] for c in calls if any(term in c['input'] for term in
                     ('/trainer/', '/round_85/base_', '/round_85/recover_', '/round_85/task.md'))]
        totals = Counter()
        for cost in costs.values():
            totals.update(cost)
        summary = {'label': label, 'task_id': task, 'episode_id': episode['id'],
                   'source': episode.get('source'), 'total_ms': episode['total_ms'],
                   'ended_at': episode['ended_at'], 'models': sorted(models),
                   'cost_by_role': dict(costs), 'cost_total': dict(totals),
                   'tools': dict(Counter(c['name'] for c in calls)),
                   'tools_by_phase': dict(Counter(c['phase'] for c in calls)),
                   'unique_tool_ids': len({c['id'] for c in calls}),
                   'tool_started_events': len(calls), 'ibl_runs': ibl_runs,
                   'model_round_events': sum(e['kind'] == 'model.round' for e in events),
                   'compactions': sum(e['kind'] == 'context.compacted' for e in events),
                   'forbidden_access_candidates': forbidden}
        summaries.append(summary)
    (DOC / 'evidence/ai_summary.json').write_text(json.dumps(summaries, ensure_ascii=False, indent=2))
    print(json.dumps([{k: s[k] for k in ('label', 'episode_id', 'total_ms', 'cost_total', 'tools', 'ended_at')} for s in summaries], ensure_ascii=False))


if __name__ == '__main__':
    capture()
