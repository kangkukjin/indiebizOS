"""Independent full-row oracle, artifact and dependency-timing checks."""
import collections
import datetime
import hashlib
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-22_89회차'
checks = []


def check(name, actual, expected):
    ok = actual == expected
    if not ok and isinstance(actual, bytes):
        actual = hashlib.sha256(actual).hexdigest()
        expected = hashlib.sha256(expected).hexdigest()
    checks.append({'name': name, 'ok': ok, **({} if ok else {'actual': actual, 'expected': expected})})


def read(path):
    return json.loads(path.read_text())


def stamp(text):
    return datetime.datetime.fromisoformat(text).timestamp()


def oracle(phase):
    source = OUT / 'reference/initial_inputs' if phase < 3 else OUT / 'staged' / f'T{phase}'
    records = read(source / 'records.json')
    tasks = read(source / 'tasks.json')['items']
    receipts = read(source / 'receipts.json')['items']
    done = {r['task_id'] for r in receipts if r['reported_done'] and r['verified']}
    reported = {r['task_id'] for r in receipts if r['reported_done']}
    flags = []
    for row in records['items']:
        invalid = {'consent': row['consent'] != 'yes', 'checksum': row['checksum'] != 'pass',
                   'search': row['searchable'] is not True, 'access': row['accessible'] is not True}
        flags.append({'id': row['id'], 'source': row, **invalid, 'eligible': not any(invalid.values())})
    present = {r['id'] for r in records['items']}
    missing = sorted({f'D{i:04d}' for i in range(1, 1801)} - present)
    states, ready, chains = [], [], collections.Counter()
    for task in tasks:
        cancelled = phase > 1 and task['optional']
        status = 'cancelled' if cancelled else 'verified_done' if task['id'] in done else 'unverified' if task['id'] in reported else 'planned'
        states.append({**task, 'status': status})
        if status not in ('cancelled', 'verified_done'):
            chains[task['stream']] += task['hours']
            if set(task['depends']) <= done:
                ready.append(task['id'])
    cost = sum(t['cost'] for t in states if t['status'] != 'cancelled')
    budget = 6000000 if phase == 1 else 3200000
    return {'source': source, 'flags': flags, 'missing': missing, 'states': states, 'ready': ready,
            'chains': dict(chains), 'version': records['version'], 'cost': cost, 'budget': budget,
            'overrun': max(0, cost - budget), 'cancelled': [t['id'] for t in states if t['status'] == 'cancelled']}


def trainer(path):
    s = read(path / 'state.json')
    label, phase = path.name, int(s['phase'][1:])
    o = oracle(phase)
    a, b, c, d, e, f = [s[k]['value'] for k in 'ABCDEF']
    check(label + ':A rows all', a['rows'], o['flags'])
    check(label + ':A missing', a['missing'], o['missing'])
    check(label + ':A version', a['version'], o['version'])
    check(label + ':A eligible', a['eligible'], sum(r['eligible'] for r in o['flags']))
    check(label + ':A blocked all', a['blocked'], [r for r in o['flags'] if not r['eligible']])
    for gate in ('consent', 'checksum', 'search', 'access'):
        check(label + ':A ' + gate, a[gate], sum(r[gate] for r in o['flags']))
    check(label + ':B costs', [b['cost'], b['budget'], b['overrun']], [o['cost'], o['budget'], o['overrun']])
    check(label + ':B cancelled', b['cancelled'], o['cancelled'])
    check(label + ':B cost lines', b['items'], [{'id': t['id'], 'cost': t['cost'], 'optional': t['optional']} for t in o['states'] if t['status'] != 'cancelled'])
    check(label + ':C tasks all', c['items'], o['states'])
    check(label + ':C ready', c['ready'], o['ready'])
    check(label + ':C chain hours', {r['stream']: r['hours'] for r in c['chains']}, o['chains'])
    check(label + ':C required', [c['required'], c['required_done'], c['remaining_required']], [60, 9, 51])
    check(label + ':D gates', d['gates'], read(o['source'] / 'project.json')['gates'])
    check(label + ':E issues', [{k: r[k] for k in ('id', 'consent', 'checksum', 'search', 'access')} for r in e['issues']],
          [{k: r[k] for k in ('id', 'consent', 'checksum', 'search', 'access')} for r in o['flags'] if not r['eligible']])
    check(label + ':E unknown', [r['id'] for r in e['unknown']], o['missing'])
    check(label + ':F correct', [f['launch_ready'], f['review_complete'], f['cost'], f['overrun'], f['ready'], f['missing']],
          [False, True, o['cost'], o['overrun'], o['ready'], o['missing']])
    for node in 'ABCDEF':
        check(label + ':artifact ' + node, read(Path(s[node]['artifact'])), s[node]['value'])
        check(label + ':time ' + node, stamp(s[node]['ended']) >= stamp(s[node]['started']), True)
    for child, parents in [('E', 'AD'), ('F', 'EBC')]:
        check(label + ':dependency ' + child, all(stamp(s[child]['started']) >= stamp(s[p]['ended']) for p in parents), True)
    check(label + ':policy revisions', [b['policy'], c['policy'], d['policy']], [s['policy']] * 3)
    text = (path / 'report.txt').read_text()
    check(label + ':report essential values', all(str(n) in text for n in [len(o['flags']), a['eligible'], len(a['blocked']), o['cost'], o['budget'], o['overrun'], 9, 51]), True)
    check(label + ':report missing ids', all(m in text for m in o['missing']), True)
    check(label + ':review versus launch', '개통 가능 false' in text and '이번 검토 완료' in text, True)
    if phase == 2:
        check(label + ':A reused', s['A']['reused'], True)
    if phase >= 3:
        check(label + ':BCD reused', [s[k]['reused'] for k in 'BCD'], [True] * 3)
        check(label + ':row recomputation', a['computed_rows'], 0 if phase == 3 else 1)
        check(label + ':row reuse', a['reused_rows'], 1799)
    spans = {k: [stamp(s[k]['started']), stamp(s[k]['ended'])] for k in 'ABCD' if not s[k]['reused']}
    overlap = [[x, y] for i, x in enumerate(spans) for y in list(spans)[i+1:]
               if max(spans[x][0], spans[y][0]) < min(spans[x][1], spans[y][1])]
    return {'label': label, 'phase': phase, 'overlap_pairs': overlap,
            'E_before_B_or_C_end': stamp(s['E']['started']) < max(stamp(s[k]['ended']) for k in 'BC'),
            'timings': {k: {x: s[k][x] for x in ('started', 'ended', 'reused')} for k in 'ABCDEF'}}


