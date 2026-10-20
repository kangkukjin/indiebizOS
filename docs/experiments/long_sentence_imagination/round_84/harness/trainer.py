"""훈련자 IBL 실행. 사용: trainer.py <check|run> <turn> <version> [--reuse <run_id>] [--input k=v ...]"""
import argparse, json, time, urllib.request, urllib.error
from pathlib import Path
ROOT = Path(__file__).resolve().parents[5]
DOC = ROOT / 'docs/experiments/long_sentence_imagination/round_84'
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-20_84회차'
p = argparse.ArgumentParser(); p.add_argument('mode'); p.add_argument('turn'); p.add_argument('version')
p.add_argument('--file', default=None); p.add_argument('--reuse', default=None); p.add_argument('--input', action='append', default=[]); p.add_argument('--describe', default=None)
a = p.parse_args()
code_path = DOC / (a.file or f'base_v{a.version}.ibl')
(OUT / 'trainer').mkdir(exist_ok=True)
inputs = {'folder': str(OUT / 'inputs'), 'dialogue': str(OUT / f'dialogue_t{a.turn}.txt'), 'outdir': str(OUT / 'trainer'), 'tag': f't{a.turn}_v{a.version}', 'prior': '', 'today': '2026-10-20'}
for kv in a.input:
    k, v = kv.split('=', 1); inputs[k] = v
body = {'code': code_path.read_text(), 'edition': 2, 'project_id': 'L84_training', 'origin': 'training', 'inputs': inputs}
if a.mode == 'check': body['check'] = True
if a.describe: body['describe'] = a.describe.split(',')
if a.reuse: body['reuse'] = {'run_id': a.reuse}
start = time.monotonic()
req = urllib.request.Request('http://localhost:8765/ibl/execute', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
try: result = json.load(urllib.request.urlopen(req, timeout=900))
except urllib.error.HTTPError as e: result = {'http_error': e.code, 'body': e.read().decode()}
secs = time.monotonic() - start
tag = f"trainer_t{a.turn}_v{a.version}_{a.mode}"
(OUT / f'{tag}_request.json').write_text(json.dumps(body, ensure_ascii=False, indent=2))
result['_seconds'] = secs
(OUT / f'{tag}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
print('SECONDS', round(secs, 3))
print(json.dumps({k: result.get(k) for k in ['success', 'ok', 'status', 'error', 'run_status', 'http_error', 'source_complete']}, ensure_ascii=False))
for key in ['issues', 'warnings']:
    if result.get(key): print(key.upper(), json.dumps(result[key], ensure_ascii=False)[:4000])
if result.get('continuation'): print('CONTINUATION', json.dumps(result['continuation'], ensure_ascii=False)[:600])
if result.get('diagnostic'): print('DIAG', json.dumps(result['diagnostic'], ensure_ascii=False)[:3000])
if result.get('descriptions'): print('DESC', json.dumps(result['descriptions'], ensure_ascii=False)[:8000])
print('VALUE', json.dumps(result.get('value'), ensure_ascii=False)[:3500])
