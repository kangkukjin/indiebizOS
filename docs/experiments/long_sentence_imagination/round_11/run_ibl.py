"""Transport saved IBL to its public API; no task calculations here."""
import json
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
LOCAL = ROOT / 'outputs/long_sentence_imagination/2026-09-30_11회차'
label = sys.argv[1]
mode = label.replace('_fixed', '')
check = len(sys.argv) > 2 and sys.argv[2] == 'check'
inputs = {'folder': str(LOCAL / 'inputs'), 'tariff_path': str(LOCAL / ('tariffs_variant.json' if mode == 'variant' else 'inputs/tariffs.json')), 'out': str(LOCAL / ('trainer_' + label))}
if mode == 'variant':
    prior = json.loads((LOCAL / ('ibl_main_fixed_run.json' if label.endswith('_fixed') else 'ibl_main_run.json')).read_text())['response']
    inputs['cached'] = prior['value']['base']
payload = {'code': (HERE / (mode + '.ibl')).read_text(), 'inputs': inputs, 'check': check, 'edition': 2, 'origin': 'training', 'project_path': str(ROOT / 'projects/하드웨어'), 'budget': {'steps': 600000, 'rows': 20000}}
started = time.monotonic()
request = urllib.request.Request('http://127.0.0.1:8765/ibl/execute', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(request, timeout=900) as response:
    result = json.load(response)
record = {'elapsed_seconds': time.monotonic() - started, 'request': payload, 'response': result}
name = 'ibl_' + label + ('_check' if check else '_run') + '.json'
(LOCAL / name).write_text(json.dumps(record, ensure_ascii=False, indent=2))
print(json.dumps({'saved': str(LOCAL / name), 'elapsed_seconds': record['elapsed_seconds'], 'response': {k: v for k, v in result.items() if k not in ('value', 'value_wire', 'guards', 'functions', 'usage', 'evidence')}}, ensure_ascii=False)[:24000])
