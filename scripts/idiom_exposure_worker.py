"""Retired edition-1 exposure experiment entry; performs no actions."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import boot_paths  # noqa: E402,F401
import json


def run(req):
    from ibl_edition import retired_result
    result = retired_result()
    return {'quality_ok': False, 'verdict': result['error'], 'result': result,
            'observed': {'leaf_calls': [], 'fn_calls': []}, 'runtime_ms': 0}


if __name__ == '__main__':
    print(json.dumps(run(json.loads(sys.stdin.read())), ensure_ascii=False))
