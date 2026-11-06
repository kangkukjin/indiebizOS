"""Evaluator instructions must follow the current prompt file in a live process."""
import boot_paths  # noqa: F401 — direct execution uses the same layered imports.
import json
from types import SimpleNamespace
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


@pytest.fixture
def evaluation_case(tmp_path, monkeypatch):
    from test_goal_eval_streaming import _Runner, _drain
    from supervision_store import TurnStore
    import thread_context as tc
    previous = tc.snapshot()
    tc.clear_all_context()
    store = TurnStore(tmp_path / 'review')
    monkeypatch.setattr('model_result_view.evidence_store', lambda: store)
    case = SimpleNamespace(store=store, calls=[], review='NOT_ACHIEVED', goal='NOT_ACHIEVED')

    def model(prompt, **kwargs):
        assert kwargs['role'] == 'evaluate'
        case.calls.append(prompt)
        return (case.review + '\nSEVERITY: 2\nDEFECTS: ' + json.dumps([
            {'criterion_id': 'C1', 'evidence': 'PDF 파일 확인이 빠져 있습니다.',
             'repair': 'PDF 생성 및 확인'}], ensure_ascii=False)
            + '\nGOAL_OUTCOME: ' + json.dumps({
                'status': case.goal, 'reason': '보존된 파일 검사 결과',
                'evidence': ['CSV 파일 영수증'],
                'remaining': ['PDF 생성 및 확인'] if case.goal == 'NOT_ACHIEVED' else [],
            }, ensure_ascii=False))

    monkeypatch.setattr('consciousness_agent.system_ai_call', model)
    case.runner = _Runner([])
    case.runner._evaluate_achievement = cognitive_eval.CognitiveEvalMixin._evaluate_achievement.__get__(case.runner)
    case.draft = 'CSV와 PDF를 모두 저장했습니다.\n[CSV](outputs/report.csv)'

    def run(rounds=1):
        return _drain(case.runner._run_goal_evaluation_stream(
            'CSV와 PDF 저장', 'CSV와 PDF 파일이 존재', case.draft, [], max_rounds=rounds))

    case.run = run
    try:
        yield case
    finally:
        tc.restore(previous)


@pytest.mark.parametrize('goal', ['NOT_ACHIEVED', 'UNKNOWN', 'ACHIEVED'])
def test_rejected_final_preserves_draft_and_separates_review_from_goal(evaluation_case, goal):
    from thread_context import get_goal_eval_outcome
    from supervision_store import digest
    case = evaluation_case
    case.goal = goal
    events, result = case.run()
    assert result == case.draft
    assert len(case.calls) == 1 and case.runner.ai.stream_calls == 0
    assert not any(e['type'] == 'final' for e in events)
    outcome = get_goal_eval_outcome()
    assert outcome['review_status'] == 'REWORK' and outcome['goal_status'] == goal
    assert outcome['response_hash'] == digest(result)
    receipt = json.loads((case.store.directory / 'review_status.json').read_text())
    assert receipt['response']['hash'] == digest(result)
    assert receipt['learning'] == 'components_only'
    assert case.store.read_evidence(receipt['response']['id'])['text'] == result


@pytest.mark.parametrize('goal', ['ACHIEVED', 'NOT_ACHIEVED', 'UNKNOWN'])
def test_approved_response_is_preserved_even_when_reporting_incomplete_goal(evaluation_case, goal):
    case = evaluation_case
    case.review, case.goal = 'ACHIEVED', goal
    case.draft = 'CSV는 저장했고 PDF는 만들지 못했습니다.'
    _, result = case.run()
    assert result == case.draft
    assert len(case.calls) == 1 and case.runner.ai.stream_calls == 0


def test_retry_failure_does_not_return_the_rejected_completion_claim(evaluation_case, monkeypatch):
    case = evaluation_case

    def fail(**kwargs):
        raise RuntimeError('executor disconnected')

    monkeypatch.setattr(case.runner.ai, 'process_message_stream', fail)
    _, result = case.run(rounds=2)
    assert result == case.draft
    from thread_context import get_goal_eval_outcome
    assert get_goal_eval_outcome()['review_status'] == 'REWORK'
    assert len(case.calls) == 1


def test_last_retry_preserves_latest_draft_without_publishing_it(evaluation_case):
    case = evaluation_case
    _, result = case.run(rounds=2)
    assert result == '보완된 응답'
    assert len(case.calls) == 2 and case.runner.ai.stream_calls == 1, __import__("thread_context").get_goal_eval_outcome()
    receipt = json.loads((case.store.directory / 'review_status.json').read_text())
    assert case.store.read_evidence(receipt['response']['id'])['text'] == '보완된 응답'


