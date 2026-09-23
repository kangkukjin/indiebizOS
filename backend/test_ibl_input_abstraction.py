"""Successful explicit inputs become AST-preserving callable memory, not literals."""
import json
import pytest
import boot_paths  # noqa
from ibl_v2_experience import closed_call, finalize_candidate
from ibl_distill_value import source_rows
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    import ibl_v2_adapters, ibl_v2_store
    monkeypatch.setattr(ibl_v2_adapters, 'load_registry', lambda *a: {})
    monkeypatch.setattr(ibl_v2_store, 'definitions', lambda: {})


def call(source='return $text', inputs=None):
    return {'tool_name': 'execute_ibl', 'success': True,
            'input': {'edition': 2, 'code': source, 'inputs': inputs or {'text': 'PRIVATE_INPUT_928'}},
            'result': {'success': True, 'executed': True, 'source_complete': True}}


def test_parameterized_function_and_composition_never_copy_values():
    original = call()
    candidate = closed_call(original)
    assert 'PRIVATE_INPUT_928' not in json.dumps(candidate, ensure_ascii=False)
    row = source_rows([(3, candidate)])[0]
    code, name, result = finalize_candidate(row, '입력반환')
    plan = compile_program('[def:두번]($x){return [fn:입력반환]{text:$x}}\n[fn:두번]{x:"OTHER"}',
                           definitions={name: code})
    assert not plan.issues
    assert Runtime(plan).run()['value'] == 'OTHER'
    assert row['abstraction']['new_input_successes'] == 0
    assert original['input']['inputs']['text'] == 'PRIVATE_INPUT_928'


def test_nested_definition_and_early_return_are_preserved():
    src = '[def:안쪽]($x){return $x+1}\n[if:$n>0]{return [fn:안쪽]{x:$n}}\nreturn 0'
    candidate = closed_call(call(src, {'n': 2}))
    assert candidate
    code, name, _ = finalize_candidate(source_rows([(1, candidate)])[0])
    for value, expected in [(10, 11), (-1, 0)]:
        plan = compile_program(f'[fn:{name}]' + '{n:$n}', inputs={'n': value}, definitions={name:code})
        assert Runtime(plan, {'n': value}).run()['value'] == expected


def test_tampering_and_open_sources_are_rejected():
    candidate = closed_call(call())
    row = source_rows([(1, candidate)])[0]
    row['code'] = row['code'].replace('return $text', 'return "inserted"')
    with pytest.raises(ValueError):
        finalize_candidate(row)
    bad = call('return $unknown', {'text':'private'})
    assert closed_call(bad) is None and bad.get('reuse_excluded')
    incomplete = call(); incomplete['result']['source_complete'] = False
    assert closed_call(incomplete) is None


def test_existing_single_reflection_stores_callable_provenance(monkeypatch, tmp_path):
    from test_distill_source_recovery_2026_09_09 import _arm
    reply = {'decision':'keep', 'intent':'입력 전달', 'benefit':'조합 절차 재사용',
             'applicability':'문자열', 'source_ids':[1], 'scope':'component', 'topic':'시험', 'name':'전달'}
    rag, saved, asked, _ = _arm(monkeypatch, tmp_path, [reply])
    assert rag.distill_experience('명시 입력 재사용', [call()], 0)
    assert len(asked) == 1 and saved[0]['alias'] == '전달'
    assert saved[0]['category'] == 'phrase'
    assert 'PRIVATE_INPUT_928' not in json.dumps(saved, ensure_ascii=False)
    assert saved[0]['provenance']['sources'][0]['abstraction']['new_input_successes'] == 0

from test_ibl_v2_assets import memory  # noqa: E402,F401


def test_real_memory_round_trip_and_actual_success_count(memory):
    from ibl_v2_learning import record_functions
    candidate = closed_call(call('return $n + 1', {'n': 7}))
    code, name, returns = finalize_candidate(source_rows([(1, candidate)])[0], '하나더')
    assert memory.add_examples_batch([{'intent':'하나 더하기', 'ibl_code':code,
                                      'category':'phrase', 'alias':name, 'returns':returns}]) == 1
    stored = memory.find_phrase_by_alias(name, edition=2)
    assert stored['success_count'] == 0 and stored['signature'] == 'n'
    plan = compile_program('[fn:하나더]{n:20}', definitions={name:stored['ibl_code']})
    result = Runtime(plan).run()
    assert result['value'] == 21
    record_functions(plan, result)
    assert memory.find_phrase_by_alias(name, edition=2)['success_count'] == 1


def test_named_function_is_not_distilled_again_under_candidate_name():
    from ibl_distill_value import redundant_reason
    candidate = closed_call(call('return $n+1', {'n':4}))
    row = source_rows([(1,candidate)])[0]
    code, _, _ = finalize_candidate(row, '덧셈')
    assert redundant_reason([row['code']], [{'ibl_code':code}])


def test_dependency_provenance_keeps_hashes_not_private_filesystem_paths(monkeypatch):
    import ibl_v2_adapters
    adapter = ibl_v2_adapters.Adapter({'params':{'n':'Number'}, 'result':'Number', 'effects':['read_external']},
                                    lambda *_:1, dependency=lambda _: {'file':'/Users/private-host/script.py'})
    monkeypatch.setattr(ibl_v2_adapters, 'load_registry', lambda *a: {'test:read':adapter})
    candidate = closed_call(call('[test:read]{n:$n}', {'n':3}))
    assert candidate
    assert '/Users/private-host' not in json.dumps(candidate['_ibl_abstraction'])


def test_partial_memory_save_retries_original_name_and_body(memory, monkeypatch, tmp_path):
    from pathlib import Path
    from test_distill_source_recovery_2026_09_09 import _arm
    import ibl_usage_db, ibl_v2_store
    db_type = type(memory)
    rag, _, _, _ = _arm(monkeypatch, tmp_path, [])
    monkeypatch.setattr(ibl_usage_db, 'IBLUsageDB', db_type)
    prepared = rag.prepare_experience('입력 전달', [call()], 0)
    reply = {'decision': 'keep', 'intent': '입력 전달', 'benefit': '조합 절차 재사용',
             'applicability': '문자열', 'source_ids': [1], 'scope': 'component',
             'topic': '시험', 'name': '전달'}
    original_replace = Path.replace
    def fail_projection(path, target):
        if path.name == 'ibl_distilled.distill.tmp':
            raise OSError('simulated projection interruption')
        return original_replace(path, target)
    monkeypatch.setattr(Path, 'replace', fail_projection)
    with pytest.raises(OSError, match='projection interruption'):
        rag.apply_experience(prepared, reply, candidate_key='same-candidate')
    stored = memory.find_distilled_candidate('same-candidate')
    assert stored['alias'] == '전달'
    # 재배달 시 이미 저장된 함수가 사전에 나타나는 실제 조건.
    monkeypatch.setattr(ibl_v2_store, 'definitions', lambda: {'전달': stored['ibl_code']})
    monkeypatch.setattr(Path, 'replace', original_replace)
    assert rag.apply_experience(prepared, reply, candidate_key='same-candidate')
    training = json.loads((tmp_path / 'data/training/ibl_distilled.json').read_text())
    assert len(training) == 1
    assert training[0]['alias'] == stored['alias']
    assert training[0]['ibl_code'] == stored['ibl_code']
    assert training[0]['provenance'] == json.loads(stored['provenance'])
    with memory._get_connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM ibl_examples').fetchone()[0] == 1


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
