"""지식 지도 후속 질문: 의식 출력 검증→정정→실제 과제 원장·HTTP 응답 회귀."""
import json
import sqlite3
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
import consciousness_agent as ca
import pursuit_bind as pb
from pursuit_ledger import PursuitLedger


QUESTION = '나는 지식의 지도를 만들어서 그걸 주입하고 싶어. 메타 지식을 트리로 조직하려는 거야.'
BROKEN = {'scope': 'pursuit', 'title': '', 'goal_criteria': '',
          'task_framing': '구상의 의미를 확인하는 후속 논의다. 이번 턴을 시스템 구현으로 확대하지 않는다.',
          'history_summary': '세계의 도구 지도와 지식 지도의 관계를 논의했다.',
          'achievement_criteria': '', 'criteria': [], 'assumptions': []}
TURN = {**BROKEN, 'scope': 'turn'}
NEW = {**BROKEN, 'title': '지식 지도 구축', 'goal_criteria': '메타 지식 트리를 구축하고 활용 예제로 검증한다.'}


@pytest.fixture
def agent(monkeypatch):
    result = ca.ConsciousnessAgent.__new__(ca.ConsciousnessAgent)
    result._provider = SimpleNamespace(is_ready=True)
    result._prompt = result._supervisor_prompt = '의식 출력 계약'
    result._prompt_path = None
    monkeypatch.setattr(ca, 'get_consciousness_agent', lambda: result)
    monkeypatch.setattr(ca, 'get_world_pulse_text', lambda: '')
    return result


@pytest.fixture
def binding(tmp_path, monkeypatch):
    b = pb.Binding(None, PursuitLedger(tmp_path / 'conversation.db', 'research'),
                   'research', 'turn', QUESTION, [])
    token = pb._current.set(b)
    monkeypatch.setattr('episode_logger.record_trajectory_event', lambda *a, **k: None)
    yield b
    pb._current.reset(token)


def replies(monkeypatch, outputs):
    pending = iter(outputs)
    calls = []

    def invoke(prompt, *args, **kwargs):
        calls.append(prompt)
        value = next(pending)
        if isinstance(value, Exception):
            raise value
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

    monkeypatch.setattr(ca, 'call_oneshot_provider', lambda provider, prompt, **kw: invoke(prompt))
    return calls, SimpleNamespace(plan=invoke)


def process(agent, supervisor=None):
    binding = pb.current()
    row = binding.row if binding else None
    return agent.process(QUESTION, [], '', supervisor=supervisor,
                         validate_framing=pb.validate_output,
                         pursuit_state={'bound': bool(row), 'id': row['id'] if row else None})


@pytest.mark.parametrize('supervised', [False, True])
@pytest.mark.parametrize('corrected', [TURN, NEW])
def test_bad_new_pursuit_is_corrected_before_sqlite(agent, binding, monkeypatch, supervised, corrected):
    calls, supervisor = replies(monkeypatch, [BROKEN, corrected])
    output = process(agent, supervisor if supervised else None)
    assert len(calls) == 2
    assert '"bound": false' in calls[0]
    assert 'title는 비울 수 없습니다' in calls[1]
    assert 'goal_criteria는 비울 수 없습니다' in calls[1]
    assert QUESTION in calls[1] and BROKEN['task_framing'] in calls[1]
    assert output == corrected and binding.ledger.list()['total'] == 0
    pb.accept_output(output)
    if corrected['scope'] == 'turn':
        assert binding.row is None and binding.ledger.list()['total'] == 0
    else:
        assert binding.row['title'] == corrected['title']
        assert binding.row['goal_criteria'] == corrected['goal_criteria']
    assert pb.audit_binding(binding) == []


@pytest.mark.parametrize('output', [TURN, NEW])
def test_valid_output_has_no_extra_model_call(agent, binding, monkeypatch, output):
    calls, supervisor = replies(monkeypatch, [output])
    assert process(agent, supervisor) == output
    assert len(calls) == 1


