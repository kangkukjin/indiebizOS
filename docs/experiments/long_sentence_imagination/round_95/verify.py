"""Independent comparison with predeclared cases; no product implementation imports."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
import json
import re
from prepare import OUT, snapshot


def verify(lane, turn):
    checks = []

    def check(name, condition, detail=None):
        checks.append({'name': name, 'passed': bool(condition), 'detail': detail})

    artifacts = OUT / lane / 'artifacts'
    expected = json.loads((OUT / 'reference' / f'T{turn}.json').read_text())
    path = artifacts / f'audit_T{turn}.json'
    check('audit exists', path.is_file())
    if not path.is_file():
        return checks
    actual = json.loads(path.read_text())
    for key in ('phase', 'release_ready', 'counts', 'verified_total'):
        check(key, actual.get(key) == expected[key], {'actual': actual.get(key), 'expected': expected[key]})
    rows = actual.get('items', [])
    check('24 unique task IDs', len(rows) == 24 and len({r.get('id') for r in rows}) == 24)
    indexed = {r.get('id'): r for r in rows}
    check('exact ID set', set(indexed) == {r['id'] for r in expected['items']})
    for want in expected['items']:
        row = indexed.get(want['id'], {})
        for key in ('status', 'attempt', 'total'):
            check(want['id'] + ' ' + key, row.get(key) == want[key],
                  {'actual': row.get(key), 'expected': want[key]})
        check(want['id'] + ' reason', isinstance(row.get('reason'), str) and bool(row['reason']))
        check(want['id'] + ' evidence', bool(row.get('evidence')))
    report = artifacts / f'report_T{turn}.md'
    check('report exists', report.is_file())
    if report.is_file():
        content = report.read_text()
        # Human reports can use J15–J24; exact JSON rows remain mandatory above.
        mentioned = set(re.findall(r'\bJ\d{2}\b', content))
        for start, end in re.findall(r'J(\d{2})\s*[–—-]\s*J(\d{2})', content):
            mentioned.update(f'J{n:02}' for n in range(int(start), int(end) + 1))
        check('report covers all tasks', all(r['id'] in mentioned for r in expected['items']))
        check('report verified total', str(expected['verified_total']) in content.replace(',', ''))
    original = json.loads((OUT / 'runs' / f'{lane}_T{turn}_inputs.json').read_text())
    completed_snapshot = OUT / 'runs' / f'{lane}_T1_inputs_after.json'
    observed = (json.loads(completed_snapshot.read_text()) if turn == 1 and completed_snapshot.exists()
                else snapshot(OUT / lane / 'inputs'))
    check('all input bytes and mtime preserved', observed == original)
    if turn == 2:
        old = json.loads((OUT / 'runs' / f'{lane}_T1_outputs.json').read_text())
        now = snapshot(artifacts)
        for name, fingerprint in old.items():
            check('preserved T1 ' + name, now.get(name) == fingerprint)
    return checks


if __name__ == '__main__':
    lane, turn = sys.argv[1], int(sys.argv[2])
    checks = verify(lane, turn)
    result = {'lane': lane, 'turn': turn, 'passed': sum(c['passed'] for c in checks),
              'failed': sum(not c['passed'] for c in checks), 'checks': checks}
    (OUT / 'runs' / f'{lane}_T{turn}_verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != 'checks'}, ensure_ascii=False))
    print(json.dumps([c for c in checks if not c['passed']], ensure_ascii=False))
