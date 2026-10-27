"""Callable transport, analysis reuse, purity and application invariants."""
import boot_paths  # noqa: F401
import pytest
from ibl_v2_compile import compile_program, Compiler
from ibl_v2_runtime import Runtime
from ibl_v2_types import NUMBER, UNKNOWN, Type
from ibl_v2_ir import unpack
from ibl_v2_adapters import Adapter


def evaluate(source, inputs=None, registry=None):
    plan = compile_program(source, registry, inputs)
    assert not plan.issues, plan.report()
    result = Runtime(plan, inputs).run()
    assert result['success'], result
    return plan, unpack(result['value_wire']['data'])


@pytest.mark.parametrize('call', ['abs(-3)', '$f(-3)', '$r.f(-3)', '$fs[0](-3)',
                                   '[fn:id]{f:$f}(-3)', '-3 >> abs()', '-3 >> $r.f()',
                                   '-3 >> (($x)=>abs($x))()'])
def test_known_callable_survives_transport(call):
    plan, value = evaluate('$f=abs; $r={f:$f}; $fs=[$f]; [def:id]($f){return $f}; return ' + call)
    assert value == 3
    assert plan.result_type == NUMBER
    assert not plan.guards


@pytest.mark.parametrize('call', ['$f("bad")', '$r.f("bad")', '$fs[0]("bad")',
                                   '[fn:id]{f:$f}("bad")', '"bad" >> $f()', '$f()', '$f(1,2)'])
def test_invalid_indirect_input_rejected_before_effect(call):
    plan = compile_program('$f=abs; $r={f:$f}; $fs=[$f]; [def:id]($f){return $f}; return ' + call)
    assert plan.issues
    assert {'TYPE', 'ARITY', 'NUMBER_REQUIRED'} & {i['code'] for i in plan.issues}


def test_captures_returned_functions_and_union_candidates():
    plan, result = evaluate('[def:make]($k){return ($x)=>$x+$k}; '
                            '$a=[fn:make]{k:2}; $b=[fn:make]{k:4}; return [$a(3),$b(3)]')
    assert result == [5, 7]
    assert not plan.guards
    bad = compile_program('$f=$flag ? abs : upper; return $f(3)', inputs={'flag': True})
    assert bad.issues  # every possible target must accept the argument


@pytest.mark.parametrize('source,expected', [
    ('$f=abs; return map([-1,-2],$f)', [1, 2]),
    ('$f=($x)=>$x+1; return map([1,2],$f)', [2, 3]),
    ('$f=($x)=>$x>1; return filter([1,2],$f)', [2]),
    ('$f=($a,$x)=>$a+$x; return reduce([1,2],0,$f)', 3),
    ('return 2 >> (($x,$y)=>$x+$y)(3)', 5),
])
def test_higher_order_and_pipe_types(source, expected):
    plan, value = evaluate(source)
    assert value == expected
    assert not plan.guards


def branching(count, leaf='return $x'):
    source = ['[def:f0]($x){' + leaf + '}']
    for n in range(1, count):
        source.append(f'[def:f{n}]($x){{[if:$flag]{{[fn:f{n-1}]{{x:$x}}}}'
                      f'[else]{{[fn:f{n-1}]{{x:$x}}}}}}'.replace('$flag', '$x>0'))
    return '\n'.join(source) + f'\nreturn [fn:f{count-1}]{{x:1}}'


@pytest.mark.parametrize('depth', [6, 10, 14, 30])
def test_branching_analysis_is_linear(depth):
    plan = compile_program(branching(depth))
    assert not plan.issues
    assert plan.preflight['analysis']['function_bodies'] == depth
    assert plan.preflight['analysis']['function_reuses'] == depth - 1
    assert plan.preflight['status'] == 'analyzed'
    assert plan.preflight['analysis_steps'] < 25 * depth


