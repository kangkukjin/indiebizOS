import boot_paths  # noqa: F401
import pytest
from ibl_v2_adapters import Adapter, Adapted
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime
from ibl_v2_ir import Fault


@pytest.mark.parametrize('partial,expected', [(False, 'satisfied'), (True, 'undetermined')])
def test_validated_fallback_preserves_audit_and_scoped_commit(partial, expected):
    committed = []
    def primary(rt, a):
        raise Fault('UNAVAILABLE', 'unavailable')
    def mirror(rt, a):
        rt.commit_scope.actions['observation'] = lambda: committed.append(1)
        return Adapted([1, 2], {'incomplete': partial})
    contract = {'version': 1, 'params': {'revision': 'Text'}, 'result': 'List<Number>', 'effects': ['read_external']}
    registry = {'t:primary': Adapter(contract, primary), 't:mirror': Adapter(contract, mirror)}
    source = 'return [t:primary]{revision:"r1"} ?? [t:mirror]{revision:"r1"}'
    completion = [{'id': 'rows', 'predicate': '$value == [1,2]',
                   'sources': [{'action': 't:mirror', 'targets': {'revision': 'r1'}}]}]
    out = Runtime(compile_program(source, registry), completion=completion).run()
    assert out['success'] and not out['source_complete']
    assert any(e['kind'] == 'tool_failure' for e in out['evidence'])
    assert out['completion']['status'] == expected, out
    assert bool(committed) is (expected == 'satisfied')


def test_business_json_cannot_certify_completion():
    spec = [{'id': 'rows', 'predicate': '$value.complete', 'sources': [{'action': 't:source', 'targets': {}}]}]
    out = Runtime(compile_program('return {complete:true}'), completion=spec).run()
    assert out['completion']['status'] == 'undetermined'


def test_effectful_completion_predicate_rejected():
    with pytest.raises(Fault):
        Runtime(compile_program('return 1'), completion=[{'id': 'x', 'predicate': '[t:write]{}',
                                                        'sources': [{'action': 't:source', 'targets': {}}]}])


def test_discarded_source_cannot_certify_literal_result():
    contract = {'version': 1, 'params': {}, 'result': 'Number', 'effects': ['read_external']}
    registry = {'t:source': Adapter(contract, lambda rt, a: 2)}
    spec = [{'id': 'x', 'predicate': '$value == 2', 'sources': [{'action': 't:source', 'targets': {}}]}]
    out = Runtime(compile_program('[t:source]{}; return 2', registry), completion=spec).run()
    assert out['completion']['status'] == 'undetermined'
    assert any(e['kind'] == 'invoke' for e in out['evidence'])



def test_completion_cannot_reset_shared_execution_budget():
    from ibl_v2_runtime import Budget
    spec = [{'id': 'x', 'predicate': 'len(map($value,($x)=>$x+1)) == 80',
             'sources': [{'action': 't:source', 'targets': {}}]}]
    registry = {'t:source': Adapter({'version': 1, 'params': {}, 'result': 'List<Number>',
                                    'effects': ['read_external']}, lambda rt, a: list(range(80)))}
    budget = Budget(steps=60)
    out = Runtime(compile_program('return [t:source]{}', registry), completion=spec, budget=budget).run()
    assert out['completion']['status'] == 'undetermined'
    assert budget.used_steps > 60


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__]))
