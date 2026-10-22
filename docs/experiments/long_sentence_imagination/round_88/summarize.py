"""Export compact, allowlisted evidence after all eight turns finish."""
import collections
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-22_88회차'


def read(relative):
    return json.loads((OUT / relative).read_text())


def main():
    captured = read('runs/episode_summary.json')
    assert len(captured) == 8
    turns = []
    total = collections.Counter()
    roles = collections.defaultdict(collections.Counter)
    for n, item in enumerate(captured, 1):
        terminal = read(f'runs/T{n}_result.json')
        assert terminal['state'] in ('succeeded', 'failed', 'cancelled')
        assert terminal['pending_children'] == 0
        for role, usage in item['usage'].items():
            roles[role].update(usage)
            total.update(usage)
        trainer = read(f'runs/trainer_T{n}.json')
        response = trainer['response']
        turns.append({
            'turn': f'T{n}', 'task_id': item['task_id'],
            'state': terminal['state'], 'pending_children': terminal['pending_children'],
            'created_at_utc': terminal['created_at'],
            'completed_at_utc': terminal['completed_at'],
            'episodes': item['episodes'], 'usage_by_role': item['usage'],
            'tool_count': item['tool_count'],
            'session_observations': item['session_observations'],
            'context_compacted_events': item['event_kinds'].get('context.compacted', 0),
            'evaluations': item['event_kinds'].get('supervision.evaluation.finished', 0),
            'trainer': {
                'success': response.get('success'),
                'wall_seconds': trainer['seconds'],
                'run_id': response.get('resume', {}).get('run_id'),
                'usage': {k: response.get('usage', {}).get(k)
                          for k in ('steps', 'rows', 'elapsed_ms', 'limits')},
                'result': response.get('value'),
            },
        })
    conflict = read('runs/T6_decision_wait_conflict.json')
    checks = read('runs/verification.json')
    verification_path = HERE / 'verification.json'
    verification_path.write_text(json.dumps(checks, ensure_ascii=False, indent=2))
    evidence = {
        'round': 88, 'start': read('start.json'), 'turns': turns,
        'usage_totals': dict(total), 'usage_by_role': dict(roles),
        'accounting': 'model.usage/accounting=billable_usage; cache is included in input',
        'codex_usage': 'not measured', 'trainer_model_calls': 0,
        'verification': {
            'passed': checks['passed'], 'failed': checks['failed'],
            'path': 'verification.json',
            'sha256': hashlib.sha256(verification_path.read_bytes()).hexdigest(),
        },
        'actor_stop_after_T4': read('runs/agent_stop_T4.json'),
        'actor_start_before_T5': read('runs/agent_start_T5.json'),
        'actor_final_stop': read('runs/agent_stop_final.json'),
        'T4_evaluation': [
            {k: e['data']['decision'].get(k) for k in ('status', 'defects', 'repair_scope')}
            for e in read('runs/T4_evaluation_rework.json')
            if e['kind'] == 'supervision.evaluation.finished'
        ],
        'T6_decision_conflict': {
            'decision': conflict['decision'],
            'issue_actions': conflict['issue_actions'],
            'inspection_wait_task_ids': [r['item'] for r in conflict['inspection_waits']
                                         if r['kind'] == '작업 검수'],
        },
        'artifacts': {
            str(p.relative_to(OUT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ('ai', 'trainer') for p in sorted((OUT / folder).rglob('*'))
            if p.is_file()
        },
    }
    (HERE / 'evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
    print(json.dumps({'turns': len(turns), 'usage': dict(total),
                      'checks': {k: checks[k] for k in ('passed', 'failed')}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
