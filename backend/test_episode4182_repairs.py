"""4182: reference-backed learning, fenced decisions, and check/execution boundaries."""
import copy
import json
from decimal import Decimal

import boot_paths  # noqa: F401
import pytest

from test_conscious_supervisor import supervisor  # noqa: F401
from test_ibl_general_capabilities import boundary, adapter  # noqa: F401
from test_unified_distill_2026_09_21 import env, arm, empty, count  # noqa: F401


def reference_call(store, tmp_path, *, nested=False):
    from ibl_v2_ir import pack
    from system_tools_ibl import _execute_ibl_unified_impl
    values = [{'n': Decimal('1.25'), 'private': 'PRIVATE_LEARNING_INPUT'}]
    ref = store.evidence({'edition': 2, 'success': True, 'source_complete': True,
                          'value_wire': {'protocol': 'ibl-value/1', 'data': pack(values)}})
    value = {'$ref': ref['id']}
    inputs = {'data': {'rows': value}} if nested else {'data': value}
    source = 'return $data.rows[0].n + 1' if nested else 'return $data[0].n + 1'
    request = {'edition': 2, 'code': source, 'inputs': inputs}
    result = json.loads(_execute_ibl_unified_impl(request, str(tmp_path)))
    assert result['success'] and result['executed'] and result['source_complete']
    return {'tool_name': 'execute_ibl', 'success': True, 'input': request, 'result': result}, ref


@pytest.mark.parametrize('nested', [False, True])
def test_reference_learning_preserves_types_without_copying_data(boundary, tmp_path, nested):
    from ibl_v2_experience import closed_call
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    original, ref = reference_call(boundary, tmp_path, nested=nested)
    before = copy.deepcopy(original)
    candidate = closed_call(original)
    assert candidate, original.get('reuse_excluded')
    assert original == before
    assert 'PRIVATE_LEARNING_INPUT' not in candidate['input']['code']
    assert ref['id'] not in json.dumps(candidate['_ibl_abstraction'])
    name = candidate['_ibl_abstraction']['name']
    value = {'rows': [{'n': Decimal('8.5')}]} if nested else [{'n': Decimal('8.5')}]
    code = candidate['input']['code'] + f'\nreturn [fn:{name}]' + '{data:$fresh}'
    plan = compile_program(code, inputs={'fresh': value})
    assert not plan.issues
    assert Runtime(plan, {'fresh': value}).run()['value'] == 9.5


@pytest.mark.parametrize('damage', ['missing', 'tampered', 'provenance', 'plan', 'missing_notes', 'masked'])
def test_reference_learning_rejects_lost_or_changed_evidence(boundary, tmp_path, damage):
    from ibl_v2_experience import closed_call
    original, ref = reference_call(boundary, tmp_path)
    path = boundary.directory / (ref['id'] + '.txt')
    if damage == 'missing':
        path.unlink()
    elif damage == 'tampered':
        path.write_text('{}')
    elif damage == 'provenance':
        original['result']['inputs_resolved'][0]['evidence']['fingerprint'] = 'changed'
    elif damage == 'missing_notes':
        original['result'].pop('inputs_resolved')
    elif damage == 'masked':
        ref = boundary.evidence({'api_key': 'sk-test-not-a-real-credential-12345678901234567890'})
        original['input']['inputs']['data'] = {'$ref': ref['id']}
    else:
        original['result']['plan_hash'] = 'changed'
    assert closed_call(original) is None
    assert original['reuse_excluded']


def test_learning_after_restart_uses_original_store_not_current_turn(boundary, tmp_path, monkeypatch):
    import model_result_view as view
    from supervision_store import TurnStore
    from ibl_v2_experience import closed_call
    root = tmp_path.resolve()
    monkeypatch.setattr('runtime_utils.get_base_path', lambda: root)
    original_store = TurnStore(root / 'data/spill/supervision' / ('a' * 32))
    monkeypatch.setattr(view, 'evidence_store', lambda: original_store)
    original, _ = reference_call(original_store, tmp_path)
    monkeypatch.setattr(view, 'evidence_store', lambda: boundary)
    assert closed_call(copy.deepcopy(original)) is None
    cost = {'events_path': str(original_store.directory / 'events.jsonl')}
    assert closed_call(original, turn_cost=cost)
    wrong = {'events_path': str(root / 'outside' / ('a' * 32) / 'events.jsonl')}
    assert closed_call(original, turn_cost=wrong) is None


def test_literal_input_learning_does_not_require_old_evidence_directory(boundary):
    from ibl_v2_experience import closed_call
    original = {'input': {'edition': 2, 'code': 'return $n+1', 'inputs': {'n': 1}},
                'result': {'success': True, 'executed': True, 'source_complete': True}}
    assert closed_call(original, turn_cost={'events_path': '/missing/old/events.jsonl'})


@pytest.mark.parametrize('fence', ['```json', '```'])
def test_fenced_empty_decision_completes_once_without_storage(env, fence):
    import unified_distill as ud
    asked = arm(env, ' \n' + fence + '\n' + json.dumps(empty()) + '\n```\n')
    assert ud.run(env.job)['status'] == 'completed_empty'
    assert ud.run(env.job)['status'] == 'completed_empty'
    assert len(asked) == 1 and count(env) == 0


@pytest.mark.parametrize('raw', [
    'explanation\n```json\n{}\n```', '```json\n{}\n```\nextra',
    '```json\n{}\n```\n```json\n{}\n```', '```json\n{broken}\n```',
    '```python\n{}\n```', '```json\n{"schema_version":1,"deep":[]}\n```',
])
def test_fence_support_never_guesses_or_repairs_invalid_decisions(raw):
    import unified_distill as ud
    from distill_ledger import PermanentDistillError
    with pytest.raises(PermanentDistillError):
        ud.parse_decision(raw)


def test_check_does_not_write_and_instructs_actual_execution(boundary, tmp_path, monkeypatch):
    from ibl_v2_entry import handle_request
    target = tmp_path / 'report.txt'
    def write(*_):
        target.write_text('done')
        return 1
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a: {
        't:write': adapter(write, effects=['write_external'])})
    request = {'edition': 2, 'code': '[t:write]{}', 'check': True}
    checked = handle_request(request, str(tmp_path))
    assert checked['ok'] and checked['executed'] is False and not target.exists()
    assert '파일 생성은 하지 않았습니다' in checked['execution_note']
    assert 'check를 제거하거나 false' in checked['next_action']
    result = handle_request({**request, 'check': False}, str(tmp_path))
    assert result['success'] and result['executed'] and target.read_text() == 'done'


@pytest.mark.parametrize('kind,expected', [('budget', 1), ('compile', 1), ('check', 0), ('runtime', 0)])
def test_rejection_counts_use_preexecution_state(supervisor, boundary, tmp_path, kind, expected):
    from ibl_v2_entry import handle_request
    request = {'edition': 2, 'code': 'return 1', 'check': True}
    if kind == 'budget':
        request['budget'] = {'steps': 2000000}
    elif kind == 'compile':
        request['code'] = 'return $missing'
    result = ({'success': False, 'executed': True, 'error': 'external failure'} if kind == 'runtime'
              else handle_request(request, str(tmp_path)))
    key = supervisor._start('execute_ibl', request)
    supervisor._finish(key, result, error=kind != 'check')
    assert supervisor.store.cost['check_rejections'] == expected


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
