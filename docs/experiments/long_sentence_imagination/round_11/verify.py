"""Independent output verification, never produces the task deliverables."""
import ast
import json
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
LOCAL = HERE.parents[3] / 'outputs/long_sentence_imagination/2026-09-30_11회차'

def read(p):
    return json.loads(p.read_text())

def rows(v):
    return v if isinstance(v, list) else v.get('rows', v.get('items'))

mode = sys.argv[1]
folder = LOCAL / mode
variant = 'variant' in mode
expected = read(LOCAL / ('expected_variant.json' if variant else 'expected.json'))
print('expected shape:', list(expected))
summary = read(folder / 'summary.json')
if isinstance(summary.get('status_counts'), list):
    summary['status_counts'] = {r['status']: r['count'] for r in summary['status_counts']}
intervals = rows(read(folder / 'intervals.json'))
anomalies = rows(read(folder / 'anomalies.json'))
errors = []
summary['status_counts'] = {k:v for k,v in summary['status_counts'].items() if v}
summary['by_meter'] = [{k:(r.get('total_usage') if k=='usage' and 'usage' not in r else r.get(k)) for k in ['meter','usage','known_charge','unpriced_intervals']} for r in summary['by_meter']]
if anomalies and 'rows' in anomalies[0]:
    for group in anomalies:
        if sorted(group['source_ids']) != sorted(r['source_id'] for r in group['rows']):
            errors.append({'key':'anomaly.source_ids','message':'source IDs mismatch'})
    anomalies = [r for group in anomalies for r in group['rows']]
for key, value in expected['summary'].items():
    if summary.get(key) != value:
        errors.append({'key': key, 'expected': value, 'actual': summary.get(key)})
key = lambda r: (r['meter'], r['start'], r['end'])
if sorted(intervals, key=key) != sorted(expected['intervals'], key=key):
    errors.append({'key': 'intervals', 'message': 'full row comparison mismatch'})
if sorted(anomalies, key=lambda r:r['source_id']) != sorted(expected['anomalies'], key=lambda r:r['source_id']):
    errors.append({'key': 'anomalies', 'message': 'full source row comparison mismatch'})
report = (folder / 'report.md').read_text()
for k in ['input_rows','interval_count','total_usage','known_charge','unpriced_intervals']:
    if str(expected['summary'][k]) not in report.replace(',', ''):
        errors.append({'key':'report.'+k, 'message':'required number absent'})
record = {'mode': mode, 'passed': not errors, 'intervals':len(intervals), 'anomalies':len(anomalies), 'by_meter':len(summary.get('by_meter', [])), 'errors':errors}
(LOCAL / ('verification_corrected_' + mode + '.json')).write_text(json.dumps(record, ensure_ascii=False, indent=2))
print(json.dumps(record, ensure_ascii=False))
if mode.startswith('trainer'):
    execution = read(LOCAL / ('ibl_' + (('variant' if variant else 'main') + ('_fixed' if mode.endswith('_fixed') else '')) + '_run.json'))
    response = execution['response']
    metrics = {k:response.get(k) for k in ['success','source_complete','usage','resume','execution_notes']}
    metrics['elapsed_seconds'] = execution['elapsed_seconds']
    metrics['response_bytes'] = (LOCAL / ('ibl_' + (('variant' if variant else 'main') + ('_fixed' if mode.endswith('_fixed') else '')) + '_run.json')).stat().st_size
    metrics['actions'] = [e.get('action') for e in response.get('evidence',[]) if e.get('kind')=='invoke']
    (LOCAL / ('metrics_' + mode + '.json')).write_text(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(json.dumps({k:v for k,v in metrics.items() if k!='usage'}, ensure_ascii=False))
raise SystemExit(bool(errors))