def test_evidence_write_failure_still_reports_rejected_state(evaluation_case, monkeypatch):
    from thread_context import get_goal_eval_outcome
    from supervision_store import digest
    case = evaluation_case

    def fail(value):
        raise OSError('disk unavailable')

    monkeypatch.setattr(case.store, 'evidence', fail)
    _, result = case.run()
    assert result == case.draft
    assert get_goal_eval_outcome()['storage_error'] == 'disk unavailable'
    assert get_goal_eval_outcome()['response_hash'] == digest(result)


def test_failed_evaluation_reaches_pipeline_final_as_incomplete(tmp_path, monkeypatch, evaluation_case):
    from test_episode3388_repairs import Runner
    from thread_context import get_goal_eval_outcome
    case = evaluation_case
    monkeypatch.setattr('conscious_supervisor.open_supervisor', lambda *a, **kw: None)
    monkeypatch.setattr('world_pulse._load_config', lambda: {'goal_eval': {'max_rounds': 1}})
    monkeypatch.setattr('consciousness_agent.get_world_pulse_text', lambda: '')
    monkeypatch.setattr('consciousness_agent.get_consciousness_agent', lambda: SimpleNamespace(
        is_ready=True, process=lambda **kw: {'task_framing': kw['user_message'],
                                            'achievement_criteria': 'CSV와 PDF 파일이 존재',
                                            'independent_review': True}))
    monkeypatch.setattr('framing_inheritance._oneshot', lambda *a, **kw: pytest.fail('예상하지 않은 모델 호출'))
    monkeypatch.setattr('capability_guard.judge_once', lambda *a, **kw: pytest.fail('예상하지 않은 모델 호출'))

    def execute(message_content, history=None, **kwargs):
        yield {'type': 'final', 'content': case.draft}

    runner = Runner(tmp_path, execute)
    events = list(runner.cognitive_stream('CSV와 PDF 저장', []))
    finals = [e['content'] for e in events if e['type'] == 'final']
    assert finals == [case.draft]
    assert next(e for e in events if e['type'] == 'final')['evaluation']['review_status'] == 'REWORK'
    assert not any(e['type'] == 'error' for e in events)
    assert get_goal_eval_outcome()['goal_status'] == 'NOT_ACHIEVED'
    assert len(case.calls) == 1


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))


def test_repeated_repair_preserves_all_original_criteria(evaluation_case, monkeypatch):
    case = evaluation_case
    def forbidden(*a, **kw):
        pytest.fail('검수 횟수나 심각도로 사용자 기준을 교체하면 안 됩니다')
    monkeypatch.setattr('reframe._revise', forbidden)
    case.run(rounds=3)
    assert len(case.calls) == 3
    import json
    contracts = [json.loads(p.context) for p in case.calls]
    assert all(c == contracts[0] for c in contracts)


def test_standalone_recovers_omitted_image_without_repeating_execution(evaluation_case, tmp_path, monkeypatch):
    from PIL import Image
    from test_goal_eval_streaming import _drain
    case = evaluation_case
    calls = []
    for i in range(4):
        path = tmp_path / f'screen-{i}.png'
        Image.new('RGB', (12, 12), (i * 60, 0, 0)).save(path)
        calls.append({'name': 'view_image', 'input': {'path': str(path)}, 'result': 'shown'})
    evaluations = []
    wanted = []
    def model(prompt, **kwargs):
        images = kwargs['images']
        evaluations.append(images)
        if len(evaluations) == 1:
            supplied = {i['base64'] for i in images}
            ref = next(r for r in prompt.references if r.get('unit') == 'images' and
                       json.loads(case.store.read_evidence(r['evidence_id'])['text'])['base64'] not in supplied)
            wanted.append(json.loads(case.store.read_evidence(ref['evidence_id'])['text'])['base64'])
            return 'UNKNOWN\nUNKNOWN_REASON: evidence\nEVIDENCE_REQUESTS: ' + json.dumps([{
                'criterion_id': 'C1', 'evidence_id': ref['evidence_id'], 'revision': ref['revision'],
                'start': 0, 'end': 1}])
        assert wanted[0] in {i['base64'] for i in images}
        return 'ACHIEVED\nGOAL_OUTCOME: {"status":"ACHIEVED","reason":"원본 이미지 확인","evidence":["이미지"],"remaining":[]}'
    monkeypatch.setattr('consciousness_agent.system_ai_call', model)
    _, response = _drain(case.runner._run_goal_evaluation_stream(
        '첫 번째 화면 상태 확인', '첫 화면 상태를 정확히 보고', '화면 확인 결과', [],
        tool_calls=calls, max_rounds=2))
    assert response == '화면 확인 결과' and len(evaluations) == 2
    assert case.runner.ai.stream_calls == 0
    saved = json.loads((case.store.directory / 'review_status.json').read_text())
    assert saved['review_status'] == 'APPROVED' and saved['goal_status'] == 'ACHIEVED'
