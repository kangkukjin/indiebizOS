#!/usr/bin/env python3
"""실제 두 세계지도 주입 경로의 용량 진단. 합성 증량은 검색 품질 평가가 아니다."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
import argparse  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import statistics  # noqa: E402
import time  # noqa: E402
import yaml  # noqa: E402
from knowledge_catalog import load_snapshot, build_index, _phrase_pattern  # noqa: E402
from evaluate_world_map_recall import evaluate  # noqa: E402


def fixture(output, count):
    """원본은 보존. 파생 진단 폴더에 고유 표제·별칭의 합성 항목만 증량한다."""
    target = output / f'synthetic_{count}'
    for relative in ('data/knowledge_catalog', 'docs/world_map', 'data/guides'):
        shutil.copytree(ROOT / relative, target / relative, dirs_exist_ok=True)
    snapshot = load_snapshot(ROOT)
    rows = []
    for n in range(max(0, count - len(snapshot.entries))):
        entry = snapshot.entries[n % len(snapshot.entries)]
        suffix = f' 용량시험{n:05d}'
        rows.append(dict(id=f'scale.synthetic.{n}', kind=entry.kind, path=list(entry.path),
                         name=entry.name[:40] + suffix, hint=entry.hint,
                         aliases=[a[:40] + suffix for a in entry.aliases],
                         source={'path': entry.source}))
    relative = 'data/knowledge_catalog/scale_synthetic.yaml'
    (target / relative).write_text(json.dumps({'entries': rows}, ensure_ascii=False))
    world = target / 'data/knowledge_catalog/world.yaml'
    doc = yaml.safe_load(world.read_text())
    doc['fragments'].append(relative)
    world.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False))
    return target


def run(root, cases, index_dir):
    os.environ['INDIEBIZ_RECALL_INDEX_DIR'] = str(index_dir)
    started = time.perf_counter()
    snapshot = load_snapshot(root)
    build_index(root)
    catalog_ms = (time.perf_counter() - started) * 1000
    _phrase_pattern.cache_clear()
    cold = evaluate(root, cases[:1])
    # Same representative questions, three passes, with a warm model and index.
    warm = evaluate(root, cases * 3)
    times = sorted(r['elapsed_ms'] for r in warm['results'])
    import numpy as np
    with np.load(index_dir / 'world.npz') as vectors:
        vector_bytes = vectors['vecs'].nbytes
    return {'entries': len(snapshot.entries), 'catalog_build_ms': round(catalog_ms, 2),
            'encoder_index_build_ms': cold['build_ms'],
            'cold_lexical_cache_first_turn_ms': cold['results'][0]['elapsed_ms'],
            'warm_turns': len(times), 'p50_ms': round(statistics.median(times), 2),
            'p95_ms': times[min(len(times) - 1, int(len(times) * .95))],
            'max_ms': max(times), 'max_injected_chars': warm['max_chars'],
            'vector_bytes': vector_bytes,
            'regex_cache': _phrase_pattern.cache_info()._asdict(),
            'operational_failures': cold['operational_failures'] + warm['operational_failures']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--count', type=int, default=10000)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.count <= len(load_snapshot(ROOT).entries):
        parser.error('--count must exceed the real catalog size')
    cases = yaml.safe_load((ROOT / 'data/knowledge_catalog/recall_evaluation.yaml').read_text())['cases'][::2]
    reports = []
    for label, root in [('real', ROOT), ('synthetic_capacity_only', fixture(output, args.count))]:
        report = {'kind': label, **run(root, cases, output / f'index_{label}')}
        reports.append(report)
        print(json.dumps(report, ensure_ascii=False), flush=True)
        (output / 'scale.json').write_text(json.dumps({
            'response_model_calls': 0, 'synthetic_quality_measured': False,
            'note': '실제 인코더와 공통 주입 흐름. 합성 항목은 반복 개념에 고유 표제·별칭을 붙인 부하이며 지식 확장이 아니다. 전체 작업 응답 시간과 구별.',
            'reports': reports}, ensure_ascii=False, indent=2) + '\n')
    return int(any(r['operational_failures'] for r in reports))


if __name__ == '__main__':
    raise SystemExit(main())
