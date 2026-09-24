"""Edition migration, old vocabulary bridges and actual memory round trips."""
import json
import sqlite3
from pathlib import Path
import sys

import boot_paths  # noqa: F401
import pytest

from ibl_edition import source_edition, program_hash
from ibl_v2_entry import handle_request


@pytest.fixture
def memory(tmp_path, monkeypatch):
    import ibl_usage_db as module
    import workflow_store
    monkeypatch.setattr(module, 'DB_PATH', str(tmp_path / 'usage.db'))
    monkeypatch.setattr(module.IBLUsageDB, '_instance', None)
    monkeypatch.setattr(module.IBLUsageDB, '_index_batch', lambda *a, **k: None)
    monkeypatch.setattr(module.IBLUsageDB, '_index_single', lambda *a, **k: None)
    monkeypatch.setattr(module, '_tree_refresh', lambda *a, **k: None)
    workflows = tmp_path / 'workflows'
    workflows.mkdir()
    monkeypatch.setattr(workflow_store, '_get_workflows_path', lambda: workflows)
    return module.IBLUsageDB()


def example(code, alias='', **extra):
    return {'intent': '검증용 순수 목록 계산', 'ibl_code': code, 'alias': alias,
            'category': 'phrase' if alias else 'composition', 'nodes': 'table', **extra}


def test_same_name_editions_have_independent_lookup_and_execution(memory):
    old = '$return = $목록 >> [table:take]{n:$개수}'
    new = '#!ibl edition=2\n[def:앞부분]($목록,$개수=1){$목록 >> [table:take]{n:$개수}}'
    assert memory.add_examples_batch([example(old, '앞부분'), example(new, '앞부분')]) == 2
    assert memory.find_phrase_by_alias('앞부분')['ibl_code'] == old
    assert memory.find_phrase_by_alias('앞부분', edition=2)['ibl_code'] == new
    result = handle_request({'edition': 2, 'code': '[fn:앞부분]{목록:["007",2]}'})
    assert result['success'] and result['value'] == ['007'], result
    assert memory.find_phrase_by_alias('앞부분')['success_count'] == 0
    assert memory.find_phrase_by_alias('앞부분', edition=2)['success_count'] == 1


def test_native_local_override_does_not_credit_stored_function(memory):
    code = '#!ibl edition=2\n[def:값](){return 1}'
    assert memory.add_examples_batch([example(code, '값')]) == 1
    result = handle_request({'edition': 2, 'code': '[def:값](){return 2}\n[fn:값]{}'})
    assert result['value'] == 2
    assert memory.find_phrase_by_alias('값', edition=2)['success_count'] == 0


def test_legacy_function_reuses_original_semantics_and_returns_envelope(memory):
    code = '$return = $목록 >> [table:take]{n:$개수}'
    assert memory.add_examples_batch([example(code, '예전앞부분')]) == 1
    result = handle_request({'edition': 2, 'code': '$r=[fn:예전앞부분]{목록:[{id:"007"},{id:"b"}],개수:1}\nreturn $r.items'})
    assert result['success'] and result['value'] == [{'id': '007'}], result
    checked = handle_request({'edition': 2, 'code': '[fn:예전앞부분]{목록:[],개수:1}', 'check': True})
    assert checked['status'] == 'incomplete'
    assert any(g.get('boundary') == 'legacy-function/1' for g in checked['guards'])


def test_legacy_pipe_receiver_survives_bridge_and_rejects_collision(memory):
    code = '$return = $목록 >> [table:take]{n:$개수}'
    assert memory.add_examples_batch([example(code, '앞부분호환')]) == 1
    result = handle_request({'edition': 2, 'code':
        '$r = [{id:"007"},{id:"b"}] >> [fn:앞부분호환]{개수:1}; return $r.items'})
    assert result['success'] and result['value'] == [{'id': '007'}], result
    bad = handle_request({'edition': 2, 'check': True, 'code':
        '[] >> [fn:앞부분호환]{목록:[],개수:1}'})
    assert any(i['code'] == 'PIPE_COLLISION' for i in bad['issues'])
    missing = handle_request({'edition': 2, 'check': True, 'code':
        '[fn:앞부분호환]{개수:1}'})
    assert any(i['code'] == 'MISSING_ARGUMENT' for i in missing['issues'])


def test_health_query_declared_options_reach_handler(memory, monkeypatch):
    import ibl_engine
    seen = []
    def execute(request, *args, **kwargs):
        seen.append(request['params'])
        return {'success': True, 'items': [{'person': request['params']['person']}]}
    monkeypatch.setattr(ibl_engine, 'execute_ibl', execute)
    result = handle_request({'edition': 2, 'code':
        '[self:health]{op:"query",query_type:"summary",person:"가족",days:365,'
        'include_images:false,active_only:true}'})
    assert result['success'], result
    assert seen[0]['person'] == '가족' and seen[0]['days'] == 365
    assert seen[0]['active_only'] is True
    bad = handle_request({'edition': 2, 'check': True,
                          'code': '[self:health]{op:"query",persno:"가족"}'})
    assert any(i['code'] == 'UNKNOWN_ARGUMENT' for i in bad['issues'])


