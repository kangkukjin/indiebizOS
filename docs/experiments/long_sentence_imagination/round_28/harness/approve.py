"""28회차 사람 통로 대역 — /ibl/approve 에 challenge 를 보내 토큰을 받는다. 훈련자가 '그 자리의 사람' 역할을 맡는다.
사용: approve.py <challenge> [label]   (발급 기록은 evidence/approvals.jsonl)"""
import json, sys, time, urllib.request
from pathlib import Path
root = Path(__file__).resolve().parents[5]
ev = root / 'docs/experiments/long_sentence_imagination/round_28/evidence/approvals.jsonl'
challenge = sys.argv[1]; label = sys.argv[2] if len(sys.argv) > 2 else ''
req = urllib.request.Request('http://127.0.0.1:8765/ibl/approve', data=json.dumps({'challenge': challenge}).encode(),
                             headers={'Content-Type': 'application/json', 'Origin': 'http://localhost:8765', 'Sec-Fetch-Mode': 'cors'})
try:
    with urllib.request.urlopen(req, timeout=30) as r: res = json.load(r)
except urllib.error.HTTPError as e:
    res = {'http_status': e.code, 'body': e.read().decode()[:500]}
with open(ev, 'a') as f: f.write(json.dumps({'at': time.strftime('%H:%M:%S'), 'label': label, 'challenge': challenge, 'result': res}, ensure_ascii=False) + '\n')
print(json.dumps(res, ensure_ascii=False))