def test_reuse_does_not_merge_writes_or_static_paths():
    reg = {'test:write': Adapter({'version':1, 'params':{'path':'Text'}, 'result':'Number',
                                 'effects':['write_external'], 'pipe_input':'path',
                                 'write_resources':{'file':'path'}}, lambda rt,a: 1)}
    prefix = '[def:w]($p){return [test:write]{path:$p}}; '
    conflict = compile_program(prefix + '[fn:w]{p:"a"} & [fn:w]{p:"a"}', reg)
    assert 'PARALLEL_WRITE_CONFLICT' in {i['code'] for i in conflict.issues}
    clean = compile_program(prefix + '[fn:w]{p:"a"} & [fn:w]{p:"b"}', reg)
    assert not clean.issues, clean.report()
    assert clean.preflight['analysis']['function_bodies'] == 2


def test_cached_diagnostics_preserve_location_and_bound_paths():
    plan = compile_program(branching(24, 'return abs("bad")'))
    assert plan.issues
    assert len(plan.issues) < 4
    assert plan.issues[0]['location']['line'] == 1
    assert plan.issues[0]['call_paths_omitted'] > 1000
    assert len(str(plan.report())) < 50000


def test_cached_and_uncached_observations_agree(monkeypatch):
    source = branching(7)
    cached = compile_program(source)
    original = Compiler.init_call_analysis
    def disable(self):
        original(self)
        self.analysis_cache_enabled = False
    monkeypatch.setattr(Compiler, 'init_call_analysis', disable)
    direct = compile_program(source)
    assert direct.result_type == cached.result_type
    assert direct.effects == cached.effects
    assert direct.dependencies == cached.dependencies
    assert direct.issues == cached.issues
    assert direct.preflight['declared_ai_visits_upper_bound'] == cached.preflight['declared_ai_visits_upper_bound']


@pytest.mark.parametrize('effect', ['pure','read_external','write_external','model','unknown'])
def test_effect_based_pure_call_and_pipe(effect):
    seen = []
    reg = {'test:inc': Adapter({'version':1, 'params':{'x':'Number'}, 'result':'Number',
                               'effects':[effect], 'pipe_input':'x'},
                              lambda rt,a: seen.append(a['x']) or a['x']+1)}
    source = 'return (($x)=>(($x >> [test:inc]) > 1)) (1)'
    plan = compile_program(source, reg)
    assert not plan.issues, plan.report()
    result = Runtime(plan).run()
    assert result['success'], result
    assert seen == [1]
    checked = compile_program('return true and (' + source[len('return '):] + ')', reg)
    assert bool(checked.issues) == (effect != 'pure')


def test_short_circuit_pure_tools_and_value_host_isolation():
    from common.expression_eval import ValueEvaluator
    from common.expression_parser import parse
    from ibl_v2_ir import Fault
    seen = []
    reg = {'test:yes': Adapter({'version':1, 'params':{}, 'result':'Bool', 'effects':['pure']},
                              lambda rt,a: seen.append(1) or True)}
    _, result = evaluate('return false and [test:yes]', registry=reg)
    assert result is False and not seen
    with pytest.raises(Fault, match='순수 값'):
        ValueEvaluator().eval(parse('[test:yes]').data['statements'][0], {})


def test_unknown_callable_is_explicit_runtime_obligation():
    plan = compile_program('return $f(1)', input_types={'f':Type('Callable')})
    assert not plan.issues and plan.guards
    assert plan.report()['status'] == 'incomplete'


