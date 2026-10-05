"""Read only the two synthetic AI episodes and persist costs/program evidence."""
import json
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
DOC = ROOT / 'docs/experiments/long_sentence_imagination/round_25'
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-06_25회차'
db = sqlite3.connect(f'file:{ROOT}/data/world_pulse.db?mode=ro', uri=True)
records = []
for episode in [4346, 4347]:
    row = db.execute('select id,started_at,ended_at,total_ms,run_id from episode_log where id=?', (episode,)).fetchone()
    if not row:
        continue
    record = dict(zip(['episode', 'started', 'ended', 'total_ms', 'run_id'], row))
    usages, calls, evaluations, route = [], [], [], []
    totals, roles = Counter(), {}
    for kind, raw in db.execute('select kind,data from trajectory_event where episode_id=? order by event_seq', (episode,)):
        data = json.loads(raw)
        if kind == 'model.usage' and data.get('accounting') == 'billable_usage':
            usages.append(data)
            role = roles.setdefault(data.get('role', 'unknown'), Counter())
            for field in ['input', 'output', 'cache_read', 'cache_create']:
                totals[field] += data.get(field, 0)
                role[field] += data.get(field, 0)
        if kind in ['cognition.route', 'cognition.evaluation', 'supervision.cost.summary', 'context.compacted']:
            route.append(dict(kind=kind, data=data))
        if kind == 'supervision.tool.started':
            ref = data.get('input', {})
            file = Path(data.get('store', '')) / (ref.get('id', '') + '.txt')
            body = json.loads(file.read_text()) if file.exists() else ref
            calls.append(dict(kind=kind, id=data.get('id'), input=body))
        if kind == 'supervision.tool.finished':
            ref = data.get('evidence', {})
            file = Path(data.get('store', '')) / (ref.get('id', '') + '.txt')
            body = json.loads(file.read_text()) if file.exists() else {}
            selected = {k:body[k] for k in ['success','ok','executed','issues','diagnostic','usage','run_status','resume','continuation','inputs_resolved','result_ref'] if k in body}
            calls.append(dict(kind=kind, id=data.get('id'), elapsed_s=data.get('elapsed_s'),
                              check_rejected=data.get('check_rejected'), is_error=data.get('is_error'), result=selected))
    record.update(totals=dict(totals), roles=roles, usage=usages, route=route,
                  calls_started=sum(c['kind']=='supervision.tool.started' for c in calls),
                  check_rejections=sum(bool(c.get('check_rejected')) for c in calls),
                  execution_errors=sum(bool(c.get('is_error')) for c in calls))
    records.append(record)
    (OUT / 'evidence' / f'ai_{episode}_calls.json').write_text(json.dumps(calls, ensure_ascii=False, indent=2))
(OUT / 'evidence/ai_metrics.json').write_text(json.dumps(records, ensure_ascii=False, indent=2))
print(json.dumps([{k:v for k,v in r.items() if k not in ['usage','route']} for r in records], ensure_ascii=False, indent=2))