def main():
    timings = []
    for path in sorted((OUT / 'trainer').iterdir()):
        if (path / 'state.json').exists():
            if path.name == 'missing_v3':
                s = read(path / 'state.json')
                a, f = s['A']['value'], s['F']['value']
                check('missing_v3:all unknown', a['missing'], [f'D{i:04d}' for i in range(1, 1801)])
                check('missing_v3:no fabricated records', [a['observed'], a['eligible'], a['rows'], a['blocked']], [0, 0, [], []])
                check('missing_v3:explicit read error', bool(a['read_error']), True)
                check('missing_v3:partial report', [f['launch_ready'], f['block_reasons']['data_unverified'], f['cost'], f['required_done']], [False, 1800, 4068000, 9])
                check('missing_v3:other branches saved', all(Path(s[k]['artifact']).is_file() for k in 'BCD'), True)
                continue
            timings.append(trainer(path))
    recovered = OUT / 'trainer/missing_recovered/state.json'
    if recovered.exists():
        s = read(recovered)
        check('missing_recovered:BCD reused', [s[k]['reused'] for k in 'BCD'], [True] * 3)
    for name, expected in read(OUT / 'reference/initial_hashes.json').items():
        check('initial snapshot unchanged:' + name, hashlib.sha256((OUT / 'reference/initial_inputs' / name).read_bytes()).hexdigest(), expected)
    bench = {}
    for mode, labels in [('sequential', ['seq1', 'seq2', 'seq3']), ('parallel', ['par2', 'par3', 'par4']),
                         ('optimized_sequential', ['opt_seq1', 'opt_seq2', 'opt_seq3']),
                         ('optimized_parallel', ['opt_par2', 'opt_par3', 'opt_par4'])]:
        values = [read(OUT / 'runs' / f'{label}.json')['seconds'] for label in labels]
        bench[mode] = {'labels': labels, 'seconds': values, 'median': statistics.median(values)}
    result = {'passed': sum(c['ok'] for c in checks), 'failed': sum(not c['ok'] for c in checks),
              'checks': checks, 'timings': timings, 'benchmark': bench}
    (OUT / 'runs/trainer_verification_full.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    compact = {**result, 'checks': {'passed_names': [c['name'] for c in checks if c['ok']], 'failures': [c for c in checks if not c['ok']]}}
    (HERE / 'trainer_verification.json').write_text(json.dumps(compact, ensure_ascii=False))
    print(json.dumps({k: v for k, v in result.items() if k not in ('checks', 'timings')}, ensure_ascii=False))
    print('failed:', json.dumps([c for c in checks if not c['ok']], ensure_ascii=False)[:4000])


if __name__ == '__main__':
    main()
