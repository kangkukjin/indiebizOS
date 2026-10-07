"""Compare saved JSON and every Markdown table cell with a minute-grid oracle."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from prepare import OUT, oracle


def verify(mode, destination):
    expected = oracle(OUT / 'source' / mode)
    folder = OUT / destination
    result = json.loads((folder / 'result.json').read_text())
    report = (folder / 'report.md').read_text()
    fields = ('booked', 'conflict', 'maintenance', 'blocked_booking', 'free', 'peak')
    table = {}
    for line in report.splitlines():
        cells = [x.strip() for x in line.strip().strip('|').split('|')]
        if len(cells) == 7 and re.fullmatch(r'R\d+', cells[0]):
            assert cells[0] not in table, cells[0]
            table[cells[0]] = [int(x.replace(',', '')) for x in cells[1:]]
    checks = {
        'all_room_values': sorted(result['rooms'], key=lambda r: r['room']) == expected['rooms'],
        'all_invalid_rows': sorted(result['invalid'], key=lambda r: r['id']) == sorted(expected['invalid'], key=lambda r: r['id']),
        'all_report_cells': table == {r['room']: [r[k] for k in fields] for r in expected['rooms']},
        'all_report_invalid': all(r['id'] in report for r in expected['invalid']),
    }
    return {'mode': mode, 'destination': destination, 'checks': checks,
            'all_ok': all(checks.values()),
            'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted((OUT / 'source' / mode).glob('*.json'))}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode')
    parser.add_argument('destination')
    args = parser.parse_args()
    result = verify(args.mode, args.destination)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['all_ok'] else 1)
