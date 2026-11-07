"""명시적 인계가 근거·효과와 현재 실행 소유권을 보존한다."""
import json
from types import SimpleNamespace as NS

import boot_paths  # noqa: F401
import pytest
import task_continuation as tc


def test_context_handoff_retains_successful_effect_and_unknown_receipt():
    calls = [{'name': 'write', 'result': {'task_ref': 'remote-1', 'success': True}},
             {'name': 'query', 'result': None, 'is_error': True}]
    prompt = tc.message('자료 찾아줘', '', calls, reason='실행 도중 문맥 부족')
    packet = json.loads(prompt.split('\n', 1)[1])
    assert packet['request'] == '자료 찾아줘'
    assert packet['attempted_calls'][0]['result'] == json.dumps(calls[0]['result'], ensure_ascii=False)
    assert packet['attempted_calls'][1]['is_error']
    assert '효과가 불명확하면' in prompt


def test_long_receipts_keep_full_inputs_and_effects_in_existing_store(monkeypatch):
    saved = []

    def save(value):
        saved.append(value)
        return {'id': 'full-receipts', 'chars': 100000}

    monkeypatch.setattr('capability_guard.evidence_ref', save)
    calls = [{'name': 'write', 'input': {'content': 'a' * 10000},
              'result': {'receipt': i, 'content': 'b' * 10000}} for i in range(20)]
    calls[-1]['is_error'] = True
    prompt = tc.message('보고서 작성', '', calls, reason='실행 도중 문맥 부족')
    packet = json.loads(prompt.split('\n', 1)[1])
    assert saved == [calls] and saved[0][0]['result']['receipt'] == 0
    assert packet['attempted_calls_ref']['id'] == 'full-receipts'
    assert len(packet['attempted_calls']) == 3 and len(prompt) < 28000


@pytest.mark.parametrize('phase,available', [
    ('execution', True), ('repair_apply', True), ('repair_active', True),
    ('verify_remaining', True), ('apply', False), ('activation', False),
    ('active_verify', False), ('review', False), ('unknown', False),
])
def test_additional_execution_respects_existing_handoff_owner(monkeypatch, phase, available):
    monkeypatch.setattr('repair_continuation.current', lambda: {'phase': phase})
    assert tc.execution_available() is available


def test_new_apply_reservation_stops_execution():
    assert not tc.execution_available(NS(apply_scheduled={'key': 'repair'}))
