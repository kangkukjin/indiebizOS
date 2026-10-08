"""Round 6: bounded budgets, visible costs, early schemas and honest reuse."""
import boot_paths  # noqa: F401
import csv
import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import pytest

from ibl_v2_adapters import Adapter, load_registry
from ibl_v2_compile import compile_program
from ibl_v2_entry import handle_request
from ibl_v2_runtime import Budget, Runtime
from ibl_v2_ir import Fault
from ibl_run_journal import Journal, reusable_receipts

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'docs/experiments/long_sentence_imagination/round_6'


@pytest.fixture(scope='module')
def registry():
    return load_registry(str(ROOT))


def run(code, registry, inputs=None, **kwargs):
    plan = compile_program(code, registry, inputs)
    assert not plan.issues, plan.issues
    return Runtime(plan, inputs, **kwargs).run()


@pytest.mark.parametrize('value', [{'steps': True}, {'steps': 0}, {'steps': 10000001},
                                    {'rows': 100001}, {'depth': 999}, {'steps': '5'}, []])
def test_invalid_budget_rejected_before_effect(value):
    result = handle_request({'code': '#!ibl edition=2\nreturn 1', 'budget': value})
    assert not result.get('executed')
    assert 'BUDGET_ARGUMENT' in json.dumps(result)


def test_public_request_budget_and_check():
    code = '#!ibl edition=2\nreturn $rows >> [table:each]{return $it*2}'
    check = handle_request({'code': code, 'inputs': {'rows': list(range(20))}, 'budget': {'steps': 20}, 'check': True})
    assert check['ok'] and check['budget'] == {'steps': 20, 'rows': 10000}
    result = handle_request({'code': code, 'inputs': {'rows': list(range(20))}, 'budget': {'steps': 20}})
    assert not result['success'] and result['diagnostic']['code'] == 'BUDGET'
    result = handle_request({'code': code, 'inputs': {'rows': list(range(20))}, 'budget': {'steps': 500}})
    assert result['success'] and result['value'] == list(range(0, 40, 2))


@pytest.mark.parametrize('parallel', [1, 4])
def test_step_costs_are_exclusive_and_bounded(registry, parallel):
    result = run(f'return $rows >> [table:each]{{parallel:{parallel}}}{{return $it*2}}', registry, {'rows': list(range(100))})
    usage = result['usage']
    assert len(usage['steps_by_span']) <= 20
    assert all(row['location'] for row in usage['steps_by_span'])
    assert sum(row['steps'] for row in usage['steps_by_span']) + usage['steps_other'] == usage['steps']


def test_original_normalization_with_explicit_budget(registry):
    code = (FIXTURE / 'drafts/p1_v0.ibl').read_text().split('$규칙문 =')[0] + '\nreturn $정규'
    inputs = {'폴더': str(FIXTURE / 'input/ledger')}
    failed = run(code, registry, inputs)
    assert not failed['success'] and failed['diagnostic']['code'] == 'BUDGET'
    passed = run(code, registry, inputs, budget=Budget.from_request({'steps': 300000}))
    assert passed['success'] and len(passed['value']) == 2698
    assert sum(r['금액'] for r in passed['value']) == 49259480 - 82000


def test_hidden_collision_is_static_and_runtime_before_model(registry, monkeypatch):
    code = (FIXTURE / 'repro/ai_schema_hidden_collision.ibl').read_text()
    plan = compile_program(code, registry)
    assert any(i['code'] == 'ARGUMENT_CONTRACT' and '분류' in i['message'] for i in plan.issues)
    spec = importlib.util.spec_from_file_location('round6_ai', ROOT / 'data/packages/installed/tools/ai-ops/handler.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    import oneshot_facade
    monkeypatch.setattr(oneshot_facade, 'oneshot_json', lambda *a, **k: pytest.fail('must not call model'))
    result = json.loads(module._transform({'instruction': '분류', 'schema': '분류(문자열)',
        'input_fields': ['설명'], 'items': [{'설명': '가게', '분류': None}]}))
    assert not result['success'] and '분류' in result['error'] and 'select' in result['error']
    fixed = code.replace('input_fields:["설명"]', 'input_fields:["설명","분류"]')
    assert not compile_program(fixed, registry).issues
    inspected = code.replace('preserve_rows:true', 'preserve_rows:true,inspect:"batch"')
    assert not compile_program(inspected, registry).issues


def test_group_skips_survive_items_projection(registry):
    result = run('$r=$rows >> [table:groupby]{by:"group",agg:{total:["sum","amount"]}};return $r.items',
                 registry, {'rows': [{'group': 'x', 'amount': 10}, {'group': 'x', 'amount': '1,200원'}]})
    assert result['success'] and result['value'] == [{'group': 'x', 'total': 10}]
    assert any('제외' in n['warning'] and '1건' in n['warning'] for n in result['execution_notes'])
    from model_result_view import project_v2_result
    assert project_v2_result(result)['execution_notes'] == result['execution_notes']


def test_compute_describe_has_current_lambda_example():
    from model_result_view import describe_actions
    result = describe_actions(['table:compute'], None, edition=2)
    hint = result['actions'][0]['definition']['target_description']
    assert '($r)=>' in hint and 'Record' in hint


@pytest.mark.parametrize('change,dimension', [('args', 'args'), ('contract', 'contract'), ('same', None)])
def test_reuse_explains_changed_identity_without_exposing_values(tmp_path, change, dimension):
    calls = []
    adapter = Adapter({'version': 1, 'params': {'value': 'Text'}, 'result': 'Text',
                       'effects': ['read_external']}, lambda rt, a: calls.append(a) or a['value'])
    registry = {'t:read': adapter}
    source = 'return [t:read]{value:$input}'
    with Journal(tmp_path, 'first') as journal:
        first = run(source, registry, {'input': 'private-value'}, journal=journal)
        rid = journal.run_id
    if change == 'contract':
        registry['t:read'] = replace(adapter, contract={**adapter.contract, 'implementation_fingerprint': 'new'})
    result = run(source, registry, {'input': 'changed' if change == 'args' else 'private-value'},
                 reusable=reusable_receipts(tmp_path, rid), reuse_run=rid)
    assert first['success'] and result['success']
    if change == 'same':
        assert result['reuse']['reused_calls'] == 1 and len(calls) == 1
    else:
        skipped = result['reuse']['skipped'][0]
        assert dimension in skipped['candidates'][0]['changed']
        assert 'private-value' not in json.dumps(result['reuse'])


def test_csv_roundtrip_and_invalid_cells(registry, tmp_path):
    rows = [{'종류': '쉼표,따옴표"', '설명': '첫줄\n둘째줄', '금액': 12},
            {'종류': '일반', '설명': '', '금액': None}]
    path = tmp_path / 'result.csv'
    result = run('return $rows >> [self:write]{path:$path,format:"csv",columns:["종류","설명","금액"]}',
                 registry, {'rows': rows, 'path': str(path)})
    assert result['success'], result
    with path.open(newline='') as stream:
        assert list(csv.DictReader(stream)) == [{**r, '금액': '' if r['금액'] is None else str(r['금액'])} for r in rows]
    before = path.read_bytes()
    bad = run('return $rows >> [self:write]{path:$path,format:"csv"}', registry,
              {'rows': [{'nested': {'x': 1}}], 'path': str(path)})
    assert not bad['success'] and path.read_bytes() == before
    empty = run('return [self:write]{path:$path,format:"csv",content:[],columns:["x"]}', registry, {'path': str(path)})
    assert empty['success'] and path.read_text() == 'x\n'


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
