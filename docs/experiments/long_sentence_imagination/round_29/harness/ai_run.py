"""29회차 시스템 AI 독립 실행 — /system-ai/chat 에 origin: training 으로 요청문을 보내고 왕복을 기록한다.
사용: ai_run.py <label> <request 파일> [--timeout 초]"""
import json, sys, time, urllib.request
from pathlib import Path
root = Path(__file__).resolve().parents[5]
d = root / 'docs/experiments/long_sentence_imagination/round_29'
o = root / 'outputs/long_sentence_imagination/2026-10-07_29회차'
label, req_file = sys.argv[1], sys.argv[2]
timeout = int(sys.argv[sys.argv.index('--timeout') + 1]) if '--timeout' in sys.argv else 900
message = (d / req_file).read_text()
payload = {'message': message, 'origin': 'training'}
start = time.monotonic(); at = time.strftime('%H:%M:%S')
req = urllib.request.Request('http://127.0.0.1:8765/system-ai/chat', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(req, timeout=timeout) as r: res = json.load(r)
except urllib.error.HTTPError as e:
    res = {'http_status': e.code, 'body': e.read().decode()[:3000]}
rec = {'label': label, 'request_file': req_file, 'start': at, 'elapsed': round(time.monotonic() - start, 2), 'response': res}
(o / f'{label}_ai_run.json').write_text(json.dumps(rec, ensure_ascii=False, indent=2))
print(json.dumps({k: (v if k != 'response' else {kk: (vv[:1500] if isinstance(vv, str) else vv) for kk, vv in v.items()}) for k, v in rec.items()}, ensure_ascii=False))
