"""Run preserved AI programs in disposable fixture copies with call/event observation.

These probes test observed programs, not universal model behavior or speedups.
The budget branch is held until schedule completion (or a bounded timeout).
No production program or prior experiment artifact is modified.
"""
import collections
import contextlib
import hashlib
import io
import json
import runpy
import shutil
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BASE = ROOT / 'outputs/long_sentence_imagination/2026-10-22_89회차'
OUT = BASE.with_name(BASE.name + '_repair')


def observe(source, args, budget=None, schedule=None):
    counts = collections.Counter()
    event = threading.Event()
    observations = []

    def profile(frame, kind, arg):
        if frame.f_code.co_filename != str(source):
            return
        name = frame.f_code.co_name
        if kind == 'call':
            counts[name] += 1
            if name == budget:
                observations.append({'budget_wait_released_by_schedule': event.wait(5)})
        if kind == 'return' and name == schedule:
            event.set()

    argv = sys.argv
    try:
        sys.argv = [str(source), *map(str, args)]
        sys.setprofile(profile)
        threading.setprofile(profile)
        with contextlib.redirect_stdout(io.StringIO()):
            runpy.run_path(str(source), run_name='__main__')
    finally:
        sys.setprofile(None)
        threading.setprofile(None)
        sys.argv = argv
    return {'source': str(source.relative_to(ROOT)),
            'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'calls': dict(counts), 'observations': observations}


def main():
    if sys.argv[1:] == ['restored']:
        target = OUT / 'behavior/restored'
        target.mkdir(parents=True, exist_ok=False)
        shutil.copytree(OUT / 'snapshots/T3/T3', target / 'previous')
        shutil.copytree(BASE / 'reference/initial_inputs', target / 'inputs')
        shutil.copyfile(BASE / 'staged/records_restored.json', target / 'inputs/records.json')
        source = OUT / 'snapshots/T4/T4/tools/review.py'
        args = ['--inputs', target / 'inputs', '--out', target / 'T4',
                '--prev', target / 'previous', '--conditions', target / 'previous/conditions.json']
        result = observe(source, args)
        path = OUT / 'runs/behavior_probes.json'
        results = json.loads(path.read_text())
        results['repair_classification'] = result
        path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
        print(json.dumps({k: result['calls'].get(k) for k in ('gate_state', 'run_data_gates', 'merge')}))
        return
    root = OUT / 'behavior/reproducible'
    root.mkdir(parents=True, exist_ok=False)
    inputs = BASE / 'reference/initial_inputs'
    results = {}
    for label in ('baseline', 'repair'):
        target = root / label
        target.mkdir()
        if label == 'baseline':
            source = HERE / 'ai_T1_observed.py'
            args = [inputs, target]
            budget, schedule = 'review_budget', 'review_schedule'
        else:
            source = OUT / 'snapshots/T1/T1/tools/review.py'
            args = ['--inputs', inputs, '--out', target]
            budget, schedule = 'run_budget', 'run_schedule'
        results[label + '_join'] = observe(source, args, budget, schedule)
    target = root / 'baseline_classification'
    shutil.copytree(BASE / 'snapshots/T3', target / 'ai')
    shutil.copytree(inputs, target / 'inputs')
    shutil.copyfile(BASE / 'staged/records_restored.json', target / 'inputs/records.json')
    (target / 'ai/T4').mkdir()
    results['baseline_classification'] = observe(HERE / 'ai_T4_observed.py', [target / 'inputs', target / 'ai'])
    (OUT / 'runs/behavior_probes.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
    assert results['baseline_join']['observations'] == [{'budget_wait_released_by_schedule': False}]
    assert results['repair_join']['observations'] == [{'budget_wait_released_by_schedule': True}]
    assert results['baseline_classification']['calls']['states_of'] == 1800
    print('Dependency event probes and baseline classification count: passed')


if __name__ == '__main__':
    main()
