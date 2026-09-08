"""기준 커밋의 모듈을 이 프로세스 메모리에만 복원한다. 작업 파일은 변경하지 않는다."""
import argparse
import importlib
import json
import subprocess
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
if args.out.exists():
    parser.error('기존 기록을 덮어쓰지 않습니다')
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths
sys.path.insert(0, str(ROOT / 'scripts'))
import idiom_experiment_worker as worker
REF = 'cef3c8d9b66ac2b862c07788dba68254dc47919e'

def source(path):
    return subprocess.check_output(['git', 'show', REF + ':' + path], cwd=ROOT, text=True)

for name in ['ibl_code_ir', 'ibl_parser', 'ibl_exec_each', 'workflow_binding', 'workflow_contract', 'workflow_engine']:
    module = importlib.import_module(name)
    path = 'backend/ibl/' + name + '.py'
    exec(compile(source(path), str(ROOT / path), 'exec'), module.__dict__)

original_load = worker.load

def load(name, path):
    module = original_load(name, path)
    relative = str(Path(path).relative_to(ROOT))
    if relative == 'data/packages/installed/tools/data-ops/handler.py':
        exec(compile(source(relative), str(path), 'exec'), module.__dict__)
    return module

worker.load = load
from ibl_boundary_probe import probe
from ibl_boundary_cases_round6 import cases
rows = [probe(c) for c in cases()]
report = {'baseline': REF, 'method': 'original production modules executed in isolated process; current fixture judge',
          'rows': rows, 'passed': sum(r['ok'] for r in rows), 'cases': len(rows)}
args.out.parent.mkdir(parents=True, exist_ok=True)
args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
print({k:v for k,v in report.items() if k != 'rows'})
