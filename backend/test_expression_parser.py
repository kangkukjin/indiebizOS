"""Helpful diagnostics for familiar foreign syntax without changing IBL grammar."""
import boot_paths  # noqa: F401
import pytest
from common.expression_parser import parse
from common.expression_ir import Fault
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime


@pytest.mark.parametrize('source', [
    'return {files:[x.name for x in $f]}',
    'return [$x.name for $x in $f]',
    'return [x.name\nfor x in $f if x.ok]',
])
def test_comprehension_points_to_map_and_each(source):
    with pytest.raises(Fault) as raised:
        parse(source)
    fault = raised.value
    assert fault.code == 'SYNTAX'
    assert 'map($f,($x)=>$x.name)' in str(fault)
    assert 'filter' in str(fault) and '[table:each]' in str(fault)
    assert source[fault.node.start:fault.node.end] == 'for'


@pytest.mark.parametrize('name,role', [('i', 'repeat'), ('it', 'table:each'), ('error', 'catch')])
def test_reserved_binding_outside_its_block_explains_role_and_alternative(name, role):
    plan = compile_program(f'${name}=1;return 1', {})
    issue = next(x for x in plan.issues if x['code'] == 'READONLY')
    assert role in issue['hint'] and '블록 밖' in issue['hint'] and '$image' in issue['hint']


def test_suggested_projection_and_non_comprehension_literals_keep_working():
    source = '$f=[{name:"a"},{name:"b"}];$image=map($f,($x)=>$x.name);return {files:$image,literal:["for"],field:{for:1}}'
    plan = compile_program(source, {})
    assert not plan.issues, plan.report()
    assert Runtime(plan).run()['value'] == {'files':['a','b'], 'literal':['for'], 'field':{'for':1}}


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
