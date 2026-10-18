"""Independent output checks; no device or model calls."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-18_75회차'
executor = sys.argv[1] if len(sys.argv) > 1 else 'trainer'
variant = len(sys.argv) > 2 and sys.argv[2] == 'variant'
folder = OUT / executor / ('variant' if variant else '')
manifest = json.loads((OUT / 'inputs' / ('variant.json' if variant else 'base.json')).read_text())
report = json.loads((folder / 'report.json').read_text())
markdown = (folder / 'report.md').read_text()
errors = []

def check(condition, message):
    if not condition:
        errors.append(message)

rows = report['rows']
expected = {x['id']: x for x in manifest['targets']}
check(len(rows) == len(expected), 'row count')
check({x['id'] for x in rows} == set(expected), 'IDs')
computed = 0
for row in rows:
    rid = row['id']
    check(row['target'] == expected[rid]['target'], rid + ': target')
    kind = row['kind'].get('roster') if isinstance(row['kind'], dict) else row['kind']
    check(kind == expected[rid]['kind'], rid + ': kind')
    raw = row.get('raw', row.get('observation', row.get('evidence', {})))
    raw = raw.get('prior', raw)
    if kind == 'pc':
        result = raw.get('result') or {}
        devices = row.get('devices', raw.get('devices', result.get('devices', [])))
        eligible = [d for d in devices if
                    (not manifest['policy']['require_volume'] or d.get('can_set_volume') is True)
                    and (not manifest['policy']['require_mute'] or d.get('can_mute') is True)]
        ready = row['verified'] is True and row['status'] in ('completed', 'ready', 'not_ready_verified') and bool(eligible)
        if row.get('initial', {}).get('status') == 'pending':
            check(row['initial']['task_ref'] == raw.get('task_ref'), rid + ': original task reference')
    else:
        tv = raw.get('result', raw)
        ready = tv.get('reachable') is True and tv.get('power') == 'on'
    check(row['ready'] is ready, rid + ': readiness')
    computed += ready
    check(rid in markdown and row['target'] in markdown, rid + ': markdown identity')
    check(bool(raw), rid + ': evidence')
check({k: report['counts'][k] for k in ('total', 'ready', 'not_ready')} == {'total': len(rows), 'ready': computed, 'not_ready': len(rows) - computed}, 'counts')
check('소리' in markdown and '영상' in markdown, 'observation limitation')
if variant:
    previous = json.loads((OUT / executor / 'report.json').read_text())
    by_id = {r['id']: r for r in previous['rows']}
    for row in rows:
        for field in ('raw', 'observation', 'evidence', 'initial'):
            if field in row and field in by_id[row['id']]:
                current = row[field]
                if field == 'evidence' and isinstance(current, dict):
                    current = current.get('prior', current)
                check(current == by_id[row['id']][field], row['id'] + ': preserved ' + field)
    check([x['id'] for x in rows] == [x['id'] for x in manifest['targets']], 'variant ordering')
    hashes = json.loads((OUT / 'evidence/before_variant_hashes.json').read_text())
    if executor == 'ai':
        hashes.update({'ai/' + k: v for k, v in json.loads((OUT / 'evidence/ai_base_hashes.json').read_text()).items()})
    for name, digest in hashes.items():
        check(hashlib.sha256((OUT / name).read_bytes()).hexdigest() == digest, name + ': unchanged')
result = {'executor': executor, 'variant': variant, 'pass': not errors, 'errors': errors,
          'rows': len(rows), 'counts': report['counts'], 'artifact_hashes': {
              p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [folder/'report.json', folder/'report.md']}}
(OUT / 'evidence' / f'verify_{executor}_{"variant" if variant else "base"}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps(result, ensure_ascii=False))
