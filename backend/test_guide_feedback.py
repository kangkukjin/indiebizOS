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
