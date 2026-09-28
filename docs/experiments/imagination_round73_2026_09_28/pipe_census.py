"""73회차 읽기 전용 census — `pipe_in: true` 로 선언된 액션 중 판본 2 계약에 파이프 자리(pipe_input)가 없는 것.

선언(`data/ibl_nodes.yaml` 의 pipe_in)과 판본 2 describe 결과(callable_contract.pipe_input)를 대조한다.
라이브 백엔드의 describe 만 부른다(효과 없음). 사용: .venv/bin/python pipe_census.py
"""
import json
import subprocess
from pathlib import Path

import yaml

BASE = Path('/Users/kangkukjin/Desktop/AI/indiebizOS')
HERE = Path(__file__).resolve().parent
nodes = yaml.safe_load(open(BASE / 'data/ibl_nodes.yaml'))
nodes = nodes.get('nodes', nodes)
declared = sorted(f'{n}:{a}' for n, spec in nodes.items() if isinstance(spec, dict)
                  for a, x in (spec.get('actions') or {}).items() if isinstance(x, dict) and x.get('pipe_in'))


def describe(actions):
    payload = dict(code='', edition=2, describe=actions, project_id='컨텐츠', origin='training',
                   agent_id='IT73_probe', task_id='IT73_task')
    p = subprocess.run(['curl', '-sS', '--max-time', '120', 'http://127.0.0.1:8765/ibl/execute',
                        '-H', 'Content-Type: application/json', '--data-binary', '@-'],
                       input=json.dumps(payload), text=True, capture_output=True, check=True)
    return json.loads(p.stdout).get('actions') or []


rows = []
for i in range(0, len(declared), 1):
    for a in describe(declared[i:i + 1]):
        cc = (a.get('definition') or {}).get('callable_contract') or {}
        rows.append({'action': a['action'], 'pipe_input': cc.get('pipe_input'),
                     'has_items_param': 'items' in (cc.get('params') or {}),
                     'compat': cc.get('compatibility')})
missing = [r for r in rows if not r['pipe_input']]
out = {'declared_pipe_in': len(declared), 'described': len(rows), 'missing_pipe_input': len(missing),
       'missing': missing}
(HERE / 'pipe_census.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(json.dumps({k: out[k] for k in ('declared_pipe_in', 'described', 'missing_pipe_input')}))
for r in missing:
    print(r['action'], 'items_param' if r['has_items_param'] else '-')