def test_model_visit_upper_bound_reuses_analysis_not_invocations(monkeypatch):
    seen = []
    reg = {'test:model': Adapter({'version':1, 'params':{}, 'result':'Number',
                                 'effects':['model']}, lambda rt,a: seen.append(1) or 1)}
    source = branching(14, 'return [test:model]')
    plan, value = evaluate(source, registry=reg)
    assert value == 1 and seen == [1]
    assert plan.preflight['declared_ai_visits_upper_bound'] == 2 ** 13
    assert plan.preflight['function_summary_reuses'] > 0
    small = branching(6, 'return [test:model]')
    cached = compile_program(small, reg)
    original = Compiler.init_call_analysis
    def disable(self):
        original(self)
        self.analysis_cache_enabled = False
    monkeypatch.setattr(Compiler, 'init_call_analysis', disable)
    direct = compile_program(small, reg)
    assert direct.preflight['declared_ai_visits_upper_bound'] == cached.preflight['declared_ai_visits_upper_bound'] == 32


def test_noncallables_and_bad_callback_arity_are_static_errors():
    for source in ('return {f:2}.f(3)', 'return [2][0](3)',
                   '$f=($x,$y)=>$x; return map([1],$f)',
                   '$f=abs; return reduce([1],0,$f)'):
        assert compile_program(source).issues, source


def test_application_order_and_evidence_for_new_call_positions():
    seen = []
    def make(rt, args):
        seen.append('fn')
        return 1
    reg = {
        'test:fn': Adapter({'version':1,'params':{},'result':'Number','effects':['read_external']}, make),
        'test:arg': Adapter({'version':1,'params':{},'result':'Number','effects':['read_external']},
                           lambda rt,a: seen.append('arg') or -2),
    }
    # New field applications evaluate the callable first; pipe evaluates source first.
    prefix = '[def:get](){[test:fn]; return abs}; '
    _, value = evaluate(prefix + 'return {f:[fn:get]}.f([test:arg])', registry=reg)
    assert value == 2 and seen == ['fn', 'arg']
    seen.clear()
    _, value = evaluate(prefix + 'return [test:arg] >> {f:[fn:get]}.f()', registry=reg)
    assert value == 2 and seen == ['arg', 'fn']


def test_extended_callable_pipe_resume_keeps_distinct_effect_receipts(tmp_path):
    import approval_tokens
    from test_ibl_run_journal import _plan, _run
    calls = []
    plan = _plan(calls, '[def:id]($f){return $f}; $x=[t:delegate]; '
                       '$a="a" >> [fn:id]{f:upper}(); [t:delete]{id:$a}; '
                       '$b="b" >> [fn:id]{f:upper}(); [t:delete]{id:$b}; return [$a,$b]')
    assert not plan.issues, plan.report()
    assert plan.preflight['analysis']['function_reuses'] == 1
    first = _run(tmp_path, plan)
    assert first['suspended'] and calls == ['delegate']
    for expected in (['delegate', 'A'], ['delegate', 'A', 'B']):
        token = approval_tokens.issue(first['waiting']['approval_required']['challenge'])['token']
        first = _run(tmp_path, plan, first['resume'], token)
        assert calls == expected
    assert first['success'] and first['value'] == ['A', 'B']
    assert _run(tmp_path, plan, first['resume'])['success']
    assert calls == ['delegate', 'A', 'B']


def test_public_contract_preserves_callable_specializations():
    plan = compile_program('[def:id]($f){return $f}; '
                           '$a=[fn:id]{f:abs}; $b=[fn:id]{f:upper}; return [$a(-2),$b("x")]')
    assert not plan.issues
    contract = next(iter(plan.function_contracts.values()))
    assert {s['result_contract']['builtin'] for s in contract['specializations']} == {'abs','upper'}
    assert contract['result_contract']['type'] == 'input-dependent'


