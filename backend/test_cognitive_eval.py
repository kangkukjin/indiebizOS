"""Evaluator instructions must follow the current prompt file in a live process."""
import boot_paths  # noqa: F401 — direct execution uses the same layered imports.
import pytest

import cognitive_eval


@pytest.fixture
def prompt_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cognitive_eval, '__file__',
                        str(tmp_path / 'backend/cognition/cognitive_eval.py'))
    path = tmp_path / 'data/common_prompts/evaluator_prompt.md'
    path.parent.mkdir(parents=True)
    return path


def test_evaluator_uses_updated_instructions_without_recreation(prompt_file):
    evaluator = cognitive_eval.CognitiveEvalMixin()
    prompt_file.write_text('이전 판정 기준', encoding='utf-8')
    assert evaluator._load_evaluator_prompt() == '이전 판정 기준'
    prompt_file.write_text('정정된 판정 기준', encoding='utf-8')
    assert evaluator._load_evaluator_prompt() == '정정된 판정 기준'


def test_evaluator_missing_prompt_recovers_and_does_not_keep_deleted_text(prompt_file):
    evaluator = cognitive_eval.CognitiveEvalMixin()
    fallback = evaluator._load_evaluator_prompt()
    assert fallback
    prompt_file.write_text('복구된 판정 기준', encoding='utf-8')
    assert evaluator._load_evaluator_prompt() == '복구된 판정 기준'
    prompt_file.unlink()
    assert evaluator._load_evaluator_prompt() == fallback


@pytest.mark.parametrize('review,goal', [('ACHIEVED','NOT_ACHIEVED'), ('ACHIEVED','ACHIEVED'), ('UNKNOWN','UNKNOWN')])
def test_review_and_original_goal_have_independent_evidence(monkeypatch, review, goal):
    import json
    import thread_context as tc
    evaluator = cognitive_eval.CognitiveEvalMixin()
    evaluator._log = lambda *args: None
    response = review + '\nGOAL_OUTCOME: ' + json.dumps({
        'status': goal, 'reason': '실제 실행 결과', 'evidence': ['tool:1'],
        'remaining': ['외부 PC 갱신'] if goal == 'NOT_ACHIEVED' else []})
    monkeypatch.setattr('consciousness_agent.system_ai_call', lambda *a, **kw: response)
    approved, _, severity = evaluator._evaluate_achievement('PC 갱신', '갱신 또는 차단 사유 보고',
                                                           '접근 불가', '')
    assert approved == (True if review == 'ACHIEVED' else None)
    assert evaluator.goal_outcome['goal_status'] == goal
    previous = tc.snapshot()
    try:
        tc.set_goal_eval_outcome(approved, severity, review_status='APPROVED', **evaluator.goal_outcome)
        saved = tc.get_goal_eval_outcome()
        tc.clear_goal_eval_outcome()
        tc.restore_goal_eval_outcome(saved)
        assert tc.get_goal_eval_outcome() == saved
        assert saved['achieved'] == {'ACHIEVED': True, 'NOT_ACHIEVED': False}.get(goal)
        tc.restore_goal_eval_outcome({'achieved': True, 'status': 'ACHIEVED'})
        assert tc.get_goal_eval_outcome()['goal_status'] == 'UNKNOWN'
        assert tc.get_goal_eval_outcome()['achieved'] is None
    finally:
        tc.restore(previous)


def test_legacy_approval_does_not_supply_goal_evidence():
    assert cognitive_eval.parse_goal_outcome('ACHIEVED')['goal_status'] == 'UNKNOWN'


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
