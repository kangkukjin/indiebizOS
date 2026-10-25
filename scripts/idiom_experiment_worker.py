"""Historical edition-1 experiment entry. Its execution contract is retired.

The pure module loader remains shared by deterministic package tests.
Use the native runtime tests for new experiments; no automatic source conversion.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
import importlib.util
import json

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_trial(code, case_id, named=True, catalog=None, suite='legacy', source_results=None):
    from ibl_edition import retired_result
    result = retired_result()
    return {'quality_ok': False, 'verdict': result['error'], 'result': result,
            'observed': {'crawl': [], 'brief': 0, 'leaf_calls': [], 'fn_calls': []},
            'runtime_ms': 0}


if __name__ == '__main__':
    req = json.loads(sys.stdin.read())
    print(json.dumps(run_trial(req['code'], req['case_id']), ensure_ascii=False))