@pytest.mark.parametrize('count', [0,1,3])
def test_declared_grep_pipe_matches_explicit_input(tmp_path, count):
    import json
    from ibl_v2_adapters import load_registry
    (tmp_path/'source.txt').write_text('needle\n'*count + 'other\n')
    registry = load_registry(str(tmp_path))
    assert registry['self:grep'].contract['pipe_input'] == 'pattern'
    suffix = '{path:' + json.dumps(str(tmp_path/'source.txt')) + ',regex:false}'
    _, piped = evaluate('return "needle" >> [self:grep]' + suffix, registry=registry)
    _, direct = evaluate('return [self:grep]{pattern:"needle",' + suffix[1:], registry=registry)
    assert piped['items'] == direct['items'] and piped['total'] == direct['total'] == count
    for value in ('null','[]','2'):
        left = compile_program(value+' >> [self:grep]'+suffix, registry)
        right = compile_program('[self:grep]{pattern:'+value+','+suffix[1:], registry)
        assert {i['code'] for i in left.issues} == {i['code'] for i in right.issues} == {'TYPE'}


def test_declared_mkdir_pipe_and_describe_share_contract(tmp_path):
    import json
    from ibl_v2_adapters import load_registry
    from model_result_view import describe_actions
    registry = load_registry(str(tmp_path))
    target = json.dumps(str(tmp_path/'created'))
    _, piped = evaluate(target+' >> [self:mkdir]', registry=registry)
    _, direct = evaluate('[self:mkdir]{path:'+target+'}', registry=registry)
    assert (tmp_path/'created').is_dir()
    assert piped['success'] and direct['success']
    report = describe_actions(['self:grep','self:mkdir'], {'self'}, edition=2)
    contracts = {x['action']: x['definition']['callable_contract'] for x in report['actions']}
    for action in contracts:
        assert contracts[action]['pipe_input'] == registry[action].contract['pipe_input']
        assert contracts[action]['params'] == registry[action].contract['params']


def test_table_callback_transport_preserves_projected_shape(tmp_path):
    from ibl_v2_adapters import load_registry
    registry = load_registry(str(tmp_path))
    callback = '($row)=>{n:$row.n,label:"fixed"}'
    direct, left = evaluate('[{n:1}] >> [table:select]{columns:'+callback+'}', registry=registry)
    alias, right = evaluate('$f='+callback+'; [{n:1}] >> [table:select]{columns:$f}', registry=registry)
    assert left == right == [{'n':1,'label':'fixed'}]
    assert direct.result_type == alias.result_type


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))


@pytest.mark.parametrize('transport', ['$op', '{f:$op}.f', 'get({f:$op},"f")',
                                      '[$op][0]', '{**{f:$op}}.f',
                                      '[fn:id]{x:$op}', '($flag ? $op : $op)'])
@pytest.mark.parametrize('producer', ['&[t:read]', '&[fn:load]', '($x)=>[t:read]{x:$x}'])
def test_component_named_transport_matrix(transport, producer):
    calls = []
    reg = {'t:read': Adapter({'version':1,'params':{'x':'Number'},'result':'Number',
                              'effects':['read_external'],'pipe_input':'x'},
                             lambda rt,a: calls.append(a['x']) or a['x'] + 1)}
    prefix = '[def:id]($x){return $x}; '
    if producer == '&[fn:load]':
        prefix += '[def:load]($x){return [t:read]{x:$x}}; '
    source = prefix + '$op=' + producer + '; return ' + transport + '{x:2}'
    plan, value = evaluate(source, {'flag':True}, reg)
    assert value == 3 and calls == [2]
    assert plan.result_type == NUMBER and not plan.guards
    assert plan.effects == {'read_external'}


@pytest.mark.parametrize('depth', [6,10,14,30])
def test_lambda_dag_uses_common_summaries(depth):
    parts = ['$f0=($x)=>$x']
    for n in range(1, depth):
        parts.append(f'$f{n}=($x)=>($x>0 ? $f{n-1}($x) : $f{n-1}($x))')
    plan, value = evaluate('; '.join(parts) + f'; return $f{depth-1}(1)')
    assert value == 1
    stats = plan.preflight['analysis']
    assert stats['lambda_bodies'] == depth
    assert stats['lambda_reuses'] == depth - 1
    assert len(str(plan.report())) < 30000


