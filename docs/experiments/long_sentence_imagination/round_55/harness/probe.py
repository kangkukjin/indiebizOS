"""탐침 — IBL 한 토막을 실행하고 응답 전체를 evidence/probe_<label>.json 에 보존. 사용: probe.py <label> '<code>' [n]"""
import json, sys, time, urllib.request
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
DROP = {"usage", "diagnostic", "plan_hash", "resume", "edition", "source_complete", "execute_args", "revise_args", "functions", "dependencies", "canonical_code", "runtime_checks", "value_wire", "evidence", "continuation", "source_map", "recordings", "run_receipt", "results"}
label, code = sys.argv[1], sys.argv[2]
if not code.lstrip().startswith('#!ibl'): code = '#!ibl edition=2\n' + code
t = time.time()
req = urllib.request.Request("http://127.0.0.1:8765/ibl/execute", data=json.dumps({"code": code, "project_id": "수동모드", "origin": "training", "task_id": "r55-probe-" + label}, ensure_ascii=False).encode(), headers={"Content-Type": "application/json"})
r = json.load(urllib.request.urlopen(req, timeout=400))
(HERE / 'evidence' / f'probe_{label}.json').write_text(json.dumps({"code": code, "elapsed": round(time.time() - t, 3), "response": r}, ensure_ascii=False, indent=1))
if r.get('issues'):
    print(label, 'REJECTED', [(i['code'], i['location']['line'], i['location']['column'], i['message'][:200], (i.get('hint') or '')[:200]) for i in r['issues']]); sys.exit(0)
print(label, round(time.time() - t, 2), 's', json.dumps({k: v for k, v in r.items() if k not in DROP}, ensure_ascii=False)[:int(sys.argv[3]) if len(sys.argv) > 3 else 2500])
