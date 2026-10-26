"""Declared row outputs compose independently of their input arity (L32-1)."""
import boot_paths  # noqa: F401
import json
import runpy
from pathlib import Path
import pytest

from ibl_v2_adapters import Adapter, load_registry
from ibl_v2_compile import compile_program
from ibl_v2_entry import handle_request
from ibl_v2_runtime import Runtime


@pytest.mark.parametrize('producer,expected', [
    ('[table:join]{left:[{id:"a",n:2}],right:[{id:"a",x:3}],on:"id"}',
     [{'id': 'a', 'n': 2, 'x': 3}]),
    ('[table:union]{inputs:[[{id:"a"}],[{id:"b"}]]}',
     [{'id': 'a'}, {'id': 'b'}]),
    ('[table:merge]{inputs:[[{id:"a",x:2}],[{id:"a",y:3}]],by:"id"}',
     [{'id': 'a', 'x': 2}]),
    ('[table:join]{left:[],right:[],on:"id"}', []),
])
@pytest.mark.parametrize('consumer', [
    '[table:each]{return $it}', '[table:select]{columns:["id"]}',
    '[table:sort]{by:"id"}',
])
def test_multi_input_row_producers_compose(tmp_path, producer, expected, consumer):
    registry = load_registry(str(tmp_path))
    code = producer + ' >> ' + consumer
    plan = compile_program(code, registry)
    assert not plan.issues, plan.issues
    out = Runtime(plan).run()
    assert out['success'] and out['source_complete'], out
    if 'select' in consumer:
        expected = [{'id': r['id']} for r in expected]
    assert out['value'] == expected


def test_output_refinement_uses_declaration_not_an_action_name():
    contract = {'version': 1, 'params': {}, 'required': [],
                'result': 'Record', 'effects': ['pure'],
                'analysis': {'flow': {'emits': 'items'}}}
    registry = {'fixture:rows': Adapter(contract, lambda rt, a: {'items': [{'n': 3}]})}
    plan = compile_program('[fixture:rows] >> [table:each]{return $it.n}', registry)
    assert not plan.issues, plan.issues
    assert Runtime(plan).run()['value'] == [3]


@pytest.mark.parametrize('result,body', [
    ('Record', {'count': 2}),
    ({'items': 'Number'}, {'items': 2}),
])
def test_non_rows_and_conflicting_declared_items_still_rejected(result, body):
    contract = {'version': 1, 'params': {}, 'required': [],
                'result': result, 'effects': ['pure']}
    if isinstance(result, dict):
        contract['analysis'] = {'flow': {'emits': 'items'}}
    registry = {'fixture:value': Adapter(contract, lambda rt, a: body)}
    plan = compile_program('[fixture:value] >> [table:each]{return $it}', registry)
    assert any(issue['code'] == 'TYPE' for issue in plan.issues)


def test_declared_rows_do_not_hide_runtime_shape_failure():
    contract = {'version': 1, 'params': {}, 'required': [],
                'result': 'Record', 'effects': ['pure'],
                'analysis': {'flow': {'emits': 'items'}}}
    registry = {'fixture:rows': Adapter(contract, lambda rt, a: {'count': 2})}
    plan = compile_program('[fixture:rows] >> [table:each]{return $it}', registry)
    assert not plan.issues, plan.issues
    out = Runtime(plan).run()
    assert not out['success']
    assert out['diagnostic']['code'] == 'TYPE_CONTRACT'


@pytest.mark.parametrize('flag', [False, True])
@pytest.mark.parametrize('consumer,expected', [
    ('[table:select]{columns:["n"]}', [{'n': 2}]),
    ('[table:filter]{where:($r)=>$r.n>0}', [{'n': 2}]),
    ('[table:sort]{by:"n"}', [{'n': 2}]),
    ('[table:take]{n:1}', [{'n': 2}]),
    ('[table:compute]{set:($r)=>{n:$r.n+1}}', [{'n': 3}]),
    ('[table:each]{return $it.n}', [2]),
])
def test_branch_list_and_envelope_share_row_consumers(tmp_path, flag, consumer, expected):
    code = ('$rows=[{n:2}]\n[if:$flag]{$rows={items:[{n:2}],count:1}}\n'
            'return $rows >> ' + consumer)
    plan = compile_program(code, load_registry(str(tmp_path)), {'flag': flag})
    assert not plan.issues, plan.issues
    out = Runtime(plan, {'flag': flag}).run()
    assert out['success'] and out['value'] == expected, out


