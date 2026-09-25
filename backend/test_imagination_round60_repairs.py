"""Loop dataflow, overload checks and iteration-index scope regressions."""
import boot_paths  # noqa: F401

import pytest

from ibl_v2_adapters import Adapter
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Budget, Runtime


def execute(code, inputs=None, registry=None, **kwargs):
    plan = compile_program(code, registry, inputs)
    result = Runtime(plan, inputs, **kwargs).run()
    assert result['success'], result
    return result['value']


@pytest.mark.parametrize('code,expected', [
    ('$xs=[]; [repeat:3]{$xs=$xs+[$i]}; return $xs', [0, 1, 2]),
    ('$s=""; [repeat:3]{$s=$s+"가"}; return $s', '가가가'),
    ('return reduce([1,2],[],($acc,$v)=>$acc+[$v])', [1, 2]),
    ('return reduce([1,2],[],($acc,$v)=>[$v]+$acc)', [2, 1]),
    ('$concat=($a,$b)=>$a+$b; return $concat([1],[2])', [1, 2]),
    ('$concat=($a,$b)=>$a+$b; return $concat("가","나")', '가나'),
    ('$concat=($a,$b)=>$a+$b; return $concat(2,3)', 5),
    ('$n=0; [repeat:while $i<3]{$n=$n+1}; return $n', 3),
    ('$n=0; [repeat:while $i<0]{$n=$n+1}; return $n', 0),
    ('$n=0; [repeat:until $cost>=3]{$cost=$i+1; $n=$n+$cost}; return $n', 6),
    ('[repeat:1]{$x={name:"가"}}; return $x.name', '가'),
    ('[repeat:3]{$x=$i}; return $x', 2),
    ('[repeat:until $x==2]{$x=$i}; return $x', 2),
    ('$x=0; [repeat:until $x=="끝"]{$x="끝"}; return $x', '끝'),
    ('$n=0; [repeat:2]{[repeat:$i+1]{$n=$n+1}}; return $n', 3),
    ('$n=0; [repeat:3]{[repeat:while $i<2]{$n=$n+1}; $n=$n+$i}; return $n', 9),
    ('$r=[]; [repeat:3]{[repeat:2]{$r=$r+[$i]}; $r=$r+[$i]}; return $r',
     [0, 1, 0, 0, 1, 1, 0, 1, 2]),
    ('$n=0; [repeat:until $i==2]{$n=$n+1}; return $n', 3),
    ('[repeat:until $x==1]{[if:true]{$x=1}[else]{$x=2}}; return $x', 1),
    ('[repeat:1]{[try]{1/0}[catch]{$x=4}}; return get({},"x",0)', 0),
])
def test_loop_and_dynamic_addition_values(code, expected):
    assert execute(code) == expected


@pytest.mark.parametrize('code,error', [
    ('[repeat:$i]{1}', 'UNBOUND'),
    ('[repeat:while $x<2]{$x=2}', 'UNBOUND'),
    ('[repeat:0]{$x=1}; return $x', 'UNBOUND'),
    ('[repeat:while false]{$x=1}; return $x', 'UNBOUND'),
    ('[repeat:$count]{$x=1}; return $x', 'UNBOUND'),
    ('[repeat:1]{[if:true]{$x=1}}; return $x', 'UNBOUND'),
    ('[repeat:until $x==1]{[if:true]{$x=1}}', 'UNBOUND'),
    ('[repeat:1]{}; return $i', 'UNBOUND'),
    ('[repeat:while false]{}; return $i', 'UNBOUND'),
    ('[repeat:until true]{}; return $i', 'UNBOUND'),
    ('[1] >> [table:each]{[repeat:1]{$it=2}}', 'READONLY'),
    ('$x=1; [1] >> [table:each]{[repeat:until true]{$x=2}}', 'READONLY'),
    ('[repeat:1]{$i=2}', 'READONLY'),
    ('[try]{1}[finally]{[repeat:1]{return 2}}', 'FINALLY_RETURN'),
    ('return []+1', 'ARITHMETIC'),
    ('return {}+[]', 'ARITHMETIC'),
    ('$f=($x)=>$x+{}; return $f(2)', 'ARITHMETIC'),
    ('[repeat:until 1]{}', 'TYPE'),
    ('[repeat:while 1]{}', 'TYPE'),
])
def test_invalid_programs_remain_rejected_before_execution(code, error):
    plan = compile_program(code, inputs={'count': 0})
    assert error in {i['code'] for i in plan.issues}, plan.report()
    assert Runtime(plan, {'count': 0}).run()['executed'] is False


@pytest.mark.parametrize('value', [1, None, {}])
def test_unknown_list_addition_checks_the_actual_runtime_operand(value):
    reg = {'fixture:read': Adapter({'version': 1, 'params': {}, 'result': 'Unknown',
                                   'effects': ['read_external']}, lambda rt, args: value)}
    plan = compile_program('$xs=[fixture:read]{}; return $xs+[2]', reg)
    assert not plan.issues, plan.report()
    assert plan.guards
    result = Runtime(plan).run()
    assert not result['success']
    assert result['diagnostic']['code'] == 'NUMBER_REQUIRED'


def test_until_body_binding_is_checked_with_its_actual_type():
    plan = compile_program('[repeat:until $ready]{$ready=1}')
    assert 'TYPE' in {i['code'] for i in plan.issues}


def test_iteration_index_does_not_bypass_the_shared_budget():
    plan = compile_program('$n=0; [repeat:while $i<100]{$n=$n+1}')
    result = Runtime(plan, budget=Budget(rows=2)).run()
    assert result['diagnostic']['kind'] == 'budget'


def test_inner_loop_failure_restores_outer_iteration_index():
    assert execute('''$r=[]
    [repeat:3]{
      [try]{[repeat:while $i<2]{1/0}}[catch]{$r=$r+[$i]}
    }
    return $r''') == [0, 1, 2]


@pytest.mark.parametrize('left,right,expected', [
    ('[]', '[1]', [1]), ('[1]', '[]', [1]),
    ('"가"', '"나"', '가나'), ('2', '3', 5),
])
@pytest.mark.parametrize('context', ['repeat', 'reduce', 'lambda', 'function'])
def test_addition_census_across_unknown_operand_contexts(left, right, expected, context):
    codes = {
        'repeat': f'$x={left}; [repeat:2]{{$x=$x+{right}; return $x}}',
        'reduce': f'return reduce([{right}],{left},($a,$b)=>$a+$b)',
        'lambda': f'$f=($a,$b)=>$a+$b; return $f({left},{right})',
        'function': f'[def:add]($a,$b){{return $a+$b}}; [fn:add]{{a:{left},b:{right}}}',
    }
    assert execute(codes[context]) == expected


@pytest.mark.parametrize('wrapper', [
    '[if:true]{BODY}[else]{BODY}',
    '[case:1]{[when:1]{BODY}[else]{BODY}}',
    '[try]{BODY}[catch]{BODY}',
    '[repeat:1]{BODY}',
])
def test_guaranteed_assignments_survive_nested_control_flow(wrapper):
    body = wrapper.replace('BODY', '$ready=true; $result=7')
    assert execute(f'[repeat:until $ready]{{{body}}}; return $result') == 7


@pytest.mark.parametrize('count', [0, 1, 3])
def test_zero_iteration_path_preserves_existing_bindings(count):
    code = '$x="처음"; [repeat:$n]{$x="나중"}; return $x'
    assert execute(code, {'n': count}) == ('나중' if count else '처음')


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
