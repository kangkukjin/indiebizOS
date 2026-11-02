"""Audit persisted acceptance results; no additional model calls."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
import hashlib
import json


def read(path):
    data = path.read_bytes()
    return json.loads(data), {'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(data).hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--initial', type=Path, required=True)
    parser.add_argument('--followup', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    initial, first_ref = read(args.initial.resolve())
    followup, next_ref = read(args.followup.resolve())
    results, calls, runs = {}, [], []
    for label, run, ref in [('initial', initial, first_ref), ('followup', followup, next_ref)]:
        usage = run['calls']
        runs.append({'label': label, 'artifact': ref, 'elapsed_s': run['elapsed_s'],
                     'provider': run['manifest']['provider'], 'model': run['manifest']['model'],
                     'calls': len(usage), 'limits': run['manifest']['limits'],
                     'input': sum(c['usage'].get('total_input_tokens', 0) for c in usage),
                     'output': sum(c['usage'].get('total_output_tokens', 0) for c in usage),
                     'cache_read_subset': sum(c['usage'].get('total_cache_read_tokens', 0) for c in usage)})
        for index, call in enumerate(usage):
            calls.append({'run': label, 'index': index, 'elapsed_s': call['elapsed_s'],
                          'usage': call['usage'], 'billable': call.get('billable'),
                          'error': call['error'], 'failure': call['failure']})
    source = initial['results']
    for name, expected in [('author', 60), ('changed_input', 72), ('baseline', 72)]:
        row = source[name]
        results[name] = {'correct': row['execution'].get('success') and row['execution'].get('value') == expected,
                         'value': row['execution'].get('value'), 'expected': expected,
                         'reuse': row.get('recall_usage')}
    row = source['composition']
    expected = {'first': 72, 'second': 45, 'rate': 3}
    results['composition'] = {'correct': row['execution'].get('success') and row['execution'].get('value') == expected,
        'value': row['execution'].get('value'), 'expected': expected, 'reuse': row['recall_usage'],
        'original_harness_correct': row['correct'],
        'oracle_note': 'Initial oracle accepted scalar 3 only; request allowed a record. '
                       'Audit checks all three independently calculated values; original artifact remains intact.'}
    results['distillation'] = source['distillation']
    results['initial_steering'] = {'status': 'rejected', 'reason': source['steering_error'],
                                 'guide_in_prompt': False}
    for name in ('completion', 'contradiction'):
        results['initial_' + name] = {'statuses': [r['decision']['status'] for r in source[name]['decisions']],
                                     'final_reason': source[name]['decisions'][-1]['decision']['reason']}
    source = followup['results']
    row = source['steering']
    actual, resumed = row['execution'][0], row['resumed']
    identities = lambda out: [(e['kind'], e['id'], e.get('action')) for e in out['evidence'] if e.get('action') == 't:send']
    results['steering'] = {'correct': actual.get('success') and resumed.get('success') and
                          actual.get('value') == 20 and resumed.get('value') == 20 and row['effects'] == [41],
                          'guide_in_prompt': True, 'decision': row['decision'], 'accepted': row['accepted'],
                          'requests': row['after']['progress']['requests'], 'value': actual.get('value'),
                          'effects': row['effects'], 'original_run': actual['resume'], 'resumed_run': resumed['resume'],
                          'same_effect_coordinate': identities(actual) == identities(resumed),
                          'effect_coordinates': identities(actual)}
    for name, expected in [('completion', 'APPROVED'), ('contradiction', 'REWORK')]:
        row = source[name]
        statuses = [r['decision']['status'] for r in row['decisions']]
        results[name] = {'correct': statuses == ['UNKNOWN', expected] and len(row['recovered']) == 1,
                         'statuses': statuses, 'recovered': row['recovered']}
    output = {'runs': runs, 'calls': calls, 'results': results,
              'total_observed_tokens': sum(r['input'] + r['output'] for r in runs),
              'unmeasured_calls': sum(not c['usage'].get('total_requests') for c in calls),
              'limits': ['Synthetic tasks; production primitives with isolated data, not a full user-agent benchmark.',
                         'Lexical discovery uses production search_aliased(alpha=0), not semantic-embedding quality.',
                         'No claim of automatic growth: distillation selected no examples.',
                         'One baseline pair; no general cost or long-term learning improvement claim.',
                         'Actual user corrections, money and reasoning tokens were not measured.']}
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(json.dumps({'total_observed_tokens': output['total_observed_tokens'],
                      'correct': {k: v['correct'] for k, v in results.items() if 'correct' in v}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
