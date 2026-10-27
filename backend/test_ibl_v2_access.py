import boot_paths  # noqa: F401
import threading
import pytest
from ibl_v2_adapters import Adapter
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime


def registry(write, read=lambda rt, a: 1):
    def spec(mode, run):
        return Adapter({'version': 1, 'params': {'key': 'Text'}, 'result': 'Number',
                        'effects': [mode + '_external'], mode + '_resources': {'record': 'key'}}, run)
    return {'t:write': spec('write', write), 't:read': spec('read', read),
            't:keys': Adapter({'version': 1, 'params': {}, 'result': 'List<Text>', 'effects': ['pure']}, lambda rt, a: ['same', 'same'])}


@pytest.mark.parametrize('left,right', [('read', 'write'), ('write', 'read'), ('write', 'write')])
def test_static_interference(left, right):
    plan = compile_program(f'[t:{left}]{{key:"same"}} & [t:{right}]{{key:"same"}}', registry(lambda rt, a: 1))
    assert any(i['code'] == 'PARALLEL_WRITE_CONFLICT' for i in plan.issues)


def test_dynamic_alias_fails_before_either_branch():
    calls = []
    plan = compile_program('$keys=[t:keys]{}; [def:w]($k){return [t:write]{key:$k}}; '
                           'return [fn:w]{k:$keys[0]} & [fn:w]{k:$keys[1]}', registry(lambda rt, a: calls.append(a) or 1))
    assert not plan.issues
    out = Runtime(plan).run()
    assert out['diagnostic']['code'] == 'PARALLEL_RESOURCE_CONFLICT'
    assert not calls


def test_independent_resources_are_concurrent():
    barrier = threading.Barrier(2)
    def write(rt, a):
        barrier.wait(timeout=2)
        return 1
    plan = compile_program('[t:write]{key:"a"} & [t:write]{key:"b"}', registry(write))
    assert Runtime(plan).run()['success']


def test_read_calculate_write_reserves_entire_branch():
    calls = []
    code = '[def:up]($k){$n=[t:read]{key:$k}; return [t:write]{key:$k}}; '
    plan = compile_program(code + '$keys=[t:keys]{}; [fn:up]{k:$keys[0]} & [fn:up]{k:$keys[1]}', registry(lambda rt, a: calls.append(a) or 1))
    assert not Runtime(plan).run()['success']
    assert not calls


def test_each_resolves_duplicate_keys_before_start():
    calls = []
    plan = compile_program('$keys=[t:keys]{}; [table:each]{items:$keys,parallel:2}{[t:write]{key:$it}}', registry(lambda rt, a: calls.append(a) or 1))
    out = Runtime(plan).run()
    assert not out['success'] and not calls, out


def test_hardlinks_conflict_at_admission(tmp_path):
    import os
    a, b = tmp_path / 'a', tmp_path / 'b'
    a.write_text('same')
    os.link(a, b)
    calls = []
    spec = Adapter({'version': 1, 'params': {'path': 'Text'}, 'result': 'Number',
                    'effects': ['write_external'], 'write_resources': {'file': 'path'}}, lambda rt, x: calls.append(x) or 1)
    plan = compile_program('[t:write]{path:$a} & [t:write]{path:$b}', {'t:write': spec}, {'a': str(a), 'b': str(b)})
    out = Runtime(plan, {'a': str(a), 'b': str(b)}).run()
    assert not out['success'] and not calls


def test_strict_mode_requires_declared_resources():
    spec = Adapter({'version': 1, 'params': {}, 'result': 'Number', 'effects': ['write_external']}, lambda rt, a: 1)
    plan = compile_program('[t:write]{} & [t:write]{}', {'t:write': spec})
    assert not Runtime(plan, strict_composition=True).run()['success']



def test_function_contract_exposes_parameter_resource_relationship():
    plan = compile_program('[def:w]($key){return [t:write]{key:$key}}', registry(lambda rt, a: 1))
    contract = next(iter(plan.function_contracts.values()))
    entry = contract['accesses']['entries'][0]
    assert entry['resource_state'] == 'unresolved' and entry['mode'] == 'write'
    assert entry['relations'][0]['variable'][-1] == 'key'


def test_cancelled_admission_starts_no_branches():
    calls = []
    plan = compile_program('[t:write]{key:"a"} & [t:write]{key:"b"}', registry(lambda rt, a: calls.append(a) or 1))
    out = Runtime(plan, cancel_check=lambda: True).run()
    assert not out['success'] and not calls



def test_large_unrelated_value_cannot_hide_known_resource_targets():
    calls = []
    inputs = {'rows': [{'n': i} for i in range(5000)], 'a': 'one', 'b': 'two'}
    plan = compile_program('[t:write]{key:$a} & [t:write]{key:$b}', registry(lambda rt, a: calls.append(a) or 1), inputs)
    out = Runtime(plan, inputs).run()
    assert out['success'] and len(calls) == 2, out


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__]))
