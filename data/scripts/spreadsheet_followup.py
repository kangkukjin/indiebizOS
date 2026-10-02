"""Run the repository-owned spreadsheet checks in its live or isolated checkout."""
import io
import json
import runpy
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
args = json.loads(sys.stdin.read() or '{}')
root = (BASE / args.pop('root', '.')).resolve()
if root != BASE and BASE / '.worktrees' not in root.parents:
    raise ValueError('정본 또는 그 격리 경로만 검사합니다')
sys.path.insert(0, str(root / 'backend'))
sys.path.insert(0, str(root / 'scripts'))
suite = args.pop('suite', 'followup')
if suite not in ('followup', 'print', 'links'):
    raise ValueError('지원하지 않는 시트 검사 묶음')
sys.stdin = io.StringIO(json.dumps(args))
script = {'print': 'verify_spreadsheet_print.py', 'links': 'verify_spreadsheet_links.py',
          'followup': 'verify_spreadsheet_followup.py'}[suite]
runpy.run_path(str(root / 'scripts' / script), run_name='__main__')