def test_member_legacy_pipe_contract_uses_same_body_rule(monkeypatch):
    from ibl_member_library import library, adapters
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    import ibl_engine
    seen = []
    def execute(call, *args, **kwargs):
        seen.append(call['params'])
        return {'success': True, 'items': call['params']['목록'][:call['params']['개수']]}
    monkeypatch.setattr(ibl_engine, 'execute_ibl', execute)
    with library('[def:앞부분]{$return = $목록 >> [table:take]{n:$개수}}'):
        registry = adapters(None, None)
    plan = compile_program('[{id:"007"}] >> [fn:앞부분]{개수:1}', registry)
    result = Runtime(plan).run()
    assert result['success'] and result['value']['items'] == [{'id': '007'}], result
    assert seen == [{'개수': 1, '목록': [{'id': '007'}]}]


def test_legacy_asset_change_invalidates_pinned_bridge(memory):
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    old = '$return = $목록 >> [table:take]{n:1}'
    memory.add_examples_batch([example(old, '옛것')])
    plan = compile_program('[fn:옛것]{목록:[]}', load_registry())
    with memory._get_connection() as conn:
        conn.execute("UPDATE ibl_examples SET ibl_code=? WHERE alias='옛것'", (old.replace('n:1', 'n:2'),))
        conn.commit()
    result = Runtime(plan).run()
    assert not result['success'] and result['diagnostic']['code'] == 'DEFINITION_CHANGED'


def test_declared_handler_bridge_keeps_whole_record_and_does_not_pipe_guess(memory, monkeypatch):
    import ibl_engine
    calls = []
    def execute(request, *a, **k):
        calls.append(request)
        return {'items': [{'id': '007'}], 'source': 'fixture'}
    monkeypatch.setattr(ibl_engine, 'execute_ibl', execute)
    result = handle_request({'edition': 2, 'code': '$r=[sense:search]{query:"literal $x"}\nreturn $r'})
    assert result['value'] == {'items': [{'id': '007'}], 'source': 'fixture'}
    assert calls[0]['params']['query'] == 'literal $x'
    bad = handle_request({'edition': 2, 'code': '[] >> [sense:search]{query:"x"}', 'check': True})
    assert bad['status'] == 'invalid'
    typo = handle_request({'edition': 2, 'code': '[sense:search]{qurey:"x"}', 'check': True})
    assert typo['status'] == 'invalid'


def test_core_router_and_open_params_remain_explicit_runtime_boundaries(memory, monkeypatch):
    import ibl_engine
    seen = []
    def execute(request, *a, **k):
        seen.append(request)
        return {'success': True, 'items': []}
    monkeypatch.setattr(ibl_engine, 'execute_ibl', execute)
    checked = handle_request({'edition': 2, 'code': '[others:ask]{target:"fixture",message:"x"}', 'check': True})
    assert checked['status'] == 'incomplete' and seen == []
    result = handle_request({'edition': 2, 'code': '[others:ask]{target:"fixture",message:"x"}'})
    assert result['success'] and seen[0]['params']['message'] == 'x'
    private = handle_request({'edition': 2, 'code': '[others:ask]{_prev_result:{},message:"x"}', 'check': True})
    assert private['status'] == 'invalid'


def test_bridge_errors_and_large_values_are_not_success(memory, monkeypatch):
    import ibl_engine
    monkeypatch.setattr(ibl_engine, 'execute_ibl', lambda *a, **k: {'success': False, 'error': 'denied', 'denied': True})
    result = handle_request({'edition': 2, 'code': '[sense:search]{query:"x"} ?? {fallback:true}'})
    assert not result['success'] and result['diagnostic']['kind'] == 'permission'
    result = handle_request({'edition': 2, 'code': '[sense:search]{query:9007199254740993}'})
    assert not result['success'] and any(i['code'] == 'TYPE' for i in result['issues'])


def test_compiler_gate_rejects_unbound_v2_and_accepts_explicit_function(memory):
    assert memory.add_examples_batch([example('#!ibl edition=2\nreturn $missing')]) == 0
    assert memory.add_examples_batch([example('#!ibl edition=2\n[def:f]($x){return $x}', 'f')]) == 1
    assert memory.find_phrase_by_alias('f', edition=2)['signature'] == 'x'


def test_recall_labels_editions_and_expands_definition_without_wrapping(memory):
    from ibl_usage_db import UsageExample
    from ibl_usage_rag import IBLUsageRAG
    import hippo_tree
    import xml.etree.ElementTree as ET
    code = '#!ibl edition=2\n[def:f]($x){return $x}'
    ex = UsageExample(1, '값 반환', code, 'table', 'phrase', 1, .8, 'synthetic', -1,
                      alias='f', signature='x')
    root = ET.fromstring(IBLUsageRAG._format_references(None, [], phrases=[ex]))
    ref = root.find('ref')
    assert ref.attrib['edition'] == '2' and '#!ibl edition=2' in ref.text
    assert hippo_tree.phrase_def_block('f', code) == code
    assert hippo_tree.split_sentences(code) == [code]


