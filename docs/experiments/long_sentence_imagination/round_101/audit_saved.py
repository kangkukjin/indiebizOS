"""101회차 보존 파일만 재집계한다. HTTP·DB·모델 호출이나 훈련 재실행 없음.

사용: PYTHONPATH=backend python3 audit_saved.py <보존 inputs 부모> <감사 JSON>
원본 collect/snapshot/ai_out/정답표는 읽기 전용으로 취급한다.
"""
import boot_paths  # noqa: F401

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from verify_coords import load_docs, verify_text


FIELDS = ('calls', 'input', 'cache_read', 'cache_create', 'output')


def sum_usage(rows):
    rows = list(rows)
    result = {field: sum(row[field] for row in rows) for field in FIELDS}
    result['input_less_reported_caches'] = (
        result['input'] - result['cache_read'] - result['cache_create'])
    return result


def audit(inputs):
    root = Path(__file__).resolve().parent
    by_turn = {}
    roles = []
    hashes = {}
    sources = json.loads((root / 'harness/sources.json').read_text())['sources']
    input_hashes = {}
    for source in sources:
        path = inputs.parent / source['file']
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != source['sha256']:
            raise ValueError(f"입력 사본 판본 불일치: {source['file']}")
        input_hashes[source['file']] = digest
    for name in ('A1', 'A2', 'B1', 'B2'):
        path = root / 'harness' / f'collect_{name}.json'
        hashes[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
        task = json.loads(path.read_text())['tasks'][0]
        by_role = task['usage_by_role']
        total = sum_usage(by_role.values())
        assert all(total[field] == task['usage_total'][field] for field in FIELDS)
        execution = sum_usage(v for k, v in by_role.items() if k.startswith('execution|'))
        other = sum_usage(v for k, v in by_role.items() if not k.startswith('execution|'))
        by_turn[name] = {'all_roles': total, 'execution': execution, 'other_roles': other}
        roles.extend(by_role.items())
    all_roles = sum_usage(v for _, v in roles)
    execution = sum_usage(v for k, v in roles if k.startswith('execution|'))
    other = sum_usage(v for k, v in roles if not k.startswith('execution|'))
    quotes = {}
    snapshots = {}
    for group in ('A', 'B'):
        docs = load_docs(inputs / group)
        for path in sorted((root / 'ai_out' / group).glob('*.md')):
            name = str(path.relative_to(root))
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            quotes[name] = verify_text(path.read_text(), docs)
        before = json.loads((root / 'harness' / f'snapshot_{group}1.json').read_text())
        after = json.loads((root / 'harness' / f'snapshot_{group}2.json').read_text())
        after_hashes = {row['file']: row['sha256'] for row in after['files']}
        snapshots[group] = {
            row['file']: (row['sha256'] == after_hashes.get(row['file']) ==
                          hashlib.sha256((root / 'ai_out' / group / row['file']).read_bytes()).hexdigest())
            for row in before['files']
        }
    quote_counts = Counter()
    coord_counts = Counter()
    for result in quotes.values():
        quote_counts.update(result['quote_status'])
        coord_counts.update(result['coordinate_status'])
    return {
        'scope': '101회차 보존 collect/snapshot/ai_out 재집계. 훈련·모델 재실행 없음.',
        'input_less_reported_caches_note': '기록된 input에서 cache_read/cache_create를 뺀 산술 잔여. 청구액이 아님.',
        'usage_by_turn': by_turn,
        'usage_all_roles': all_roles,
        'usage_execution_only': execution,
        'usage_other_roles': other,
        'other_input_percent': other['input'] / all_roles['input'] * 100,
        'latency_note': 'send_ai.seconds는 요청→종료 응답 회수. 파일 준비 시각이나 역할별 임계 경로 시간을 뜻하지 않음.',
        'original_files_preserved': snapshots,
        'coordinate_status': dict(coord_counts),
        'quote_status': dict(quote_counts),
        'citation_results': quotes,
        'source_sha256': hashes,
        'input_sha256': input_hashes,
        'operator_tokens': '미측정: 훈련 전체 총비용 불완전',
    }


def render_json(value, level=0):
    """좌표/구절 발생 한 건을 한 줄로 보존해 전건 증거의 중복 들여쓰기를 줄인다."""
    if isinstance(value, dict) and 'line' not in value:
        rows = [json.dumps(key, ensure_ascii=False) + ': ' + render_json(item, level + 1)
                for key, item in value.items()]
        opening, closing = '{', '}'
    elif isinstance(value, list):
        rows = [render_json(item, level + 1) for item in value]
        opening, closing = '[', ']'
    else:
        return json.dumps(value, ensure_ascii=False)
    if not rows:
        return opening + closing
    return opening + '\n' + ',\n'.join('  ' * (level + 1) + row for row in rows) + '\n' + '  ' * level + closing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = audit(args.inputs)
    args.output.write_text(render_json(result) + '\n')
    print(json.dumps({key: result[key] for key in (
        'usage_all_roles', 'usage_execution_only', 'other_input_percent',
        'coordinate_status', 'quote_status', 'original_files_preserved')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
