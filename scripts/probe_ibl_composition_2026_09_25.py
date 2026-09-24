#!/usr/bin/env python3
"""Deterministic composition audit; no model, network leaf, or business write.

Run with the repository venv. --live repeats cases through the running localhost
HTTP API (normal execution receipts are retained). --library checks stored native
definitions without executing their bodies. Outputs contain synthetic inputs only.
This diagnostic reports known failures rather than hiding them as expected passes.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
import json
import tempfile
import time
import urllib.request

from ibl_v2_compile import compile_program
from ibl_v2_ir import Fault
from ibl_v2_runtime import Runtime


def cases():
    out = []

    def add(name, code, expected, inputs=None, complete=True):
        out.append(dict(name=name, code=code, expected=expected,
                        inputs=inputs or {}, complete=complete))

    for count in (2, 3, 4, 8):
        branches = ' & '.join('{n:' + str(n) + '}' for n in range(count))
        add(f'parallel_record_{count}', '$x=' + branches + '\nreturn $x[0].n', 0)
        lists = ' & '.join('[{n:' + str(n) + '}]' for n in range(count))
        add(f'parallel_flat_map_{count}', '$x=' + lists + '''
          $flat=$x >> [table:each]{mode:"flat_map"}{return $it}
          $flat >> [table:each]{return $it.n}''', list(range(count)))
    for choice in (1, 2):
        add(f'case_return_{choice}', '''[def:f]($choice){
          [case:$choice]{[when:1]{return {n:1}}[else]{$y={n:2}}}
          return $y
        }
        $r=[fn:f]{choice:$choice}
        return $r.n''', choice, {'choice': choice})
        add(f'if_return_control_{choice}', '''[def:f]($choice){
          [if:$choice==1]{return {n:1}}[else]{$y={n:2}}
          return $y
        }
        $r=[fn:f]{choice:$choice}
        return $r.n''', choice, {'choice': choice})
    for divisor in (1, 0):
        add(f'catch_return_{divisor}', '''[def:f]($divisor){
          [try]{$x={n:8/$divisor}}[catch]{return {n:0}}
          return $x
        }
        $r=[fn:f]{divisor:$divisor}
        return $r.n''', 8 if divisor else 0, {'divisor': divisor})
        add(f'catch_expression_control_{divisor}', '''[def:f]($divisor){
          $x=[try]{{n:8/$divisor}}[catch]{{n:0}}
          return $x
        }
        $r=[fn:f]{divisor:$divisor}
        return $r.n''', 8 if divisor else 0, {'divisor': divisor})
    for size in (0, 1, 3, 130):
        add(f'nested_function_each_{size}', '''[def:scale]($rows,$factor){
          $rows >> [table:each]{parallel:4}{return {id:$it.id,n:$it.n*$factor}}
        }
        [def:twice]($rows){
          $first=[fn:scale]{rows:$rows,factor:2}
          return $first >> [fn:scale]{factor:3}
        }
        [fn:twice]{rows:$rows}''',
            [{'id': f'{n:03}', 'n': n * 6} for n in range(size)],
            {'rows': [{'id': f'{n:03}', 'n': n} for n in range(size)]})
    add('nested_flat_map', '''[[1,2],[],[3]] >> [table:each]{mode:"flat_map",parallel:2}{
      $it >> [table:each]{parallel:2}{return $it*2}
    }''', [2, 4, 6])
    add('collect_failure_then_compose', '''$r=[2,0,4] >> [table:each]{on_error:"collect",parallel:3}{return 8/$it}
      $r >> [table:each]{[if:is_ok($it)]{return unwrap($it)}[else]{return -1}}''',
        [4, -1, 2], complete=False)
    add('empty_is_not_failure', '[] ?? [1]', [])
    add('failure_fallback', '(1/0) ?? 7', 7)
    add('closure_snapshot', '$n=2\n$f=($x)=>$x*$n\n$n=9\nreturn $f(3)', 6)
    add('function_defaults_pipe', '[def:add]($x,$n=3){return $x+$n}\n4 >> [fn:add]{}', 7)
    add('repeat_reduce', '$n=0\n[repeat:5]{$n=$n+$i}\nreturn $n', 10)
    return out


def evaluate(case, live=False):
    start = time.perf_counter()
    try:
        if live:
            body = json.dumps({'edition': 2, 'code': case['code'],
                               'project_path': case.get('project_path', str(ROOT)),
                               'inputs': case['inputs']}).encode()
            req = urllib.request.Request('http://127.0.0.1:8765/ibl/execute',
                                         data=body, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=60) as response:
                result = json.load(response)
        else:
            plan = compile_program(case['code'], inputs=case['inputs'])
            result = Runtime(plan, case['inputs']).run()
    except Exception as exc:
        result = {'success': False, 'error': f'{type(exc).__name__}: {exc}'}
    passed = (result.get('success') is True and result.get('value') == case['expected']
              and result.get('source_complete') == case['complete'])
    return {**case, 'surface': 'http' if live else 'core', 'passed': passed,
            'elapsed_ms': round((time.perf_counter() - start) * 1000, 1),
            'actual': {k: result[k] for k in ('success', 'value', 'source_complete',
                        'executed', 'status', 'issues', 'diagnostic', 'error', 'usage') if k in result}}


def library_audit():
    from ibl_v2_adapters import load_registry
    from ibl_v2_store import definitions
    registry, sources = load_registry(str(ROOT)), definitions()
    results = []
    for name, code in sorted(sources.items()):
        try:
            p = compile_program(code, registry, definitions=sources)
            results.append({'name': name, 'status': p.report()['status'], 'issues': p.issues})
        except (Fault, ValueError) as exc:
            results.append({'name': name, 'status': 'invalid', 'error': str(exc)})
    return {'registered_actions_and_legacy_functions': len(registry),
            'native_definitions': len(sources), 'definitions': results}


def live_files():
    # Actual file handler, only generated fixture files, no writes by IBL.
    with tempfile.TemporaryDirectory(prefix='ibl-composition-audit-') as tmp:
        for i in range(3):
            (Path(tmp) / f'{i}.txt').write_text(f'fixture-{i}', encoding='utf-8')
        c = {'name': 'real_file_collect_then_transform', 'project_path': tmp, 'inputs': {
            'paths': [str(Path(tmp) / f'{i}.txt') for i in range(4)]},
            'code': '''$read=$paths >> [table:each]{parallel:3,on_error:"collect"}{[self:read]{path:$it}}
              $read >> [table:each]{
                [if:is_ok($it)]{$doc=unwrap($it);return $doc.text}
                [else]{return "missing"}
              }''', 'expected': ['fixture-0', 'fixture-1', 'fixture-2', 'missing'],
            'complete': False}
        return evaluate(c, live=True)


def live_catalog():
    """Two inspected, table-only stored functions; ordinary usage is accounted."""
    definitions = [
        ('stored_native_functions', '''$rows=[{id:"a",score:2},{id:"b",score:7},{id:"c",score:4}]
          $rank=$rows >> [fn:정렬해추리기]{기준:"score",내림차순:true,개수:2,열:["id","score"]}
          $rank >> [fn:열추려보기]{열:["id"],개수:1}''', [{'id': 'b'}]),
        ('stored_legacy_then_native_table', '''$rows=[{team:"a",n:2},{team:"b",n:7},{team:"a",n:4}]
          $r=$rows >> [fn:묶어순위내기]{묶음:"team",값열:"n",개수:2}
          $r.items >> [table:select]{columns:["team","합계"]}''',
         [{'team': 'b', '합계': 7}, {'team': 'a', '합계': 6}]),
    ]
    return [evaluate({'name': name, 'code': code, 'expected': expected,
                      'inputs': {}, 'complete': True}, live=True)
            for name, code, expected in definitions]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--library', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    records = [evaluate(c) for c in cases()]
    if args.live:
        records += [evaluate(c, live=True) for c in cases()]
        records.append(live_files())
        records += live_catalog()
    result = {'cases': records}
    if args.library:
        result['library'] = library_audit()
    result['summary'] = {'total': len(records), 'passed': sum(r['passed'] for r in records),
                         'failed': [r['surface'] + ':' + r['name'] for r in records if not r['passed']]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result['summary'], ensure_ascii=False, indent=2))
    if args.library:
        print('Library:', len(result['library']['definitions']), 'definitions;',
              sum(r['status'] == 'invalid' for r in result['library']['definitions']), 'invalid')
    return int(bool(result['summary']['failed']))


if __name__ == '__main__':
    raise SystemExit(main())
