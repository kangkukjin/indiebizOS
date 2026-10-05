"""[self:package]{op: activate|deactivate} 용례 시딩 (② 권한 연결 2026-10-05) — 해마 단일 경로 add_examples_batch.

새 op 두 개(깨우기·잠재우기)는 사람 승인 토큰이 필요한 동작이다. 회상이 "능력 켜줘/꺼줘" 의도를 install/remove(제안)가 아니라
activate/deactivate(실제 선택, 승인 왕복)로 잇게 용례를 둔다. 사용: python3 scripts/seed_package_activation_examples.py --apply
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: F401, E402
import argparse

EXAMPLES = [
    ('record-ops 어휘 묶음을 깨워 줘 (사람 승인 뒤 활성)', '#!ibl edition=2\nreturn [self:package]{op: "activate", package_id: "record-ops"}'),
    ('turn on the youtube capability package', '#!ibl edition=2\nreturn [self:package]{op: "activate", package_id: "youtube"}'),
    ('cctv 능력은 당분간 안 쓸 테니 잠재워 줘', '#!ibl edition=2\nreturn [self:package]{op: "deactivate", package_id: "cctv"}'),
    ('put the radio package to sleep but keep its files and memories', '#!ibl edition=2\nreturn [self:package]{op: "deactivate", package_id: "radio"}'),
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
    pending = [{'intent': intent, 'ibl_code': code, 'source': 'package_activation_2026_10_05',
                'nodes': 'self', 'tags': 'package,activate,deactivate,approval'}
               for intent, code in EXAMPLES if (intent, code) not in existing]
    if pending:
        assert db._load_model_sync(), '로컬 해마 모델 로드 실패'
        added = db.add_examples_batch(pending)
        assert added == len(pending), added
        print(f'해마 +{added}, 색인: {db.rebuild_index()}')
    else:
        print('해마: 추가 없음(이미 있음)')


if __name__ == '__main__':
    main()
