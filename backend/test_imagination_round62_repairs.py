"""Callable builtin substitution across reusable domain compositions."""
import boot_paths  # noqa: F401

import pytest

from ibl_v2_compile import compile_program
from ibl_v2_expr import BUILTINS
from ibl_v2_runtime import Runtime, Budget, Binding
from ibl_v2_adapters import Adapter, table_operation


def run(code, registry=None, **kwargs):
    plan = compile_program(code, registry)
    assert not plan.issues, plan.report()
    return Runtime(plan, **kwargs).run()


# Census covers every declared builtin, including evidence and reduce which
# need the runtime's Binding/budget context rather than just Python values.
EXAMPLES = {
    'len': ('"가족"', 2),
    'has': ('{id:"a"},"id"', True),
    'get': ('{id:"a"},"missing",7', 7),
    'json': ('{id:"a"}', '{"id": "a"}'),
    'number': ('"12"', 12),
    'text': ('true', 'true'),
    'abs': ('-7', 7),
    'round': ('12.345,2', 12.35),
    'min': ('[7,2,4]', 2),
    'max': ('7,2,4', 7),
    'sum': ('[7,2,4]', 13),
    'is_ok': ('$results[0]', True),
    'unwrap': ('$results[0]', 5),
    'error_of': ('$results[1]', None),
    'evidence': ('7', None),
    'reduce': ('[1,2,3],0,($acc,$row)=>$acc+$row', 6),
}


def test_builtin_census_remains_complete():
    assert set(EXAMPLES) == set(BUILTINS)


@pytest.mark.parametrize('name', EXAMPLES)
@pytest.mark.parametrize('placement', ['variable', 'argument', 'default', 'container'])
def test_every_builtin_can_be_passed_as_an_existing_callable(name, placement):
    args, expected = EXAMPLES[name]
    setup = '$results=[2,0] >> [table:each]{on_error:"collect"}{return 10/$it}; '
    # Functions take the result inputs explicitly; they never capture callers.
    forms = {
        'variable': f'$f={name}; return $f({args})',
        'argument': f'[def:apply]($f,$results){{return $f({args})}}; [fn:apply]{{f:{name},results:$results}}',
        'default': f'[def:apply]($results,$f={name}){{return $f({args})}}; [fn:apply]{{results:$results}}',
        'container': f'$ops={{functions:[{name}]}}; $f=$ops.functions[0]; return $f({args})',
    }
    result = run(setup + forms[placement])
    assert result['success'], result
    if name == 'evidence':
        assert result['value']['events']
        assert result['value']['fingerprint']
    elif name == 'error_of':
        assert result['value']['code'] == 'VALUE'
    else:
        assert result['value'] == expected, result


@pytest.mark.parametrize('name', BUILTINS)
def test_indirect_builtin_arity_is_checked_before_argument_access(name):
    result = run(f'$f={name}; return $f()')
    assert not result['success']
    assert result['diagnostic']['code'] == 'ARITY', result


def test_builtin_reduce_callback_and_runtime_bound_reduce_alias():
    result = run('$fold=reduce; return $fold([10,30,20],0,max)')
    assert result['success'] and result['value'] == 30, result


def test_builtin_capture_uses_callable_guard_and_request_fingerprint():
    registry = {'fixture:select': Adapter(
        {'version': 1, 'params': {'items': 'List', 'columns': 'Callable'},
         'result': 'List', 'effects': ['pure']},
        lambda rt, args: table_operation('select', rt, args))}
    code = '$size=len; [fixture:select]{items:["가족","소식"],columns:($row)=>{n:$size($row)}}'
    result = run(code, registry)
    assert result['success'] and result['value'] == [{'n': 2}, {'n': 2}], result
    assert any(e.get('request_hash') for e in result['evidence'])


def test_builtin_can_be_a_direct_declared_callback():
    registry = {'fixture:size': Adapter(
        {'version': 1, 'params': {'f': 'Callable'}, 'result': 'Number', 'effects': ['pure']},
        lambda rt, args: rt.callback(args['f'], [Binding('가족')]).value)}
    result = run('[fixture:size]{f:len}', registry)
    assert result['success'] and result['value'] == 2, result


def test_builtin_alias_runtime_errors_are_catchable():
    result = run('$f=abs; [try]{return $f("invalid")}[catch]{return $error.code}')
    assert result['success'] and result['value'] == 'NUMBER_REQUIRED', result


def test_evidence_alias_preserves_value_provenance():
    result = run('$inspect=evidence; $x=1+2; return $inspect($x)')
    assert result['success'], result
    assert any(e['kind'] == 'binary' for e in result['value']['events'])


@pytest.mark.parametrize('expression', ['abs', '{f:abs}', '[abs]', '($x)=>$x'])
def test_callable_does_not_escape_the_value_wire_protocol(expression):
    result = run('return '+expression)
    assert not result['success'] and result['diagnostic']['code'] == 'VALUE_PROTOCOL', result


def test_indirect_reduce_keeps_shared_row_budget():
    result = run('$fold=reduce; return $fold([1,2,3],0,max)', budget=Budget(rows=1))
    assert not result['success'] and result['diagnostic']['kind'] == 'budget', result


@pytest.mark.parametrize('literal,expected', [('true', True), ('false', False), ('null', None)])
@pytest.mark.parametrize('context', ['return [{value}]', 'return {{items:[{value}]}}',
                                     'return [[{value}]]'])
def test_singleton_named_literals_are_lists(literal, expected, context):
    result = run(context.format(value=literal))
    assert result['success'], result
    wanted = {'items': [expected]} if 'items' in context else [[expected]] if '[[' in context else [expected]
    assert result['value'] == wanted


@pytest.mark.parametrize('code,expected', [
    ('[try]{return [true]}[catch]{return [false]}', [True]),
    ('[try]{1/0}[catch]{return [null]}[finally]{1}', [None]),
    ('[if:true]{return [true]}[else]{return [false]}', [True]),
    ('[case:1]{[when:1]{return [true]}[else]{return [false]}}', [True]),
    ('[repeat:1]{return [true]}', [True]),
    ('[def:f](){return [null]}; [fn:f]{}', [None]),
])
def test_list_disambiguation_preserves_existing_control_heads(code, expected):
    result = run(code)
    assert result['success'] and result['value'] == expected, result


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
