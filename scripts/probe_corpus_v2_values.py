"""Reproducible pure-value probes for the first corpus-review batch."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
import json

from ibl_corpus_snapshot import dump, sha
from audit_ibl_corpus_v2 import forbidden
from ibl_v2_adapters import Adapter, table_operation
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime
from ibl_v2_ir import UNIT, unpack


def pure_registry(contracts):
    result = {}
    for key, contract in contracts.items():
        adapter = contract.get('adapter', {})
        if adapter.get('protocol') == 'core-table/2' and contract['effects'] == ['pure']:
            op = adapter['operation']
            def run(rt, args, op=op):
                return table_operation(op, rt, args)
        else:
            run = forbidden
        result[key] = Adapter(contract, run)
    return result


def probes(base):
    frozen = json.loads((base / 'audit/contracts.json').read_text())
    registry = pure_registry(frozen['contracts'])
    definitions = frozen['definitions']
    out = []
    def check(name, code, inputs, expected=None, expected_success=True):
        plan = compile_program(code, registry, inputs, definitions)
        result = Runtime(plan, inputs).run()
        actual = unpack(result['value_wire']['data']) if result.get('success') else None
        assert result.get('success') is expected_success, (name, result)
        if expected_success:
            assert actual == expected, (name, actual, expected)
        out.append({'name': name, 'passed': True, 'static_status': plan.report()['status'],
                    'success': result.get('success'), 'value_wire': result.get('value_wire'),
                    'diagnostic': result.get('diagnostic'), 'issues': result.get('issues', [])})
    for rows in ([], [{'id': '007', 'score': 3}], [{'id': '007', 'score': 3}, {'id': 'b', 'score': 5}]):
        check('selected_columns_' + str(len(rows)), '[fn:열추려보기]{목록:$rows,열:["id"],개수:1}',
              {'rows': rows}, [{'id': rows[0]['id']}] if rows else [])
        check('sorted_columns_' + str(len(rows)), '[fn:정렬해추리기]{목록:$rows,기준:"score",내림차순:true,개수:1,열:["id"]}',
              {'rows': rows}, [{'id': sorted(rows, key=lambda r: r['score'], reverse=True)[0]['id']}] if rows else [])
    check('negative_take_rejected', '[fn:열추려보기]{목록:[1],열:[],개수:-1}', {}, expected_success=False)
    check('legacy_return_assignment_is_unit',
          '[def:probe]($목록){$return=$목록}\n[fn:probe]{목록:[1,2]}', {}, UNIT)
    check('parallel_keeps_nesting', '[1] & [2]', {}, [[1], [2]])
    check('empty_is_not_fallback', '[] ?? [9]', {}, [])
    check('string_is_literal', '$x="actual"\nreturn "${x}"', {}, '${x}')
    # All six stored native composition programs, not rewritten substitutes.
    seeds = json.loads((base / 'data/idioms/ibl_v2_seeds.json').read_text())
    expected = [
        [{'id': '007', 'score': 14}], [1, 2, 3], None,
        [{'original': n, 'square': n*n} for n in (3, 1, 2)], 26, '결과: 5',
    ]
    native = [seed for seed in seeds if not seed.get('alias')]
    if len(native) != len(expected):
        raise ValueError('Native seed inventory changed; review expected values')
    for i, (seed, value) in enumerate(zip(native, expected)):
        if i == 2:
            # Result carries a failure object whose source spans are dynamic.
            plan = compile_program(seed['ibl_code'], registry, definitions=definitions)
            result = Runtime(plan).run()
            assert result['success'], result
            values = unpack(result['value_wire']['data'])
            assert [v.ok for v in values] == [True, False, True]
            assert [values[0].value, values[2].value] == [4, 2]
            assert values[1].error['kind'] == 'runtime'
            out.append({'name': 'native_collect', 'passed': True,
                        'static_status': plan.report()['status'],
                        'value_wire': result['value_wire']})
        else:
            check('native_seed_' + str(i), seed['ibl_code'], {}, value)
        out[-1].update(code_sha256=sha(seed['ibl_code']), intent_sha256=sha(seed['intent']))
    dump(base / 'audit/value_probes.json', {'passed': len(out), 'external_calls': 0, 'cases': out})
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    args = parser.parse_args()
    print(json.dumps({'passed': len(probes(args.snapshot.resolve())), 'external_calls': 0}))
