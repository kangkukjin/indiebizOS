"""Validate all output rows and the actual reports against the independent oracle."""
import csv
import hashlib
import json
import re

from generate import OUT, oracle


def read(path):
    return json.loads(path.read_text())


def report_checks(report, expected):
    if '요약(수량·원가·상태별 주문수): ' in report:
        summary = json.loads(report.split('요약(수량·원가·상태별 주문수): ')[1].splitlines()[0])
        top = json.loads(report.split('부족 상위10: ')[1].splitlines()[0])
    else:
        summary_section = report.split('## 요약', 1)[1].split('\n## ', 1)[0]
        summary = {key: int(value) for key, value in re.findall(
            r'^\| (\w+) \| ([0-9]+) \|$', summary_section, re.M) if key in expected['summary']}
        top = [{'order': cells[0], 'shortage': int(cells[-1])}
               for line in report.splitlines() if re.match(r'^\| O\d{3}-\d{2} \|', line)
               for cells in [[v.strip() for v in line.strip('|').split('|')]]]
    wanted = [{'order': row['order'], 'shortage': row['shortage']} for row in sorted(
        [r for r in expected['orders'] if r['shortage'] > 0], key=lambda r: (-r['shortage'], r['order']))[:10]]
    return {'report_summary': summary == expected['summary'], 'report_top10': top == wanted,
            'report_sources_rules': all(term in report for term in ['skus.json','lots.json','orders.csv','FIFO'])}


checks = {}
for actor in ['trainer', 'agent', 'trainer_after']:
    for mode in ['base', 'variant']:
        path = OUT / actor / mode
        if not (path/'result.json').exists():
            continue
        expected = read(OUT/f'harness/expected_{mode}.json')
        actual = read(path/'result.json')
        check = {key: actual.get(key) == value for key, value in expected.items()}
        check.update(report_checks((path/'report.md').read_text(), expected))
        if mode == 'variant':
            check['delta'] = read(path/'delta.json') == read(OUT/'harness/expected_delta.json')
        checks[f'{actor}_{mode}'] = check
    hashes = OUT / f'harness/{actor}_base_hashes.json'
    if hashes.exists():
        checks[actor+'_base_preserved'] = all(hashlib.sha256((OUT/actor/'base'/name).read_bytes()).hexdigest() == value
                                             for name, value in read(hashes).items())

with (OUT/'inputs/orders.csv').open(newline='') as f:
    orders = list(csv.DictReader(f))
for row in orders:
    row['seq'] = int(row['seq'])
allcancel = OUT/'trainer_after/allcancel'
if (allcancel/'result.json').exists():
    cancellation = [r['order'] for r in orders] + ['NO-SUCH-1']
    expected = oracle(read(OUT/'inputs/skus.json'), read(OUT/'inputs/lots.json'), orders, cancellation)
    actual = read(allcancel/'result.json')
    checks['allcancel'] = {key: actual.get(key) == value for key, value in expected.items()}
    checks['allcancel'].update(report_checks((allcancel/'report.md').read_text(), expected))
(OUT/'harness/validation.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2))
print(json.dumps(checks, ensure_ascii=False, indent=2))
assert all(all(value.values()) if isinstance(value, dict) else value for value in checks.values())
