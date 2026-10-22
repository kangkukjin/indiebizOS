"""Independent artifact comparison for the actual task-worker replay."""
import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-22_91회차_repair'
checks = []


def read(path):
    return json.loads(path.read_text())


def check(name, actual, expected):
    checks.append({'name': name, 'ok': actual == expected,
                   **({} if actual == expected else {'actual': actual, 'expected': expected})})


def initial():
    p = OUT / 'ai/T1'
    inputs = OUT / 'ai/inputs'
    records = read(inputs / 'records.json')['items']
    tasks = read(inputs / 'tasks.json')['items']
    receipts = read(inputs / 'receipts.json')['items']
    data = read(p / 'sub/data.json')['result']
    schedule = read(p / 'sub/schedule.json')['results']
    cost = read(p / 'sub/cost.json')['result']
    report = read(p / 'final_report.json')
    bad = []
    for r in records:
        failed = [k for k in ('checksum', 'searchable', 'accessible')
                  if r[k] != ('pass' if k == 'checksum' else True)]
        unknown = ['consent'] if r['consent'] != 'yes' else []
        if failed or unknown:
            bad.append({'id': r['id'], 'failed_conditions': failed, 'unknown_conditions': unknown})
    actual = [{k: r[k] for k in ('id', 'failed_conditions', 'unknown_conditions')}
              for r in data['remediation_list']]
    check('T1 all record remediation and gates', actual, bad)
    check('T1 record count', data['reconciliation']['record_count'], len(records))
    check('T1 eligible', data['status_totals']['충족'], len(records) - len(bad))
    check('T1 no missing IDs', data['reconciliation']['missing_ids'], [])
    done = sorted({r['task_id'] for r in receipts if r['reported_done'] and r['verified']})
    check('T1 all completed tasks', schedule['status_ids']['완료'], done)
    check('T1 all task coverage', sorted(r['id'] for r in schedule['task_status']), sorted(t['id'] for t in tasks))
    ready = sorted(t['id'] for t in tasks if t['id'] not in done and set(t['depends']) <= set(done))
    check('T1 all ready tasks', schedule['ready_ids'], ready)
    check('T1 required completion', schedule['required']['done'], 9)
    check('T1 total cost', cost['total'], sum(t['cost'] for t in tasks))
    check('T1 required cost', cost['required']['cost'], sum(t['cost'] for t in tasks if not t['optional']))
    check('T1 launch blocked', report['verdict']['개통_가능'], False)
    check('T1 deadline unknown', report['schedule']['기한']['judgment'], '확정 불가')
    for name in ('data', 'schedule', 'cost', 'ops'):
        artifact = read(p / f'sub/{name}.json')
        for source in artifact['source_files']:
            expected = hashlib.sha256(Path(source['path']).read_bytes()).hexdigest()
            observed = source.get('sha256_recomputed', source.get('recomputed_sha256', source.get('sha256')))
            check(f'T1 {name} input {Path(source["path"]).name}', observed, expected)
    conn = sqlite3.connect(f'file:{ROOT / "projects/L91_repair_ai/conversations.db"}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    root = read(OUT / 'runs/ai_T1_accepted.json')['task_id']
    rows = [dict(r) for r in conn.execute('SELECT task_id,parent_task_id,status,worker_session FROM tasks')]
    children = [r for r in rows if r['parent_task_id'] == root]
    grandchildren = [r for r in rows if r['parent_task_id'] in {c['task_id'] for c in children}]
    check('T1 actual child count', len(children), 3)
    check('T1 actual redelegation', len(grandchildren), 1)
    check('T1 separate worker sessions', len({r['worker_session'] for r in children + grandchildren}), 4)
    check('T1 workers terminal', all(r['status'] == 'completed' for r in children + grandchildren), True)
    conn.close()


def changed():
    p = OUT / 'ai/T2'
    tasks = read(OUT / 'ai/inputs/tasks.json')['items']
    required = [t for t in tasks if not t['optional']]
    schedule = read(p / 'sub/schedule.json')['results']
    cost = read(p / 'sub/cost.json')['result']
    ops = read(p / 'sub/ops.json')['result']
    report = read(p / 'final_report.json')
    check('T2 final launch blocked', report['verdict']['개통_가능'], False)
    check('T2 final budget', [report['budget']['예산'], report['budget']['범위_내_tasks_cost'],
                            report['budget']['부족액']], [3200000, 3390000, 190000])
    check('T2 final records reused', report['data_status']['totals'],
          read(OUT / 'ai/T1/final_report.json')['data_status']['totals'])
    check('T2 final no missing result', report['results_not_arrived'], [])
    check('T2 cost', cost['total_in_scope'], sum(t['cost'] for t in required))
    check('T2 budget and deficit', [cost['budget'], cost['shortfall']], [3200000, 190000])
    check('T2 required preserved', sorted(t['id'] for t in schedule['task_status']), sorted(t['id'] for t in required))
    check('T2 cancelled only W6', schedule['excluded_ids'], sorted(t['id'] for t in tasks if t['optional']))
    check('T2 required completion', schedule['required']['done'], 9)
    check('T2 ready', schedule['ready_ids'], ['W1-03', 'W2-03', 'W3-03', 'W4-02', 'W5-03'])
    check('T2 operations excluded', ops['scope_after_policy']['options_excluded'], ['O2', 'O3'])
    check('T2 original record judgment reused', ops['records_judgement_reused']['re_verified'], False)
    before = read(OUT / 'runs/T1_snapshot.json')
    for name, digest in before.items():
        check('T1 preserved ' + name, hashlib.sha256((OUT / 'ai/T1' / name).read_bytes()).hexdigest(), digest)
    conn = sqlite3.connect(f'file:{ROOT / "projects/L91_repair_ai/conversations.db"}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute('SELECT task_id,parent_task_id,status,worker_session FROM tasks')]
    root = read(OUT / 'runs/ai_T2_accepted.json')['task_id']
    children = [r for r in rows if r['parent_task_id'] == root]
    grandchildren = [r for r in rows if r['parent_task_id'] in {c['task_id'] for c in children}]
    old = read(OUT / 'ai/T1/delegations.json')['delegations']
    old_children = {r['task_ref']['task_id'] for r in old if r['request_id'] in ('L91-T1-cost', 'L91-T1-sched')}
    old_grandchildren = {r['task_ref']['task_id'] for r in old if r['request_id'] == 'L91-T1-ops'}
    check('T2 only two followup children', len(children), 2)
    check('T2 nested followup count', len(grandchildren), 1)
    check('T2 exact child sessions reused', sorted(r['worker_session'] for r in children),
          sorted(r['worker_session'] for r in rows if r['task_id'] in old_children))
    check('T2 exact grandchild session reused', [r['worker_session'] for r in grandchildren],
          [r['worker_session'] for r in rows if r['task_id'] in old_grandchildren])
    check('T2 no active child', all(r['status'] == 'completed' for r in children + grandchildren), True)
    for n in (1, 2):
        result = read(OUT / f'runs/ai_T{n}_result.json')
        check(f'T{n} parent finished', [result['state'], result['pending_children']], ['succeeded', 0])
    conn.close()


if __name__ == '__main__':
    initial()
    if (OUT / 'runs/ai_T2_result.json').exists():
        changed()
    result = {'passed': sum(c['ok'] for c in checks), 'failed': sum(not c['ok'] for c in checks), 'checks': checks}
    (OUT / 'runs/artifact_verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('passed', 'failed')}))
    print([c for c in checks if not c['ok']])
