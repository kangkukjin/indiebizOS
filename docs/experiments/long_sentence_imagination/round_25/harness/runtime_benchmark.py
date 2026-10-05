"""Paired isolated runtime benchmark of the same full pure settlement prefix."""
import boot_paths  # noqa: F401
import json
import statistics
import time
from pathlib import Path
import ibl_v2_runtime as runtime
import ibl_v2_types as types
from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime, Budget
from guard_probe import candidate, original

ROOT = Path(__file__).resolve().parents[5]
DOC = ROOT / 'docs/experiments/long_sentence_imagination/round_25'
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-06_25회차'
rows = json.loads((OUT / 'trainer/main/details.json').read_text())
inputs = {'prepared': {'rows': rows, 'source_complete': True, 'failures': []}, 'threshold': 30000}
source = (DOC / 'drafts/settle_v1.ibl').read_text().split('$writes=')[0] + '\nreturn $summary'
registry = load_registry(str(ROOT), 'LSI25_trainer')
plan = compile_program(source, registry, inputs)
old_guard = original
times = {'before': [], 'candidate': []}
expected = None
for i in range(3):
    for label, guard in ([('before', old_guard), ('candidate', candidate)] if i % 2 == 0
                         else [('candidate', candidate), ('before', old_guard)]):
        runtime.guard = guard
        start = time.perf_counter()
        result = Runtime(plan, inputs, budget=Budget(steps=1000000, rows=100000)).run()
        elapsed = time.perf_counter() - start
        assert result['success'], result
        comparable = {k:result[k] for k in ['value_wire', 'source_complete', 'evidence', 'recordings']}
        comparable['steps'] = result['usage']['steps']
        comparable['rows'] = result['usage']['rows']
        if expected is None:
            expected = comparable
        assert comparable == expected
        times[label].append(elapsed)
runtime.guard = old_guard
report = dict(timings=times, medians={k:statistics.median(v) for k,v in times.items()},
              equal_value_evidence_recordings_usage=True,
              scope='runtime only, already compiled; no file IO, model, network, final result projection')
(OUT / 'evidence/runtime_after.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps(report, ensure_ascii=False, indent=2))
