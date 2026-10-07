"""29회차 실행 틀 — /ibl/execute 에 판본 2 프로그램을 보내고 요청·응답을 회차 출력 폴더에 남긴다.
사용: run.py <label> <draft 파일명> [inputs.json] [--check] [--describe a,b] [--approval TOKEN]
--approval 은 사람 통로(approve.py)가 발급한 토큰을 같은 요청에 실어 재전송할 때 쓴다(요청 지문 = code+inputs 가 같아야 한다)."""
import json, sys, time, urllib.request
from pathlib import Path
root = Path(__file__).resolve().parents[5]
d = root / 'docs/experiments/long_sentence_imagination/round_29'
o = root / 'outputs/long_sentence_imagination/2026-10-07_29회차'
args = [a for a in sys.argv[1:] if not a.startswith('--') and (sys.argv.index(a) == 0 or not sys.argv[sys.argv.index(a) - 1].startswith('--'))]
label = args[0]
payload = dict(origin='training', project_id='홍보', project_path=str(root), agent_id='LSI29_trainer', task_id='LSI29')
if '--describe' in sys.argv:
    payload.update(code='', describe=sys.argv[sys.argv.index('--describe') + 1].split(','))
else:
    payload['code'] = (d / 'drafts' / args[1]).read_text()
    if len(args) > 2: payload['inputs'] = json.loads(Path(args[2]).read_text())
    if '--check' in sys.argv: payload['check'] = True
if '--approval' in sys.argv: payload['approval'] = sys.argv[sys.argv.index('--approval') + 1]
start = time.monotonic()
req = urllib.request.Request('http://127.0.0.1:8765/ibl/execute', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(req, timeout=600) as r: result = json.load(r)
except urllib.error.HTTPError as e:
    result = {'http_status': e.code, 'body': e.read().decode()[:4000]}
rec = dict(label=label, request={k: v for k, v in payload.items()}, response=result, elapsed=time.monotonic() - start, at=time.strftime('%Y-%m-%dT%H:%M:%S'))
(o / f'{label}_run.json').write_text(json.dumps(rec, ensure_ascii=False, indent=2))
skip = {'execute_args', 'revise_args', 'functions', 'dependencies', 'canonical_code', 'results', 'runtime_checks', 'value_wire'}
print(json.dumps({k: v for k, v in result.items() if k not in skip}, ensure_ascii=False)[:int(sys.argv[sys.argv.index('--max') + 1]) if '--max' in sys.argv else 6000])
print('elapsed', round(rec['elapsed'], 3))
