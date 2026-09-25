"""Reuse collected callables without leaking them onto the public wire."""
import boot_paths  # noqa: F401

import pytest

from ibl_v2_adapters import Adapter, table_operation
from ibl_v2_compile import compile_program
from ibl_v2_expr import Closure
from ibl_v2_runtime import Runtime


def execute(code, registry=None, inputs=None):
    plan = compile_program(code, registry, inputs=inputs)
    assert not plan.issues, plan.report()
    return Runtime(plan, inputs=inputs).run()


def table_registry(operation):
    key = 'where' if operation == 'filter' else 'set' if operation == 'compute' else 'columns'
    return {f'fixture:{operation}': Adapter(
        {'version': 1, 'params': {'items': 'List<Record>', key: 'Callable'},
         'result': 'List<Record>', 'effects': ['pure'], 'pipe_input': 'items'},
        lambda rt, args: table_operation(operation, rt, args))}


@pytest.mark.parametrize('operation,argument,body,expected', [
    ('select', 'columns', '{score:$row.score*2}', [{'score': 60}]),
    ('compute', 'set', '{weighted:$row.score*2}', [{'score': 30, 'weighted': 60}]),
    ('filter', 'where', '$row.score>20', [{'score': 30}]),
])
@pytest.mark.parametrize('fn', ['($x)=>$x*2', 'abs'])
def test_unrelated_collected_functions_do_not_poison_table_calls(operation, argument, body, expected, fn):
    code = f'''$unused=[1] >> [table:each]{{on_error:"collect"}}{{return {fn}}}
    [{{score:30}}] >> [fixture:{operation}]{{{argument}:($row)=>{body}}}'''
    out = execute(code, table_registry(operation))
    assert out['success'] and out['value'] == expected, out


@pytest.mark.parametrize('fn', ['($a,$x)=>$a+$x*2', 'max'])
@pytest.mark.parametrize('container,path', [
    ('$collected', '$held[0]'),
    ('{rules:$collected}', '$held.rules[0]'),
    ('[[$collected]]', '$held[0][0][0]'),
])
def test_required_collected_functions_are_fingerprinted_recursively(fn, container, path):
    code = f'''$collected=[1] >> [table:each]{{on_error:"collect"}}{{return {fn}}}
    $held={container}
    [{{score:30}}] >> [fixture:select]{{columns:($row)=>{{score:reduce([$row.score],0,unwrap({path}))}}}}'''
    out = execute(code, table_registry('select'))
    expected = 60 if fn.startswith('(') else 30
    assert out['success'] and out['value'] == [{'score': expected}], out
    assert any(e.get('request_hash') for e in out['evidence'])


def test_nested_result_callable_in_success_value_is_supported_internally():
    code = '''$inner=[1] >> [table:each]{on_error:"collect"}{return abs}
    $outer=[1] >> [table:each]{on_error:"collect"}{return $inner[0]}
    [def:apply]($fn,$x){return $fn($x)}
    $f=unwrap(unwrap($outer[0])); $n=[fn:apply]{fn:$f,x:-30}
    [{score:$n}] >> [fixture:select]{columns:($r)=>{score:$r.score,n:len($outer)}}'''
    out = execute(code, table_registry('select'))
    assert out['success'] and out['value'] == [{'score': 30, 'n': 1}], out


def test_collected_failure_evidence_survives_unused_capture_removal():
    code = '''$rules=[0,2] >> [table:each]{on_error:"collect"}{
    $factor=10/$it; return ($r)=>{score:$r.score*$factor}}
    $f=unwrap($rules[1]); [{score:4}] >> [fixture:select]{columns:$f}'''
    out = execute(code, table_registry('select'))
    assert out['success'] and out['value'] == [{'score': 20}], out
    assert not out['source_complete']
    assert any(e['kind'] == 'collected_error' for e in out['evidence'])


def inspect_closure(expression, setup=''):
    observed = []
    registry = {'fixture:inspect': Adapter(
        {'version': 1, 'params': {'f': 'Callable'}, 'result': 'Number', 'effects': ['pure']},
        lambda rt, args: observed.append(args['f']) or 0)}
    result = execute(setup + '\n[fixture:inspect]{f:' + expression + '}', registry)
    assert result['success'], result
    assert isinstance(observed[0], Closure)
    return observed[0]


@pytest.mark.parametrize('expression,expected', [
    ('($x)=>$x+$factor', {'factor'}),
    ('($factor)=>$factor+1', set()),
    ('($x)=>($y)=>$x+$y+$factor', {'factor'}),
    ('($x)=>($factor)=>$x+$factor', set()),
    ('($x)=>{name:f"${title}",score:$x*$factor}', {'title', 'factor'}),
    ('($x)=>$rules[$x]', {'rules'}),
    ('($x)=>reduce($rules,0,($a,$v)=>$a+$v*$factor)', {'rules', 'factor'}),
])
def test_closures_capture_only_lexically_free_bindings(expression, expected):
    closure = inspect_closure(expression, '$factor=2; $title="가족"; $rules=[3,4]; $unused=99;')
    assert set(closure.env) == expected


def test_nested_lambda_keeps_outer_argument_and_creation_time_values():
    code = '''$factor=2; $make=($x)=>($y)=>$x+$y*$factor
    $add=$make(10); $factor=99; return $add(3)'''
    out = execute(code)
    assert out['success'] and out['value'] == 16, out


def test_unrelated_closure_chain_does_not_grow_the_next_capture():
    setup = '\n'.join(f'$f{i}=($x)=>$x+{i}' for i in range(12))
    closure = inspect_closure('($row)=>$row.score', setup)
    assert closure.env == {}


def test_used_capture_changes_request_hash_but_unused_input_does_not():
    code = '''$rules=[1] >> [table:each]{on_error:"collect"}{return ($a,$x)=>$a+$x*$factor}
    [{score:30}] >> [fixture:select]{columns:($r)=>{score:reduce([$r.score],0,unwrap($rules[0]))}}'''
    outputs = [execute(code, table_registry('select'), inputs={'factor': factor, 'unused': unused})
               for factor, unused in [(2, 10), (2, 99), (3, 99)]]
    assert all(out['success'] for out in outputs), outputs
    hashes = [next(e['request_hash'] for e in out['evidence'] if e.get('request_hash')) for out in outputs]
    assert hashes[0] == hashes[1] and hashes[1] != hashes[2]
    assert [out['value'][0]['score'] for out in outputs] == [60, 60, 90]


@pytest.mark.parametrize('value', ['abs', '($x)=>$x', '[abs]', '{f:abs}'])
def test_internal_fingerprint_support_does_not_expand_public_wire(value):
    out = execute(f'$r=[1] >> [table:each]{{on_error:"collect"}}{{return {value}}}; return $r')
    assert not out['success'] and out['diagnostic']['code'] == 'VALUE_PROTOCOL', out


def test_wrong_callback_arity_is_not_hidden_by_request_encoding():
    code = '''$rules=[2] >> [table:each]{on_error:"collect"}{return ($r)=>$r*$it}
    [{score:30}] >> [fixture:select]{columns:($row)=>{score:reduce([$row.score],0,unwrap($rules[0]))}}'''
    out = execute(code, table_registry('select'))
    assert not out['success'] and out['diagnostic']['code'] == 'CALLABLE', out


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
