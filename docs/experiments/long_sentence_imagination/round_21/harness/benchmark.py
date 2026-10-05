"""Compare pre-repair source from Git and working source, alternating five runs."""
import cProfile
import json
import statistics
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-10-05_21회차'
SOURCE = 'data/packages/installed/tools/data-ops/chunk_ops.py'
OLD = '0e85d86f96ac0baf72ac99380a77993f57cc457c'


def load(source):
    namespace = {}
    exec(compile(source, SOURCE, 'exec'), namespace)
    return namespace['_op_chunk']


before = load(subprocess.check_output(['git', 'show', f'{OLD}:{SOURCE}'], cwd=ROOT, text=True))
after = load((ROOT / SOURCE).read_text())
documents = json.loads((OUT / 'input/documents.json').read_text())['documents']
cases = {'manual_lines': '\n'.join(d['text'] for d in documents), 'short_lines': 'ab\n' * 30000,
         'short_paragraphs': 'ab\n\n' * 30000}
results = {}
for name, text in cases.items():
    params = {'by': 'paragraph' if name == 'short_paragraphs' else 'line', 'size': 20000}
    original, repaired = before(text, params), after(text, params)
    assert repaired == original
    row = {'chars': len(text), 'chunks': repaired['count'], 'outputs_equal': True}
    timings = {'before': [], 'after': []}
    for i in range(5):
        functions = [('before', before), ('after', after)]
        for label, operation in functions if i % 2 == 0 else reversed(functions):
            start = time.perf_counter()
            operation(text, params)
            timings[label].append(time.perf_counter() - start)
    for label, operation in [('before', before), ('after', after)]:
        profile = cProfile.Profile()
        profile.runcall(operation, text, params)
        joins = sum(e.callcount for e in profile.getstats()
                    if isinstance(e.code, str) and "'join' of 'str'" in e.code)
        row[label] = {'seconds': timings[label], 'median_seconds': statistics.median(timings[label]),
                      'join_calls': joins}
    row['speedup_median'] = row['before']['median_seconds'] / row['after']['median_seconds']
    results[name] = row
path = ROOT / 'docs/experiments/long_sentence_imagination/round_21/evidence/benchmark.json'
path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
print(json.dumps(results, ensure_ascii=False, indent=2))
