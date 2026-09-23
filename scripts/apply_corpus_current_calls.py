"""Apply the reviewed current-call lessons and quarantine unbound verify intents.

No legacy body, execution history or success count is rewritten. This bounded
bundle is pinned to the reviewed file digest, not an automatic migration rule.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
import json

from ibl_corpus_snapshot import connect, dump, sha, snapshot

SOURCE = Path('data/training/_proposed_verify_intents_20260525.json')
ARCHIVE = Path('data/training/_archive/2026-09-23_ambiguous_verification.json')
REVIEWED_SHA = '794ff01d088c9cf00f02676b03f7e901926f72fddeb608f88ad0f31326d7581c'
REASON = ('요청에 대상 파일·함수·패턴을 식별할 입력이 없는데 고정 경로·줄번호·검색어를 '
          '정답으로 연결했다. 문맥 입력을 복원하기 전에는 독립 학습 쌍으로 사용하지 않는다.')


def quarantine_rows(root=ROOT):
    source, archive = root / SOURCE, root / ARCHIVE
    if source.exists() and archive.exists():
        raise ValueError('원본과 격리본이 동시에 존재합니다. 수동 대사가 필요합니다.')
    path = source if source.exists() else archive
    if not path.exists() or sha(path.read_bytes()) != REVIEWED_SHA:
        raise ValueError('검토한 제안 용례와 지문이 다릅니다. 재검토가 필요합니다.')
    rows = json.loads(path.read_text())
    if len(rows) != 40:
        raise ValueError('검토 모집단 불일치')
    with connect(root / 'data/ibl_usage.db') as conn:
        matches = sum(conn.execute(
            'SELECT COUNT(*) FROM ibl_examples WHERE intent=? AND ibl_code=?',
            (row['intent'], row['ibl_code'])).fetchone()[0] for row in rows)
    if matches:
        raise ValueError('같은 학습 쌍이 운영 DB에도 있습니다. DB 격리 검토가 필요합니다.')
    decisions = [{'origin': str(SOURCE), 'row_id': i, 'row_sha256': sha(json.dumps(row, sort_keys=True)),
                  'decision': 'quarantine', 'reason': REASON} for i, row in enumerate(rows)]
    return source.exists(), decisions


def seed_examples(lessons, resolved_sources):
    from ibl_edition import source_edition
    examples = []
    for lesson in lessons:
        source = resolved_sources.get(lesson['name'], '')
        if (sha(source) != lesson['source_sha256']
                or source_edition(source) != lesson['source_edition']):
            raise ValueError(f"호출 정의가 검토 이후 바뀌었습니다: {lesson['name']}")
        examples.append({
            'intent': lesson['seed_intent'], 'ibl_code': lesson['example'],
            'edition': 2, 'alias': '', 'category': 'composition', 'source': 'synthetic',
            'topic': lesson['topic'], 'returns': lesson['returns'],
            'provenance': {'version': 1, 'edition': 2, 'kind': 'reviewed_current_call',
                           'callee': lesson['name'], 'callee_edition': lesson['source_edition'],
                           'callee_sha256': lesson['source_sha256'],
                           'runtime_success_claimed': False}})
    return examples


def run(apply=False):
    from ibl_v2_compat import legacy_functions
    from ibl_v2_store import definitions
    from ibl_v2_learning import check_source
    from ibl_v2_assets import seed
    pending, decisions = quarantine_rows()
    lessons = json.loads((ROOT / 'data/idioms/current_call_lessons.json').read_text())['idioms']
    sources = {name: asset.get('code', '') for name, asset in legacy_functions().items()}
    sources.update(definitions())
    examples = seed_examples(lessons, sources)
    for example in examples:
        why = check_source(example['ibl_code'], False)
        if why:
            raise ValueError(why)
    report = {'version': 1, 'mode': 'apply' if apply else 'preview', 'call_examples': len(examples),
              'quarantine_rows': len(decisions), 'quarantine_pending': pending,
              'legacy_bodies_rewritten': 0, 'runtime_success_claimed': False}
    if not apply:
        return report
    dest = snapshot()
    report['backup'] = str(dest.relative_to(ROOT))
    dump(dest / 'current_calls/decisions.json', decisions)
    dump(dest / 'current_calls/seeds.json', examples)
    dump(dest / 'current_calls/report.json', {**report, 'state': 'prepared'})
    # Standard ingestion owns syntax, signature, FTS, vectors and tree refresh.
    result = seed(dest / 'current_calls/seeds.json', apply=True)
    report['seed'] = result
    dump(dest / 'current_calls/report.json', {**report, 'state': 'seeded'})
    if result['semantic_indexed'] != len(examples):
        raise RuntimeError('등록 후 벡터 색인이 미완료입니다. 재실행해 복구하세요.')
    # Recheck the review digest and DB absence after the potentially slow load.
    pending, _ = quarantine_rows()
    if pending:
        target = ROOT / ARCHIVE
        target.parent.mkdir(parents=True, exist_ok=True)
        (ROOT / SOURCE).rename(target)
    report.update(state='applied', quarantine_changed=pending, archive=str(ARCHIVE))
    dump(dest / 'current_calls/report.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run(args.apply), ensure_ascii=False, indent=2))