def test_get_presence_and_callable_return_relationships():
    for source in ('return get({f:abs},"f")(-3)',
                   '$r={f:abs}; return (($x)=>get($r,"f")($x))(-3)',
                   '[def:pick]($r,$key){return get($r,$key)}; return [fn:pick]{r:{f:abs},key:"f"}(-3)',
                   'return map([{f:abs}],($r)=>get($r,"f"))[0](-3)'):
        plan, value = evaluate(source)
        assert value == 3 and not plan.guards
    _, value = evaluate('return [get({f:null},"f",2),get({},"f",2)]')
    assert value == [None,2]


def test_effectful_creation_and_pure_requirements():
    reg = {'t:read': Adapter({'version':1,'params':{'x':'Number'},'result':'Number',
                              'effects':['read_external']}, lambda rt,a:a['x'])}
    plan, value = evaluate('$op=($x)=>[t:read]{x:$x}; return 1', registry=reg)
    assert value == 1 and not plan.effects
    for use in ('return map([1],$op)', 'return $op(1)>0 ? 1 : 2',
                'return true and $op(1)>0', '[def:f]($v=$op(1)){return $v}; return [fn:f]'):
        bad = compile_program('$op=($x)=>[t:read]{x:$x}; '+use,reg)
        assert bad.issues, use
    plan, value = evaluate('[def:keep]($op){return $op}; '
                           '$op=[fn:keep]{op:($x)=>[t:read]{x:$x}}; return $op(2)',registry=reg)
    assert value == 2 and plan.effects == {'read_external'}


@pytest.mark.parametrize('effect', ['pure','read_external','write_external','model','unknown'])
def test_reference_named_pipe_alias_and_variant_contracts(effect):
    calls=[]
    reg={'q:op':Adapter({'version':1,'params':{'x':'Number','op':'Text'},'required':['x'],
                         'aliases':{'value':'x'},'result':'Number','effects':['unknown'],
                         'pipe_input':'x','variants':[{'when':{'op':'go'},'effects':[effect]}]},
                        lambda rt,a:calls.append(a) or a['x'])}
    for source in ('$f=&[q:op]; return $f{value:3,op:"go"}',
                   '$f=&[q:op]; return 3 >> $f{op:"go"}',
                   '[def:apply]($f,$mode){return $f{x:3,op:$mode}}; return [fn:apply]{f:&[q:op],mode:"go"}'):
        plan,value=evaluate(source,registry=reg)
        assert value==3 and plan.effects=={effect},plan.report()
    for source in ('$f{x:1,value:2}', '1 >> $f{x:2}', '$f{}', '$f{x:"bad"}', '$f{x:1,extra:2}'):
        assert compile_program('$f=&[q:op]; '+source,reg).issues
    assert len(calls)==3


def test_leaf_authorization_is_checked_again_on_component_resume(tmp_path):
    from ibl_run_journal import Journal
    from ibl_v2_ir import Fault
    allowed=[True]
    calls=[]
    def authorize():
        if not allowed[0]:
            raise Fault('DENIED','권한 변경',kind='protocol')
    reg={'q:read':Adapter({'version':1,'params':{},'result':'Number','effects':['read_external']},
                         lambda rt,a:calls.append(1) or 1,authorize=authorize)}
    plan=compile_program('$f=&[q:read]; return $f{}',reg)
    with Journal(tmp_path,plan.fingerprint) as journal:
        first=Runtime(plan,journal=journal).run()
    assert first['success'] and calls==[1]
    allowed[0]=False
    with Journal(tmp_path,plan.fingerprint,first['resume']) as journal:
        second=Runtime(plan,journal=journal).run()
    assert not second['success'] and second['diagnostic']['code']=='DENIED'
    assert calls==[1]


