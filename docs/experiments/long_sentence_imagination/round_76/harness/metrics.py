"""Read-only episode accounting, scoped to this round's two task IDs."""
import collections
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-18_76회차'
DOC = Path(__file__).resolve().parents[1]
task_ids = ['task_sysai_3a93ec10', 'task_sysai_8dc4e68e']
db = sqlite3.connect(f'file:{ROOT}/data/world_pulse.db?mode=ro', uri=True)
db.row_factory = sqlite3.Row
report = {'token_note': 'Provider input, output, cache_read/cache_create separately. No addition of cache to input. Trainer author tokens unmeasured.', 'ai': [], 'trainer': []}
trace = []
for task_id in task_ids:
    for ep in db.execute('SELECT id,source,task_id,total_ms,started_at,ended_at FROM episode_log WHERE task_id=? ORDER BY id', (task_id,)):
        rows = db.execute('SELECT kind,data,event_seq FROM trajectory_event WHERE episode_id=? ORDER BY event_seq', (ep['id'],)).fetchall()
        roles = {}; seen = set(); tools = {}; total = collections.Counter(); kinds = collections.Counter(); models = set()
        for row in rows:
            kind = row['kind']; data = json.loads(row['data']); kinds[kind] += 1
            if kind == 'supervision.tool.started':
                tools[data.get('id', str(row['event_seq']))] = data.get('name', 'unknown')
                trace.append({'episode': ep['id'], 'seq': row['event_seq'], 'id': data.get('id'), 'name': data.get('name'), 'input': data.get('input')})
            if kind != 'model.usage' or data.get('accounting') != 'billable_usage':
                continue
            key = (data.get('call_id'), data.get('round_index'), data.get('role'))
            if key in seen:
                continue
            seen.add(key)
            models.add(str(data.get('provider')) + '/' + str(data.get('model')))
            role = roles.setdefault(data.get('role', 'unknown'), collections.Counter())
            for f in ('input', 'output', 'cache_read', 'cache_create'):
                role[f] += data.get(f, 0) or 0; total[f] += data.get(f, 0) or 0
        report['ai'].append({**dict(ep), 'tools': dict(collections.Counter(tools.values())), 'usage': dict(total), 'roles': {k: dict(v) for k, v in roles.items()}, 'models': sorted(models), 'event_counts': dict(kinds)})
for label in ('base_run','variant_run','repaired_base_run','repaired_variant_run','restored_run','guide_ref_repro','receipt_contract_run'):
    d = json.loads((OUT / 'runs' / (label + '.json')).read_text()); r = d['response']
    report['trainer'].append({'label': label, 'wall_s': round(d['ended'] - d['started'], 3), 'success': r.get('success'), 'state': r.get('run_status'), 'task_ref': r.get('task_ref'), 'usage': {k: r.get('usage', {}).get(k) for k in ('steps', 'rows', 'elapsed_ms')}, 'tool_ms_by_line': r.get('usage', {}).get('tool_ms_by_line')})
(OUT / 'evidence/metrics.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
(OUT / 'evidence/ai_tool_inputs.json').write_text(json.dumps(trace, ensure_ascii=False, indent=2))
print(json.dumps(report['ai'], ensure_ascii=False, indent=2))
