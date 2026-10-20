"""재기동으로 task 접수증이 사라진 턴의 답변을 episode_log/trajectory_event 에서 회수한다. 재실행하지 않는다."""
import json, sqlite3, sys, datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]; OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-20_84회차'
label = sys.argv[1]
ticket = json.loads((OUT / 'runs' / f'{label}_accepted.json').read_text())
c = sqlite3.connect(f'file:{ROOT}/data/world_pulse.db?mode=ro', uri=True); c.row_factory = sqlite3.Row
ep = c.execute('select * from episode_log where task_id=?', (ticket['task_id'],)).fetchone()
assert ep, 'episode not found'
ev = [dict(r) for r in c.execute('select kind,data,ts from trajectory_event where episode_id=? order by ts,event_seq', (ep['id'],))]
answer = None; closed = None
for e in ev:
    d = json.loads(e['data'])
    if e['kind'] == 'model.response_snapshot' and d.get('text'): answer = d.get('text')
    if e['kind'] == 'supervision.turn.closed': closed = d
    if e['kind'] == 'run.ended': run_end = d
log = None
result = {'state': 'succeeded' if ep['ended_at'] else 'unknown', 'recovered_from_episode': ep['id'], 'task_id': ticket['task_id'],
          'started_at': ep['started_at'], 'ended_at': ep['ended_at'], 'total_ms': ep['total_ms'], 'result': answer,
          'turn_closed': closed, 'run_ended': run_end, 'note': 'task 접수증은 재기동 뒤 404. 상태·답변은 에피소드 기록에서 회수. 재실행 없음.',
          'recovered_at': datetime.datetime.now().astimezone().isoformat()}
(OUT / 'runs' / f'{label}_result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps({k: result[k] for k in ('state', 'recovered_from_episode', 'started_at', 'ended_at', 'total_ms')}, ensure_ascii=False))
print('ANSWER:', (answer or '')[:3000])
print('CLOSED:', json.dumps(closed, ensure_ascii=False)[:300])