def test_runtime_pure_callback_guard_and_value_host_cannot_execute_tools():
    from common.expression_eval import Binding, ValueEvaluator
    from common.expression_ops import Closure
    from ibl_v2_parser import parse
    from ibl_v2_ir import Fault
    calls=[]
    body=parse('[q:read]').data['statements'][0]
    reg={'q:read':Adapter({'version':1,'params':{},'result':'Number','effects':['read_external']},
                         lambda rt,a:calls.append(1) or 1)}
    runtime=Runtime(compile_program('return 1',reg))
    with pytest.raises(Fault) as denied:
        runtime.callback(Closure(('x',),body,{}),[Binding(1)])
    assert denied.value.code=='PURE_EXPRESSION' and not calls
    for source in ('&[q:read]','(&[q:read]){}'):
        with pytest.raises(Fault):
            ValueEvaluator().eval(parse(source).data['statements'][0],{})


def test_result_transport_and_internal_callable_json_boundary():
    plan,value=evaluate('$r=[table:each]{items:[1],on_error:"collect"}{return abs}; return unwrap($r[0])(-4)')
    assert value==4 and plan.result_type==NUMBER
    from ibl_v2_ir import pack, projection, Fault
    from common.expression_ops import CallableRef, Closure
    from common.expression_eval import Binding
    from ibl_v2_parser import parse
    closure=Closure((),parse('return 1'),{'secret':Binding('do-not-publish')})
    assert 'do-not-publish' not in str(projection({'f':closure}))
    with pytest.raises(Fault) as err:
        pack({'data':[CallableRef('q','read')]})
    assert err.value.details['path']==['data',0]


def test_dependency_specializations_share_one_binder_without_overwriting_snapshots():
    revisions={'a':1,'b':1}
    calls=[]
    reg={'q:read':Adapter({'version':1,'params':{'id':'Text'},'result':'Number','effects':['read_external']},
                         lambda rt,a:calls.append(a['id']) or revisions[a['id']],
                         dependency=lambda a:{'revision':revisions.get(a.get('id'))})}
    code='[def:run]($f,$id){return $f{id:$id}}; $f=&[q:read]; return [[fn:run]{f:$f,id:"a"},[fn:run]{f:$f,id:"b"}]'
    plan=compile_program(code,reg)
    first=Runtime(plan)
    assert first.run()['value']==[1,1] and calls==['a','b']
    receipts={r['reuse_key']:r for r in first.recordings}
    revisions['a']=2
    result=Runtime(plan).run()
    assert not result['success'] and result['diagnostic']['code']=='DEFINITION_CHANGED'
    assert calls==['a','b']
    refreshed=compile_program(code+' # new source revision',reg)
    result=Runtime(refreshed,reusable=receipts,reuse_run='previous').run()
    assert result['value']==[2,1] and calls==['a','b','a'], result
    assert result['reuse']['reused_calls']==1


@pytest.mark.parametrize('selection',['get($r,$k)','$r[$k]'])
def test_finite_selector_and_optional_record_alternatives_keep_contract(selection):
    plan,value=evaluate('$r={a:abs,b:abs}; $k=$flag ? "a" : "b"; return '+selection+'(-2)',{'flag':True})
    assert value==2 and not plan.guards
    plan,value=evaluate('$r=$flag ? {f:abs} : {}; return get($r,"f",abs)(-2)',{'flag':False})
    assert value==2 and not plan.guards


@pytest.mark.parametrize('kind', ['lambda', 'function'])
def test_composed_calls_share_depth_budget(kind):
    from ibl_v2_runtime import Budget
    if kind == 'lambda':
        source = ['$f0=($x)=>$x']
        source += [f'$f{n}=($x)=>$f{n-1}($x)' for n in range(1,6)]
        source += ['return $f5(1)']
    else:
        source = ['[def:f0]($x){return $x}']
        source += [f'[def:f{n}]($x){{return [fn:f{n-1}]{{x:$x}}}}' for n in range(1,6)]
        source += ['return (&[fn:f5]){x:1}']
    plan = compile_program(';'.join(source), {})
    assert not plan.issues, plan.report()
    out = Runtime(plan, budget=Budget(depth=2)).run()
    assert out['diagnostic']['code'] == 'BUDGET' and out['diagnostic']['kind'] == 'budget'


