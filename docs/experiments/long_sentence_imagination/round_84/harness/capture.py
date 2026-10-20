"""84회차 독립 AI 증거 수집: runs/*_accepted.json 의 task_id → episode_log/trajectory_event. 원본은 outputs/, 요약은 docs/evidence."""
import collections, json, sqlite3, shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]; OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-20_84회차'; DOC = ROOT / 'docs/experiments/long_sentence_imagination/round_84'
c = sqlite3.connect(f'file:{ROOT}/data/world_pulse.db?mode=ro', uri=True); c.row_factory = sqlite3.Row
FORBIDDEN = ['/trainer/', '/harness/', '/reference/', 'round_84/task.md', 'INTENT_FRAMING', 'expected.md', 'fixed_answers']
summary = []
for p in sorted((OUT / 'runs').glob('*_accepted.json')):
    label = p.stem.removesuffix('_accepted'); task = json.loads(p.read_text())['task_id']
    ep = c.execute('select * from episode_log where task_id=?', (task,)).fetchone()
    if not ep: summary.append({'label': label, 'task_id': task, 'episode': None}); continue
    ep = dict(ep); folder = OUT / 'evidence' / label; folder.mkdir(parents=True, exist_ok=True)
    events = [dict(r) for r in c.execute('select * from trajectory_event where episode_id=? order by ts,event_seq', (ep['id'],))]
    for e in events: e['data'] = json.loads(e['data'])
    (folder / 'events.json').write_text(json.dumps(events, ensure_ascii=False, indent=1)); (folder / 'episode.json').write_text(json.dumps(ep, ensure_ascii=False, indent=1))
    cost = collections.defaultdict(collections.Counter); calls = []; stores = set(); compacted = 0
    for ev in events:
        d = ev['data']; k = ev['kind']
        if k == 'model.usage' and d.get('accounting') == 'billable_usage':
            for key in ['input', 'output', 'cache_read', 'cache_create']: cost[d.get('role', 'unknown')][key] += d.get(key, 0) or 0
            cost[d.get('role', 'unknown')]['usage_events'] += 1
        if k == 'supervision.tool.started':
            payload = d.get('input', {}); text = payload.get('excerpt', '') if isinstance(payload, dict) else str(payload)
            sp = Path(d.get('store', '')) / (payload.get('id', '') + '.txt') if isinstance(payload, dict) else None
            if sp and sp.is_file(): text = sp.read_text()
            calls.append({'name': d.get('name'), 'input': text[:4000], 'time': d.get('time')})
        if k == 'context.compacted': compacted += 1
        if d.get('store'): stores.add(d['store'])
    for i, store in enumerate(sorted(stores)):
        if Path(store).is_dir(): shutil.copytree(store, folder / f'store_{i}', dirs_exist_ok=True)
    (folder / 'calls.json').write_text(json.dumps(calls, ensure_ascii=False, indent=1))
    forbidden = [cl for cl in calls if any(s in cl['input'] for s in FORBIDDEN)]
    summary.append({'label': label, 'task_id': task, 'episode': ep['id'], 'total_ms': ep['total_ms'], 'started_at': ep['started_at'], 'ended_at': ep['ended_at'],
                    'cost': {r: dict(v) for r, v in cost.items()}, 'tool_calls': len(calls), 'tools': collections.Counter(cl['name'] for cl in calls),
                    'model_round_events': sum(e['kind'] == 'model.round' for e in events), 'context_compacted': compacted, 'forbidden_access_candidates': len(forbidden)})
(OUT / 'ai_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1))
(DOC / 'evidence').mkdir(exist_ok=True); (DOC / 'evidence' / 'ai_execution_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1))
for s in summary: print(json.dumps(s, ensure_ascii=False)[:600])
