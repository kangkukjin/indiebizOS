#!/usr/bin/env python3
"""Reproduce the inert authoring benchmark; optionally compare an old compiler.

The baseline loads only that local git revision's compiler, with the current
parser/types/runtime dependencies. This is a compiler comparison, not a full
historical checkout or an AI quality/token benchmark.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
import json
import statistics
import subprocess
import time
import types
from ibl_v2_compile import compile_program
from test_ibl_authoring_support import (FAMILIES, long_fixture,
                                        test_long_programs_have_independent_expected_results)


ERRORS = [
    ('builtin_len', 'return len(4)', 'TYPE'),
    ('builtin_has', 'return has([], "x")', 'TYPE'),
    ('builtin_get', 'return get({}, 1, null)', 'TYPE'),
    ('builtin_result', 'return unwrap(1)', 'TYPE'),
    ('builtin_text', 'return text([])', 'TYPE'),
    ('numeric_literal', 'return 1 + "hello"', 'NUMBER_REQUIRED'),
    ('numeric_call', 'return number("hello")', 'NUMBER_REQUIRED'),
    ('loop_shape', '$x={n:1}\n[repeat:1]{$x={m:2}}\nreturn $x.n', 'MISSING_FIELD'),
    ('repeat_integer', '[repeat:1.5]{return 1}', 'REPEAT_COUNT'),
]


def measure(compile_fn):
    bad, normal, elapsed = [], [], []
    for name, code, expected in ERRORS:
        p = compile_fn(code)
        bad.append({'case': name, 'status': p.report()['status'],
                    'expected': expected, 'detected': expected in [e['code'] for e in p.issues]})
    for family in FAMILIES:
        for size in (0, 1, 3, 10, 50):
            source, inputs, registry, calls = long_fixture(family, size)
            start = time.perf_counter()
            p = compile_fn(source, registry, inputs)
            elapsed.append((time.perf_counter() - start) * 1000)
            normal.append({'family': family, 'size': size, 'lines': len(source.splitlines()),
                           'chars': len(source), 'status': p.report()['status']})
            assert calls == [], 'check invoked a tool'
    stress = []
    for count in (50, 200, 500):
        source = '$x=0\n' + '\n'.join('$x=$x+1' for _ in range(count)) + '\nreturn $x'
        compile_fn(source)
        timings = []
        for _ in range(10):
            start = time.perf_counter()
            p = compile_fn(source)
            timings.append((time.perf_counter() - start) * 1000)
            assert not p.issues
        stress.append({'statements': count + 2, 'p50_ms': round(statistics.median(timings), 3),
                       'p95_ms': round(sorted(timings)[-1], 3), 'samples': 10})
    return {'errors': bad, 'detected': sum(r['detected'] for r in bad),
            'normal_cases': normal, 'normal_rejected': sum(r['status'] == 'invalid' for r in normal),
            'median_fixture_check_ms': round(statistics.median(elapsed), 3), 'stress': stress}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', help='Trusted local git ref: load only its compiler for comparison')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = {'kind': 'synthetic-inert-regression', 'structural_families': 6,
              'input_sizes_per_family': [0, 1, 3, 10, 50], 'external_calls': 0,
              'model_tokens': 'not measured', 'current': measure(compile_program)}
    for family in FAMILIES:
        for size in (0, 1, 3, 10, 50):
            test_long_programs_have_independent_expected_results(family, size)
    result['value_oracles_passed'] = 30
    if args.baseline_ref:
        ref = subprocess.check_output(['git', 'rev-parse', '--verify', args.baseline_ref + '^{commit}'], cwd=ROOT, text=True).strip()
        source = subprocess.check_output(['git', 'show', ref + ':backend/ibl/ibl_v2_compile.py'], cwd=ROOT, text=True)
        module = types.ModuleType('_ibl_authoring_baseline')
        module.__file__ = str(ROOT / 'backend/ibl/ibl_v2_compile.py')
        sys.modules[module.__name__] = module
        exec(compile(source, module.__file__, 'exec'), module.__dict__)
        result['baseline_compiler_ref'] = ref
        result['baseline_scope'] = 'compiler only; current shared dependencies'
        result['baseline'] = measure(module.compile_program)
    output = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
    else:
        print(output)
    return int(result['current']['normal_rejected'] != 0 or result['current']['detected'] != len(ERRORS))


if __name__ == '__main__':
    raise SystemExit(main())