def test_recovery_context_is_part_of_summary_and_does_not_hide_outer_type_errors():
    prefix = '[def:pick]($r){return get($r,"a")}; '
    code = '$v=[try]{[fn:pick]{r:null}}[catch]{3}; return $v'
    plan, value = evaluate(prefix+code, registry={})
    assert value == 3 and any(g.get('recoverable') for g in plan.guards)
    bad = compile_program(prefix+code.replace('return $v','return [fn:pick]{r:null}'), {})
    assert any(i['code']=='TYPE' for i in bad.issues)
    _, value = evaluate('return get(null,"a") ?? 4', registry={})
    assert value == 4


def test_null_projection_and_empty_membership_keep_unreachable_values_unobserved():
    _, value = evaluate('$r={x:null}; return get($r,"x")==null ? "empty" : ", "+get($r,"x")')
    assert value == 'empty'
    _, value = evaluate('$r={}; [if:$key in keys($r)]{return f"${get($r,$key)}"}; return "empty"',
                        inputs={'key':'anything'})
    assert value == 'empty'



def test_private_callable_identity_cannot_be_forged_by_ordinary_json():
    from common.expression_ops import callable_identity, Builtin
    from common.expression_ir import pack
    fn = Builtin('abs')
    descriptor = callable_identity(fn)
    assert descriptor != callable_identity(descriptor)
    assert callable_identity({'f':fn}) != callable_identity({'f':descriptor})
    ordinary = {'list':[1, None, True], 'nested':{'text':'x'}}
    assert callable_identity(ordinary) == pack(ordinary)


def test_unique_specialization_limit_is_explicit_and_does_not_limit_execution():
    count = 4100
    calls = ','.join(f'[fn:id]{{x:{n}}}' for n in range(count))
    plan = compile_program('[def:id]($x){return $x}; return ['+calls+']', {})
    assert not plan.issues, plan.report()
    assert plan.preflight['analysis']['function_bodies'] == 4096
    assert any(g.get('specializations_omitted') for g in plan.guards)
    assert 'unknown' in plan.effects and plan.report()['status'] == 'incomplete'
    result = Runtime(plan).run()
    assert result['success'] and result['value'] == list(range(count))


def test_candidate_limit_and_recursive_reference_are_explicit():
    source = '$parts=['+','.join(f'()=>{n}' for n in range(65))+']; return $parts[$index]()'
    plan = compile_program(source, {}, {'index':64})
    assert not plan.issues, plan.report()
    assert any(g.get('alternatives_omitted') == 1 for g in plan.guards)
    assert 'unknown' in plan.effects
    assert Runtime(plan, {'index':64}).run()['value'] == 64
    recursive = compile_program('[def:f](){return (&[fn:f]){}}; return [fn:f]{}', {})
    assert any(i['code']=='RECURSION' for i in recursive.issues)



@pytest.mark.parametrize('target', ['[t:select]', '(&[t:select])'])
@pytest.mark.parametrize('options,effects', [('{**$args}',{'unknown'}), ('{**{mode:"read"}}',{'read_external'})])
def test_nested_spread_uncertainty_survives_contract_specialization(target, options, effects):
    def specialize(contract, values):
        options = values.get('options')
        if isinstance(options, dict) and options.get('mode', 'read') == 'read':
            return {**contract, 'effects':['read_external']}
        return contract
    spec = Adapter({'version':1, 'params':{'options':'Record'}, 'result':'Number', 'effects':['unknown']},
                   lambda rt,a:1, specialize=specialize)
    plan = compile_program('return '+target+'{options:'+options+'}', {'t:select':spec}, {'args':{}})
    assert not plan.issues, plan.report()
    assert plan.effects == effects
