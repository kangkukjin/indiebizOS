"""가이드 후처리가 예약된 수리의 입력 판본을 바꾸지 않는지 확인한다."""
import json
import pytest
import boot_paths  # noqa: F401
import guide_feedback as feedback
from restart_protocol import atomic_json


@pytest.mark.parametrize('status,pending', [('apply_scheduled', True), ('applying', True),
                                          ('staging', False), ('applied', False)])
def test_feedback_preserves_reserved_inputs_and_full_proposal(tmp_path, monkeypatch, status, pending):
    guides = tmp_path / 'guides'
    guides.mkdir()
    path = guides / 'test.md'
    path.write_text('원래 가이드\n')
    proposal = tmp_path / 'proposals.jsonl'
    monkeypatch.setattr(feedback, 'GUIDES_DIR', guides)
    monkeypatch.setattr(feedback, 'PROPOSALS_PATH', proposal)
    monkeypatch.setattr('repair_continuation.state_root', lambda: tmp_path)
    atomic_json(tmp_path / 'repair_sessions/task.json', {'status': status})
    observation = '보존할 관측 ' * 100
    out = {'observations': [observation]}
    monkeypatch.setattr(feedback, '_live_actions', lambda: set())
    monkeypatch.setattr(feedback, 'should_review', lambda *a: (True, 'test'))
    monkeypatch.setattr(feedback, '_review_one', lambda *a: out)
    monkeypatch.setattr(feedback, '_record_edit', lambda *a: None)
    monkeypatch.setattr('guide_registry.record_review', lambda *a: None)
    result = feedback.review_used_guides(['test.md'], 'request', 'answer')
    if pending:
        assert path.read_text() == '원래 가이드\n'
        assert result['appended'] == 0 and result['proposed'] == 1
        assert json.loads(proposal.read_text())['feedback'] == out
    else:
        assert observation.strip() in path.read_text() and result['appended'] == 1


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))


def test_driver_feedback_preserves_full_evidence_and_source_hash_without_append(tmp_path, monkeypatch):
    import hashlib
    guides = tmp_path / 'guides'
    guides.mkdir()
    path = guides / 'driver.md'
    path.write_text('## Call\nOriginal contract\n')
    proposal = tmp_path / 'proposals.jsonl'
    monkeypatch.setattr(feedback, 'GUIDES_DIR', guides)
    monkeypatch.setattr(feedback, 'PROPOSALS_PATH', proposal)
    monkeypatch.setattr('guide_registry.guide_delivery', lambda _: {'driver_owned': True})
    monkeypatch.setattr(feedback, '_live_actions', lambda: set())
    monkeypatch.setattr(feedback, 'should_review', lambda *a: (True, 'test'))
    monkeypatch.setattr('guide_registry.record_review', lambda *a: None)
    out = {'observations': ['A device failed; unknown installed version'],
           'factual_fixes': [{'old': 'Original', 'new': 'Unfounded'}]}
    monkeypatch.setattr(feedback, '_review_one', lambda *a: out)
    source = path.read_bytes()
    calls = [{'name': 'execute_ibl', 'result': {'device_id': 'one', 'unknown': True}}]
    result = feedback.review_used_guides(['driver.md'], 'request', 'answer', calls)
    saved = json.loads(proposal.read_text())['feedback']
    assert path.read_bytes() == source
    assert saved['review'] == out and saved['tool_calls'] == calls
    assert saved['source_hash'] == hashlib.sha256(source).hexdigest()
    assert result['appended'] == result['fixed'] == 0 and result['proposed'] == 1


def test_device_feedback_requires_execution_environment_and_keeps_version(monkeypatch):
    saved = []
    monkeypatch.setattr('control_observations.record', lambda surface, row: saved.append((surface, row)))
    row = {'environment': {'device_id': 'one', 'generation': 'installation-1'},
           'version': 'old-build', 'observed_at': '2026-11-01T10:00:00+09:00', 'fact': 'Permission denied'}
    assert feedback._store_driver_observations('pc_control.md', 'hash', [row], []) == 0
    assert feedback._store_driver_observations('pc_control.md', 'hash', [row], [{'result': row}]) == 1
    assert saved[0][0] == 'device:one'
    assert saved[0][1]['version'] == 'old-build' and saved[0][1]['status'] == 'recheck'
    assert saved[0][1]['source'] == 'guide:pc_control.md@hash'


def test_driver_observation_ignores_malformed_or_input_only_attribution(monkeypatch):
    saved = []
    monkeypatch.setattr('control_observations.record', lambda *args: saved.append(args))
    row = {'environment': {'device_id': 'one', 'generation': 'g'}, 'version': 'v',
           'observed_at': '2026-11-01T10:00:00+09:00', 'fact': 'Observed'}
    assert feedback._store_driver_observations('driver.md', 'h', [{'environment': 'invalid'}], []) == 0
    assert feedback._store_driver_observations('driver.md', 'h', [row], [{'input': row}]) == 0
    assert not saved
