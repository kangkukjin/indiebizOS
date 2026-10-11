"""runs/<label>.json 요약 출력. 사용: show.py <label> [n]"""
import json, sys
from pathlib import Path
OUT = Path(__file__).resolve().parents[5] / 'outputs/long_sentence_imagination/2026-10-11_55회차'
d = json.loads((OUT / 'runs' / (sys.argv[1] + '.json')).read_text()); r = d['response']
print('elapsed', round(d['ended'] - d['started'], 2), 'status', r.get('status'), 'success', r.get('success'), 'run_id', r.get('run_id'))
if r.get('issues'):
    for i in r['issues'][:10]: print(' ', i.get('code'), 'L%s:%s' % (i['location']['line'], i['location']['column']), i['message'][:300], '|', (i.get('hint') or '')[:200])
for k in ('error', 'diagnostic', 'failure'):
    if r.get(k): print(k, json.dumps(r[k], ensure_ascii=False)[:1800])
if 'value' in r: print('value', json.dumps(r['value'], ensure_ascii=False)[:int(sys.argv[2]) if len(sys.argv) > 2 else 2500])
u = r.get('usage') or {}
print('usage', {k: u.get(k) for k in ('steps', 'rows', 'tool_calls', 'tool_ms', 'model_calls') if k in u}, 'keys', list(r.keys()))
