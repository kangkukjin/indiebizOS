"""Independent oracle from input bytes; validate all rows and context, not samples."""
import argparse
import json
import re
from pathlib import Path


def read_lines(path):
    data = path.read_bytes()
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError:
        text = data.decode('cp949')
    return text.splitlines()


def verify(source, output, pattern):
    inventory = json.loads((source / 'inventory.json').read_text())
    expected_devices, expected_details, zones = [], {}, {}
    for row in inventory:
        path = source / row['file']
        lines = read_lines(path) if path.exists() else []
        selected = [n for n, text in enumerate(lines, 1) if pattern in text]
        count = len(selected) if path.exists() else None
        expected_devices.append({**row, 'count': count, 'status': 'ok' if path.exists() else 'missing'})
        zones[row['zone']] = zones.get(row['zone'], 0) + (count or 0)
        for n in selected:
            expected_details[(row['device'], n)] = {
                'file': row['file'], 'text': lines[n - 1],
                'context': [(k, lines[k - 1]) for k in range(max(1, n - 1), min(len(lines), n + 1) + 1)],
            }
    summary = json.loads((output / 'summary.json').read_text())
    details = json.loads((output / 'details.json').read_text())
    failures = []
    if summary['devices'] != expected_devices:
        failures.append('devices')
    if {r['zone']: r['count'] for r in summary['zones']} != zones:
        failures.append('zones')
    if summary['total'] != len(expected_details) or summary['complete'] is not True:
        failures.append('total/complete')
    if summary['missing_devices'] != ['D25']:
        failures.append('missing')
    actual_keys = [(r['device'], r['line']) for r in details]
    if len(actual_keys) != len(set(actual_keys)) or set(actual_keys) != set(expected_details):
        failures.append('detail_keys')
    for row in details:
        key = (row['device'], row['line'])
        expected = expected_details.get(key)
        if not expected:
            continue
        if row['file'] != expected['file'] or row['text'] != expected['text']:
            failures.append(f'text:{key}')
        context = row.get('context')
        if isinstance(context, list):
            actual = [(r['line'], r['text']) for r in context]
        elif isinstance(context, str):
            actual = []
            for line in context.split('\n'):
                match = re.match(r'^(\d+)[ >] (.*)$', line)
                if match:
                    actual.append((int(match[1]), match[2]))
        else:
            actual = None
        if actual != expected['context']:
            failures.append(f'context:{key}')
    return {'passed': not failures, 'devices': len(expected_devices),
            'details': len(expected_details), 'failures': failures}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('source', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('pattern')
    args = p.parse_args()
    print(json.dumps(verify(args.source, args.output, args.pattern), ensure_ascii=False, indent=2))
