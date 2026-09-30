#!/usr/bin/env python3
"""Seed the tested file-authoring and pure-expression composition contracts."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: F401, E402
import argparse
import json

EXAMPLES = [
    ('등록 없이 Python 계산 절차를 작성하고 IBL 안에서 실행하기', '''#!ibl edition=2
[def:임시파일계산]($본문,$자료) {
  $f=[self:write]{path:"~turn/계산.py",content:$본문}
  return [self:script]{path:$f.path,args:$자료}
}'''),
    ('Edit a failed Python file and start a new IBL attempt with confirmed input', '''#!ibl edition=2
[def:임시파일수리실행]($수정전,$수정후,$자료) {
  [self:edit]{path:"~turn/계산.py",old_string:$수정전,new_string:$수정후}
  return [self:script]{path:"~turn/계산.py",args:$자료}
}'''),
    ('Python 결과의 항목을 다음 표 필터로 이어 처리하기', '''#!ibl edition=2
[def:파일결과거르기]($자료) {
  $r=[self:script]{path:"~turn/계산.py",args:$자료}
  return $r.items >> [table:filter]{where:($행)=>$행.n>2}
}'''),
    ('글자 목록의 빈 항목을 빼고 양끝 공백 제거하기', '''#!ibl edition=2
[def:글자목록정리]($목록) {
  return map(filter($목록,($s)=>len(strip($s))>0),($s)=>strip($s))
}'''),
    ('금액에 천 단위 쉼표와 소수 두 자리 붙이기', '''#!ibl edition=2
[def:금액표시]($금액) { return format_number($금액,",.2f") }'''),
    ('Format a ratio as a percentage with one decimal place', '''#!ibl edition=2
[def:비율표시]($비율) { return format_number($비율,".1%") }'''),
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
    print(f'용례 검사: {len(EXAMPLES)}건 통과')
    if not args.apply:
        return
    from ibl_usage_db import IBLUsageDB
    db = IBLUsageDB()
    with db._get_connection() as conn:
        existing = {tuple(row) for row in conn.execute('SELECT intent,ibl_code FROM ibl_examples')}
    pending = [{'intent': intent, 'ibl_code': code, 'source': 'file_script_2026_10_01',
                'nodes': 'self,table', 'tags': 'script,inputs,edit,expression'}
               for intent, code in EXAMPLES if (intent, code) not in existing]
    if pending:
        assert db._load_model_sync(), '로컬 해마 모델 로드 실패'
        added = db.add_examples_batch(pending)
        assert added == len(pending), added
        print(f'해마 +{added}, 색인: {db.rebuild_index()}')
    path = ROOT / 'data/training/ibl_distilled.json'
    raw = path.read_text()
    training = json.loads(raw)
    existing = {(s.get('intent'), s.get('ibl_code')) for s in training}
    additions = [{'intent': intent, 'ibl_code': code} for intent, code in EXAMPLES
                 if (intent, code) not in existing]
    if additions:
        assert path.read_text() == raw, '학습 원장이 바뀌었습니다. 다시 실행하세요.'
        path.write_text(json.dumps(training + additions, ensure_ascii=False, indent=2) + '\n')
    print(f'학습 용례 +{len(additions)}')


if __name__ == '__main__':
    main()
