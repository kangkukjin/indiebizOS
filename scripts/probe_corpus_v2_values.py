"""Reproducible pure-value probes for the first corpus-review batch."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401

import argparse
import json

from ibl_corpus_snapshot import dump
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
    dump(base / 'audit/value_probes.json', {'passed': len(out), 'external_calls': 0, 'cases': out})
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    args = parser.parse_args()
    print(json.dumps({'passed': len(probes(args.snapshot.resolve())), 'external_calls': 0}))
