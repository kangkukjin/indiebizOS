"""Compare the existing guard with an isolated candidate, without editing live code."""
import boot_paths  # noqa: F401
import ast
import json
import statistics
import subprocess
import time
from pathlib import Path
import ibl_v2_types as types

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-06_25회차'
rows = json.loads((OUT / 'trainer/main/details.json').read_text())
before_source = subprocess.check_output(
    ['git', 'show', '5bd2c0c1:backend/ibl/ibl_v2_types.py'], cwd=ROOT, text=True)
guard_node = next(node for node in ast.parse(before_source).body
                  if isinstance(node, ast.FunctionDef) and node.name == 'guard')
namespace = dict(vars(types))  # All helpers are unchanged; compare the exact old function.
exec(ast.get_source_segment(before_source, guard_node), namespace)
original = namespace['guard']
candidate = types.guard


if __name__ == "__main__":
    results = []
    for spec, value in [('Unknown', rows), ('List', rows), ('Record', {'rows': rows}), ('List<Record>', rows)]:
        timings = {'before': [], 'candidate': []}
        for repeat in range(5):
            for name, fn in ([('before', original), ('candidate', candidate)] if repeat % 2 == 0 else [('candidate', candidate), ('before', original)]):
                started = time.perf_counter()
                assert fn(value, spec, 'probe') is value
                timings[name].append(time.perf_counter() - started)
        results.append(dict(spec=spec, rows=len(rows), **timings,
                            medians={key: statistics.median(values) for key, values in timings.items()}))
    (OUT / 'evidence/guard_after.json').write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
