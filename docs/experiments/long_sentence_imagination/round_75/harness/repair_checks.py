"""Audit all repair attempts without hiding differing interpretations of API support."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-18_75회차'
checks = []
for who in ['repair_trainer', 'repair_ai', 'repair2_trainer', 'repair2_ai']:
    for variant in ['', 'variant', 'api_scope']:
        folder = OUT / who / variant
        if not (folder / 'report.json').exists():
            continue
        manifest = json.loads((OUT / 'inputs' / ('variant.json' if variant else 'base.json')).read_text())
        report = json.loads((folder / 'report.json').read_text())
        text = (folder / 'report.md').read_text()
        rows, errors = report['rows'], []
        def check(condition, message):
            if not condition:
                errors.append(message)
        check(len(rows) == len(manifest['targets']), 'row count')
        check([r['id'] for r in rows] == [r['id'] for r in manifest['targets']], 'row ordering')
        ready = 0
        for row, expected in zip(rows, manifest['targets']):
            rid = row['id']
            check(row['target'] == expected['target'] and row['kind'] == expected['kind'], rid + ': identity')
            check(rid in text and row['target'] in text, rid + ': markdown identity')
            raw = row.get('raw') or row.get('observation') or row.get('evidence') or {}
            check(bool(raw), rid + ': evidence')
            obs = raw if isinstance(raw, dict) else {}
            if row['kind'] == 'pc':
                devices = row.get('devices', row.get('outputs', obs.get('devices', (obs.get('result') or {}).get('devices', [])))) or []
                eligible = [d for d in devices if
                            (not manifest['policy']['require_volume'] or d.get('can_set_volume') is True) and
                            (not manifest['policy']['require_mute'] or d.get('can_mute') is True)]
                expected_ready = row['verified'] is True and bool(eligible)
                for d in devices:
                    check(d.get('capability_basis') in ('coreaudio_property_settable', 'wasapi_endpoint_volume_interface'), rid + ': capability basis')
            else:
                expected_ready = row.get('reachable', obs.get('reachable')) is True and row.get('power', obs.get('power')) == 'on'
            check(row['ready'] is expected_ready, rid + ': API support interpretation')
            ready += expected_ready
        check({k: report['counts'][k] for k in ('total', 'ready', 'not_ready')} ==
              dict(total=len(rows), ready=ready, not_ready=len(rows)-ready), 'API policy counts')
        check(report['counts']['ready'] == sum(r['ready'] is True for r in rows), 'reported counts consistency')
        check('소리' in text and '영상' in text, 'verification limitation')
        if variant:
            base = json.loads((OUT / who / 'report.json').read_text())
            before = {r['id']: r for r in base['rows']}
            for row in rows:
                for field in ('raw', 'initial', 'devices', 'outputs', 'receipt'):
                    if field in row and field in before[row['id']]:
                        check(row[field] == before[row['id']][field], row['id'] + ': preserved ' + field)
                old_obs, new_obs = before[row['id']].get('observation'), row.get('observation')
                if isinstance(old_obs, dict) and isinstance(new_obs, dict):
                    # AI may replace its own interpretation labels; compare OS values and identity.
                    for key in ('platform', 'hostname', 'os_version', 'observed_at', 'verification_scope',
                                'source_sha256', 'reachable', 'power', 'verified'):
                        if key in old_obs:
                            check(new_obs.get(key) == old_obs[key], row['id'] + ': observed ' + key)
                    old_devices, new_devices = old_obs.get('devices'), new_obs.get('devices')
                    if old_devices is not None:
                        native_keys = ('id', 'name', 'volume', 'muted', 'is_default', 'default',
                                       'can_set_volume', 'can_mute', 'capability_basis', 'volume_channels')
                        project = lambda ds: [{k: d[k] for k in native_keys if k in d} for d in ds]
                        check(project(old_devices) == project(new_devices or []), row['id'] + ': native devices')
        checks.append({'executor': who, 'variant': variant or 'base', 'passed': not errors,
                       'errors': errors, 'counts': report['counts'], 'api_policy_ready': ready})
for who in ['repair_trainer', 'repair_ai', 'repair2_trainer', 'repair2_ai']:
    for name, digest in json.loads((OUT / f'evidence/{who}_base_hashes.json').read_text()).items():
        assert hashlib.sha256((OUT / name).read_bytes()).hexdigest() == digest, name
for name in ['repair_trainer_variant', 'repair2_trainer_variant', 'repair_empty', 'repair2_receipts', 'repair_null', 'repair_missing']:
    r = json.loads((OUT / f'runs/{name}.json').read_text())['response']
    assert r['success']
    calls = [e['action'] for e in r['evidence'] if e['kind'] == 'invoke']
    assert 'limbs:guestpc' not in calls
    assert calls.count('self:task') == (1 if name == 'repair2_receipts' else 0)
    if name == 'repair2_receipts':
        assert r['value'][0]['result']['status'] == 'completed'
        assert all(x['result']['status'] == 'unknown' and x['result']['verified'] is False for x in r['value'][1:])
    elif name in ['repair_null', 'repair_missing']:
        assert r['value']['status'] == 'unknown' and r['value']['verified'] is False
    elif name == 'repair_empty':
        assert r['value']['counts'] == dict(total=0, ready=0, not_ready=0)
    checks.append({'probe': name, 'passed': True, 'calls': calls})
(OUT / 'evidence/repair_checks.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2))
print(json.dumps(checks, ensure_ascii=False))
