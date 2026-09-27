"""General value composition, migration, effects and execution identity laws."""
import itertools
import json
from pathlib import Path
import pytest
import boot_paths  # noqa: F401
from common.safe_expr import compile_expr, eval_expr
from common.expression_ir import Fault, pack, unpack
from common.expression_ops import pure_call
from common.value_semantics import values_equal, equality_bucket
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime, Budget
from ibl_v2_adapters import Adapter
from ibl_run_journal import Journal, reusable_receipts


def run(source, inputs=None, registry=None, **kwargs):
    plan = compile_program(source, registry or {}, inputs or {})
    return Runtime(plan, inputs or {}, **kwargs).run()


@pytest.mark.parametrize('expr,expected', [
    ('split("a b c")[1:]', ['b', 'c']),
    ('split("a,b,c", ",", 1)', ['a', 'b,c']),
    ('replace("a-b-a", "a", "x", 1)', 'x-b-a'),
    ('strip(" a ")', 'a'),
    ('upper("ab")', 'AB'), ('lower("AB")', 'ab'),
    ('contains("Seoul", "SEO")', True),
    ('join("-", ["a","b"])', 'a-b'),
    ('[0,1,2,3][::-1]', [3,2,1,0]),
    ('"abc"[-1]', 'c'), ('"abcdef"[1:5:2]', 'bd'),
    ('unique([1,"1",true,"true",null,null])', [1,True,None]),
    ('union([2,1],["2",3])', [2,1,3]),
    ('intersection([2,1,2],["2"])', [2]),
    ('difference([2,1,1],["2"])', [1]),
    ('zip([1,2],["a"])', [[1,'a']]),
    ('enumerate(["a","b"],3)', [[3,'a'],[4,'b']]),
    ('any([])', False), ('all([])', True),
    ('any([false,true])', True), ('all([true,false])', False),
    ('sorted([3,1,2])', [1,2,3]),
    ('sorted([{k:2},{k:1}],"k")', [{'k':1},{'k':2}]),
    ('sorted([{k:2},{k:1}],($row)=>$row.k,true)', [{'k':2},{'k':1}]),
    ('keys({a:1,b:2})', ['a','b']), ('values({a:1,b:2})',[1,2]),
    ('entries({a:1})', [['a',1]]),
    ('{**{a:1,b:2},a:3,**{b:4}}', {'a':3,'b':4}),
    ('"""one\ntwo \'quote\'"""', 'one\ntwo \'quote\''),
    ("'''one\ntwo \"quote\"'''", 'one\ntwo "quote"'),
    ('f"""sum\n${1+2}"""', 'sum\n3'),
])
def test_value_operations_roundtrip(expr, expected):
    result = run('return ' + expr)
    assert result['success'], result
    assert result['value'] == expected
    assert unpack(result['value_wire']['data']) == expected


@pytest.mark.parametrize('expr', [
    'split(null)', 'replace("a",null,"b")', 'join(",",[1])',
    'any([1])', 'all([false,1])', 'sorted([1,"n/a"])',
    '[1][::0]', '[1][true:]', '{**[1]}', 'difference([1],1)',
])
def test_bad_values_are_never_silently_coerced(expr):
    assert not run('return ' + expr)['success']


@pytest.mark.parametrize('expr,row,expected', [
    ('split(name)[0]', {'name':'a b'}, 'a'),
    ('split(name)[0]', {'name':None}, 'None'),
    ('join(",",xs)', {'xs':[1,None]}, '1,None'),
    ('str(x)', {'x':None}, 'None'),
    ('1 if x > 2 else 0', {'x':'3'}, 1),
    ('1 < x < 4', {'x':'3'}, True),
    ('x or "fallback"', {'x':''}, 'fallback'),
    ('col("not a name") + 2', {'not a name':'3'}, 5),
    ('acc + [x]', {'x':2,'acc':[1]}, [1,2]),
    ('{**base, k:2}', {'base':{'k':1,'x':3}}, {'k':2,'x':3}),
    ('split(x)[::-1]', {'x':'a b'}, ['b','a']),
    ('str((1,2))', {}, '(1, 2)'),
    ('str({"a":(1,2)})', {}, "{'a': (1, 2)}"),
    ('"x"*3', {}, 'xxx'),
    ('"%s" % "x"', {}, 'x'),
    ('min(["10","2"])', {}, '10'),
    ('len((1,2))', {}, 2),
    ('(1,2)[0]', {}, 1),
])
def test_legacy_spelling_uses_shared_values_with_explicit_compatibility(expr,row,expected):
    code, _, _ = compile_expr(expr)
    assert code.__class__.__name__ == 'Node'  # Python code objects retired
    assert eval_expr(code,row) == expected


