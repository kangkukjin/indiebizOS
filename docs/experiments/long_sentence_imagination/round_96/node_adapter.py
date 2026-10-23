"""One Node invocation; orchestration and acceptance live in the IBL program."""
import json
import os
import subprocess
import sys
from pathlib import Path

args = json.load(sys.stdin)
proc = subprocess.run(['/usr/local/bin/node', args['runner'], args['engine']],
    input=json.dumps(args['scenario']), text=True, capture_output=True, timeout=40)
if proc.returncode:
    raise RuntimeError(proc.stderr[-4000:])
Path(os.environ['INDIEBIZ_SCRIPT_RESULT']).write_text(proc.stdout, encoding='utf-8')
