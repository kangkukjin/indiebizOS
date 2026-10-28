"""Append one receipt per call to a round-local training ledger."""
import datetime
import json
import os
from pathlib import Path
import sys
import uuid

args = json.load(sys.stdin)
path = Path(args['path']).resolve()
root = (Path(__file__).resolve().parents[2] / 'outputs/long_sentence_imagination').resolve()
if root not in path.parents:
    raise ValueError('training ledger only')
receipt = uuid.uuid4().hex
row = {
    'receipt': receipt,
    'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'origin': os.environ.get('INDIEBIZ_EXECUTION_ORIGIN'),
    'request': args['request'],
}
path.parent.mkdir(parents=True, exist_ok=True)
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
try:
    os.write(fd, (json.dumps(row, ensure_ascii=False) + '\n').encode())
finally:
    os.close(fd)
print(json.dumps({'receipt': receipt, 'path': str(path)}))
