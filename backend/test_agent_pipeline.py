"""도구 관측·실행자 종료·선택된 검수의 책임 경계."""
from types import SimpleNamespace as NS
import json

import boot_paths  # noqa: F401
import pytest
import execution_turn
from test_conscious_supervisor import supervisor  # noqa: F401


@pytest.fixture
def turn():
    binding = execution_turn.Binding(NS(), 'owner', 'task', context={}, conversation=None)
    token = execution_turn._current.set(binding)
    yield binding
    execution_turn._current.reset(token)


@pytest.mark.parametrize('route', ['EXECUTE', 'THINK'])
@pytest.mark.parametrize('case', ['recovered', 'unresolved', 'missing', 'partial', 'effect'])
def test_failure_history_does_not_reopen_or_replace_executor_answer(turn, monkeypatch, route, case):
    from agent_pipeline import CognitivePipelineMixin
    from cognitive_consciousness import CognitiveConsciousnessMixin
    from cognitive_eval import CognitiveEvalMixin
    from execution_situation import Situation, fingerprint
    from recovery_observation import configure
    from test_reflex_execution import AI
    from thread_context import get_goal_eval_outcome

    class Runner(CognitivePipelineMixin, CognitiveConsciousnessMixin, CognitiveEvalMixin):
        pass

    turn.situation = Situation('owner', 'task', lambda *a, **kw: None,
                               lambda value: {'id': fingerprint(value)})
    configure(turn.situation)
    initial = [{'type': 'tool_start', 'id': 'attempt', 'name': 'shell', 'input': {'command': 'lookup'}}]
    if case != 'missing':
        result = ({'success': True, 'operation_outcomes': [{'id': 'one', 'status': 'failed'}]}
                  if case == 'partial' else 'query failed')
        initial.append({'type': 'tool_result', 'id': 'attempt', 'result': result,
                        'is_error': case != 'partial'})
    if case in {'recovered', 'effect'}:
        initial.extend([
            {'type': 'tool_start', 'id': 'alternative',
             'name': 'read' if case == 'recovered' else 'write', 'input': {}},
            {'type': 'tool_result', 'id': 'alternative',
             'result': 'source confirms answer' if case == 'recovered' else {'receipt': 'saved'}},
        ])
    answer = ('자료를 확인했습니다. 계획과 재규정 경로가 이미 있습니다.' if case == 'recovered'
              else '확인된 결과와 남은 제약을 보고합니다.')
    initial.extend([{'type': 'text', 'content': answer}, {'type': 'final', 'content': answer}])
    runner = Runner()
    runner.config = {'name': 'worker'}
    # 이전 구현은 오류 이력 때문에 두 번째 호출을 열고 이 미완성 답으로 교체했다.
    runner.ai = AI([initial, [{'type': 'final', 'content': '是的。 Wait Korean fix.'}]])
    runner._associate = lambda *a, **kw: None
    runner._decide_request_type = lambda *a, **kw: (route, None)
    runner._run_consciousness_or_reuse = lambda *a, **kw: {
        'task_framing': '자료 확인', 'achievement_criteria': '근거에 맞게 설명', 'independent_review': False}
    runner._apply_consciousness_to_history = lambda history, co: history
    runner._refresh_execution_prompt = lambda message, *a, **kw: message
    runner._after_response_async = lambda *a, **kw: None
    monkeypatch.setattr('supervision_bus.current', lambda: None)
    monkeypatch.setattr('unified_distill.capture_model', lambda *a: None)
    monkeypatch.setattr('framing_inheritance.remember', lambda *a, **kw: None)
    monkeypatch.setattr('consciousness_agent.system_ai_call',
                        lambda *a, **kw: pytest.fail('선택하지 않은 평가 호출'))

    events = list(runner._cognitive_stream_body('현재 구조를 확인해서 설명해줘', []))
    assert len(runner.ai.calls) == 1
    assert [e['content'] for e in events if e['type'] == 'final'] == [answer]
    assert [e['content'] for e in events if e['type'] == 'text'] == [answer]
    assert not turn.followup_reason
    assert get_goal_eval_outcome()['review_status'] == 'NOT_RUN'
    # 실패 사실은 성공으로 지우지 않는다. 미반환 호출은 관측된 running으로 남긴다.
    if case == 'missing':
        assert any(row['latest']['facet'] == 'execution' and
                   row['latest']['value']['state'] == 'running'
                   for row in turn.situation.snapshot()['observations'])
    else:
        incidents = turn.situation.recovery_view()
        assert incidents and all(row['resolution'] != 'verified' for row in incidents)


