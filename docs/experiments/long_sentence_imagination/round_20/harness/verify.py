"""Check captured artifacts against source fixtures without re-running the task."""
import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-05_20회차'
oracle = {row['path']: row for row in json.loads((OUT / 'oracle.json').read_text())}
results = {}
for label, artifact, count, extra, failures, drift in [
        ('base_v0', 'base', 18, 1, 0, 6), ('missing_v0', 'missing', 12, 7, 1, 4),
        ('base_after', 'base_after', 18, 1, 0, 0),
        ('missing_after', 'missing_after', 12, 7, 1, 0),
        ('bom_cr', 'bom_cr', 18, 1, 0, 0), ('empty', 'empty', 12, 7, 0, 0)]:
    record = json.loads((OUT / 'runs' / (label + '.json')).read_text())
    response = record['response']
    report = json.loads((OUT / 'trainer' / (artifact + '.json')).read_text())
    with (OUT / 'trainer' / (artifact + '.csv')).open(encoding='utf-8', newline='') as stream:
        csv_rows = list(csv.DictReader(stream))
    assert response['success'] and response['run_status'] == 'completed'
    assert response['source_complete'] is (failures == 0)
    assert len(report['rows']) == count and len(report['unexpected']) == extra
    assert len(report['failures']) == failures
    assert len({r['path'] for r in report['rows']}) == count
    assert {r['status']: r['count'] for r in report['summary']} == {
        'missing': 1, 'mismatch': 1, 'duplicate': 1, 'ok': count - 3}
    actual = json.loads(Path(record['request']['inputs']['actual']).read_text())
    mismatches = []
    for row, csv_row in zip(report['rows'], csv_rows, strict=True):
        original = oracle[row['path']]
        assert row['component'] == original['component']
        assert row['expected_bytes'] == int(original['expected_bytes'])
        sizes = [r['bytes'] for r in actual if r['path'] == row['path']]
        assert row['actual_count'] == len(sizes) and json.loads(row['actual_bytes']) == sizes
        expected_status = {'part0/file0.bin': 'missing', 'part0/file1.bin': 'mismatch',
                           'part0/file2.bin': 'duplicate'}.get(row['path'], 'ok')
        assert row['status'] == expected_status
        assert row['source'] in record['request']['inputs']['sources']
        assert csv_row == {k: str(v) for k, v in row.items()}
        if row['note'] != original['note']:
            mismatches.append({'path': row['path'], 'expected': original['note'], 'actual': row['note']})
    assert len(mismatches) == drift
    assert response['value']['json_verified'] and response['value']['csv_verified']
    results[label] = dict(run_id=response['resume']['run_id'], status=response['run_status'],
                          achieved=not mismatches, rows=count, unexpected=extra, failures=failures,
                          drift=mismatches, source_complete=response['source_complete'],
                          elapsed_seconds=record['elapsed'], usage=response['usage'],
                          save_readback_equal=True, result_ref=response['result_ref']['id'])
output = ROOT / 'docs/experiments/long_sentence_imagination/round_20/evidence'
output.mkdir(exist_ok=True)
(output / 'validation.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
print(json.dumps({k: {key: val[key] for key in ['achieved', 'rows', 'unexpected', 'failures']}
                  for k, val in results.items()}, ensure_ascii=False, indent=2))
