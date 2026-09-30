"""Shared contracts exposed by the second long-program exercise."""
import boot_paths  # noqa: F401
import json
from pathlib import Path
from decimal import Decimal

import pytest

from ibl_v2_adapters import Adapter, load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime
from ibl_run_journal import Journal, reusable_receipts
from ibl_v2_ir import Fault

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'docs/experiments/long_sentence_imagination/round_2'


@pytest.fixture(scope='module')
def registry():
    return load_registry(str(ROOT))


def run(code, registry, inputs=None, **kwargs):
    plan = compile_program(code, registry, inputs)
    assert not plan.issues, plan.issues
    result = Runtime(plan, inputs, **kwargs).run()
    assert result['success'], result
    return result


def test_report_static_reproductions(registry):
    for name, error in [('ai_schema_typo', 'MISSING_FIELD'), ('sorted_list_key', 'UNORDERED')]:
        plan = compile_program((FIXTURE / 'repro' / (name + '.ibl')).read_text(), registry)
        assert error in [i['code'] for i in plan.issues], plan.report()
    with pytest.raises(Fault) as raised:
        compile_program((FIXTURE / 'repro/ternary_pipe.ibl').read_text(), registry)
    assert raised.value.code == 'PURE_EXPRESSION'


def test_schema_projection_uses_declared_names_without_guessing_types(registry):
    source = '$r=[{id:1}] >> [table:ai]{instruction:"x",schema:"pros(목록), cons(목록)"};'
    assert not compile_program(source + 'return $r.items[0].pros', registry).issues
    assert not compile_program(source + 'return $r.items[0].id', registry).issues
    assert compile_program(source + 'return $r.items[0].conz', registry).issues
    inspect = source.replace('instruction:"x"', 'instruction:"x",inspect:"batch"')
    assert not compile_program(inspect + 'return $r.items[0].id', registry).issues
    assert compile_program(inspect + 'return $r.items[0].pros', registry).issues
    free = source.replace('pros(목록), cons(목록)', '자유 요약')
    assert not compile_program(free + 'return $r.items[0].novel', registry).issues
    struct = '$r=[self:struct]{text:"x",schema:"a(설명), b(설명)"};return $r.items[0].typo'
    assert any(i['code'] == 'MISSING_FIELD' for i in compile_program(struct, registry).issues)


def test_invalid_check_preserves_errors_and_retrievable_guards(registry):
    from ibl_v2_analysis import compact_check
    from model_result_view import read_result
    code = '[def:f]($x){return $x.field};return {a:1}.typo'
    plan = compile_program(code, registry)
    result = compact_check(plan)
    assert not result['ok'] and result['issues'] == plan.issues
    assert result['guards'] == [] and result['guards_omitted'] == len(plan.guards)
    saved = read_result({**result['guards_ref']['read_args'], 'path': ['guards', 0]})
    assert json.loads(saved['text']) == plan.guards[0]
    assert Runtime(plan).run()['guards_ref']


@pytest.mark.parametrize('value', [0.5, Decimal('0.5')])
def test_floor_division_and_display_have_no_input_path_bias(value):
    code = ('return {a:text((0-12*0.5)//1),b:text((0-12*$r)//1),'
            'c:text(12*$r),negative:text(-1.5//1),precise:0.3//0.1,from_input:$x//$y}')
    result = run(code, {}, {'r': value, 'x': 0.3, 'y': 0.1})
    assert result['value'] == {'a': '-6', 'b': '-6', 'c': '6', 'negative': '-2', 'precise': 3, 'from_input': 3}


@pytest.mark.parametrize('key', ['($x)=>[$x.a,$x.b]', '($x)=>{a:$x.a}', '($x)=>true'])
def test_sorted_rejects_definitely_unordered_keys(key):
    plan = compile_program('return sorted([{a:1,b:2,nested:[]}], ' + key + ')', {})
    assert 'UNORDERED' in [i['code'] for i in plan.issues]


def test_field_sort_keeps_heterogeneous_bucket_contract():
    result = run('return sorted([{a:[]},{a:[1]}],"a")', {})
    assert len(result['value']) == 2


def test_round_matches_literal_decimal_for_json_inputs():
    result = run('return {a:round(2.675,2),b:round($x,2)}', {}, {'x': 2.675})
    assert result['value']['a'] == result['value']['b'] == 2.68


@pytest.mark.parametrize('name', ['decimal_boundary', 'floordiv_display', 'input_float',
                                 'intdiv_decimal', 'intdiv_decimal2', 'sorted_type_loss'])
