"""Measure only context retrieval; identical files and windows before/after."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
import builtins
import importlib.util
import json
import time
import tracemalloc

spec = importlib.util.spec_from_file_location('probe_fs_grep', ROOT / 'data/packages/installed/tools/system_essentials/fs_grep.py')
grep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grep)
out = ROOT / 'outputs/long_sentence_imagination/2026-10-07_31회차'
path = out / 'context_large.txt'
if not path.exists():
    with path.open('w') as stream:
        for n in range(100000):
            stream.write(f'{n:06} ' + '본문 ' * 20 + '\n')
counter = {'lines': 0}


class ObservedFile:
    def __init__(self, *args, **kwargs):
        self.file = builtins.open(*args, **kwargs)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.file.close()

    def __iter__(self):
        return self

    def __next__(self):
        line = next(self.file)
        counter['lines'] += 1
        return line


grep.open = ObservedFile
results = []
for positions in ([2], [2, 99999]):
    counter['lines'] = 0
    tracemalloc.start()
    started = time.perf_counter()
    windows = grep._context_windows(str(path), positions, 1, {})
    elapsed = time.perf_counter() - started
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert all([n for n, _ in windows[p]] == [p - 1, p, p + 1] for p in positions)
    results.append({'positions': positions, 'lines_read': counter['lines'], 'elapsed_s': elapsed,
                    'peak_bytes': peak, 'windows': windows})
print(json.dumps(results, ensure_ascii=False, indent=2))
