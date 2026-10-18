"""Independent artifact checks, no IBL execution or task implementation."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-18_76회차'


def verify(lane, phase):
    manifest = json.loads((OUT / 'inputs' / lane / 'manifest.json').read_text())
    folder = OUT / lane / phase
    report = json.loads((folder / 'report.json').read_text())
    markdown = (folder / 'report.md').read_text()
    rows = {row['id']: row for row in report['rows']}
    checks = []
    def check(name, ok):
        checks.append({'name': name, 'ok': bool(ok)})
    check('all_ids_once', len(rows) == len(report['rows']) == 6 and set(rows) == {r['id'] for r in manifest['rows']})
    expected_order = [r['id'] for r in manifest['rows']]
    if phase == 'restored': expected_order.reverse()
    check('requested_order', list(rows) == expected_order)
    expected = dict.fromkeys(rows, 'unchanged')
    if phase.endswith('variant'): expected.update(D1='changed', D3='missing')
    if phase == 'restored': expected['D1'] = 'changed'
    for source in manifest['rows']:
        row = rows[source['id']]
        snapshot = OUT / 'snapshots' / lane / Path(source['path']).name
        lines = snapshot.read_bytes().decode().splitlines(keepends=True)[:3]
        excerpt = ''.join(f'{i}\t{line}' for i, line in enumerate(lines, 1)) if source['numbered'] else ''.join(lines)
        check(source['id'] + '_path', row['path'] == source['path'])
        check(source['id'] + '_claim', row['claim'] == source['claim'])
        check(source['id'] + '_displayed_excerpt', excerpt.rstrip() in markdown)
        check(source['id'] + '_excerpt', row['excerpt'] == excerpt)
        check(source['id'] + '_state', row['evidence_status']['state'] == expected[source['id']])
        check(source['id'] + '_evidence', bool(row['evidence_status']['outcomes']) and bool(row['note_id']))
        check(source['id'] + '_markdown', source['id'] in markdown and expected[source['id']] in markdown and source['path'] in markdown)
    for state in ['unchanged', 'changed', 'missing', 'unknown']:
        check('count_' + state, report['counts'][state] == list(expected.values()).count(state))
    if phase != 'base':
        base = json.loads((OUT / lane / 'base/report.json').read_text())
        old = {r['id']:r for r in base['rows']}
        check('note_ids_preserved', all(r['note_id'] == old[r['id']]['note_id'] for r in rows.values()))
    summary = {'lane':lane,'phase':phase,'passed':sum(c['ok'] for c in checks),'total':len(checks),'checks':checks}
    (OUT / f'verify_{lane}_{phase}.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False))
    return all(c['ok'] for c in checks)

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('lane');p.add_argument('phase');a=p.parse_args()
    raise SystemExit(0 if verify(a.lane,a.phase) else 1)
