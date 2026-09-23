"""Reconcile a frozen corpus against reviews; never turn missing evidence into a pass.

This closes *dispositions*, not semantic verification of rejected programs.
Every exclusion keeps its source, exact compiler diagnostics and migration risks.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'scripts')]
import boot_paths  # noqa: E402,F401

import argparse
import json
from collections import Counter

from ibl_corpus_snapshot import dump, sha
from audit_ibl_corpus_v2 import rows_from_snapshot
from corpus_policy import exclusion_reason
from ibl_edition import source_edition

RISK_REASONS = {
    'pipeline': '자동 봉투 추출 대신 생산자 반환형과 다음 입력 자리를 명시해야 한다.',
    'parallel': '현재 병렬은 가지별 값을 중첩 목록으로 보존하므로 옛 병합 결과와 구별해야 한다.',
    'fallback': '실패와 정상 빈 결과의 대체 조건을 따로 검증해야 한다.',
    'variables': '외부 입력과 실제 생산자 필드·값 타입을 확정해야 한다.',
    'interpolation_review': '일반 문자열은 보간하지 않는다. 입력 자리와 문자 그대로의 데이터를 구별해야 한다.',
    'table_callback': '조건·계산 문자열을 명시 콜백과 실제 열 계약으로 다시 검토해야 한다.',
    'each': '반복의 값·순서·실패·map/flat_map/effect 계약을 확정해야 한다.',
    'nested_source_boundary': '저장·예약·스크립트의 안쪽 코드 판본과 의존성을 따로 검증해야 한다.',
    'control': '분기·반복·중단·정리의 값 및 효과 순서를 확정해야 한다.',
    'function': '저장 이름의 판본·서명·반환형 및 전이적 호출자를 함께 검토해야 한다.',
    'legacy_return': '$return 할당은 현재 return이 아니며 Unit을 돌려줄 수 있다.',
    'envelope_field': 'Record 봉투와 명시 값의 필드 접근을 구별해야 한다.',
}


def read_lines(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def reconcile(base, reviews, priority, probes):
    original = {(r['origin'], r['row_id']): r for r in rows_from_snapshot(base)}
    audited = read_lines(base / 'audit/rows.jsonl')
    if set(original) != {(r['origin'], r['row_id']) for r in audited}:
        raise ValueError('Static ledger population mismatch')
    reviewed = {}
    for path in reviews:
        for row in json.loads(path.read_text())['rows']:
            key = row['origin'], row['row_id']
            if key in reviewed:
                raise ValueError('Overlapping reviews')
            reviewed[key] = {**row, 'review_path': str(path), 'review_sha256': sha(path.read_bytes())}
    prioritised = {(r['origin'], r['row_id']): r for r in read_lines(priority)}
    native_proofs = {r['code_sha256']: r for r in json.loads(probes.read_text())['cases']
                     if r.get('code_sha256') and r['passed']}
    lessons = json.loads((base / 'data/idioms/current_call_lessons.json').read_text())['idioms']
    callees = {}
    for row in sorted(original.values(), key=lambda r: r.get('updated_at', '') or ''):
        if row.get('alias') and row['origin'].endswith(':ibl_examples'):
            callees[(row['alias'], source_edition(row['ibl_code']))] = row['ibl_code']
    for lesson in lessons:
        if sha(callees.get((lesson['name'], lesson['source_edition']), '')) != lesson['source_sha256']:
            raise ValueError('Current-call definition changed: ' + lesson['name'])
    current_calls = {sha(l['example']): l for l in lessons}
    output = []
    for static in audited:
        key = static['origin'], static['row_id']
        row = original[key]
        record = {**static, 'external_execution': 'not_run', 'runtime_success_claimed': False}
        if sha(row['ibl_code']) != static['code_sha256']:
            raise ValueError('Static source hash mismatch')
        review = reviewed.get(key)
        if row['role'] == 'history':
            record.update(decision='history_preserved', reason='과거 실행 원문·판본·실적을 보존한다. 현재 학습 입력이 아니다.',
                          semantic_review='not_claimed_for_history', execution_test='not_run', applied=False)
        elif review:
            expected = review['after_code'] if review['decision'] != 'hold' else review['before_code']
            if row['ibl_code'] != expected or sha(row['intent']) != review['intent_sha256']:
                raise ValueError(f'Review/live conflict: {key}')
            record.update(decision=review['decision'], reason=review['reason'],
                          review_path=review['review_path'], review_sha256=review['review_sha256'],
                          semantic_review='individual_intent_review',
                          execution_test='compiler_and_boundary_fixtures' if review['decision'] != 'hold' else 'not_passed',
                          applied=review['decision'] != 'hold')
        elif key in prioritised:
            p = prioritised[key]
            if p['group_id'] != static['group_id'] or p['intent'] != row['intent']:
                raise ValueError(f'Priority review source/intent changed: {key}')
            record.update(decision='keep_current' if static['edition'] == 2 else 'compatibility_only',
                          reason=p['reason'], semantic_review='intent_and_contract',
                          execution_test='pure_value_probes' if static['edition'] == 2 else 'compatibility_boundary_only',
                          applied=False)
        elif static['code_sha256'] in native_proofs:
            proof = native_proofs[static['code_sha256']]
            if proof['intent_sha256'] != sha(row['intent']):
                raise ValueError('Native proof intent mismatch')
            record.update(decision='keep_current', reason='저장된 원문을 순수 실행하여 의도의 기대값과 대조했다.',
                          semantic_review='intent_and_expected_value', execution_test='pure_value_probes', applied=False)
        elif static['code_sha256'] in current_calls:
            lesson = current_calls[static['code_sha256']]
            if row['intent'] != lesson['seed_intent']:
                raise ValueError('Current-call intent mismatch')
            record.update(decision='keep_current', reason='검토한 함수 정의의 명시 입력·반환 계약을 부르는 교재다.',
                          semantic_review='intent_and_call_contract', execution_test='current_call_fixtures', applied=False)
        elif static['edition'] == 1:
            status = static['current_check']['status']
            issues = sorted({i.get('code', '?') for i in static['current_check'].get('issues', [])})
            reason = ('현재 컴파일러 거절: ' + ', '.join(issues) + '. ' if status == 'invalid' else
                      '정적 통과·미확정은 옛 프로그램의 의도·값 동등성 증명이 아니다. ')
            reason += ' '.join(RISK_REASONS[t] for t in static['risk_tags'] if t in RISK_REASONS)
            if static['missing_functions']:
                reason += ' 누락 함수: ' + ', '.join(static['missing_functions'])
            record.update(decision='compatibility_only' if row.get('alias') else 'hold',
                          reason=reason, semantic_review=('not_evaluated_after_static_rejection' if status == 'invalid'
                                                         else 'migration_contract_unresolved'),
                          execution_test='not_run', applied=False)
        else:
            raise ValueError(f'Unreviewed current source: {key}')
        reason = exclusion_reason(row) if row['role'] == 'learning' else 'history_not_training'
        record.update(authoring_exclusion=reason, training_eligible=reason is None)
        if record['training_eligible'] and static['current_check']['status'] in ('invalid', 'failed'):
            raise ValueError(f'Current source failed static checking: {key}')
        if record['training_eligible'] and record['decision'] not in ('keep_current', 'convert', 'repair'):
            raise ValueError(f'Unqualified current source remains exposed: {key}')
        output.append(record)
    out = base / 'audit/dispositions.jsonl'
    out.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in output))
    learning = [r for r in output if r['role'] == 'learning']
    report = {'scope': 'complete row dispositions; rejected sources are NOT semantically verified',
              'total': len(output), 'learning': len(learning), 'history': len(output)-len(learning),
              'unclassified': 0, 'review_conflicts': 0,
              'decisions': dict(Counter(r['decision'] for r in learning)),
              'semantic_review': dict(Counter(r['semantic_review'] for r in learning)),
              'eligible': sum(r['training_eligible'] for r in learning),
              'excluded': dict(Counter(r['authoring_exclusion'] for r in learning if r['authoring_exclusion'])),
              'by_origin': {origin: dict(Counter(r['decision'] for r in learning if r['origin'] == origin))
                            for origin in sorted({r['origin'] for r in learning})},
              'ledger_sha256': sha(out.read_bytes()), 'external_execution': 'not_run',
              'migration_complete': False, 'all_rows_semantically_verified': False}
    dump(base / 'audit/disposition_summary.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--reviews', nargs='+', required=True, type=Path)
    parser.add_argument('--priority', required=True, type=Path)
    parser.add_argument('--probes', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(reconcile(args.snapshot, args.reviews, args.priority, args.probes), ensure_ascii=False, indent=2))
