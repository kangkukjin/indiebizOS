"""73회차 읽기 전용 census — 선언된 인자 중 핸들러가 입력 dict 에서 한 번도 읽지 않는 것(선언 ∖ 읽기).

B72-2 census(읽기 ∖ 선언)의 반대 방향. 패키지 `ibl_actions.yaml` 의 actions.*.params 키를,
그 패키지 .py 전체에서 **입력 dict 이름**(tool_input·input_data·tool_args·params·p·inp)에 대한
`.get("키")`·`["키"]`·`"키" in 이름` 읽기와 대조한다. 입력을 통째로 **kwargs 로 넘기는 패키지는
읽기를 못 세므로 결과에서 빼고(passthrough) 따로 적는다. 패키지 단위 합집합이라 **하한**이다.
사용: .venv/bin/python declared_unread_census.py
"""
import ast
import json
from pathlib import Path

import yaml

BASE = Path('/Users/kangkukjin/Desktop/AI/indiebizOS')
HERE = Path(__file__).resolve().parent
NAMES = {'tool_input', 'input_data', 'tool_args', 'params', 'p', 'inp', 'ti'}


def reads(src):
    keys, passthrough = set(), False
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return keys, passthrough
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ('get', 'pop', 'setdefault') \
                and isinstance(n.func.value, ast.Name) and n.func.value.id in NAMES and n.args \
                and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
            keys.add(n.args[0].value)
        elif isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and n.value.id in NAMES \
                and isinstance(n.slice, ast.Constant) and isinstance(n.slice.value, str):
            keys.add(n.slice.value)
        elif isinstance(n, ast.Compare) and isinstance(n.left, ast.Constant) and isinstance(n.left.value, str) \
                and any(isinstance(c, ast.Name) and c.id in NAMES for c in n.comparators):
            keys.add(n.left.value)
        elif isinstance(n, ast.Call) and any(isinstance(k, ast.keyword) and k.arg is None and isinstance(k.value, ast.Name)
                                             and k.value.id in NAMES for k in n.keywords):
            passthrough = True
    return keys, passthrough


rows, skipped = [], []
for spec_path in sorted((BASE / 'data/packages/installed/tools').glob('*/ibl_actions.yaml')):
    pkg = spec_path.parent
    spec = yaml.safe_load(spec_path.read_text()) or {}
    got, passthrough = set(), False
    for f in pkg.rglob('*.py'):
        if '__pycache__' in str(f):
            continue
        k, pt = reads(f.read_text(errors='ignore'))
        got |= k
        passthrough |= pt
    node = spec.get('node')
    for action, a in (spec.get('actions') or {}).items():
        if not isinstance(a, dict):
            continue
        miss = [k for k in (a.get('params') or {}) if k not in got]
        if not miss:
            continue
        (skipped if passthrough else rows).append({'action': f'{node}:{action}', 'params': miss, 'package': pkg.name})
out = {'actions_with_unread_declared': len(rows), 'rows': rows, 'passthrough_packages_skipped': skipped}
(HERE / 'declared_unread_census.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(len(rows), 'actions;', sum(len(r['params']) for r in rows), 'params | skipped(passthrough):', len(skipped))
for r in rows:
    print(r['action'], r['params'])
