"""26회차 실행 틀 — /ibl/execute 에 판본 2 프로그램을 보내고 요청·응답을 회차 출력 폴더에 남긴다.
사용: run.py <label> <draft 파일명> [inputs.json 경로] [--check] [--describe a,b]"""
import json, sys, time, urllib.request
from pathlib import Path
root = Path(__file__).resolve().parents[5]
d = root / 'docs/experiments/long_sentence_imagination/round_26'
o = root / 'outputs/long_sentence_imagination/2026-10-07_26회차'
args = [a for a in sys.argv[1:] if not a.startswith('--')]
label = args[0]
payload = dict(origin='training', project_id='앱모드', project_path=str(root), agent_id='LSI26_trainer', task_id='LSI26')
if '--describe' in sys.argv:
    payload.update(code='', describe=sys.argv[sys.argv.index('--describe') + 1].split(','))
else:
    payload['code'] = (d / 'drafts' / args[1]).read_text()
    if len(args) > 2: payload['inputs'] = json.loads(Path(args[2]).read_text())
    if '--check' in sys.argv: payload['check'] = True
start = time.monotonic()
req = urllib.request.Request('http://127.0.0.1:8765/ibl/execute', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(req, timeout=600) as r: result = json.load(r)
rec = dict(label=label, request={k: v for k, v in payload.items()}, response=result, elapsed=time.monotonic() - start, at=time.strftime('%Y-%m-%dT%H:%M:%S'))
(o / f'{label}_run.json').write_text(json.dumps(rec, ensure_ascii=False, indent=2))
skip = {'execute_args', 'revise_args', 'functions', 'dependencies', 'canonical_code', 'results', 'runtime_checks', 'value_wire'}
print(json.dumps({k: v for k, v in result.items() if k not in skip}, ensure_ascii=False)[:int(sys.argv[sys.argv.index('--max') + 1]) if '--max' in sys.argv else 6000])
print('elapsed', round(rec['elapsed'], 3))
