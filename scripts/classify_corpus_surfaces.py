"""Assign every extracted surface its consumer context, without executing templates.

A code mention, a stored compatibility program and a verified current program
are different claims. This report does not certify old guide examples.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'backend')]
import boot_paths  # noqa: E402,F401

import argparse
import json
from collections import Counter
from ibl_corpus_snapshot import dump, sha
from audit_ibl_corpus_v2 import static_check, forbidden
from ibl_v2_adapters import Adapter


def context(row):
    path, kind = row['origin'], row['kind']
    if path.startswith('data/hippocampus_tree/'):
        return 'explicit_history_expansion', 'DB 원문·주행의 파생 기억. 기본 회상은 이름/ID이며 전문은 명시 expand로 연다.'
    if path in ('data/ibl_nodes.yaml',) or '/tool.json' in path:
        return 'generated_vocabulary_reference', '빌드 파생물. 어휘 표기·설명 조각을 독립 프로그램으로 간주하지 않는다.'
    if path.startswith('data/ibl_nodes_src/') or path.endswith('/ibl_actions.yaml'):
        return 'vocabulary_source_reference', '액션 이름·인자 설명의 사전 정본. 실행 문법은 현재 주 교재와 callable_contract가 정한다.'
    if path.startswith('data/idioms/'):
        if Path(path).name in ('ibl_v2_seeds.json', 'current_call_lessons.json'):
            return 'reviewed_current_seed_reference', '학습 행 및 함수 호출 검증 원장과 연결한다. 설명 필드도 포함한 후보 수다.'
        return 'compatibility_seed_reference', '구형 정의·선정집을 원문 보존한다. 시딩해도 현재 작성·학습 자격으로 승격하지 않는다.'
    if path.startswith('data/workflows/'):
        return 'stored_workflow', '저장 판본의 함수/템플릿이다. 인자 문맥 없는 독립 프로그램 실행은 하지 않는다.'
    if path in ('data/calendar_events.json', 'data/event_triggers.json', 'data/member_apps.yaml',
                'data/webapps.json'):
        return 'stored_runtime_template', '스케줄·트리거·앱의 기존 저장 실행 문맥을 보존한다. 본문을 새 작성 교재로 승격하지 않는다.'
    if path.startswith('data/scripts/'):
        if '/test_' in path:
            return 'compatibility_test_fixture', '호환 시험의 문자열/조각이며 학습 코퍼스가 아니다.'
        return 'script_documentation', '등록 스크립트의 설명·도움말 문자열. 이번 추출의 Python 문자열은 IBL 실행 본문이 아니다.'
    if path.startswith(('data/guides/', 'data/common_prompts/', 'data/system_docs/')):
        if '#!ibl edition=2' in row['code'] and kind == 'markdown_fence':
            return 'current_program_example', '명시 현재 판본 예제. 정적 판정과 업무 의미 검증은 구별한다.'
        if kind == 'markdown_inline':
            return 'documentation_fragment', '문장 안의 어휘/호출 조각. 완성 프로그램·학습 정답으로 판정하지 않는다.'
        return 'documentation_context', '업무 조건·도구 사용법의 문맥. 구형 조합 예시는 현재 주 교재에 맞춰 작성해야 한다.'
    raise ValueError('Unclassified surface owner: ' + path)


def classify(base):
    audit = base / 'audit'
    inventory = json.loads((audit / 'surfaces.json').read_text())
    if inventory['errors']:
        raise ValueError('Surface extraction errors remain')
    frozen = json.loads((audit / 'contracts.json').read_text())
    registry = {k: Adapter(v, forbidden) for k, v in frozen['contracts'].items()}
    rows, example_libraries = [], {}
    for line in (audit / 'surface_candidates.jsonl').read_text().splitlines():
        row = json.loads(line)
        if sha(row['code']) != row['code_sha256']:
            raise ValueError('Surface source changed')
        category, reason = context(row)
        result = {**row, 'context_disposition': category, 'reason': reason,
                  'semantic_verification_claimed': False, 'external_execution': 'not_run'}
        if category == 'current_program_example':
            library = example_libraries.setdefault(row['origin'], dict(frozen['definitions']))
            result['example_context'] = 'earlier literal workflow saves in this document, never executed'
            result['current_check'] = static_check(row['code'], registry, library, edition=2)
            # A later call example depends on the definition just shown under Save.
            # Only unconditional top-level literal saves establish this document context.
            from ibl_v2_parser import parse
            from ibl_v2_store import definition_name
            nodes = (parse(row['code']).data['statements']
                     if result['current_check']['status'] in ('valid', 'incomplete') else [])
            for node in nodes:
                if node.kind != 'call' or (node.data['node'], node.data['action']) != ('self', 'workflow'):
                    continue
                fields = node.data['params'].data.get('fields', {})
                op, code = fields.get('op'), fields.get('code')
                if (op and op.kind == 'literal' and op.data['value'] == 'save'
                        and code and code.kind == 'literal' and isinstance(code.data['value'], str)):
                    source = code.data['value']
                    checked = static_check(source, registry, library, edition=2)
                    if checked['status'] in ('valid', 'incomplete'):
                        library[definition_name(source)] = source
                        result['declared_example_source_sha256'] = sha(source)
        rows.append(result)
    target = audit / 'surface_dispositions.jsonl'
    target.write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in rows))
    report = {'candidates': len(rows), 'unclassified_contexts': 0,
              'contexts': dict(Counter(r['context_disposition'] for r in rows)),
              'current_examples_static': dict(Counter(r['current_check']['status'] for r in rows if 'current_check' in r)),
              'semantic_verification_claimed': False, 'ledger_sha256': sha(target.read_bytes()),
              'scope': 'Snapshot surfaces only. Old guide snippets are context-labelled, not fully migrated. External apps/imports not traversed.'}
    dump(audit / 'surface_disposition_summary.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    args = parser.parse_args()
    print(json.dumps(classify(args.snapshot), ensure_ascii=False, indent=2))