def test_pipeline_reviews_recovered_task_without_second_execution(turn, supervisor, monkeypatch):
    from agent_pipeline import CognitivePipelineMixin
    from cognitive_consciousness import CognitiveConsciousnessMixin
    from cognitive_eval import CognitiveEvalMixin
    from test_reflex_execution import AI
    from thread_context import get_goal_eval_outcome

    class Runner(CognitivePipelineMixin, CognitiveConsciousnessMixin, CognitiveEvalMixin):
        pass

    runner = Runner()
    runner.config = {'name': 'worker'}
    runner.ai = AI([[{'type': 'tool_start', 'id': 'check1', 'name': 'check', 'input': {}},
                     {'type': 'tool_result', 'id': 'check1', 'result': 'focus missing', 'is_error': True},
                     {'type': 'tool_start', 'id': 'check2', 'name': 'check', 'input': {}},
                     {'type': 'tool_result', 'id': 'check2', 'result': 'focus restored; 30 checks passed'},
                     {'type': 'final', 'content': '초점 복구와 검사 완료'}]])
    runner._associate = lambda *a, **kw: None
    runner._decide_request_type = lambda *a, **kw: ('THINK', None)
    runner._run_consciousness_or_reuse = lambda *a, **kw: {
        'task_framing': '초점 복구', 'achievement_criteria': '초점 복구와 실제 검사', 'independent_review': True}
    runner._apply_consciousness_to_history = lambda history, co: history
    runner._refresh_execution_prompt = lambda message, *a, **kw: message
    runner._after_response_async = lambda *a, **kw: None
    supervisor.runner = runner
    monkeypatch.setattr('supervision_bus.current', lambda: supervisor)
    monkeypatch.setattr('unified_distill.capture_model', lambda *a: None)
    monkeypatch.setattr('framing_inheritance.remember', lambda *a, **kw: None)
    evaluations = []

    def evaluate(prompt, **kw):
        evaluations.append(prompt)
        assert 'recovery_incidents' in prompt and 'focus missing' in prompt
        assert 'focus restored; 30 checks passed' in prompt
        return 'ACHIEVED'

    monkeypatch.setattr('consciousness_agent.system_ai_call', evaluate)
    events = list(runner._cognitive_stream_body('초점을 복구하고 검사해줘', []))
    assert len(runner.ai.calls) == len(evaluations) == 1
    assert get_goal_eval_outcome()['status'] == 'ACHIEVED'
    assert [e['content'] for e in events if e['type'] == 'final'] == ['초점 복구와 검사 완료']
    assert supervisor.recovery.view() and not turn.followup_reason


@pytest.mark.parametrize('origin', ['review', 'executor'])
def test_reframed_request_reaches_real_pipeline_evaluation_and_next_turn(turn, supervisor, monkeypatch, origin):
    from agent_pipeline import CognitivePipelineMixin
    from cognitive_consciousness import CognitiveConsciousnessMixin
    from cognitive_eval import CognitiveEvalMixin
    from test_reflex_execution import AI
    from reframe import current

    original = '한국 청년 채용을 조사해줘'
    initial = {'task_framing': '전체 감소 원인을 조사하라', 'achievement_criteria': '초기 기준',
               'criteria': [{'text': '초기 기준'}], 'independent_review': True}
    update = {'task_framing': '직종별 증가와 감소를 구분해 비교하라',
              'achievement_criteria': '직종별 변화와 한계', 'criteria': [{'text': '직종별 변화와 한계'}]}
    class Runner(CognitivePipelineMixin, CognitiveConsciousnessMixin, CognitiveEvalMixin):
        pass
    class ExecutionAI(AI):
        def process_message_stream(self, **kwargs):
            self.calls.append(kwargs)
            message = kwargs['message_content']
            assert message.index(initial['task_framing']) < message.index(original)
            channel = current(supervisor.owner, supervisor.task)
            assert channel is supervisor._framing_channel
            if origin == 'review':
                supervisor.review('milestone', paused=True)
                notice = supervisor.boundary()['instruction']
            else:
                notice = supervisor.reframe({'broken_assumption': '전체 감소라는 가정', 'evidence': '직종별 원자료'})
            assert update['task_framing'] in notice
            yield {'type': 'final', 'content': '직종별 변화와 자료 한계를 정리했습니다.'}
    runner = Runner()
    runner.config = {'name': 'worker'}
    runner.ai = ExecutionAI([])
    runner._associate = lambda *a, **kw: None
    runner._decide_request_type = lambda *a, **kw: ('THINK', None)
    runner._run_consciousness_or_reuse = lambda *a, **kw: initial
    runner._run_consciousness = lambda *a, **kw: update
    runner._load_role = lambda: 'role'
    runner._build_system_prompt_split = lambda *a, **kw: ('system', 'execution context')
    runner._after_response_async = lambda *a, **kw: None
    supervisor.runner = runner
    monkeypatch.setattr('supervision_bus.current', lambda: supervisor)
    monkeypatch.setattr('unified_distill.capture_model', lambda *a: None)
    remembered, evaluated, reviews = [], [], []
    monkeypatch.setattr('framing_inheritance.remember', lambda r, message, framing, **kw: remembered.append(framing))
    monkeypatch.setattr('supervisor_runtime.invoke', lambda *a, **kw:
        reviews.append(kw['phase']) or json.dumps({'status': 'REWORK', 'reason': '관측에 맞게 문제 변경', **update}))
    def evaluate(prompt, **kwargs):
        evaluated.append(prompt)
        assert update['task_framing'] in prompt and update['achievement_criteria'] in prompt
        assert '초기 기준' not in prompt
        return 'ACHIEVED'
    monkeypatch.setattr('consciousness_agent.system_ai_call', evaluate)
    events = list(runner._cognitive_stream_body(original, []))
    assert len(runner.ai.calls) == len(evaluated) == len(remembered) == 1
    assert remembered[0]['task_framing'] == update['task_framing']
    assert remembered[0]['criteria'] == update['criteria']
    assert remembered[0] is supervisor.framing
    assert reviews == (['review'] if origin == 'review' else [])
    assert [e['content'] for e in events if e['type'] == 'final'] == ['직종별 변화와 자료 한계를 정리했습니다.']



