"""Edition 2 compositional laws and effect-boundary regression tests."""
import boot_paths  # noqa: F401
import copy
import time
from decimal import Decimal
import pytest
from ibl_v2_ir import Fault, UNIT, ResultValue, pack, unpack
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime, Budget
from ibl_v2_adapters import Adapter, decode_envelope
from ibl_v2_parser import edition_of


def run(source, inputs=None, registry=None, **kwargs):
    plan = compile_program(source, registry, inputs)
    return Runtime(plan, inputs, **kwargs).run()


def value(source, **kwargs):
    result = run(source, **kwargs)
    assert result['success'], result
    return unpack(result['value_wire']['data'])


def adapter(fn, params=None, result='Unknown', effects=None, receiver=None):
    return Adapter({'version': 1, 'params': params or {}, 'result': result,
                    'effects': effects or ['read_external'], 'pipe_input': receiver}, fn)


@pytest.mark.parametrize('data', [None, True, 2**70, Decimal('0.0000000000000000007'),
    UNIT, [], {}, {'items': [], 'success': False, 'error': 'business', '$ibl': 'unit'},
    ResultValue(True, {'value': [1, UNIT]}), ResultValue(False, error={'code': 'x'})])
def test_value_codec_roundtrip_no_user_key_discriminator(data):
    assert unpack(pack(data)) == data


@pytest.mark.parametrize('bad', [['scalar', float('nan')], ['record', [['a', ['scalar', 1]], ['a', ['scalar', 2]]]], ['unit', 1], ['bogus']])
def test_protocol_rejects_invalid_values(bad):
    with pytest.raises(Fault):
        unpack(bad)


def test_edition_conflict_and_default():
    assert edition_of('return 1') == 1
    assert edition_of('#!ibl edition=2\nreturn 1') == 2
    for requested in [1, 3, True]:
        with pytest.raises(Fault):
            edition_of('#!ibl edition=2\nreturn 1', requested)


@pytest.mark.parametrize('data', [[], [{'id': 'a'}], [{'id': 'a'}, {'id': 'b'}]])
def test_binding_shape_independent_of_cardinality_and_metadata(data):
    assert value('$x = $input\nreturn $x', inputs={'input': data}) == data
    record = {'items': data, 'success': False, 'provenance': {'source': 'fixture'}}
    assert value('$x = $input\nreturn $x', inputs={'input': record}) == record


def test_explicit_function_pipeline_and_forward_definition():
    src = '''$rows = [{id:"007",score:7},{id:"b",score:5}]
$result = $rows >> [fn:weight]{factor:3}
[def:weight]($rows, $factor=2) {
 $rows >> [table:each]{mode:"map"} { return {id:$it.id, weighted:$it.score * $factor} }
}
return $result'''
    assert value(src) == [{'id': '007', 'weighted': 21}, {'id': 'b', 'weighted': 15}]


@pytest.mark.parametrize('src,code', [
    ('[def:f]($x) { return $typo }\n[fn:f]{x:1}', 'UNBOUND'),
    ('[def:f]($x) {return $x}\n1 >> [fn:f]{x:null}', 'PIPE_COLLISION'),
    ('[def:f]() {return 1}\n1 >> [fn:f]{}', 'PIPE_COLLISION'),
    ('[def:f]($x) {return $x}\n[fn:f]{}', 'MISSING_ARGUMENT'),
    ('[def:f]() {return [fn:f]{}}\n[fn:f]{}', 'RECURSION'),
    ('[def:f]() {return 1}\n[def:f]() {return 2}', 'DUPLICATE_FUNCTION'),
    ('$x=1\n[def:f]() {return $x}\n[fn:f]{}', 'UNBOUND'),
    ('[try]{return 1}[finally]{return 2}', 'FINALLY_RETURN'),
    ('[if:1] {return 2}', 'TYPE'),
    ('[if:true] {$x=1}\nreturn $x', 'UNBOUND'),
    ('$x=1\n[table:each]{items:[2]} {$x=$it}', 'READONLY'),
    ('[table:each]{items:[1],limit:1}{return $it}', 'UNKNOWN_ARGUMENT'),
    ('[table:each]{items:[1],mode:"flat_map",on_error:"collect"}{return [$it]}', 'EACH_COLLECT'),
    ('[def:f]($x={doc:[self:read]{path:"secret"}}){return $x};[fn:f]{}', 'PURE_EXPRESSION'),
])
def test_static_errors_before_any_effect(src, code):
    result = run(src)
    assert result['success'] is False
    assert result['executed'] is False
    assert code in [e['code'] for e in result['issues']]