@pytest.mark.parametrize('source', ['"3"-2', '-"3"', '+"3"', 'abs("3")'])
def test_legacy_literal_type_errors_are_not_silently_reinterpreted(source):
    with pytest.raises((ValueError, TypeError)):
        eval_expr(compile_expr(source)[0], {})


@pytest.mark.parametrize('name,args', [
    ('split',['a b']), ('strip',[' x ']), ('replace',['a','a','b']),
    ('unique',[[1,'1',2]]), ('difference',[[1,2],[2]]), ('union',[[1],[2]]),
    ('enumerate',[[1,2]]), ('zip',[[1,2],[3]]), ('sorted',[[3,1]]),
])
def test_two_surfaces_share_function_meaning(name,args):
    source = f'{name}(' + ','.join(json.dumps(a) for a in args) + ')'
    old = eval_expr(compile_expr(source)[0], {})
    new = run('return '+source)
    assert new['success'] and new['value'] == old


def test_bucket_is_only_candidate_filter_and_preserves_calendar_semantics():
    values = [None, True, False, 'true', 'false', 1, '1', 1.0, '01',
              '서울', ' 서울 ', 'A', 'a', [], {}, [1], ['1'], {'a':1}, {'a':'1'},
              '2026-09-27', '2026-09-27T12:00+09:00', '2026-09-27T22:00+09:00']
    for a,b in itertools.product(values, repeat=2):
        if values_equal(a,b):
            assert equality_bucket(a) == equality_bucket(b), (a,b)
    expected=[]
    for v in values:
        if not any(values_equal(v,x) for x in expected):
            expected.append(v)
    assert pure_call('unique',[values]) == expected


def test_indexed_membership_scales_without_quadratic_comparisons():
    result=run('return difference($a,$b)', {'a':list(range(3000)), 'b':list(range(1500))})
    assert result['success'] and result['value']==list(range(1500,3000))


def test_assert_failure_is_structured_catchable_and_lazy():
    result=run('[try] { assert false,"missing",{expected:3,actual:2} } [catch] { return $error }')
    assert result['success']
    error=result['value']
    assert error['code']=='ASSERTION_FAILED' and error['details']=={'expected':3,'actual':2}
    assert error['source_span'] and error['evidence']
    result=run('assert true, get({},"missing",null); return 7')
    assert result['success'] and result['value']==7  # failure message evaluated only on failure
    result=run('assert 1; return 7')
    assert not result['success']


def test_assert_stops_later_effects_and_finally_still_runs():
    effects=[]
    reg={'x:write':Adapter({'version':1,'params':{'n':'Number'},'result':'Number','effects':['write_external']},
                           lambda rt,a:effects.append(a['n']) or a['n'])}
    result=run('[try] { assert false; [x:write]{n:1} } [finally] { [x:write]{n:2} }',registry=reg)
    assert not result['success'] and effects==[2]


def test_spread_preserves_source_order_and_dynamic_function_checks():
    calls=[]
    reg={'x:read':Adapter({'version':1,'params':{'n':'Number'},'result':'Record','effects':['read_external']},
                         lambda rt,a:calls.append(a['n']) or {'n':a['n']})}
    result=run('return {**[x:read]{n:1}, last:[x:read]{n:2}, **[x:read]{n:3}}',registry=reg)
    assert result['success'] and calls==[1,2,3] and result['value']=={'n':3,'last':{'n':2}}
    source='[def:f]($n) { return $n }; $a=[x:read]{n:4}; return [fn:f]{**$a}'
    assert run(source,registry=reg)['value']==4
    source='[def:f]($other) { return $other }; $a=[x:read]{n:4}; return [fn:f]{**$a}'
    result=run(source,registry=reg)
    assert not result['success']


