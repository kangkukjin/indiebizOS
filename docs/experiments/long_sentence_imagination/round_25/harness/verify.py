"""Compare all final cells to an independent input-derived oracle."""
import csv
import json
import sys
from pathlib import Path
from generate import OUT, oracle


def verify(folder, missing=None, threshold=30000):
    expected = oracle(missing, threshold)
    rows = json.loads((folder / 'details.json').read_text())
    summary = json.loads((folder / 'summary.json').read_text())
    errors = []
    if isinstance(rows, dict):
        rows = rows.get('items', rows.get('rows', []))
    key = lambda r: (r['order_id'], str(r['line_no']))
    actual = {key(r): r for r in rows}
    if len(rows) != expected['count'] or len(actual) != len(rows):
        errors.append({'kind': 'row_count', 'actual': len(rows), 'expected': expected['count']})
    for row in expected['rows']:
        found = actual.get(key(row), {})
        for field, value in row.items():
            if field not in found or found[field] != value:
                errors.append({'kind': 'cell', 'key': key(row), 'field': field,
                               'expected': value, 'actual': found.get(field)})
    for field in ['count', 'total_amount', 'threshold']:
        if summary.get(field) != expected[field]:
            errors.append({'kind': 'summary', 'field': field, 'actual': summary.get(field), 'expected': expected[field]})
    groups = summary.get('summary', summary.get('regions', []))
    if isinstance(groups, dict):
        groups = [dict(region=k, **v) for k, v in groups.items()]
    if sorted(groups, key=lambda r:r['region']) != sorted(expected['summary'], key=lambda r:r['region']):
        errors.append({'kind': 'groups', 'actual': groups, 'expected': expected['summary']})
    if summary.get('source_complete') != (missing is None):
        errors.append({'kind': 'source_complete', 'actual': summary.get('source_complete')})
    if missing is not None and not summary.get('failures'):
        errors.append({'kind': 'missing_failure_details'})
    with (folder / 'details.csv').open(newline='') as file:
        csv_rows = list(csv.DictReader(file))
    csv_actual = {key(r): r for r in csv_rows}
    if len(csv_rows) != expected['count']:
        errors.append({'kind': 'csv_count', 'actual': len(csv_rows)})
    for row in expected['rows']:
        found = csv_actual.get(key(row), {})
        for field, value in row.items():
            target = '' if value is None else str(value)
            observed = found.get(field)
            equal = (str(observed).lower() == target.lower()) if isinstance(value, bool) else observed == target
            if not equal:
                errors.append({'kind': 'csv_cell', 'key': key(row), 'field': field, 'expected': target, 'actual': observed})
    return dict(folder=str(folder), passed=not errors, row_count=len(rows), checks=len(expected['rows'])*26,
                errors_count=len(errors), errors=errors[:20])


if __name__ == '__main__':
    who, mode = sys.argv[1:3]
    threshold = {'policy': 50000, 'reverse': 15000}.get(mode, 30000)
    result = verify(OUT / who / mode, 1 if mode == 'missing' else None, threshold)
    (OUT / 'evidence' / f'verify_{who}_{mode}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))