def test_existing_pursuit_reuses_identity_without_creating(agent, binding, monkeypatch):
    row = binding.ledger.create(NEW['title'], NEW['goal_criteria'], 'origin')
    binding.bind(row)
    calls, supervisor = replies(monkeypatch, [BROKEN])
    out = process(agent, supervisor)
    pb.accept_output(out)
    assert len(calls) == 1 and '"bound": true' in calls[0] and row['id'] in calls[0]
    assert binding.row['id'] == row['id']
    assert binding.row['goal_criteria'] == NEW['goal_criteria']
    assert binding.ledger.list()['total'] == 1


@pytest.mark.parametrize('patch', [{'title': '   '}, {'title': None}, {'title': 'x' * 61},
                                 {'goal_criteria': []}, {'goal_criteria': 'x' * 1501}])
def test_invalid_replacement_does_not_detach_existing_pursuit(binding, patch):
    row = binding.ledger.create(NEW['title'], NEW['goal_criteria'], 'origin')
    binding.bind(row)
    with pytest.raises(ValueError):
        pb.accept_output({**NEW, **patch, 'detach_pursuit': True})
    assert binding.row['id'] == row['id'] and binding.output == {}
    assert binding.ledger.turns(row['id'])[0]['state'] == 'running'


@pytest.mark.parametrize('second', [BROKEN, '{"task_framing":', '', 'null', RuntimeError('연결 실패')])
def test_second_invalid_output_fails_explicitly_without_writing(agent, binding, monkeypatch, second):
    calls, supervisor = replies(monkeypatch, [BROKEN, second])
    with pytest.raises(ca.FramingContractError, match='자동 정정도 실패'):
        process(agent, supervisor)
    assert len(calls) == 2 and binding.row is None and binding.output == {}
    assert binding.ledger.list()['total'] == 0
    assert pb.audit_binding(binding) == []


# 기존 HTTP 시험의 격리 DB·실제 인지 파이프라인을 함께 사용한다.
from test_episode3388_repairs import Runner, isolated  # noqa: E402, F401


@pytest.mark.parametrize('corrected', [TURN, BROKEN])
def test_http_question_reaches_reply_or_visible_failure(tmp_path, monkeypatch, isolated, agent, corrected):
    import api_agents
    import thread_context as tc
    ledger = PursuitLedger(tmp_path / 'conversations.db', 'agent_test')
    monkeypatch.setattr(pb, 'owner_for', lambda runner: (ledger, 'agent_test', tc.get_current_task_id()))
    monkeypatch.setattr(pb, 'ask_json', lambda *a, **kw: {'id': None})
    monkeypatch.setattr(api_agents, 'project_manager', SimpleNamespace(get_project_path=lambda _: tmp_path))
    calls, supervisor = replies(monkeypatch, [BROKEN, corrected])
    monkeypatch.setattr('supervisor_runtime.invoke', lambda owner, prompt, **kw: supervisor.plan(prompt))
    executed = []

    def stream(**kw):
        executed.append(True)
        yield {'type': 'final', 'content': '지식 지도 구상에 대한 답변입니다.'}

    runner = Runner(tmp_path, stream)
    if corrected['scope'] == 'turn':
        assert api_agents._run_agent_command('p', 'agent_test', runner, QUESTION) == '지식 지도 구상에 대한 답변입니다.'
        assert executed == [True]
    else:
        with pytest.raises(ca.FramingContractError):
            api_agents._run_agent_command('p', 'agent_test', runner, QUESTION)
        assert executed == []  # 잘못된 기준을 버린 일반 실행으로 폴백하지 않는다.
    assert len(calls) == 2 and ledger.list()['total'] == 0
    with sqlite3.connect(tmp_path / 'conversations.db') as conn:
        messages = conn.execute('SELECT content FROM messages ORDER BY id').fetchall()
        status = conn.execute('SELECT status FROM tasks').fetchone()[0]
    assert len(messages) == 2 and messages[0][0] == QUESTION
    assert status == ('completed' if executed else 'failed')
    assert ('지식 지도 구상' if executed else '자동 정정도 실패') in messages[1][0]
    assert tc.get_current_task_id() is None and pb.current() is None


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