def test_other_preserved_value_reproductions(registry, name):
    result = run((FIXTURE / 'repro' / (name + '.ibl')).read_text(), registry, {'비율': 0.5})
    if name == 'floordiv_display':
        assert result['value']['리터럴'] == result['value']['입력'] == '-6'
    elif name == 'input_float':
        assert result['value']['x'] == '6' and result['value']['합'] == '67'


@pytest.mark.parametrize('name,expected', [('reuse_after_write', 1), ('reuse_no_write', 1),
                                         ('reuse_after_groupby', 2)])
def test_preserved_reuse_reproductions(tmp_path, name, expected):
    reg = load_registry(str(tmp_path))
    inputs = {'폴더': str(FIXTURE / 'input'), '출력': str(tmp_path / 'scratch.txt')}
    with Journal(tmp_path / 'runs', 'first') as journal:
        run((FIXTURE / 'repro' / (name + '_a.ibl')).read_text(), reg, inputs, journal=journal)
        original = journal.run_id
    result = run((FIXTURE / 'repro' / (name + '_b.ibl')).read_text(), reg, inputs,
                 reusable=reusable_receipts(tmp_path / 'runs', original), reuse_run=original)
    assert result['reuse']['reused_calls'] == expected


def test_unmeasured_model_failures_are_not_reported_as_zero():
    from model_call_context import capture_usage, call_scope, summarize_usage
    from providers.base import ProviderMetrics
    from types import SimpleNamespace
    provider = SimpleNamespace(metrics=ProviderMetrics(), model='fixture', agent_role='execution')
    with capture_usage() as rows:
        with pytest.raises(ValueError), call_scope(provider):
            raise ValueError('network failed')
    usage = summarize_usage(rows)
    assert usage['unmeasured_requests'] == 1
    assert usage['input'] is None and usage['output'] is None


def test_evidence_compaction_keeps_lineage_and_failures(registry):
    code = (FIXTURE / 'repro/evidence_scale.ibl').read_text()
    result = run(code, registry, {'n': list(range(1000))})
    assert result['value'] == 499
    assert len(json.dumps(result, ensure_ascii=False)) < 100000
    assert any(e.get('evaluations', 0) > 100 for e in result['evidence'])
    proof = run('$x=[1,2,3] >> [table:each]{return $it*3};return evidence($x)', {})
    assert any(e['kind'] == 'binary' for e in proof['value']['events'])
    assert all(p in {e['id'] for e in proof['value']['events']}
               for e in proof['value']['events'] for p in e['parents'])
    fail = run('[1,0,2] >> [table:each]{on_error:"collect"}{return 1/$it}', {})
    assert any(e['kind'] == 'failure' and 'node_id' in e for e in fail['evidence'])
    assert not fail['source_complete']


def test_resource_invalidation_sequential_parallel_unknown_and_aliases(tmp_path):
    from ibl_run_journal import call_resources
    source, output = tmp_path / 'in.txt', tmp_path / 'out.txt'
    source.write_text('old')
    alias = tmp_path / 'alias.txt'
    alias.symlink_to(source)
    hard = tmp_path / 'hard.txt'
    hard.hardlink_to(source)
    spec = Adapter({'read_resources': {'file': 'path'}, 'write_resources': {'file': 'path'}}, None)
    reads = call_resources(spec, spec.contract, {'path': str(source)}, 'read')
    separate = call_resources(spec, spec.contract, {'path': str(output)}, 'write')
    for target, safe in [(separate, True), (reads, False), (None, False),
                         (call_resources(spec, spec.contract, {'path': str(alias)}, 'write'), False),
                         (call_resources(spec, spec.contract, {'path': str(hard)}, 'write'), False)]:
        with Journal(tmp_path / 'runs', 'test') as journal:
            journal.begin('read', 'r', reusable=True, state_change=False, resources=reads)
            journal.finish('read', {'value': {'t': 'text', 'v': 'old'}, 'reuse_key': 'k'})
            journal.begin('write', 'w', resources=target)
            # Both directions of overlap: a read also starts during the write.
            journal.begin('during', 'd', reusable=True, state_change=False, resources=reads)
            journal.finish('during', {'value': 1, 'reuse_key': 'k2'})
            assert journal.reuse_summary()['read_calls'] == (2 if safe else 0)
            journal.finish('write', {'value': None})
            journal.complete({'success': True})


