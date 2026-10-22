"""Read-only artifact audit; produce compact, non-sensitive rehearsal evidence."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: F401,E402
import hashlib
import json
from collections import Counter

HERE = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-22_94회차'


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preserved(artifacts, snapshot, names):
    for name in names:
        p, old = artifacts/name, snapshot[name]
        assert digest(p) == old.get('sha256', old.get('sha')), name
        assert p.stat().st_mtime_ns == old.get('mtime_ns', old.get('mtime')), name
    return names


def final_check(artifacts):
    value = read(artifacts/'final.json')
    rows = value['items']
    expected = {'a1': 21, 'a2': 9, 'b1': 20, 'c1': 30}
    assert len(rows) == 4
    assert {r['id']: r['amount'] for r in rows} == expected
    assert all(r['qty'] * r['price'] == r['amount'] for r in rows)
    totals = [value[k] for k in ('total', 'amount_total', 'total_amount', 'grand_total') if k in value]
    assert totals and all(v == 80 for v in totals)
    return {'rows': 4, 'amounts': expected, 'total': 80}


def collect():
    evidence = {'baseline': read(OUT/'runs/phase_boundaries.json'), 'trainer': {}, 'ai': {}}
    for phase, lane in (('baseline', 'trainer'), ('repair', 'trainer_repair'), ('plan_fix', 'trainer_final')):
        runs = OUT/'runs' if phase == 'baseline' else OUT/'runs'/phase
        first, last = (read(runs/f'trainer_T{i}_result.json') for i in (1, 2))
        assert first['success'] and not first['value']['ready']
        assert last['success'] and last['value']['ready']
        assert [s['status'] for s in first['value']['steps']] == [
            'completed', 'completed', 'completed', 'blocked', 'blocked']
        assert all(s['status'] == 'completed' for s in last['value']['steps'])
        if phase == 'plan_fix':
            assert all(s.get('content') for r in (first, last) for s in r['value']['steps'])
        assert [s['id'] for s in first['value']['steps']] == [s['id'] for s in last['value']['steps']]
        unchanged = preserved(OUT/lane/'artifacts', read(runs/'trainer_T1_files.json'), ['A.json', 'B.json'])
        evidence['trainer'][phase] = {'run_ids': [r['resume']['run_id'] for r in (first, last)],
            'preserved_bytes_and_mtime': unchanged, 'final': final_check(OUT/lane/'artifacts')}
    bad = read(OUT/'runs/repair/trainer_invalid_result.json')
    assert bad['success'] and not bad['value']['ready']
    assert not (OUT/'trainer_invalid/artifacts/final.json').exists()
    evidence['trainer']['invalid_C'] = {'run_id': bad['resume']['run_id'], 'final_withheld': True}
    bad = read(OUT/'runs/plan_fix/trainer_invalid_result.json')
    assert bad['success'] and not bad['value']['ready']
    assert all(s.get('content') for s in bad['value']['steps'])
    assert not (OUT/'trainer_final_invalid/artifacts/final.json').exists()
    evidence['trainer']['plan_fix_invalid_C'] = {'run_id': bad['resume']['run_id'], 'final_withheld': True}

    for phase, lane in (('baseline', 'ai'), ('repair', 'ai_repair')):
        runs = OUT/'runs' if phase == 'baseline' else OUT/'runs/repair'
        artifacts = OUT/lane/'artifacts'
        snap = read(runs/'ai_T1_files.json')
        assert 'final.json' not in snap
        names = ['A.result.json', 'B.result.json'] if phase == 'baseline' else ['result_A.json', 'result_B.json']
        versions = ['plan_versions/plan.v1.json', 'plan_versions/plan.v2.json'] if phase == 'baseline' else ['plan.v1.json', 'plan.v2.json']
        unchanged = preserved(artifacts, snap, names + versions)
        old_plan, plan = read(artifacts/versions[0]), read(artifacts/'plan.json')
        assert [s['id'] for s in old_plan['steps']] == [s['id'] for s in plan['steps']]
        assert all(s['status'] in ('done', 'completed') for s in plan['steps'])
        assert all(digest(OUT/lane/'inputs'/p.name) == digest(p) for p in (HERE/'fixtures').glob('*.json'))
        result = {'final': final_check(artifacts), 'preserved_bytes_and_mtime': unchanged,
                  'stable_step_ids': [s['id'] for s in plan['steps']], 'turns': []}
        for row in read(runs/'episodes.json'):
            turn = row['turn']
            terminal = read(runs/f'ai_T{turn}_result.json')
            assert terminal['state'] == 'succeeded' and terminal['pending_children'] == 0
            events = read(runs/f'ai_T{turn}_events.json')
            row['supervised_tool_calls'] = dict(Counter(e['data'].get('name') for e in events if e['kind'] == 'supervision.tool.started'))
            row['model_rounds'] = dict(Counter(e['data'].get('role') for e in events if e['kind'] == 'model.round'))
            row['evaluations'] = [e['data']['decision']['status'] for e in events if e['kind'] == 'supervision.evaluation.finished']
            row['compactions'] = sum(e['kind'] == 'context.compacted' for e in events)
            row['total_usage'] = {k: sum(v.get(k, 0) for v in row['usage'].values())
                                  for k in ('input', 'output', 'cache_read', 'cache_create')}
            result['turns'].append(row)
        if phase == 'repair':
            first = list(read(runs/'ai_T1_todo_states.json').values())
            last = list(read(runs/'ai_T2_todo_states.json').values())
            assert len(first) == len(last) == 1
            assert Counter(t['status'] for t in first[0]['todos']) == {'completed': 5, 'pending': 2}
            assert len(last[0]['todos']) == 7 and all(t['status'] == 'completed' for t in last[0]['todos'])
            result['todo_states'] = {'T1': first[0]['todos'], 'T2': last[0]['todos']}
        evidence['ai'][phase] = result
    (HERE/'evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    print('Verified five final artifacts, original inputs, stable plan IDs, unchanged A/B and versions, real todos.')


if __name__ == '__main__':
    collect()
