"""Training fixture: normalize row formats and numeric units only."""
import json
import sys

args = json.load(sys.stdin)
payload = args['payload']
kind = args['kind']
aliases = args.get('aliases', {})
if kind == 'jsonl':
    payload = [json.loads(line) for line in payload.splitlines() if line.strip()]
rows = []
for row in payload:
    normalized = dict(row)
    if 'item' in normalized:
        normalized['item'] = aliases.get(normalized['item'], normalized['item'])
    for name in ['quantity', 'available', 'reserved', 'pack', 'unit_price', 'shipping']:
        if name in normalized and normalized[name] not in (None, ''):
            normalized[name] = int(normalized[name])
    rows.append(normalized)
print(json.dumps(rows, ensure_ascii=False))