def test_return_not_caught_finally_runs_and_tail_not_run():
    seen = []
    reg = {'test:write': adapter(lambda rt, a: seen.append(a['x']) or UNIT, {'x':'Number'}, 'Unit', ['write_external'])}
    assert value('[try]{return 7}[catch]{return 9}[finally]{[test:write]{x:1}}\n[test:write]{x:2}', registry=reg) == 7
    assert seen == [1]


def test_cleanup_failure_preserves_primary_failure():
    result = run('[try]{return 1/0}[finally]{returnx()}')
    assert not result['success']  # unknown builtin rejected before execution
    result = run('[try]{return 1/0}[finally]{1/0}')
    assert result['diagnostic']['code'] == 'CLEANUP'
    assert result['diagnostic']['details']['cause']


def test_closure_capture_is_creation_time_and_strings_literal():
    assert value('$n=2\n$f=($x)=>$x*$n\n$n=9\nreturn {result:$f(3),literal:"$n",text:f"${n}: ${1+2}"}') == {'result':6, 'literal':'$n','text':'9: 3'}


def test_one_time_interpolation_and_missing_vs_null():
    assert value('return f"${x}"', inputs={'x':'${do_not_interpret}'}) == '${do_not_interpret}'
    assert value('return {a:get({x:null},"x",2),b:get({},"x",2),c:has({x:null},"x")}') == {'a':None,'b':2,'c':True}
    assert not run('return f"${null}"')['success']


@pytest.mark.parametrize('items', [[], [1], [1, 2, 3]])
def test_map_flat_map_effect_laws(items):
    assert value('$xs >> [table:each]{} { return [$it, $it+1] }', inputs={'xs':items}) == [[i,i+1] for i in items]
    assert value('$xs >> [table:each]{mode:"flat_map"} { return [$it, $it+1] }', inputs={'xs':items}) == [v for i in items for v in [i,i+1]]
    assert value('$xs >> [table:each]{mode:"effect"} { return $it }', inputs={'xs':items}) == UNIT
    assert value('$xs >> [table:each]{} { $x=$it }', inputs={'xs':items}) == [UNIT]*len(items)


def test_collect_is_typed_result_not_user_record():
    result = value('[table:each]{items:[2,0,1],on_error:"collect"}{return 4/$it}')
    assert [r.ok for r in result] == [True,False,True]
    assert result[0].value == 2
    assert value('$r=[table:each]{items:[0],on_error:"collect"}{1/$it}\nreturn is_ok($r[0])') is False
    assert not run('$r=[table:each]{items:[0],on_error:"collect"}{1/$it}\nreturn unwrap($r[0])')['success']


def test_parallel_returns_ordered_unflattened_values():
    reg = {'test:wait': adapter(lambda rt,a: time.sleep((4-a['n'])/100) or [a['n']], {'n':'Number'}, 'List')}
    assert value('[test:wait]{n:1} & [test:wait]{n:2} & [test:wait]{n:3}', registry=reg) == [[1],[2],[3]]
    assert value('[table:each]{items:[1,2,3],parallel:3}{[test:wait]{n:$it}}', registry=reg) == [[1],[2],[3]]


def test_shared_budget_is_not_reset_in_function_or_row():
    result = run('[def:f]($x){[table:each]{items:$x}{return $it}}\n[fn:f]{x:[1,2,3,4]}', budget=Budget(rows=2))
    assert not result['success']
    assert result['diagnostic']['kind'] == 'budget'
    assert unpack(result['partial_wire']['data']) == [1,2]
    assert result['diagnostic']['details']['coverage'] == ['ok','ok','failed','pending']


