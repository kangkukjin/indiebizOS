"""Read-only completed-episode accounting; never reruns models to measure cost."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
import json
import sqlite3
import hashlib


def experiment_usage(directory):
    """Only primary probe results, not derived metrics or repeated control logs."""
    results = []
    names = ['controller_probe.json', 'controller_recovery_probe.json', 'controller_missing_probe.json',
             'evaluation_probe.json', 'transfer_probe.json', 'transfer_program_probe.json']
    for name in names:
        path = directory / name
        if not path.exists():
            results.append({'file': name, 'status': 'missing'})
            continue
        payload = path.read_bytes()
        records = []
        def walk(value, location=''):
            if isinstance(value, dict):
                usage = value.get('usage')
                if isinstance(usage, dict) and ('total_input_tokens' in usage or 'measured' in usage):
                    records.append({'location': location, 'usage': usage,
                                    'call_id': value.get('call_id'), 'run_id': value.get('run_id')})
                for key, item in value.items():
                    if key not in ('usage', 'control_events'):
                        walk(item, location + '/' + key)
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    walk(item, location + '/' + str(index))
        walk(json.loads(payload))
        results.append({'file': name, 'sha256': hashlib.sha256(payload).hexdigest(),
                        'status': 'unjoined', 'records': records})
    return {'files': results, 'added_to_episode_total': False,
            'reason': 'These persisted results lack common call/run identities; overlap is unresolved.'}


# 일반 연구 측정과 같은 소유 구현을 사용한다. 과거 실험 CLI는 호환한다.
from research_measurement import aggregate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--episode', type=int, default=5767)
    parser.add_argument('--database', type=Path, default=ROOT / 'data/world_pulse.db')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--research-artifacts', type=Path)
    args = parser.parse_args()
    result = aggregate(args.database, args.episode)
    if args.research_artifacts:
        result['separate_experiments'] = experiment_usage(args.research_artifacts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({k: result[k] for k in ('billable_records', 'input_plus_output', 'unmeasured_calls')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
