#!/usr/bin/env python3
"""저장된 실험의 지표 집계와 첫 생성 코드의 수정 전후 재생(모델 호출 없음)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import statistics
import subprocess

from idiom_experiment import dump, ARMS


def metrics(trials):
    attempts = [a for r in trials for a in r['attempts']]
    usage = [a['model'].get('usage') or {} for a in attempts]
    return {
        'trials': len(trials),
        'first_pass': sum(r['attempts'][0]['execution']['quality_ok'] for r in trials),
        'final_pass': sum(r['quality_ok'] for r in trials),
        'repairs': len(attempts) - len(trials),
        'named_first_trials': sum(bool(r['attempts'][0]['execution'].get('observed', {}).get('fn_calls')) for r in trials),
        'output_tokens': sum(u.get('output_tokens', 0) for u in usage),
        'input_tokens': sum(u.get('input_tokens', 0) for u in usage),
        'cache_creation_input_tokens': sum(u.get('cache_creation_input_tokens', 0) for u in usage),
        'cache_read_input_tokens': sum(u.get('cache_read_input_tokens', 0) for u in usage),
        'model_wall_s': round(sum(a['model']['wall_ms'] for a in attempts) / 1000, 3),
        'median_trial_model_wall_s': round(statistics.median(
            sum(a['model']['wall_ms'] for a in r['attempts']) / 1000 for r in trials), 3),
        'leaf_calls': sum(len(a['execution'].get('observed', {}).get('leaf_calls', [])) for a in attempts),
    }


def replay(trial, catalogs, suite='legacy'):
    result = {'id': trial['id'], 'case': trial['case'], 'arm': trial['arm'],
              'original_first_pass': trial['attempts'][0]['execution']['quality_ok']}
    for label, catalog in catalogs.items():
        req = {'code': trial['attempts'][0]['code'], 'case_id': trial['case'],
               'named': trial['arm'] != 'none', 'catalog': catalog, 'suite': suite}
        p = subprocess.run([sys.executable, str(ROOT / 'scripts/idiom_experiment_worker.py')],
                           input=json.dumps(req), text=True, capture_output=True, timeout=30, cwd=ROOT)
        if p.returncode:
            raise RuntimeError(p.stderr[-1500:])
        result[label] = json.loads(p.stdout)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('out', type=Path)
    p.add_argument('--replay', action='store_true')
    a = p.parse_args()
    trials = [json.loads(f.read_text()) for f in sorted((a.out / 'trials').glob('*.json'))]
    if not trials:
        p.error('trial이 없습니다')
    summary = {'arms': {}, 'cases': {}, 'trials': []}
    for arm in ARMS:
        subset = [r for r in trials if r['arm'] == arm]
        if subset:
            summary['arms'][arm] = metrics(subset)
    for case in sorted({r['case'] for r in trials}):
        summary['cases'][case] = {
            arm: metrics(subset) for arm in ARMS
            if (subset := [r for r in trials if r['case'] == case and r['arm'] == arm])}
    summary['models'] = sorted({m for r in trials for t in r['attempts']
                                for m in (t['model'].get('modelUsage') or {})})
    for r in trials:
        summary['trials'].append({'id': r['id'], 'first_pass': r['attempts'][0]['execution']['quality_ok'],
                                  'final_pass': r['quality_ok'], 'metrics': metrics([r])})
    dump(a.out / 'summary.json', summary)
    print(json.dumps(summary['arms'], ensure_ascii=False, indent=2))
    if a.replay:
        catalogs = {'baseline': json.loads((a.out / 'catalog.json').read_text()),
                    'repaired': json.loads((ROOT / 'data/idioms/curated.json').read_text())}
        with ThreadPoolExecutor(max_workers=2) as pool:
            suite = json.loads((a.out / 'manifest.json').read_text()).get('suite', 'legacy')
            rows = list(pool.map(lambda r: replay(r, catalogs, suite), trials))
        payload = {'mode': '同一 first-attempt code; fresh fixture per execution; no model generation',
                   'catalogs': catalogs, 'trials': rows,
                   'worker_sha256': hashlib.sha256((ROOT / 'scripts/idiom_experiment_worker.py').read_bytes()).hexdigest()}
        dump(a.out / 'repaired_replay.json', payload)
        for arm in ARMS:
            rs = [r for r in rows if r['arm'] == arm]
            print(arm, {label: sum(r[label]['quality_ok'] for r in rs) for label in catalogs})
        print('baseline mismatches:', sum(r['baseline']['quality_ok'] != r['original_first_pass'] for r in rows))


if __name__ == '__main__':
    main()
