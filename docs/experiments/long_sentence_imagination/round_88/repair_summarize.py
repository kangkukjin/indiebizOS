"""Export measured repair results; raw tool bodies stay in local outputs."""
import collections
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BASE = ROOT / 'outputs/long_sentence_imagination/2026-10-22_88회차'
OUT = BASE.with_name(BASE.name + '_repair2')
FINAL = BASE.with_name(BASE.name + '_repair3')
SCOPE = BASE.with_name(BASE.name + '_repair4')


def read(folder, name):
    return json.loads((folder / name).read_text())


def measured(folder, expected_turns):
    captured = read(folder, 'runs/repair_summary.json')
    assert len(captured['turns']) == expected_turns
    rows = []
    totals = collections.Counter()
    models = {}
    for item in captured['turns']:
        label = item['turn']
        result = read(folder, f'runs/{label}_result.json')
        assert result['state'] == 'succeeded' and result['pending_children'] == 0
        total = collections.Counter()
        for usage in item['usage'].values():
            total.update(usage)
        totals.update(total)
        models[label] = item['models']
        row = {k: item[k] for k in ('turn', 'task_id', 'episodes', 'usage', 'tool_count',
                                    'full_tool_inputs', 'planning_tool_count', 'full_planning_inputs', 'context_compacted')}
        row.update(state=result['state'], pending_children=0,
                   evaluations=item['evaluations'], totals=dict(total),
                   session_new_count=sum('session=new' in s for s in item['sessions']))
        trainer_path = folder / f'runs/trainer_{label}.json'
        if trainer_path.exists():
            trainer = json.loads(trainer_path.read_text())
            response = trainer['response']
            row['trainer'] = {
                'success': response.get('success'), 'wall_seconds': trainer['seconds'],
                'run_id': response.get('resume', {}).get('run_id'),
                'usage': {k: response.get('usage', {}).get(k)
                          for k in ('steps', 'rows', 'elapsed_ms')},
            }
        rows.append(row)
    return {'turns': rows, 'totals': dict(totals), 'preservation': captured['preservation']}, models


def main():
    failed, failed_models = measured(BASE.with_name(BASE.name + '_repair'), 1)
    replay, replay_models = measured(OUT, 8)
    final, final_models = measured(FINAL, 3)
    scope, scope_models = measured(SCOPE, 1)
    checks = read(OUT, 'runs/repair_verification.json')
    final_checks = read(FINAL, 'runs/final_verification.json')
    scope_checks = read(SCOPE, 'runs/final_verification.json')
    (HERE / 'repair_scope_verification.json').write_text(json.dumps(scope_checks, ensure_ascii=False, indent=2))
    (HERE / 'repair_final_verification.json').write_text(json.dumps(final_checks, ensure_ascii=False, indent=2))
    (HERE / 'repair_verification.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2))
    evidence = {
        'round': 88, 'baseline_commit': '35c36b31',
        'first_candidate': failed, 'second_candidate': replay, 'checkpoint_candidate': final, 'final_scope_replay': scope,
        'accounting': 'model.usage/accounting=billable_usage; cache included in input',
        'codex_tokens': 'not measured',
        'second_candidate_start': read(OUT, 'start.json'),
        'second_candidate_sources': read(OUT, 'runs/repair_source_hashes.json'),
        'checkpoint_sources': read(FINAL, 'runs/repair_source_hashes.json'),
        'final_sources': read(SCOPE, 'runs/repair_source_hashes.json'),
        'seeded_history': read(FINAL, 'runs/seeded_history.json'),
        'checks': {'passed': checks['passed'], 'failed': checks['failed']},
        'checkpoint_checks': {k: final_checks[k] for k in ('passed', 'failed')},
        'final_checks': {k: scope_checks[k] for k in ('passed', 'failed')},
        'final_checks_file': 'repair_scope_verification.json',
        'behavior_audit': read(FINAL, 'runs/behavior_audit.json'),
        'final_behavior_audit': read(SCOPE, 'runs/behavior_audit.json'),
        'tests': read(HERE, 'repair_tests.json'),
        'final_seeded_history': read(SCOPE, 'runs/seeded_history.json'),
        'stop_T4': read(OUT, 'runs/agent_stop_T4.json'),
        'restart_T5': read(OUT, 'runs/agent_start_T5.json'),
        'second_stop': read(OUT, 'runs/agent_stop_final.json'),
        'checkpoint_stop': read(FINAL, 'runs/agent_stop_final.json'),
        'final_stop': read(SCOPE, 'runs/agent_stop_final.json'),
    }
    (HERE / 'repair_evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
    artifacts = {
        str(p.relative_to(OUT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ('ai', 'trainer') for p in sorted((OUT / folder).rglob('*')) if p.is_file()
    }
    artifacts.update({str(p.relative_to(OUT)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in sorted((OUT / 'runs').glob('T*_tool_inputs.json'))})
    artifacts.update({'checkpoint/' + str(p.relative_to(FINAL)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for folder in ('ai', 'runs') for p in sorted((FINAL / folder).rglob('*'))
                      if p.is_file() and (folder == 'ai' or p.name.endswith('_tool_inputs.json'))})
    artifacts.update({'scope/' + str(p.relative_to(SCOPE)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for folder in ('ai', 'runs') for p in sorted((SCOPE / folder).rglob('*'))
                      if p.is_file() and (folder == 'ai' or p.name.endswith('_tool_inputs.json'))})
    (HERE / 'repair_artifacts.json').write_text(json.dumps({
        'sha256': artifacts, 'models': {'first': failed_models, 'second': replay_models, 'checkpoint': final_models, 'final': scope_models}},
        ensure_ascii=False, indent=2))
    print(json.dumps({'first': failed['totals'], 'second': replay['totals'], 'checkpoint': final['totals'], 'final': scope['totals'],
                      'checks': evidence['checks']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
