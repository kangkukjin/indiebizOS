"""Independent oracle comparison of the repair replay; never imports AI code."""
import hashlib
import json
from pathlib import Path

import verify as baseline

HERE = Path(__file__).resolve().parent
OUT = baseline.OUT.with_name(baseline.OUT.name + '_repair')
checks = []


def read(path):
    return json.loads(path.read_text())


def check(name, actual, expected):
    checks.append({'name': name, 'pass': actual == expected,
                   **({} if actual == expected else {'actual': actual, 'expected': expected})})


def main():
    for phase in range(1, 5):
        root = OUT / 'ai' / f'T{phase}'
        if not (OUT / 'runs' / f'T{phase}_result.json').exists():
            continue
        tag = f'T{phase} '
        ticket = read(OUT / 'runs' / f'T{phase}_result.json')
        check(tag + 'terminal', (ticket['state'], ticket['pending_children']), ('succeeded', 0))
        oracle = baseline.oracle(phase)
        data = read(root / 'reviews/data_gates.json')
        budget = read(root / 'reviews/budget.json')
        schedule = read(root / 'reviews/schedule.json')
        final = read(root / 'acceptance_review.json')
        check(tag + 'rows', data['rows_in_file'], len(oracle['flags']))
        check(tag + 'missing', data['integrity']['missing_ids'], oracle['missing'])
        check(tag + 'version', data['records_version'], oracle['version'])
        check(tag + 'usable', data['overall']['usable'], sum(r['eligible'] for r in oracle['flags']))
        for key, flag in [('consent', 'consent'), ('checksum', 'checksum'),
                          ('searchable', 'search'), ('accessible', 'access')]:
            gate = data['per_gate'][key]
            check(tag + 'gate ids ' + key,
                  sorted(set(gate['fail_ids'] + gate['unknown_ids']) - set(oracle['missing'])),
                  sorted(r['id'] for r in oracle['flags'] if r[flag]))
        fail_ids = [r['id'] for r in oracle['flags'] if r['checksum'] or r['search'] or r['access']]
        unknown_ids = [r['id'] for r in oracle['flags'] if r['consent'] and r['id'] not in fail_ids]
        check(tag + 'failed ids', sorted(data['overall']['not_usable_ids']), sorted(fail_ids))
        check(tag + 'unknown ids', sorted(data['overall']['unknown_ids']), sorted(unknown_ids + oracle['missing']))
        check(tag + 'cost', budget['total_cost'], oracle['cost'])
        check(tag + 'budget', budget['budget'], oracle['budget'])
        check(tag + 'done ids', schedule['done'], sorted(r['id'] for r in oracle['states'] if r['status'] == 'verified_done'))
        check(tag + 'ready ids', sorted(schedule['ready'] + schedule['reported_unverified']), sorted(oracle['ready']))
        expected_status = {r['id']: 'done' if r['status'] == 'verified_done' else
                           'reported_unverified' if r['status'] == 'unverified' else
                           'ready' if r['id'] in oracle['ready'] else 'waiting'
                           for r in oracle['states'] if r['status'] != 'cancelled'}
        check(tag + 'all task states', schedule['status'], expected_status)
        check(tag + 'required remaining', schedule['remaining']['tasks_required'], 51)
        check(tag + 'not open', '개통 불가' in final['verdict'], True)
        check(tag + 'required completed', final['acceptance_check']['required_tasks_done_with_receipts']['detail'], {'required': 60, 'done': 9})
        check(tag + 'report exists', (root / '인수검토서.md').is_file(), True)
        ledger = read(root / 'run_ledger.json')
        reuse = ['data_gates'] if phase == 2 else ['budget', 'schedule', 'operations'] if phase >= 3 else []
        for name in reuse:
            check(tag + 'reused status ' + name, ledger['reviews'][name]['status'], 'reused')
            current = root / 'reviews' / (name + '.json')
            previous = OUT / 'ai' / f'T{phase-1}' / 'reviews' / (name + '.json')
            check(tag + 'reused bytes ' + name, hashlib.sha256(current.read_bytes()).hexdigest(),
                  hashlib.sha256(previous.read_bytes()).hexdigest())
        for name, job in ledger['reviews'].items():
            file = root / 'reviews' / (name + '.json')
            check(tag + 'output hash ' + name, hashlib.sha256(file.read_bytes()).hexdigest(), job['output_sha256'])
            check(tag + 'time order ' + name, job['started_at'] <= job['ended_at'] <= ledger['merge']['started_at'], True)
        for previous in range(1, phase):
            snap = OUT / 'snapshots' / f'T{phase}' / f'T{previous}'
            for path in snap.rglob('*'):
                if path.is_file():
                    current = OUT / 'ai' / f'T{previous}' / path.relative_to(snap)
                    check(tag + 'preserved ' + str(current.relative_to(OUT / 'ai')),
                          hashlib.sha256(current.read_bytes()).hexdigest(), hashlib.sha256(path.read_bytes()).hexdigest())
    result = {'passed': sum(c['pass'] for c in checks), 'failed': sum(not c['pass'] for c in checks), 'checks': checks}
    (OUT / 'runs/repair_verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != 'checks'}, ensure_ascii=False))
    print(json.dumps([c for c in checks if not c['pass']], ensure_ascii=False))


if __name__ == '__main__':
    main()
