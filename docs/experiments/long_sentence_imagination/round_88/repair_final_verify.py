"""Verify checkpoint replay against fixed fixture facts and preserved source evidence."""
import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-22_88회차_repair3'
checks = []


def check(name, passed, detail=None):
    checks.append({'check': name, 'pass': bool(passed), 'detail': detail})


def read(name):
    return json.loads((OUT / name).read_text())


end_file = OUT / 'runs/repair_source_end_hashes.json'
end = json.loads(end_file.read_text()) if end_file.exists() else {}
for name, digest in read('runs/repair_source_hashes.json').items():
    check('replay production source unchanged ' + name, end.get(name, hashlib.sha256((ROOT / name).read_bytes()).hexdigest()) == digest)
for name, digest in read('runs/seeded_artifacts.json').items():
    check('seeded prior artifact preserved ' + name, hashlib.sha256((OUT / 'ai' / name).read_bytes()).hexdigest() == digest)
history = read('runs/history_at_resume.json')
check('initial scope reaches resumed history', '다른 실행자의 trainer·harness·reference·staged·snapshots' in str(history))
check('bounded resumed history', sum(len(r['content']) for r in history) < 61000)
for n in range(1, 4):
    file = OUT / f'runs/T{n}_result.json'
    if file.exists():
        result = json.loads(file.read_text())
        check(f'replay {n} terminal', result['state'] == 'succeeded' and result['pending_children'] == 0)
for snap in sorted((OUT / 'snapshots').glob('T*')):
    changed = [str(p.relative_to(snap)) for p in snap.rglob('*') if p.is_file()
               and p.read_bytes() != (OUT / 'ai' / p.relative_to(snap)).read_bytes()]
    check(snap.name + ' all prior outputs unchanged', not changed, changed)

if (OUT / 'ai/T5/record_summary.json').exists():
    d = read('ai/T5/record_summary.json')
    check('T5 full records', d['integrity']['count'] == 1800 and d['all_four_pass']['now'] == 1799
          and d['not_all_pass']['now'] == 1 and not d['integrity']['duplicate_ids'])
    rows = list(csv.DictReader((OUT / 'ai/T5/record_ledger.csv').open(encoding='utf-8-sig')))
    check('T5 every record judgment', len(rows) == 1800 and {r['id'] for r in rows} == {f'D{i:04}' for i in range(1, 1801)}
          and {r['id'] for r in rows if r['all_four_pass'].lower() != 'true'} == {'D1777'})
    tasks = read('ai/T5/task_ledger.json')['items']
    done = {f'W{w}-{n:02}' for w in range(1, 6) for n in (1, 2)} - {'W4-02'}
    check('T5 exact completed tasks', {r['id'] for r in tasks if r['counts_toward_progress']} == done)
    check('T5 cancelled kept', {r['id'] for r in tasks if r['scope'] == 'cancelled'} == {f'W6-{i:02}' for i in range(1, 13)})
    check('T5 exact ready tasks', {r['id'] for r in tasks if r['executable'].startswith('실행 가능')}
          == {'W1-03', 'W2-03', 'W3-03', 'W4-02', 'W5-03'})
    budget = read('ai/T5/budget.json')
    check('T5 budget unchanged', budget['budget'] == 4200000 and budget['in_scope_cost'] == 3390000 and budget['remaining'] == 810000)
    gate = read('ai/T5/launch_gate.json')
    q4 = next(r for r in read('ai/T5/raid_ledger.json')['open_decisions'] if r['id'] == 'Q4')
    check('T5 stale completion blocker repaired', q4['status'] == 'resolved_for_completion'
          and '선행조건 아님' in q4['impact'] and 'B4' not in {r['id'] for r in gate['blockers']})

if (OUT / 'ai/T6/action_table.json').exists():
    d = read('ai/T6/action_table.json')
    tasks = list(csv.DictReader((OUT / 'ai/T6/remaining_tasks.csv').open(encoding='utf-8-sig')))
    done = {f'W{w}-{n:02}' for w in range(1, 6) for n in (1, 2)} - {'W4-02'}
    remaining = {f'W{w}-{n:02}' for w in range(1, 6) for n in range(1, 13)} - done
    check('T6 only remaining tasks assigned', len(tasks) == 51 and {t['task_id'] for t in tasks} == remaining)
    check('T6 completed and cancelled excluded', {t['task_id'] for t in d['excluded_completed']} == done
          and set(d['cancelled_not_reassigned']) == {f'W6-{i:02}' for i in range(1, 13)})
    optional = next(p for p in d['problems'] if p['problem_id'] == 'P8')
    check('T6 optional evidence no longer blocks', optional['blocker'] == [] and optional['conditions'] == []
          and optional['depends_on'] == [] and '차단 아님' in optional['review_gate'])
    order = read('ai/T6/review_order.json')['steps']
    check('T6 optional evidence not prerequisite', not any(optional['problem_id'] + ':' in str(s) for s in order))
    check('T6 independent work proceeds', {'W1-03', 'W2-03', 'W3-03', 'W5-03'}
          <= {t['task_id'] for t in tasks if t['next_action'] == '착수'})

if (OUT / 'ai/T9/action_table_t9.json').exists():
    d = read('ai/T9/action_table_t9.json')
    tasks = list(csv.DictReader((OUT / 'ai/T9/handover_tasks.csv').open(encoding='utf-8-sig')))
    check('T9 remaining task set preserved', {t['task_id'] for t in tasks} == remaining and len(tasks) == 51)
    check('T9 old policy questions excluded', len(read('ai/T9/questions_excluded.json')) == 4)
    check('T9 known site constraint scoped to P2 and P4', {p['problem_id'] for p in d['problems'] if p['site_constraints']} == {'P2', 'P4'})
    # Preserve this failure: fields still say executable but next action/order adds OQ3.
    check('T9 no speculative prerequisite for independent work', all('확인되면' not in t['t9_next_action'] for t in tasks if t['task_id'] in {'W1-03', 'W2-03', 'W3-03', 'W5-03'}))

report = {'checks': checks, 'passed': sum(r['pass'] for r in checks), 'failed': sum(not r['pass'] for r in checks)}
(OUT / 'runs/final_verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps({k: report[k] for k in ('passed', 'failed')}, ensure_ascii=False))
