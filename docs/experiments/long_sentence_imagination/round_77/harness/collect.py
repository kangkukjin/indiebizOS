"""Read existing evidence only; never dispatch work or modify production records."""
import collections
import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-19_77회차'


def main():
    db = sqlite3.connect(f'file:{ROOT}/data/world_pulse.db?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    task_ids = ['long_sentence_77_trainer_base', 'long_sentence_77_trainer_variant']
    for p in sorted(OUT.glob('repair_*.json')):
        request = json.loads(p.read_text())
        if request.get('task_id') and not request.get('check'):
            task_ids.append(request['task_id'])
    for p in sorted((OUT / 'runs').glob('ai*submit.json')):
        task_ids.append(json.loads(p.read_text())['response']['task_id'])
    report = {'usage_note': 'Provider reported input/output/cache_read/cache_create. Cache is not added again. Trainer author usage unmeasured.', 'tasks': []}
    traces = []
    for task_id in dict.fromkeys(task_ids):
        eps = [dict(e) for e in db.execute('SELECT id,source,task_id,total_ms,started_at,ended_at FROM episode_log WHERE task_id=? ORDER BY id', (task_id,))]
        rows = db.execute('SELECT run_id,event_seq,ts,kind,data FROM trajectory_event WHERE task_id=? ORDER BY ts,event_seq', (task_id,)).fetchall()
        roles = {}; seen = {}; total = collections.Counter(); kinds = collections.Counter(); models = set(); inputs = []; tools = {}; conflicts = []
        for row in rows:
            kind = row['kind']; data = json.loads(row['data']); kinds[kind] += 1
            if kind == 'model.input':
                inputs.append({'seq': row['event_seq'], 'ts': row['ts'], **data})
            if kind in ('supervision.tool.started', 'supervision.tool.finished'):
                event = {**data, 'task_id': task_id, 'seq': row['event_seq'], 'ts': row['ts'], 'kind': kind}
                for field in ('input', 'evidence'):
                    ref = data.get(field)
                    if not isinstance(ref, dict) or not ref.get('id') or not data.get('store'):
                        continue
                    path = Path(data['store']) / (ref['id'] + '.txt')
                    if path.exists():
                        raw = path.read_bytes()
                        event[field + '_full'] = raw.decode()
                        event[field + '_sha256'] = hashlib.sha256(raw).hexdigest()
                traces.append(event)
                if kind == 'supervision.tool.started':
                    tools[data.get('id', str(row['event_seq']))] = data.get('name', 'unknown')
            if kind != 'model.usage' or data.get('accounting') != 'billable_usage':
                continue
            key = (data.get('call_id'), data.get('round_index'), data.get('role'))
            if key in seen:
                if seen[key] != data:
                    conflicts.append({'key': key, 'event_seq': row['event_seq']})
                continue
            seen[key] = data
            models.add(str(data.get('provider')) + '/' + str(data.get('model')))
            role = roles.setdefault(data.get('role', 'unknown'), collections.Counter())
            for f in ('input', 'output', 'cache_read', 'cache_create'):
                role[f] += data.get(f, 0) or 0; total[f] += data.get(f, 0) or 0
        report['tasks'].append({'task_id': task_id, 'episodes': eps, 'tools': dict(collections.Counter(tools.values())), 'usage': dict(total), 'roles': {k: dict(v) for k, v in roles.items()}, 'models': sorted(models), 'event_counts': dict(kinds), 'input_shapes': inputs, 'usage_conflicts': conflicts})
    (OUT / 'evidence/metrics.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (OUT / 'evidence/ai_tools_full.json').write_text(json.dumps(traces, ensure_ascii=False, indent=2))
    print(json.dumps([{k: t[k] for k in ('task_id','episodes','tools','usage','usage_conflicts')} for t in report['tasks']], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
