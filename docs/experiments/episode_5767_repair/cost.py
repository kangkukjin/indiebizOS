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
from collections import Counter
from common.value_semantics import numeric_value


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


def aggregate(database, episode_id):
    with sqlite3.connect(f'file:{database}?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        episode = dict(conn.execute('SELECT id,task_id,run_id,started_at,ended_at,total_ms '
                                    'FROM episode_log WHERE id=?', (episode_id,)).fetchone())
        rows = [dict(r) for r in conn.execute("SELECT * FROM trajectory_event WHERE kind LIKE 'model.%'")]
    for row in rows:
        row['data'] = json.loads(row['data'])
    # Ancestry joins use persisted identities, never timing proximity or prose.
    selected = [r for r in rows if r['episode_id'] == episode_id]
    ids = {r['data'].get('call_id') for r in selected} - {None}
    runs = {episode['run_id']}
    while True:
        joined = [r for r in rows if r['episode_id'] == episode_id or r['run_id'] in runs
                  or r['parent_run_id'] in runs or r['data'].get('parent_call_id') in ids
                  or r['data'].get('call_id') in ids]
        next_ids = ids | {r['data'].get('call_id') for r in joined} - {None}
        next_runs = runs | {r['run_id'] for r in joined} - {None, ''}
        if next_ids == ids and next_runs == runs:
            selected = joined
            break
        ids, runs = next_ids, next_runs
    started, finished, billed = {}, {}, set()
    seen, unique, duplicates, conflicts = {}, [], 0, []
    for row in selected:
        data, kind = row['data'], row['kind']
        cid = data.get('call_id')
        if kind == 'model.call_started':
            started[cid] = data
        elif kind == 'model.call_finished':
            finished[cid] = data
        if kind != 'model.usage' or data.get('accounting') != 'billable_usage':
            continue  # response snapshots and boundary timings are not new charges.
        key = (cid, data.get('round_index')) if cid else (row['run_id'], row['event_seq'])
        charges = {k: data.get(k) for k in ('input', 'output', 'cache_read', 'cache_create')}
        if key in seen:
            if seen[key] == charges:
                duplicates += 1
            else:
                conflicts.append({'identity': key, 'first': seen[key], 'other': charges})
            continue
        seen[key] = charges
        unique.append(data)
        if cid:
            billed.add(cid)
    measured, roles, invalid = Counter(), {}, []
    for row in unique:
        role = roles.setdefault(row.get('role', 'unknown'), {'records': 0, 'input': 0, 'output': 0, 'cache_read': 0})
        role['records'] += 1
        for key in ('input', 'output', 'cache_read', 'cache_create'):
            number = numeric_value(row.get(key))
            if number is None or number < 0:
                invalid.append({'call_id': row.get('call_id'), 'field': key})
                continue
            measured[key] += number
            if key in role:
                role[key] += number
    unknown = [{'call_id': cid, 'role': data.get('role'), 'phase': data.get('phase'),
                'reason': 'finished_without_usage' if cid in finished else 'unfinished_call'}
               for cid, data in started.items() if cid not in billed]
    return {'episode': episode, 'joined_runs': sorted(runs), 'billable_records': len(unique),
            'duplicates_removed': duplicates, 'conflicts': conflicts, 'measured': dict(measured),
            'input_plus_output': measured['input'] + measured['output'], 'roles': roles,
            'calls_started': len(started), 'calls_finished': len(finished), 'unmeasured_calls': unknown,
            'unattributed_usage': sum(not r.get('call_id') for r in unique), 'invalid_fields': invalid,
            'usage_partial': [r['data'].get('call_id') for r in selected if r['data'].get('usage_partial')],
            'complete': False,
            'limitations': ['Unbound subprocess experiments cannot be assigned without call/run identities.',
                            'Cache read is a subset of input; never added again.',
                            'Only episode.total_ms is wall time; parallel call latencies are not summed.',
                            'Missing usage and conflicting records are not replaced with zero.'],
            'user_corrections': None}


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
