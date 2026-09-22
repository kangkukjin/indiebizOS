#!/usr/bin/env python3
"""실 로컬 인코더·운영 렌더러로 분야별 개발 질문을 재현한다. 응답 모델·라이브 DB 무접촉."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
import argparse  # noqa: E402
from collections import Counter  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import statistics  # noqa: E402
import time  # noqa: E402
from unittest.mock import patch  # noqa: E402
import yaml  # noqa: E402
import catalog_recall  # noqa: E402
import associative_recall  # noqa: E402
import tree_recall  # noqa: E402
from world_recall_store import WorldStore  # noqa: E402


def evaluate(root, cases):
    store = WorldStore(root)
    started = time.perf_counter()
    tree_recall.build_now(store)
    build_ms = (time.perf_counter() - started) * 1000
    ids = {e.id for e in store.snapshot.entries}
    results = []
    # World-only fixture: run the common flow with its real two world sources.
    sources = tuple(s for s in associative_recall.SOURCES if s.name in {"method_map", "world_memory"})
    events = []
    with patch.object(catalog_recall, 'get_base_path', return_value=root), \
         patch.object(catalog_recall, 'load_config', return_value={}), \
         patch.object(catalog_recall, '_record', events.append), \
         patch.object(associative_recall, 'SOURCES', sources), \
         patch.object(associative_recall, '_record_presented', lambda recall: None), \
         patch.object(associative_recall, '_print_summary', lambda recall: None):
        for case in cases:
            q = case['query']
            started = time.perf_counter()
            events.clear()
            recall = associative_recall.begin(None, q, history=[])
            recall.route('THINK')
            blocks = {b.source: b for b in recall.blocks}
            lexical = blocks['method_map'].text
            semantic = blocks['world_memory'].text
            event = next(e for e in events if e.get('channel') == 'world_memory')
            elapsed = (time.perf_counter() - started) * 1000
            lex_ids = blocks['method_map'].ids
            selected = set(lex_ids + event['ids'])
            accepted = set(case['acceptable_ids'])
            results.append({**case, 'available_targets': sorted(ids & accepted),
                            'retrieval_status': event['status'], 'lexical_ids': lex_ids,
                            'semantic_ids': event['ids'], 'branches': event['branches'],
                            'hit': bool(selected & accepted),
                            'lexical': lexical, 'semantic': semantic,
                            'chars': len(lexical) + len(semantic), 'elapsed_ms': round(elapsed, 2)})
    failures = [r['id'] for r in results if r['retrieval_status'] != 'ok']
    return {'root': str(root), 'revision': store.snapshot.revision, 'entries': len(ids),
            'encoder': tree_recall.MODEL_NAME, 'build_ms': round(build_ms, 2),
            'cases': len(results), 'hits': sum(r['hit'] for r in results),
            'status_counts': dict(Counter(r['retrieval_status'] for r in results)),
            'operational_failures': failures,
            'p50_ms': round(statistics.median(r['elapsed_ms'] for r in results), 2),
            'max_chars': max(r['chars'] for r in results), 'results': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    os.environ.setdefault('INDIEBIZ_RECALL_INDEX_DIR', str(ROOT / 'outputs/world_map/recall_index'))
    cases = yaml.safe_load((ROOT / 'data/knowledge_catalog/recall_evaluation.yaml').read_text())['cases']
    current = WorldStore(ROOT)
    valid = {e.id for e in current.snapshot.entries}
    unknown = {i for c in cases for i in c['acceptable_ids'] if i not in valid}
    if unknown:
        raise ValueError(f'unknown expected IDs: {sorted(unknown)}')
    reports = []
    if args.baseline_root:
        reports.append(evaluate(args.baseline_root.resolve(), cases))
    reports.append(evaluate(ROOT, cases))
    report = {'kind': 'development_retrieval_comparison', 'blind_holdout': False,
              'response_model_calls': 0, 'behavioral_quality_measured': False,
              'note': '동일 편집자가 작성한 고정 진단. 동일 기본 예산, 실제 자동 주입 두 채널의 합집합에서 허용 개념 포함 여부.',
              'reports': reports}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    for r in reports:
        print(json.dumps({k: v for k, v in r.items() if k != 'results'}, ensure_ascii=False))
    return int(any(r['operational_failures'] for r in reports))


if __name__ == '__main__':
    raise SystemExit(main())
