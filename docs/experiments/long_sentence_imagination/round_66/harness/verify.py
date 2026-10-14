"""Independent comparison of source rows with actual phone read receipts."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-14_66회차'


def read(path):
    return json.loads(path.read_text())


def fields(rows):
    return [{k: r[k] for k in ('id', 'purpose', 'note')} for r in rows]


def main():
    checked = []
    for phase in ('base', 'variant', 'base_v2', 'variant_v2', 'repair_base', 'repair_variant', 'repair_new'):
        folder = OUT / 'trainer' / phase
        if not (folder / 'result.json').exists():
            continue
        result = read(folder / 'result.json')
        source = read(OUT / ('base_v1.request.json' if phase.startswith('base') else 'variant_v1.request.json'))['inputs']['rows']
        if phase.startswith('repair'):
            source = read(OUT / (phase + '.request.json'))['inputs']['rows']
        device = result['devices'][0]
        observed = device['observations']
        actual = observed[2]['data']['value']['rows']
        assert fields(actual) == fields(source), phase
        assert result['rows'] == source and result['roundtrip_verified']
        assert len(result['matrix']) == len(source)
        assert observed[1]['data']['value']['radio']['playing'] is False
        assert observed[1]['data']['value']['music']['now_playing'] is None
        assert observed[0]['data']['device_id'] == 'guestpc-4e51c614b25b'
        if len(result['devices']) > 1:
            assert all(not row['ok'] for row in result['devices'][1]['observations'])
            assert all('task_ref' not in row for row in result['devices'][1]['observations'])
        report = (folder / 'report.md').read_text()
        assert all(row['purpose'] in report for row in source)
        checked.append({'execution': 'trainer/' + phase, 'rows': len(actual), 'matched': True})
    for phase, filename in [('base', 'evidence_phone_roundtrip_v2_raw.json'), ('variant', 'evidence_variant_raw.json')]:
        folder = OUT / 'agent' / phase
        if not (folder / filename).exists():
            continue
        evidence = read(folder / filename)
        receipt = evidence['read'] if phase == 'base' else evidence['read']['response']
        actual = receipt['result']['items']
        source = read(OUT / 'inputs' / ('checklist.json' if phase == 'base' else 'checklist_variant.json'))['items']
        assert fields(actual) == fields(source)
        assert receipt['success'] and receipt['result']['success']
        if phase == 'variant':
            assert evidence['ghost_registry_rows'] == []
            assert evidence['ghost_info']['response']['failed'] and evidence['ghost_ibl']['response']['failed']
        checked.append({'execution': 'agent/' + phase, 'rows': len(actual), 'matched': True})
    repair = OUT / 'agent/repair_base'
    if (repair / 'evidence_remote_roundtrip.json').exists():
        receipt = read(repair / 'evidence_remote_roundtrip.json')
        actual = receipt['result']['value']
        source = read(OUT / 'inputs/checklist.json')['items']
        assert receipt['state'] == 'succeeded'
        assert fields(actual['items']) == fields(source)
        assert actual['text'] == (repair / 'checklist_roundtrip.json').read_text()
        assert len(read(repair / 'check_result.json')['purposes']) == len(source)
        checked.append({'execution': 'agent/repair_base', 'rows': len(source), 'matched': True, 'raw_text_equal': True})
    for name, digest in read(OUT / 'agent_base_hashes.json').items():
        assert hashlib.sha256((OUT / name).read_bytes()).hexdigest() == digest, name
    (OUT / 'verification.json').write_text(json.dumps(checked, ensure_ascii=False, indent=2))
    print(json.dumps(checked, ensure_ascii=False))


if __name__ == '__main__':
    main()
