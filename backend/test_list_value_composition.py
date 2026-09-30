"""General list functions share the expression evaluator and decimal semantics."""
import boot_paths  # noqa: F401
import pytest
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime, Budget


def run(code, inputs=None, **kwargs):
    plan = compile_program(code, inputs=inputs)
    assert not plan.issues, plan.report()
    return Runtime(plan, inputs, **kwargs).run()


def test_text_list_filter_map_and_structural_inference():
    out = run('return map(filter($x,($s)=>len(strip($s))>0),($s)=>{label:upper(strip($s))})',
              {'x': [' a ', '', '한글', '  ']})
    assert out['success'] and out['value'] == [{'label': 'A'}, {'label': '한글'}]
    plan = compile_program('return map([1,2],($n)=>{n:$n})[0].n')
    assert not plan.issues and str(plan.result_type) == 'Number'


def test_first_class_nested_functions_and_empty_lists():
    assert run('$f=abs\nreturn map([-2,3],$f)')['value'] == [2, 3]
    assert run('return map([[1],[2]],($a)=>map($a,($n)=>$n+1))')['value'] == [[2], [3]]
    assert run('return filter([],($x)=>true)')['value'] == []
    assert compile_program('return filter([1],($x)=>$x)').issues
    assert compile_program('return map([1],($a,$b)=>$a)').issues


@pytest.mark.parametrize('code,value', [
    ('format_number(1234.5,",.2f")', '1,234.50'),
    ('format_number(2.675,".2f")', '2.68'),
    ('format_number(12.345,".2f")', '12.34'),
    ('format_number(0.125,".1%")', '12.5%'),
    ('format_number(-12,".0f")', '-12'),
])
def test_decimal_formatting(code, value):
    assert run('return ' + code)['value'] == value


def test_invalid_format_and_shared_budget():
    out = run('return format_number(1,"1000000000f")')
    assert not out['success'] and out['diagnostic']['code'] == 'NUMBER_FORMAT'
    out = run('return map($rows,($n)=>$n+1)', {'rows': list(range(100))}, budget=Budget(steps=20))
    assert not out['success'] and out['diagnostic']['kind'] == 'budget'


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