def test_fallback_does_not_catch_empty_null_permission_or_cancellation():
    assert value('[] ?? [test:bad]{}', registry={'test:bad':adapter(lambda rt,a: pytest.fail('must not execute'))}) == []
    assert value('null ?? 3') is None
    for kind in ['permission','cancelled','budget']:
        def fail(rt, args):
            raise Fault('TEST', 'denied', kind=kind)
        assert run('[test:bad]{} ?? 3', registry={'test:bad':adapter(fail)})['diagnostic']['kind'] == kind


def test_partial_evidence_survives_handling_and_pure_computation():
    def partial(rt,args):
        raise Fault('PARTIAL', 'half', kind='partial', partial=[{'x':1}])
    source = '$x=[try]{[test:read]{}}[catch]{return $error.partial}\nreturn $x'
    # Return inside catch returns the nearest program frame, immediately.
    result = run(source, registry={'test:read':adapter(partial)})
    assert result['success'] and not result['source_complete']
    assert any(e['kind']=='handled_partial' for e in result['evidence'])


def test_replay_matches_request_definition_and_never_calls_on_miss():
    calls = []
    reg={'test:read':adapter(lambda rt,a: calls.append(a['n']) or a['n'], {'n':'Number'},'Number')}
    p=compile_program('[test:read]{n:1}', reg)
    first=Runtime(p).run()
    second=Runtime(p, recordings=first['recordings'], replay=True).run()
    assert second['value']==1 and calls==[1]
    missing=Runtime(p, recordings=[], replay=True).run()
    assert missing['diagnostic']['code']=='REPLAY_MISSING' and calls==[1]
    p2=compile_program('[test:read]{n:2}', reg)
    assert not Runtime(p2, recordings=first['recordings'], replay=True).run()['success']


def test_evidence_observation_has_control_and_value_dependencies():
    result=value('$a=$input\n$x=[if:$a > 0]{7}[else]{8}\nreturn evidence($x)',inputs={'input':2})
    kinds={e['kind'] for e in result['events']}
    assert {'if','binary','ref'} <= kinds


def test_repeat_case_and_pure_arithmetic():
    assert value('$sum=0\n[repeat:4]{$sum=$sum+$i}\nreturn $sum')==6
    assert value('$x=0\n[repeat:until $x >= 3]{$x=$x+1}\nreturn $x')==3
    assert value('[case:2]{[when:1]{"a"}\n[when:2]{"b"}\n[else]{"c"}}')=='b'


def test_declared_adapter_does_not_inspect_business_items_or_preview():
    schema={'value_path':'/items'}
    rows=[{'error':'business','success':False}]
    assert decode_envelope({'items':rows,'_preview':True},schema)[0]==rows
    assert decode_envelope({'items':[]},schema)[0]==[]
    with pytest.raises(Fault) as exc:
        decode_envelope({'items':rows,'truncated':True},schema)
    assert exc.value.kind=='partial' and exc.value.partial==rows
    selected={'items':rows,'truncated':True,'truncations':[{'scope':'selection'}]}
    assert decode_envelope(selected,schema)[0]==rows


def test_static_error_after_write_prevents_the_write():
    seen=[]
    reg={'test:write':adapter(lambda rt,a: seen.append(1) or UNIT, result='Unit', effects=['write_external'])}
    result=run('[test:write]{}\nreturn $missing',registry=reg)
    assert not result['executed'] and not seen


def test_empty_callback_body_is_unit_not_empty_argument_record():
    assert value('[1,2] >> [table:each] {}') == [UNIT, UNIT]


