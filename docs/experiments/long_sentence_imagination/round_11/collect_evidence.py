"""Collect existing receipts; no task execution or expected-value mutation."""
import hashlib
import json
from pathlib import Path
HERE = Path(__file__).resolve().parent
LOCAL = HERE.parents[3] / 'outputs/long_sentence_imagination/2026-09-30_11회차'
def read(p):
    return json.loads(p.read_text())
record = {'verification': [], 'artifacts': [], 'tool_failures': []}
for mode in ['trainer_main_fixed', 'trainer_variant_fixed', 'system_main', 'system_variant']:
    v = read(LOCAL / ('verification_corrected_' + mode + '.json'))
    errors = []
    for e in v['errors']:
        if e['key'] == 'by_meter':
            e = {'key': 'by_meter', 'differences': [
                {'meter': a['meter'], 'expected': a, 'actual': b}
                for a, b in zip(e['expected'], e['actual']) if a != b]}
        errors.append(e)
    record['verification'].append({**v, 'errors': errors})
    for p in sorted((LOCAL / mode).glob('*')):
        if p.is_file():
            record['artifacts'].append({'mode':mode, 'file':p.name,
                'bytes':p.stat().st_size, 'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
for p in sorted((LOCAL / 'inputs').glob('*.json')):
    record['artifacts'].append({'mode':'inputs', 'file':p.name,
        'bytes':p.stat().st_size, 'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
        'system_copy_identical':p.read_bytes()==(LOCAL/'system_inputs'/p.name).read_bytes()})
for row in read(LOCAL/'system_tool_trace.json')['items']:
    d=json.loads(row['data'])
    if row['kind']=='supervision.tool.finished' and (d.get('is_error') or d.get('check_rejected') or d.get('source_failures')):
        record['tool_failures'].append({'episode':row['episode_id'],'seq':row['event_seq'],
            'evidence':d.get('evidence'),'source_failures':d.get('source_failures')})
(HERE/'evidence.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'verification':record['verification'],'artifact_count':len(record['artifacts'])},ensure_ascii=False))
