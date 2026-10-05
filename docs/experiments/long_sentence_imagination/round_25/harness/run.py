"""Transport only: preserve requests, responses and elapsed wall time."""
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-06_25회차'
label, endpoint, request_file = sys.argv[1:4]
data = None if request_file == '-' else Path(request_file).read_bytes()
request = urllib.request.Request('http://127.0.0.1:8765' + endpoint, data=data,
                                 headers={'Content-Type': 'application/json'})
started = time.time()
with urllib.request.urlopen(request, timeout=180) as response:
    result = json.load(response)
record = dict(started=started, ended=time.time(), response=result)
if data:
    record['request'] = json.loads(data)
(OUT / 'runs' / f'{label}.json').write_text(json.dumps(record, ensure_ascii=False, indent=2))
print(json.dumps({k: v for k, v in result.items() if k not in
                 ('value', 'value_wire', 'results', 'functions', 'dependencies',
                  'guards_ref', 'preflight', 'canonical_code')}, ensure_ascii=False)[:6500])
print('elapsed', record['ended'] - started)
