"""Seed current helper-management examples; --apply updates recall, never devices."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402, F401
import argparse
import json

UPDATE = '#!ibl edition=2\nreturn [self:limb]{op:"update",target:"사무실PC"}'
STATUS = '#!ibl edition=2\nreturn [self:limb]{op:"list",limb:"사무실PC"}'
TRACK = '''#!ibl edition=2
$접수 = [self:limb]{op:"update",target:"사무실PC"}
[if:$접수.state=="updating"] {
  $작업 = [self:task]{op:"wait",ref:$접수.task_ref,timeout:60}
  $설치 = [self:limb]{op:"list",limb:"사무실PC"}
  return {접수:$접수,작업:$작업,설치:$설치}
}
return $접수'''
EXAMPLES = [
    ('사무실PC 헬퍼를 중앙의 최신 배포본으로 업데이트해 줘', UPDATE),
    ('사무실PC의 원격 헬퍼를 교체해 줘', UPDATE),
    ('내가 요청하니 사무실PC 헬퍼 업데이트를 진행해', UPDATE),
    ('사무실PC 헬퍼를 정식 업데이트 절차로 갱신해 줘', UPDATE),
    ('Update the helper on 사무실PC to the published release', UPDATE),
    ('사무실PC 헬퍼 교체 버튼 대신 네가 업데이트를 실행해 줘', UPDATE),
    ('사무실PC 헬퍼 업데이트를 접수하고 진행 결과와 설치 지문을 확인해 줘', TRACK),
    ('사무실PC 헬퍼 갱신 후 재시작 결과와 현재 배포판 정보를 보여 줘', TRACK),
    ('사무실PC 헬퍼가 최신인지 확인만 해 줘', STATUS),
    ('사무실PC 헬퍼 업데이트 상태만 보고 설치는 하지 마', STATUS),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    registry = load_registry(str(ROOT))
    for intent, code in EXAMPLES:
        plan = compile_program(code, registry)
        assert not plan.issues, (intent, plan.report())
    print(f'helper examples compiled: {len(EXAMPLES)}')
    if not args.apply:
        return
    from ibl_usage_db import IBLUsageDB
    db = IBLUsageDB()
    with db._get_connection() as conn:
        present = {tuple(row) for row in conn.execute('SELECT intent,ibl_code FROM ibl_examples')}
    pending = [dict(intent=intent, ibl_code=code, nodes='self', source='synthetic',
                    tags='guest-helper,helper-update', topic='외부 PC 헬퍼')
               for intent, code in EXAMPLES if (intent, code) not in present]
    if pending:
        assert db._load_model_sync(), 'recall model unavailable'
        assert db.add_examples_batch(pending) == len(pending)
    training = ROOT / 'data/training/ibl_distilled.json'
    rows = json.loads(training.read_text(encoding='utf-8'))
    known = {(r.get('intent'), r.get('ibl_code')) for r in rows}
    added = [dict(intent=intent, ibl_code=code) for intent, code in EXAMPLES
             if (intent, code) not in known]
    if added:
        training.write_text(json.dumps(rows + added, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'recall added: {len(pending)}; training added: {len(added)}')


if __name__ == '__main__':
    main()