def test_v2_selection_is_atomic_and_never_joins_program_return_scopes(memory):
    from ibl_distill_value import source_rows
    from ibl_distill_gates import select_distill_source
    source = '$x=1\nreturn $x+2'
    tc = {'input': {'code': source, 'edition': 2}}
    rows = source_rows([(4, tc)])
    assert len(rows) == 1 and rows[0]['edition'] == 2
    code, _ = select_distill_source({'call_ids': [1]}, [rows[0]['code']])
    assert code == '#!ibl edition=2\n' + source
    for calls in ([code, code], [code, '[self:time]']):
        assert select_distill_source({'call_ids': [1, 2]}, calls)[0] is None


@pytest.mark.parametrize('change', [{'inputs': {'x': 2}}, {'partial': True}, {'check': True}])
def test_learning_rejects_external_input_partial_or_check(memory, change):
    from ibl_v2_experience import closed_call
    request = {'code': 'return 1', 'edition': 2}
    result = {'success': True, 'executed': True, 'source_complete': True}
    if change.get('partial'):
        result['source_complete'] = False
    elif change.get('check'):
        result['executed'] = False
    else:
        request.update(change)
    assert closed_call({'input': request, 'result': result}) is None


def test_successful_closed_program_enters_existing_distillation_path(memory, monkeypatch, tmp_path):
    from test_distill_source_recovery_2026_09_09 import _arm
    import ibl_v2_adapters
    monkeypatch.setattr(ibl_v2_adapters, 'load_registry', lambda *a: {})
    import ibl_v2_store
    monkeypatch.setattr(ibl_v2_store, 'definitions', lambda: {})
    source = '#!ibl edition=2\n$x=[1,2,3]\nreturn reduce($x,0,($a,$b)=>$a+$b)'
    reply = {'decision': 'keep', 'intent': '목록 합산', 'benefit': '반복 합산 재사용',
             'applicability': '숫자 목록', 'source_ids': [1], 'scope': 'component', 'topic': '시험'}
    rag, saved, asked, _ = _arm(monkeypatch, tmp_path, [reply])
    tc = {'tool_name': 'execute_ibl', 'success': True, 'input': {'code': source},
          'result': {'edition': 2, 'success': True, 'executed': True, 'source_complete': True, 'value': 6}}
    assert rag.distill_experience('합산 재사용', [tc], 0)
    assert len(asked) == 1 and saved[0]['ibl_code'] == source


def test_corpus_distinguishes_identical_text_editions_and_joins_trajectory(tmp_path, monkeypatch):
    import episode_logger as el
    from system_tools_ibl import _execute_ibl_unified
    path = tmp_path / 'pulse.db'
    def connection():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn
    monkeypatch.setattr(el, '_get_db', connection)
    el._ensure_episode_tables()
    el.record_ibl_code('return 3', False, edition=1)
    with el.trajectory_scope(task_id='edition-test'):
        _execute_ibl_unified({'edition': 2, 'code': 'return 3'}, str(tmp_path))
    with connection() as conn:
        rows = conn.execute('SELECT edition,code_sha256 FROM ibl_code_corpus ORDER BY edition').fetchall()
        started = [json.loads(r[0]) for r in conn.execute("SELECT data FROM trajectory_event WHERE kind='ibl.started'")]
    assert [r['edition'] for r in rows] == [1, 2]
    assert rows[0]['code_sha256'] != rows[1]['code_sha256']
    assert started[-1]['code_sha256'] == rows[1]['code_sha256'] == program_hash('return 3', 2)


def test_reviewed_seeds_compile_and_native_translations_agree(memory):
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    root = Path(__file__).resolve().parents[1]
    examples = json.loads((root / 'data/idioms/ibl_v2_seeds.json').read_text())
    assert memory.add_examples_batch(examples) == len(examples)
    registry = load_registry()
    for ex in examples:
        if not ex.get('alias'):
            result = Runtime(compile_program(ex['ibl_code'], registry)).run()
            assert result['success'], result
    for count in [0, 1, 3]:
        data = [{'id': '007', 'n': 4}, {'id': 'b', 'n': 2}]
        result = handle_request({'edition': 2, 'code': '[fn:열추려보기]{목록:$rows,열:["id"],개수:$n}',
                                 'inputs': {'rows': data, 'n': count}})
        assert result['value'] == [{'id': r['id']} for r in data][:count]
    result = handle_request({'edition': 2, 'code': '[fn:정렬해추리기]{목록:[{n:2},{n:4}],기준:"n",내림차순:true,개수:1,열:["n"]}'})
    assert result['value'] == [{'n': 4}], result


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
