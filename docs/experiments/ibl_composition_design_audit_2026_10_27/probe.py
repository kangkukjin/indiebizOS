"""Read-only design audit: synthetic adapters, temporary catalog/journals only.

Run from the canonical repository with .venv/bin/python3 <this file>.
This records current behavior, not acceptance tests for the proposed design.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
from ibl_v2_adapters import Adapter  # noqa: E402
from ibl_v2_compile import compile_program  # noqa: E402
from ibl_v2_ir import Fault  # noqa: E402
from ibl_v2_runtime import Runtime  # noqa: E402
from ibl_run_journal import Journal, reusable_receipts  # noqa: E402


def adapter(run, params=None, result='Number', effects=('pure',), **extra):
    return Adapter({'version': 1, 'params': params or {}, 'result': result,
                    'effects': list(effects), 'implementation_fingerprint': 'audit-v1',
                    **extra}, run)


def codes(plan):
    return [issue['code'] for issue in plan.issues]


def view(out):
    return {key: out[key] for key in ('success', 'value', 'source_complete', 'state_commit')
            if key in out} | {'diagnostic': out.get('diagnostic', {}).get('code')}


def higher_order(tmp):
    source = '[def:choose]($x,$pred){[if:$pred($x)]{return $x}[else]{return null}}'
    applied = source + '; return [fn:choose]{x:2,pred:($v)=>$v>0}'
    isolated, local = compile_program(source), compile_program(applied)
    import function_store
    from function_library import register, validate_changes
    saved_wiring = (function_store._root_provider, function_store._validator,
                    function_store._registrar)
    try:
        function_store.wire(lambda **_: tmp / 'functions', validate_changes, None)
        with patch('ibl_v2_adapters.load_registry', return_value={}), \
                patch('function_consumers.stored_programs', return_value=[]):
            try:
                register('choose', '#!ibl edition=2\n' + source, edition=2)
                saved = {'accepted': True}
            except ValueError as exc:
                saved = {'accepted': False, 'message': str(exc)}
    finally:
        function_store.wire(*saved_wiring)
    numeric = compile_program('[def:absolute]($x){return abs($x)}')
    contract = next(iter(numeric.function_contracts.values()))
    return {'definition': source, 'local_issues': codes(local),
            'local_run': view(Runtime(local).run()), 'standalone_issues': codes(isolated),
            'save': saved, 'numeric_input_contract': contract['param_contracts'],
            'numeric_runtime_guards': numeric.guards}


def resources():
    barrier = threading.Barrier(2)
    lock = threading.Lock()
    state = {'active': 0, 'maximum': 0, 'calls': []}

    def write(rt, args):
        with lock:
            state['active'] += 1
            state['maximum'] = max(state['maximum'], state['active'])
            state['calls'].append(args['key'])
        try:
            barrier.wait(timeout=3)
            return 1
        finally:
            with lock:
                state['active'] -= 1

    registry = {
        'audit:write': adapter(write, {'key': 'Text'}, effects=('write_external',),
                               write_resources={'record': 'key'}),
        'audit:read': adapter(lambda rt, a: 1, {'key': 'Text'}, effects=('read_external',),
                              read_resources={'record': 'key'}),
        'audit:keys': adapter(lambda rt, a: ['same', 'same'], result='List<Text>'),
    }
    direct = compile_program('[audit:write]{key:"same"} & [audit:write]{key:"same"}', registry)
    readwrite = compile_program('[audit:read]{key:"same"} & [audit:write]{key:"same"}', registry)
    source = ('$keys=[audit:keys]{}; '
              '[def:save]($key){return [audit:write]{key:$key}}; '
              'return [fn:save]{key:$keys[0]} & [fn:save]{key:$keys[1]}')
    dynamic = compile_program(source, registry)
    out = Runtime(dynamic).run()
    return {'dynamic_source': source, 'static_write_write_issues': codes(direct),
            'static_read_write_issues': codes(readwrite), 'dynamic_write_write_issues': codes(dynamic),
            'dynamic_run': view(out), 'maximum_concurrent_writes': state['maximum'],
            'resource_keys': state['calls']}


def recovery(tmp):
    writes = []
    registry = {'audit:send': adapter(lambda rt, a: writes.append(a['id']) or 1,
                                    {'id': 'Text'}, effects=('write_external',))}
    original = '$sent=[audit:send]{id:"delivery"}; return 10 / $divisor'
    edited = '$sent=[audit:send]{id:"delivery"}; return 10 / ($divisor + 1)'
    inputs = {'divisor': 0}
    first, second = (compile_program(code, registry, inputs) for code in (original, edited))
    root = tmp / 'journals'
    with Journal(root, first.fingerprint) as journal:
        prior_id = journal.run_id
        failed = Runtime(first, inputs, journal=journal).run()
    with Journal(root, first.fingerprint, {'run_id': prior_id}) as journal:
        same = Runtime(first, inputs, journal=journal).run()
    count_after_same = len(writes)
    try:
        with Journal(root, second.fingerprint, {'run_id': prior_id}):
            changed_resume = 'accepted'
    except Fault as exc:
        changed_resume = exc.code
    receipts = reusable_receipts(root, prior_id)
    with Journal(root, second.fingerprint) as journal:
        repaired = Runtime(second, inputs, journal=journal, reusable=receipts,
                           reuse_run=prior_id).run()
    return {'original': original, 'edited': edited, 'initial': view(failed),
            'same_code_resume': view(same), 'writes_after_same_resume': count_after_same,
            'changed_code_resume': changed_resume, 'reuse_receipts': len(receipts),
            'edited_reuse': view(repaired), 'writes_after_edit': len(writes)}


def completeness():
    committed = []

    def unavailable(rt, args):
        raise Fault('UNAVAILABLE', 'synthetic source unavailable')

    def available(rt, args):
        rt.commit_scope.actions['observation'] = lambda: committed.append('observation')
        return {'items': [1, 2], 'complete': True}

    registry = {
        'audit:primary': adapter(unavailable, result={'items': 'List<Number>', 'complete': 'Bool'},
                                 effects=('read_external',)),
        'audit:mirror': adapter(available, result={'items': 'List<Number>', 'complete': 'Bool'},
                                effects=('read_external',)),
    }
    source = '$r=([audit:primary]{} ?? [audit:mirror]{}); return $r'
    plan = compile_program(source, registry)
    out = Runtime(plan).run()
    failure_count = sum(e['kind'] == 'tool_failure' for e in out.get('evidence', []))
    recovered_count = sum(e['kind'] == 'recovered' for e in out.get('evidence', []))
    direct = Runtime(compile_program('return [audit:mirror]{}', registry)).run()
    return {'source': source, 'issues': codes(plan), 'fallback': view(out),
            'tool_failures_preserved': failure_count, 'recovered_events': recovered_count,
            'direct_mirror': view(direct), 'committed_observations_total': len(committed),
            'note': 'Synthetic mirrors return identical data; the language has no declared equivalence obligation here.'}


def output_boundary():
    calls = []
    registry = {'audit:send': adapter(lambda rt, a: calls.append('sent') or 1,
                                    effects=('write_external',))}
    source = '[audit:send]{}; return {callback:abs}'
    plan = compile_program(source, registry)
    out = Runtime(plan).run()
    return {'source': source, 'issues': codes(plan), 'result_contract': plan.report()['result_contract'],
            'run': view(out), 'write_calls_before_transport_failure': len(calls)}


def main():
    with tempfile.TemporaryDirectory(prefix='ibl-design-audit-') as temp:
        tmp = Path(temp)
        result = {
            'baseline_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'scope': 'synthetic adapters; temporary catalogs and journals; no real external effects',
            'higher_order_contract': higher_order(tmp), 'resource_composition': resources(),
            'edited_recovery': recovery(tmp), 'completion_composition': completeness(),
            'output_boundary': output_boundary(),
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