def test_reuse_after_disjoint_write_and_new_run_mutation(tmp_path):
    calls = []
    path = str(tmp_path / 'a')
    other = str(tmp_path / 'b')
    read = Adapter({'version': 1, 'params': {'path': 'Text'}, 'result': 'Text',
                    'effects': ['read_external'], 'read_resources': {'file': 'path'}},
                   lambda rt, a: calls.append('read') or 'value')
    write = Adapter({'version': 1, 'params': {'path': 'Text'}, 'result': 'Text',
                     'effects': ['write_external'], 'write_resources': {'file': 'path'}},
                    lambda rt, a: calls.append('write') or 'done')
    reg = {'t:read': read, 't:write': write}
    with Journal(tmp_path / 'runs', 'first') as journal:
        out = run('$r=[t:read]{path:$p};[t:write]{path:$q};return $r', reg,
                  {'p': path, 'q': other}, journal=journal)
        original = journal.run_id
    assert out['continuation']['read_calls'] == 1
    receipts = reusable_receipts(tmp_path / 'runs', original)
    for target, expected in [(other, 1), (path, 0)]:
        calls.clear()
        result = run('[t:write]{path:$q};return [t:read]{path:$p}', reg,
                     {'p': path, 'q': target}, reusable=receipts, reuse_run=original)
        assert result['reuse']['reused_calls'] == expected
        assert calls == (['write'] if expected else ['write', 'read'])


def test_model_usage_is_scoped_parallel_and_not_recharged_by_resume(tmp_path):
    from providers.base import ProviderMetrics
    from model_call_context import call_scope
    from types import SimpleNamespace
    def model(rt, args):
        provider = SimpleNamespace(metrics=ProviderMetrics(), model='fixture', agent_role='oneshot:execution')
        with call_scope(provider):
            provider.metrics.record_usage(2, {'input_tokens': 20, 'output_tokens': 5})
        return args['n']
    reg = {'t:model': Adapter({'version': 1, 'params': {'n': 'Number'},
                               'result': 'Number', 'effects': ['model']}, model)}
    code = '[1,2,3] >> [table:each]{parallel:3}{[t:model]{n:$it}}'
    with Journal(tmp_path, 'model') as journal:
        first = run(code, reg, journal=journal)
        original = journal.run_id
    usage = first['usage']['model']
    assert (usage['requests'], usage['input'], usage['output']) == (3, 60, 15)
    assert {row['model'] for row in usage['calls']} == {'fixture'}
    with Journal(tmp_path, 'model', resume={'run_id': original}) as journal:
        second = run(code, reg, journal=journal)
    assert 'model' not in second['usage']
    assert all(r['evidence']['model_usage'][0]['model'] == 'fixture' for r in second['recordings'])
    assert 'model' not in run('return 1', {})['usage']


@pytest.mark.parametrize('version', ['v3', 'v4'])
def test_full_program_original_change_reuse_and_missing_review(tmp_path, monkeypatch, version):
    import oneshot_facade
    from providers.base import ProviderMetrics
    requests = []
    def model(prompt, system_prompt=None, role='execution'):
        payload = json.loads(prompt.split('[items]\n', 1)[1].split('\n\n[지시]', 1)[0])
        requests.append(payload)
        ProviderMetrics().record_usage(1, {'input_tokens': 100, 'output_tokens': 20})
        return json.dumps([{'_i': row['_i'], 'pros': ['좋음'], 'cons': ['확인 필요']} for row in payload])
    monkeypatch.setattr(oneshot_facade, 'execution_oneshot', model)
    reg = load_registry(str(tmp_path))
    code = (FIXTURE / 'drafts' / (version + '.ibl')).read_text()
    inputs = {'폴더': str(FIXTURE / 'input'), '출력': str(tmp_path / 'proposal.md'), '미정비율': 1}
    with Journal(tmp_path / 'runs', 'full') as journal:
        first = run(code, reg, inputs, journal=journal)
        original = journal.run_id
    assert first['value']['verified'] and first['value']['rows_read'] == 120
    assert first['value']['추천'] == [{'venue': 'V2', 'date': '12-13', 'cost': 2590000},
                                     {'venue': 'V3', 'date': '12-13', 'cost': 2860000}]
    assert first['continuation']['read_calls'] == 7
    second = run(code, reg, {**inputs, '미정비율': 0.5},
                 reusable=reusable_receipts(tmp_path / 'runs', original), reuse_run=original)
    assert second['reuse']['reused_calls'] == 7
    assert second['reuse']['model_calls'] == 1
    assert second['value']['추천'][0] == {'venue': 'V2', 'date': '12-12', 'cost': 2818000}
    assert '67/70' in Path(inputs['출력']).read_text()
    assert '67.0' not in Path(inputs['출력']).read_text()
    missing = run(code, reg, {**inputs, '폴더': str(FIXTURE / 'input_variant')})
    assert missing['value']['verified'] and not missing['source_complete']
    assert missing['value']['후기실패'][0]['venue'] == 'V2'
    assert len(requests) == 2  # Only the initial and changed-source model calls are billed.
    assert 'model' not in second['usage']
    assert missing['usage']['model']['input'] == 100


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
