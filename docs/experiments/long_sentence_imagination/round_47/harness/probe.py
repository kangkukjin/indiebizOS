"""탐침 — 짧은 IBL 을 /ibl/execute 로 보내고 evidence/probe_<label>.json 에 남긴다. 사용: probe.py <label> <task_id|-> <code파일|-> (stdin)"""
import json, sys, time, urllib.request
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
def main():
    label, task, src = sys.argv[1], sys.argv[2], sys.argv[3]
    code = sys.stdin.read() if src == '-' else Path(src).read_text()
    if not code.startswith('#!ibl'): code = '#!ibl edition=2\n' + code
    body = {'code': code, 'origin': 'training', 'project_id': '수동모드', 'budget': {'steps': 200000, 'rows': 100000}}
    if task != '-': body['task_id'] = task
    t = time.time()
    req = urllib.request.Request('http://127.0.0.1:8765/ibl/execute', data=json.dumps(body, ensure_ascii=False).encode(), headers={'Content-Type': 'application/json'})
    try: r = json.load(urllib.request.urlopen(req, timeout=300))
    except Exception as e: r = {'transport_error': str(e)}
    el = round(time.time() - t, 2)
    keep = {k: v for k, v in r.items() if k in ('success', 'status', 'error', 'value', 'issues', 'diagnostic', 'ok', 'executed', 'failure')}
    (HERE / 'evidence' / f'probe_{label}.json').write_text(json.dumps({'code': code, 'task_id': task, 'elapsed': el, 'response': keep}, ensure_ascii=False, indent=1).replace('lsi47-pass-', '<password>'))
    out = json.dumps(keep.get('value') if keep.get('success') else {k: keep.get(k) for k in ('status', 'error', 'issues')}, ensure_ascii=False)
    print(label, el, 's', out[:int(sys.argv[4]) if len(sys.argv) > 4 else 3500])
if __name__ == '__main__':
    main()
