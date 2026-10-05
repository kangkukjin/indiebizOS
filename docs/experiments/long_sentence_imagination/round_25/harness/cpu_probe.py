"""Isolated CPU diagnostic of the already executed pure settlement prefix."""
import boot_paths  # noqa: F401
import cProfile
import io
import json
import pstats
import time
from pathlib import Path
from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime, Budget

ROOT = Path(__file__).resolve().parents[5]
DOC = ROOT / 'docs/experiments/long_sentence_imagination/round_25'
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-06_25회차'
rows = json.loads((OUT / 'trainer/main/details.json').read_text())
inputs = {'prepared': {'rows': rows, 'source_complete': True, 'failures': []}, 'threshold': 30000}
source = (DOC / 'drafts/settle_v1.ibl').read_text().split('$writes=')[0] + '\nreturn $summary'
registry = load_registry(str(ROOT), 'LSI25_trainer')
profile = cProfile.Profile()
start = time.monotonic()
profile.enable()
plan = compile_program(source, registry, inputs)
compiled = time.monotonic()
result = Runtime(plan, inputs, budget=Budget(steps=1000000, rows=100000)).run()
profile.disable()
assert result['success'], result
buffer = io.StringIO()
pstats.Stats(profile, stream=buffer).strip_dirs().sort_stats('cumulative').print_stats(40)
(OUT / 'evidence/profile_before.txt').write_text(buffer.getvalue())
print('compile', compiled-start, 'runtime', time.monotonic()-compiled)
print(buffer.getvalue())