def test_repair_executor_recovers_in_same_stream_with_grant_and_owner_lock(tmp_path, monkeypatch):
    from agent_pipeline import CognitivePipelineMixin
    from cognitive_consciousness import CognitiveConsciousnessMixin
    from cognitive_eval import CognitiveEvalMixin
    from test_reflex_execution import AI
    from thread_context import actor_context
    from repair_context import active
    from repair_continuation import key
    from restart_protocol import OwnerLock
    monkeypatch.setenv('INDIEBIZ_BASE_PATH', str(tmp_path))
    monkeypatch.setattr('supervision_bus.current', lambda: None)
    monkeypatch.setattr('system_ai_core._switch_to_role', lambda *a: None)
    monkeypatch.setattr('unified_distill.capture_model', lambda *a: None)
    monkeypatch.setattr('framing_inheritance.remember', lambda *a, **kw: None)
    def adopt(guard, runner, message, response, *args, **kwargs):
        yield from ()
        return response
    monkeypatch.setattr('capability_guard.adopt_response', adopt)
    class Runner(CognitivePipelineMixin, CognitiveConsciousnessMixin, CognitiveEvalMixin):
        pass
    class RepairAI(AI):
        def process_message_stream(self, **kwargs):
            assert active(), '후속 실행이 원래 수리 권한을 잃었다'
            lock = OwnerLock(tmp_path / 'data/system_ai_state/repair_sessions' / ('owner-' + key('recovery') + '.lock'))
            assert not lock.acquire(), '같은 사본의 실행자 잠금이 없다'
            yield from super().process_message_stream(**kwargs)
    r = Runner(); r.config = {'name': 'system_ai', '_is_system_ai': True}
    r.ai = RepairAI([
        [{'type': 'tool_start', 'name': 'search', 'input': {'query': 'x'}},
         {'type': 'tool_result', 'result': {'success': False, 'error': 'parser'}},
         {'type': 'text', 'content': '다른 방법으로 확인하겠습니다.'},
         {'type': 'tool_start', 'name': 'alternative'},
         {'type': 'tool_result', 'result': {'items': ['recovered']}},
         {'type': 'final', 'content': '요청 결과 확인'}]])
    r._associate = lambda *a, **kw: None
    r._decide_request_type = lambda *a, **kw: ('REPAIR', None)
    r._run_consciousness_or_reuse = lambda *a, **kw: {'needs_repair': True, 'task_framing': '결함 해결'}
    r._load_role = lambda: 'role'
    r._build_system_ai_prompt_split = lambda *a, **kw: ('System structure + IBL + rules', '')
    r._apply_consciousness_to_history = lambda history, co: history
    r._after_response_async = lambda *a, **kw: None
    with actor_context(agent_id='system_ai', task_id='recovery', origin='user'), r.turn_ai_scope():
        events = list(r._cognitive_stream_body('문제를 고치고 결과를 내줘', []))
        assert len(r.ai.calls) == 1
    assert [e['content'] for e in events if e['type'] == 'final'] == ['요청 결과 확인']
    assert not any(e.get('content') == '첫 시도 실패' for e in events)
    assert not active()

