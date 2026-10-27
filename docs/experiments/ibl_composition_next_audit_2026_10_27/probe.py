"""Current-design counterexamples, not acceptance tests for a future repair.

Only synthetic adapters execute. Journals/function revisions live in temporary
storage. Exit 0 means the recorded limitations were reproduced, not repaired.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import threading
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
from ibl_v2_adapters import Adapter
from ibl_v2_compile import compile_program
from ibl_v2_completion import validate
from ibl_v2_entry import handle_request
from ibl_v2_ir import Fault
from ibl_v2_runtime import Runtime


def adapter(result, effects, run, **contract):
    return Adapter({'version': 1, 'params': {}, 'result': result,
                    'effects': effects, **contract}, run)


def brief(out):
    return {key: out.get(key) for key in ('success', 'executed', 'value', 'source_complete')} | {
        'diagnostic': (out.get('diagnostic') or {}).get('code'),
        'completion': (out.get('completion') or {}).get('status'),
        'state_commit': (out.get('state_commit') or {}).get('status'),
        'issues': [i.get('code') for i in out.get('issues', [])]}


def summarize(source, registry=None):
    plan = compile_program(source, registry or {})
    return {'issues': [i['code'] for i in plan.issues], 'guards': len(plan.guards),
            'functions': [{k: c[k] for k in ('name', 'requirements', 'declared_requirements',
                                            'effects', 'accesses', 'result_contract')}
                          for c in plan.function_contracts.values()]}


def execute(source, registry=None, **kwargs):
    return Runtime(compile_program(source, registry or {}), **kwargs).run()


def requirement_paths(root):
    sources = {
        'scalar': '[def:f]($x){return abs($x)}',
        'field': '[def:f]($x){return abs($x.n)}',
        'field_conflict': '[def:f]($x){$a=abs($x.n);return not $x.n}',
        'application_conflict': '[def:f]($p){$x=$p(1);$a=abs($x);return not $x}',
        'scalar_predicate': '[def:f]($p){[if:$p(1)]{return 1}[else]{return 0}}',
        'field_predicate': '[def:f]($cfg){[if:$cfg.p(1)]{return 1}[else]{return 0}}',
    }
    reports = {name: summarize(source) for name, source in sources.items()}
    assert reports['scalar']['functions'][0]['requirements']['x']
    assert reports['field']['functions'][0]['requirements'] == {}
    assert reports['field_conflict']['issues'] == []
    assert reports['field_conflict']['functions'][0]['requirements'] == {}
    assert reports['application_conflict']['issues'] == []
    assert {r['expected']['type'] for r in reports['application_conflict']['functions'][0]['requirements']['p']
            if r['kind'] == 'result'} == {'Number', 'Bool'}
    assert reports['scalar_predicate']['issues'] == []
    assert 'PURE_EXPRESSION' in reports['field_predicate']['issues']
    concrete = execute(sources['field_predicate'] + ';return [fn:f]{cfg:{p:($n)=>$n>0}}')
    assert concrete['success'] and concrete['value'] == 1
    explicit = '[def:f]($cfg:{p:{"$callable":{params:["Number"],result:"Bool",effects:["pure"]}}}){[if:$cfg.p(1)]{return 1}[else]{return 0}}'
    assert summarize(explicit)['issues'] == []
    import function_store
    from function_library import register, validate_changes
    saved = function_store._root_provider, function_store._validator, function_store._registrar
    try:
        function_store.wire(lambda **_: root / 'functions', validate_changes, None)
        with (patch('ibl_v2_adapters.load_registry', lambda *a, **k: {}),
              patch('function_consumers.stored_programs', lambda: [])):
            ref = register('f', '#!ibl edition=2\n' + sources['field_conflict'], edition=2)
            assert ref['revision']
    finally:
        function_store.wire(*saved)
    # A separate store rules out name/CAS rejection as the cause below.
    try:
        function_store.wire(lambda **_: root / 'predicate_functions', validate_changes, None)
        with (patch('ibl_v2_adapters.load_registry', lambda *a, **k: {}),
              patch('function_consumers.stored_programs', lambda: [])):
            try:
                register('f', '#!ibl edition=2\n' + sources['field_predicate'], edition=2)
                accepted = True
            except ValueError as exc:
                assert '저장 전 검사 거절' in str(exc), str(exc)
                accepted = False
        assert not accepted
    finally:
        function_store.wire(*saved)
    write = adapter('Number', ['write_external'], lambda rt, a: 1,
                    params={'key': 'Text'}, write_resources={'record': 'key'})
    resources = {name: summarize(source, {'t:write': write}) for name, source in {
        'scalar': '[def:w]($key){return [t:write]{key:$key}}',
        'field': '[def:w]($cfg){return [t:write]{key:$cfg.key}}'}.items()}
    assert resources['scalar']['functions'][0]['accesses']['entries'][0]['relations']
    assert resources['field']['functions'][0]['accesses']['entries'][0]['relations'] == []
    return {'sources': sources, 'reports': reports, 'concrete_field_predicate': brief(concrete),
            'explicit_annotation_accepted': True, 'registration': {
                'unsatisfiable_field': 'accepted', 'independent_field_predicate': 'rejected'},
            'resource_relation_reports': resources}


def modular_completion():
    commits = []
    def down(rt, args):
        raise Fault('UNAVAILABLE', 'synthetic source unavailable')
    def good(rt, args):
        rt.commit_scope.actions['observation'] = lambda: commits.append('committed')
        return 2
    reg = {'t:down': adapter('Number', ['read_external'], down),
           't:good': adapter('Number', ['read_external'], good)}
    definition = '[def:fetch](){return [t:down]{} ?? [t:good]{}}'
    source = 'return [fn:fetch]{}'
    plan = compile_program(source, reg, definitions={'fetch': definition})
    duty = {'id': 'result', 'predicate': '$value==2',
            'sources': [{'action': 't:good', 'targets': {}}]}
    explicit = Runtime(plan, completion=[duty]).run()
    assert explicit['completion']['status'] == 'satisfied' and commits == ['committed']
    commits.clear()
    plain = Runtime(plan).run()
    assert plain['success'] and plain['value'] == 2 and not plain['source_complete']
    assert 'completion' not in plain and not commits
    contract = next(c for c in plan.function_contracts.values() if c['name'] == 'fetch')
    assert 'completion' not in contract
    try:
        validate([{**duty, 'id': str(i), 'scope': [i]} for i in range(33)])
        limit = None
    except Fault as exc:
        limit = exc.code
    assert limit == 'COMPLETION_CONTRACT'
    return {'definition': definition, 'source': source, 'request_duty': duty,
            'with_request_contract': brief(explicit), 'without_request_contract': brief(plain),
            'function_contract_keys': sorted(contract), 'flat_33_duties': limit}


def modular_repair(root):
    calls = []
    reg = {'t:send': adapter('Number', ['write_external'], lambda rt, a: calls.append(a['id']) or 10,
                            params={'id': 'Text'}, write_resources={'delivery': 'id'},
                            implementation_fingerprint='synthetic-v1')}
    prefix = '[def:calc]($x,$d){return $x/$d};$sent=[t:send]{id:"delivery"};'
    variants = {
        'inline': ('return $sent/$n', 'return $sent/($n+1)'),
        'function': ('return [fn:calc]{x:$sent,d:$n}', 'return [fn:calc]{x:$sent,d:$n+1}'),
        'binding': ('$v=$sent/$n;return $v', '$v=$sent/($n+1);return $v'),
    }
    results = {}
    with (patch('ibl_v2_adapters.load_registry', lambda *a, **k: reg),
          patch('ibl_v2_store.definitions', lambda: {}),
          patch('tool_batch.prepared_plan', lambda *a: None),
          patch('ibl_run_journal.journal_root', lambda *a: root / 'runs'),
          patch('ibl_continuations.remember', lambda *a: None),
          patch('ibl_continuations.finished', lambda *a: None),
          patch('ibl_v2_learning.record_functions', lambda *a: None)):
        for name, (before, after) in variants.items():
            calls.clear()
            request = {'edition': 2, 'inputs': {'n': 0}}
            first = handle_request({**request, 'code': prefix + before}, str(root))
            assert not first['success'] and first['executed'] and len(calls) == 1
            checked = handle_request({**request, 'code': prefix + after, 'check': True,
                                      'repair': first['resume']}, str(root))
            code = (checked.get('diagnostic') or {}).get('code')
            if name == 'inline':
                assert checked['ok'] and checked['repair']['status'] == 'ready', checked
                resumed = handle_request({**request, 'code': prefix + after,
                    'repair': {**first['resume'], 'plan_hash': checked['repair']['plan_hash']}}, str(root))
                assert resumed['success'] and resumed['value'] == 10 and len(calls) == 1
            else:
                assert code == 'REPAIR_UNSUPPORTED', checked
            results[name] = {'before': prefix + before, 'after': prefix + after,
                             'first': brief(first), 'repair_ready': bool(checked.get('repair')),
                             'diagnostic': code, 'writes': len(calls)}
    return results


def resource_default():
    def run(declared, strict):
        lock, barrier = threading.Lock(), threading.Barrier(2)
        active, peak, calls = 0, 0, 0
        def write(rt, args):
            nonlocal active, peak, calls
            with lock:
                active += 1; calls += 1; peak = max(peak, active)
            barrier.wait(timeout=5)
            with lock:
                active -= 1
            return 1
        extra = {'write_resources': {'record': 'key'}} if declared else {}
        reg = {'t:write': adapter('Number', ['write_external'], write, params={'key': 'Text'}, **extra)}
        source = '[t:write]{key:"shared"} & [t:write]{key:"shared"}'
        out = execute(source, reg, strict_composition=strict)
        return brief(out) | {'calls': calls, 'max_concurrent_writes': peak}
    loose, strict, declared = run(False, False), run(False, True), run(True, False)
    assert loose['success'] and loose['max_concurrent_writes'] == 2
    assert strict['calls'] == 0 and not strict['success']
    assert declared['calls'] == 0 and not declared['success']
    return {'undeclared_default': loose, 'undeclared_strict': strict, 'declared_default': declared}


def failure_composition():
    def fail(rt, args):
        raise Fault('SOURCE_MISSING', 'synthetic missing source', details={'key': 'a'})
    reg = {'t:read': adapter('Number', ['read_external'], fail)}
    direct = '[try]{return [t:read]{}}[catch]{return $error.code}'
    wrapped = '[try]{$r=[table:each]{items:[1],on_error:"collect"}{return [t:read]{}};return unwrap($r[0])}[catch]{return $error.code}'
    values = {k: execute(v, reg) for k, v in {'direct': direct, 'collect_unwrap': wrapped}.items()}
    assert values['direct']['value'] == 'SOURCE_MISSING'
    assert values['collect_unwrap']['value'] == 'UNWRAP_ERR'
    detail = execute(wrapped.replace('return $error.code}', 'return $error.details.code}'), reg)
    assert detail['value'] == 'SOURCE_MISSING'
    return {'sources': {'direct': direct, 'collect_unwrap': wrapped},
            'outcomes': {k: brief(v) for k, v in values.items()},
            'original_error_retained_as_details': detail['value'],
            'function_contract': summarize('[def:read](){return [t:read]{}}', reg)['functions'][0]}


def main():
    with TemporaryDirectory(prefix='ibl-design-audit-') as folder:
        root = Path(folder)
        with patch.dict(os.environ, {'INDIEBIZ_RUNTIME_STATE_DIR': str(root / 'runtime'),
                                      'INDIEBIZ_RECALL_INDEX_DIR': str(root / 'recall')}):
            return {'D1_symbolic_paths': requirement_paths(root),
                    'D2_modular_completion': modular_completion(),
                    'D3_modular_repair': modular_repair(root),
                    'D4_resource_default': resource_default(),
                    'D5_failure_composition': failure_composition()}


if __name__ == '__main__':
    with contextlib.redirect_stdout(io.StringIO()):
        result = main()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
