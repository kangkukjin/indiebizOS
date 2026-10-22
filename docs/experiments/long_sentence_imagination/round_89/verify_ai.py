"""Compare independent AI artifacts with the fixed input oracle, without executing its code."""
import hashlib
import json
from pathlib import Path

import verify as reference

OUT, HERE = reference.OUT, reference.HERE
read, check, stamp = reference.read, reference.check, reference.stamp


def main():
    traces = []
    for phase in range(1, 5):
        root = OUT / 'ai' / f'T{phase}'
        if not (OUT / 'runs' / f'T{phase}_result.json').exists():
            continue
        result = read(OUT / 'runs' / f'T{phase}_result.json')
        tag = f'AI T{phase}:'
        check(tag + 'terminal', result['state'], 'succeeded')
        check(tag + 'children', result.get('pending_children'), 0)
        o = reference.oracle(phase)
        a = read(root / 'A_records.json')
        b = read(root / 'B_budget.json')
        c = read(root / 'C2_schedule.json')
        s = read(root / 'S_synthesis.json')
        if 'integrity' in a:
            actual_count = a['integrity']['actual']
            actual_missing = a['integrity']['missing_ids']
            actual_version = a['data_version']
        else:
            actual_count = a['coverage']['in_version']
            actual_missing = sorted({rid for gate in a['gates'].values() for rid in gate.get('not_in_version_ids', [])})
            versions = [v['version'] for v in a['version_comparison'].values() if isinstance(v, dict) and isinstance(v.get('version'), int)]
            actual_version = max(versions)
        check(tag + 'record count', actual_count, len(o['flags']))
        check(tag + 'record missing', actual_missing, o['missing'])
        check(tag + 'record version', actual_version, o['version'])
        check(tag + 'eligible', a['record_verdicts']['usable'], sum(r['eligible'] for r in o['flags']))
        for actual, expected in [('consent', 'consent'), ('checksum', 'checksum'), ('searchable', 'search'), ('accessible', 'access')]:
            gate = a['gates'][actual]
            check(tag + 'gate IDs ' + actual, sorted(set(gate['fail_ids'] + gate['unknown_ids']) - set(o['missing'])),
                  sorted(r['id'] for r in o['flags'] if r[expected]))
        bad = []
        unknown = []
        for row in o['flags']:
            failures = [key for key, short in [('checksum', 'checksum'), ('searchable', 'search'), ('accessible', 'access')] if row[short]]
            unconfirmed = ['consent'] if row['consent'] else []
            if failures:
                bad.append({'id': row['id'], 'failed': failures, 'unknown': unconfirmed})
            elif unconfirmed:
                unknown.append(row['id'])
        check(tag + 'failure records all', [{k: r[k] for k in ('id', 'failed', 'unknown')} for r in a['not_usable']], bad)
        unconfirmed_ids = a.get('unconfirmed_ids', [r['id'] for r in a.get('unconfirmed', [])])
        check(tag + 'consent only unconfirmed', sorted(set(unconfirmed_ids) - set(o['missing'])), sorted(unknown))
        check(tag + 'budget cost', b.get('tasks_total_cost', b.get('in_scope_cost')), o['cost'])
        check(tag + 'budget', b['budget'], o['budget'])
        if phase > 1:
            check(tag + 'shortfall', b['shortfall'], 190000)
            check(tag + 'cancelled', b['excluded_tasks'], o['cancelled'])
        check(tag + 'ready', sorted(c['ready']), sorted(o['ready']))
        expected_tasks = {}
        for task in o['states']:
            if task['status'] == 'cancelled':
                continue
            expected_tasks[task['id']] = 'done' if task['status'] == 'verified_done' else 'ready' if task['id'] in o['ready'] else 'blocked'
        check(tag + 'task states all', {t['task']: t['state'] for t in c['task_states'] if t['state'] != 'cancelled'}, expected_tasks)
        decision = s.get('final_verdict', s.get('open_readiness', {}))
        check(tag + 'launch decision', decision['open_ready'], False)
        check(tag + 'report exists', (root / '검토서.md').exists(), True)
        report = (root / '검토서.md').read_text()
        check(tag + 'report no launch', '개통 불가' in report or '개통 보류' in report, True)
        check(tag + 'report cost', str(o['cost']) in report.replace(',', ''), True)
        if phase == 3:
            check(tag + 'report missing id', 'D1800' in report and '미확인' in report, True)
        manifest = read(root / 'manifest.json')
        for name, digest in manifest['artifacts'].items():
            check(tag + 'manifest ' + name, hashlib.sha256((root / name).read_bytes()).hexdigest(), digest)
        log = read(root / 'run_log.json')
        jobs = {j['job']: j for j in log['jobs']}
        for name, job in jobs.items():
            check(tag + 'duration ' + name, stamp(job['ended_at']) >= stamp(job['started_at']), True)
            for parent in job.get('upstream', []):
                if parent in jobs:
                    check(tag + 'dependency ' + parent + '>' + name, stamp(job['started_at']) >= stamp(jobs[parent]['ended_at']), True)
        overlapping = [[left, right] for i, left in enumerate(jobs) for right in list(jobs)[i+1:]
                       if max(stamp(jobs[left]['started_at']), stamp(jobs[right]['started_at'])) < min(stamp(jobs[left]['ended_at']), stamp(jobs[right]['ended_at']))]
        traces.append({'phase': phase, 'overlap_pairs': overlapping, 'reused': log.get('reused', log.get('preserved')), 'recomputed': log.get('recomputed', log.get('reprocessed', log.get('updated'))), 'stages': log.get('stages')})
        if phase == 2:
            check(tag + 'A identical T1', (root / 'A_records.json').read_bytes(), (OUT / 'ai/T1/A_records.json').read_bytes())
        if phase >= 3:
            for name in ['B_budget.json', 'C1_graph.json', 'C2_schedule.json', 'R_receipts.json']:
                check(tag + 'unchanged ' + name, (root / name).read_bytes(), (OUT / 'ai/T2' / name).read_bytes())
        snapshot = OUT / 'snapshots' / f'T{phase}'
        for previous in range(1, phase):
            for file in (snapshot / f'T{previous}').rglob('*'):
                if file.is_file():
                    check(tag + 'preserved ' + str(file.relative_to(snapshot)), hashlib.sha256((OUT / 'ai' / file.relative_to(snapshot)).read_bytes()).hexdigest(), hashlib.sha256(file.read_bytes()).hexdigest())
    checks = reference.checks
    result = {'passed': sum(c['ok'] for c in checks), 'failed': sum(not c['ok'] for c in checks), 'checks': checks, 'traces': traces,
        'interpretation': 'AI는 consent=missing을 미확인으로 세분화한다. 입력 부재와 조건 미충족을 구분하며 모든 부적합 ID와 근거를 대조한다. 사후에 합격 기준을 완화한 것이 아니라 상태 명칭을 공통 의미로 대응한 것이다.'}
    (OUT / 'runs/ai_verification_full.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    compact = {**result, 'checks': {'passed_names': [c['name'] for c in checks if c['ok']], 'failures': [c for c in checks if not c['ok']]}}
    (HERE / 'ai_verification.json').write_text(json.dumps(compact, ensure_ascii=False))
    print(json.dumps({k: v for k, v in result.items() if k not in ('checks', 'traces')}, ensure_ascii=False))
    print(json.dumps([c for c in checks if not c['ok']], ensure_ascii=False)[:6000])


if __name__ == '__main__':
    main()
