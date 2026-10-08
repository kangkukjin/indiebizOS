"""Interleaved old/current shared sorting, with identical input and output checks."""
import cProfile
import hashlib
import json
import pstats
import statistics
import subprocess
import sys
import time
import tracemalloc
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-08_35회차'
sys.path.insert(0, str(ROOT / 'backend'))
from common import value_semantics as current

BASE = 'c7bc6d5be989641c64f0c5ba62da546a08f98b7a'
old = types.ModuleType('round35_before_values')
sys.modules[old.__name__] = old
exec(subprocess.check_output(['git', 'show', BASE + ':backend/common/value_semantics.py'], cwd=ROOT), old.__dict__)
rows = json.loads((OUT / 'source/base/events.json').read_text())
modules = {'before': old, 'after': current}
samples = {name: [] for name in modules}
outputs = {}
for iteration in range(22):
    names = ['before', 'after'] if iteration % 2 == 0 else ['after', 'before']
    for name in names:
        start = time.perf_counter()
        result = modules[name].sort_records(rows, 'at')
        samples[name].append((time.perf_counter() - start) * 1000)
        outputs[name] = result
assert outputs['before'] == outputs['after']
record = dict(baseline=BASE, rows=len(rows), same_output=True, measures={})
for name, module in modules.items():
    profile = cProfile.Profile()
    profile.runcall(module.sort_records, rows, 'at')
    counts = {key[2]: value[1] for key, value in pstats.Stats(profile).stats.items()
              if key[2] in {'key', 'datetime_value', '_canonical_moment_text', '_moment_microseconds'}}
    tracemalloc.start()
    module.sort_records(rows, 'at')
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    record['measures'][name] = dict(median_ms=statistics.median(samples[name]), samples_ms=samples[name],
                                    calls=counts, python_peak_bytes=peak)
(OUT / 'runs/benchmark.json').write_text(json.dumps(record, indent=2))
print(json.dumps(record, indent=2))
