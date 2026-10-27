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
    if effect == 'pure':
        assert not plan.issues, plan.report()
        result = Runtime(plan).run()
        assert result['success'], result
        assert seen == [1]
    else:
        assert 'PURE_EXPRESSION' in {i['code'] for i in plan.issues}
        assert not seen


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