@pytest.mark.parametrize('bad', ['{count:2}', '{items:3}', 'null', '7', '"rows"'])
@pytest.mark.parametrize('consumer', [
    '[table:each]{return $it.n}', '[table:select]{columns:["n"]}',
])
def test_non_row_branch_rejected_before_any_effect(tmp_path, bad, consumer):
    calls = []
    registry = load_registry(str(tmp_path))
    registry['fixture:effect'] = Adapter(
        {'version': 1, 'params': {}, 'result': 'Number', 'effects': ['write_external']},
        lambda *_: calls.append(True) or 1)
    code = ('[fixture:effect]\n$rows=[{n:2}]\n[if:$flag]{$rows=' + bad + '}\n'
            'return $rows >> ' + consumer)
    plan = compile_program(code, registry, {'flag': False})
    assert any(i['code'] == 'TYPE' for i in plan.issues), plan.report()
    out = Runtime(plan, {'flag': False}).run()
    assert not out['executed'] and not calls


@pytest.mark.parametrize('empty', ['[]', '{items:[]}'])
def test_branch_empty_rows_preserve_element_type(tmp_path, empty):
    from ibl_v2_types import declared, compatible
    registry = load_registry(str(tmp_path))
    code = ('$rows=' + empty + '\n[if:$flag]{$rows={items:[{n:2}]}}\n'
            'return $rows >> [table:each]{return $it.n + 1}')
    for flag, expected in [(False, []), (True, [3])]:
        plan = compile_program(code, registry, {'flag': flag})
        assert not plan.issues, plan.issues
        assert compatible(plan.result_type, declared('List<Number>'))
        out = Runtime(plan, {'flag': flag}).run()
        assert out['success'] and out['value'] == expected, out


def test_branch_row_flow_survives_legacy_transform(tmp_path):
    registry = load_registry(str(tmp_path))
    source = ('$rows=[{n:2}]\n[if:$flag]{$rows={items:[{n:3}]}}\n'
              '$unique=$rows >> [table:dedup]{by:"n"}\n'
              'return $unique >> [table:each]{return $it.n + 1}')
    for flag, expected in [(False, [3]), (True, [4])]:
        plan = compile_program(source, registry, {'flag': flag})
        assert not plan.issues, plan.issues
        assert str(plan.result_type) == 'List<Number>'
        out = Runtime(plan, {'flag': flag}).run()
        assert out['success'] and out['value'] == expected, out


@pytest.mark.system
def test_round32_whole_program_and_missing_source(tmp_path):
    fixture = Path(__file__).resolve().parents[1] / 'docs/experiments/long_sentence_imagination/round_32'
    runpy.run_path(str(fixture / 'harness/prepare.py'))['generate'](tmp_path)
    code = (fixture / 'drafts/main_repaired.ibl').read_text()
    for variant in ['base', 'missing']:
        folder = tmp_path / 'out' / variant
        result = handle_request({'code': code, 'origin': 'training',
                                 'inputs': {'source': str(tmp_path / 'source' / variant),
                                            'out': str(folder)}}, str(tmp_path))
        assert result['success'], result
        actual = json.loads((folder / 'result.json').read_text())
        expected = json.loads((tmp_path / 'oracle' / f'{variant}.json').read_text())
        assert actual['rows'] == expected['rows']
        assert actual['events'] == expected['events']
        assert actual['missing_sites'] == (['부산'] if variant == 'missing' else [])
        report = (folder / 'report.md').read_text()
        assert '서울: 기초 6000, 이동 595, 마감 6595' in report
        if variant == 'missing':
            assert not result['source_complete']
            assert '부산: 기초 6000, 이동 미확인, 마감 미확인; 누락 true' in report
        else:
            assert result['source_complete']


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