def test_spread_tool_contract_observes_fields_and_guards_before_dispatch():
    calls=[]
    reg={'x:read':Adapter({'version':1,'params':{'n':'Number'},'result':'Number','effects':['read_external']},
                         lambda rt,a:calls.append(a['n']) or a['n'])}
    assert run('$args={n:2};return [x:read]{**$args}',registry=reg)['value']==2
    assert not run('$args={n:"bad"};return [x:read]{**$args}',registry=reg)['success']
    assert calls==[2]


def test_nested_unknown_spread_cannot_certify_stale_effect_selector():
    reg={'x:mode':Adapter({'version':1,'params':{'mode':'Text'},'result':'Text',
                          'effects':['read_external','write_external'],
                          'variants':[{'when':{'mode':'read'},'effects':['read_external']},
                                      {'when':{'mode':'write'},'effects':['write_external']}]},
                         lambda rt,a:a['mode'])}
    source='return [x:mode]{mode:"read", **{**$config}}'
    plan=compile_program(source,reg,{'config':{'mode':'write'}})
    assert not plan.issues
    assert plan.effects=={'read_external','write_external'}
    result=Runtime(plan,{'config':{'mode':'write'}}).run()
    assert result['success'] and result['value']=='write'


def test_collection_work_obeys_shared_budget_and_cancel():
    result=run('return union($a,$a)', {'a':list(range(100))},budget=Budget(steps=15))
    assert not result['success']
    assert 'BUDGET' in str(result)
    assert not run('return split("a b")',cancel_check=lambda:True)['success']
    assert not run('return reduce([1,2,3],0,($acc,$row)=>$acc+$row)',
                   budget=Budget(rows=2))['success']


def test_assert_and_library_composition_retain_reference_evidence():
    result=run('$x=unique($rows); assert len($x)==2; return {xs:$x,e:evidence($x)}',
               {'rows':[1,1,2]},input_evidence={'rows':{'result_ref':'example','path':['rows'],'source_complete':True}})
    assert result['success']
    assert any(e['kind']=='input_ref' for e in result['evidence'])


def test_new_expression_core_is_in_reuse_identity(tmp_path):
    calls=[]
    reg={'x:read':Adapter({'version':1,'params':{},'result':'List','effects':['read_external']},
                         lambda rt,a:calls.append(1) or [1,1,2])}
    plan=compile_program('return unique([x:read]{})',reg)
    # Tool calls are deliberately not pure builtin arguments: bind first.
    assert plan.issues
    plan=compile_program('$rows=[x:read]{};return unique($rows)',reg)
    assert 'expressions' in plan.dependencies
    with Journal(tmp_path,'values') as journal:
        out=Runtime(plan,journal=journal).run()
        run_id=journal.run_id
    assert out['success'] and out['value']==[1,2]
    reuse=reusable_receipts(tmp_path,run_id)
    changed=compile_program('$rows=[x:read]{};return difference($rows,[2])',reg)
    again=Runtime(changed,reusable=reuse,reuse_run=run_id).run()
    assert again['success'] and again['value']==[1] and calls==[1]
    changed.dependencies['expressions']='changed-contract'
    again=Runtime(changed,reusable=reuse,reuse_run=run_id).run()
    assert again['success'] and calls==[1,1]


def test_no_python_eval_engine_or_duplicate_pure_dispatch():
    import ast
    import common.safe_expr as adapter
    import common.expression_legacy as translator
    for module in (adapter,translator):
        tree=ast.parse(Path(module.__file__).read_text())
        assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in ('eval','compile','exec') for n in ast.walk(tree))


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