def test_reduce_and_function_extraction_equivalence():
    for n in range(12):
        rows = [{'id':str(i).zfill(3),'n':i} for i in range(n)]
        inline = value('$xs >> [table:each] {return {id:$it.id,n:$it.n*3+1}}',inputs={'xs':rows})
        extracted = value('[def:f]($x){return {id:$x.id,n:$x.n*3+1}}\n$xs >> [table:each]{[fn:f]{x:$it}}',inputs={'xs':rows})
        assert inline == extracted == [{'id':r['id'],'n':r['n']*3+1} for r in rows]
        assert value('reduce($xs,0,($acc,$x)=>$acc+$x.n)',inputs={'xs':rows}) == sum(r['n'] for r in rows)


def test_caught_return_and_finally_both_contribute_evidence():
    source='[def:f](){[try]{1/0}[catch]{return 7}[finally]{8}}\n$x=[fn:f]{}\nreturn evidence($x)'
    evidence=value(source)
    assert {'recovered','sequence'} <= {e['kind'] for e in evidence['events']}


def test_cancellation_cleanup_is_bounded_and_cannot_become_success():
    cancelled=[False]
    seen=[]
    def trigger(rt,args):
        cancelled[0]=True
        return 0
    reg={'test:cancel':adapter(trigger,result='Number'),
         'test:cleanup':adapter(lambda rt,a:seen.append(1) or UNIT,result='Unit',effects=['write_external'])}
    out=run('[try]{[test:cancel]{}\nreturn 3}[catch]{return 8}[finally]{[test:cleanup]{}}',
            registry=reg,cancel_check=lambda:cancelled[0])
    assert not out['success'] and out['diagnostic']['kind']=='cancelled'
    assert seen==[1]


def test_empty_record_type_is_closed():
    plan=compile_program('$x={}\nreturn $x.missing')
    assert any(e['code']=='MISSING_FIELD' for e in plan.issues)


def test_branch_return_does_not_change_outer_function_return_type():
    source='[def:f](){([if:true]{return 1}[else]{2}) & 3}\n[fn:f]{} >> [table:each]{return $it*2}'
    assert value(source)==[2,6]


@pytest.mark.parametrize('header',['#!ibl edition=bogus','#!ibl edition=2 junk','#!ibl edition=99'])
def test_invalid_header_never_falls_through_to_legacy(header):
    with pytest.raises(Fault):
        edition_of(header+'\nreturn 1')


def test_large_integer_wire_never_uses_lossy_json_number():
    assert pack(2**70)==['integer',str(2**70)]
    assert unpack(pack({'id':2**70}))=={'id':2**70}


def test_declared_parallel_write_conflict_is_rejected_before_effects():
    seen=[]
    spec=adapter(lambda rt,a:seen.append(a) or UNIT, {'path':'Text'}, 'Unit', ['write_external'])
    spec.contract['write_resources']={'file':'path'}
    result=run('[test:write]{path:"same"} & [test:write]{path:"same"}',registry={'test:write':spec})
    assert not result['executed'] and not seen
    assert any(i['code']=='PARALLEL_WRITE_CONFLICT' for i in result['issues'])



def test_returning_branch_is_excluded_from_definite_assignment_join():
    code='[def:f]($n){[if:$n<0]{return 0}[else]{$x=$n*2}\nreturn $x}\n[fn:f]{n:$n}'
    assert value(code,inputs={'n':-1})==0
    assert value(code,inputs={'n':3})==6


def test_explicit_return_retains_preceding_effect_evidence():
    spec=adapter(lambda rt,a:7,result='Number')
    result=value('[def:f](){[test:read]{}\nreturn 3}\n$x=[fn:f]{}\nreturn evidence($x)',registry={'test:read':spec})
    assert any(e['kind']=='invoke' for e in result['events'])



if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))


def test_default_budget_has_no_wall_time_but_work_limits_remain(monkeypatch):
    import ibl_v2_runtime
    budget = Budget(steps=1)
    start = budget.started
    monkeypatch.setattr(ibl_v2_runtime.time, 'monotonic', lambda: start + 7200)
    budget.tick()
    with pytest.raises(Fault) as error:
        budget.tick()
    assert error.value.kind == 'budget'
