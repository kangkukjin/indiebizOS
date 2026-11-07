"""계획 계약의 한 번 정정과 HTTP의 명시적 실패 전달."""
import json
import sqlite3
from types import SimpleNamespace
import pytest
import boot_paths  # noqa: F401
import consciousness_agent as ca

QUESTION = "요청의 의미를 확인해 주세요."
GOOD = {"task_framing": "요청의 의미를 확인한다", "criteria": [{"text": "의미를 설명한다"}]}
BAD = {"task_framing": "", "achievement_criteria": ""}


def validate(value):
    if not isinstance(value, dict) or not value.get("task_framing"):
        raise ValueError("문제 규정이 필요합니다")


@pytest.fixture
def agent(monkeypatch):
    agent = ca.ConsciousnessAgent.__new__(ca.ConsciousnessAgent)
    agent._provider = SimpleNamespace(is_ready=True)
    agent._prompt = agent._supervisor_prompt = "계획 계약"
    agent._prompt_path = None
    monkeypatch.setattr(ca, "get_consciousness_agent", lambda: agent)
    monkeypatch.setattr(ca, "get_world_pulse_text", lambda: "")
    original = agent.process
    monkeypatch.setattr(agent, "process", lambda *a, **kw: original(*a, **{**kw, "validate_framing": validate}))
    return agent


def replies(monkeypatch, values):
    pending, calls = iter(values), []
    def invoke(prompt, *args, **kwargs):
        calls.append(prompt)
        value = next(pending)
        if isinstance(value, Exception):
            raise value
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    monkeypatch.setattr(ca, "call_oneshot_provider", lambda provider, prompt, **kw: invoke(prompt))
    return calls, SimpleNamespace(plan=invoke)


@pytest.mark.parametrize("supervised", [False, True])
def test_contract_correction_is_bounded(agent, monkeypatch, supervised):
    calls, supervisor = replies(monkeypatch, [BAD, GOOD])
    assert agent.process(QUESTION, [], "", supervisor=supervisor if supervised else None) == GOOD
    assert len(calls) == 2 and "문제 규정이 필요합니다" in calls[1]


def test_valid_plan_needs_only_one_call(agent, monkeypatch):
    calls, supervisor = replies(monkeypatch, [GOOD])
    assert agent.process(QUESTION, [], "", supervisor=supervisor) == GOOD
    assert len(calls) == 1


def test_partial_plan_parser_is_explicit_and_preserves_invalid_overrides(agent):
    raw = json.dumps({'research_plan': '# plan', 'criteria': None})
    assert agent._parse_response(raw) is None
    assert agent._parse_response(raw, partial=True) == {'criteria': None}
    assert agent._parse_response('[]', partial=True) is None


@pytest.mark.parametrize("key", ["capability_focus", "ibl_focus"])
@pytest.mark.parametrize("retired", [["self:read"], "bad shape", 7, {"nested": True}])
def test_current_projection_preserves_framing_without_retry_for_retired_field(agent, monkeypatch, key, retired):
    from copy import deepcopy
    raw = {**GOOD, key: {"hint": "자료의 기간을 비교", "highlight_actions": retired},
           "criteria": [{"text": "같은 기간 비교", "user_quote": "기간 비교", "fallback": ""}],
           "_inherited_from": {"episode_id": 1}}
    original = deepcopy(raw)
    calls, supervisor = replies(monkeypatch, [raw])
    result = agent.process(QUESTION, [], "", supervisor=supervisor)
    assert result == {**{k: v for k, v in raw.items() if k != key},
                      "capability_focus": {"hint": "자료의 기간을 비교"}}
    assert raw == original and len(calls) == 1
    assert ca.project_framing(result) == result


@pytest.mark.parametrize("focus", [[], "", False, {"hint": []}, {"hint": 1}])
def test_current_hint_types_still_use_correction_boundary(agent, monkeypatch, focus):
    calls, supervisor = replies(monkeypatch, [{**GOOD, "capability_focus": focus}, GOOD])
    assert agent.process(QUESTION, [], "", supervisor=supervisor) == GOOD
    assert len(calls) == 2 and 'validation_error' in calls[-1]


@pytest.mark.parametrize("second", [BAD, '{"task_framing":', '', 'null', RuntimeError("연결 실패")])
def test_second_invalid_plan_stops(agent, monkeypatch, second):
    calls, supervisor = replies(monkeypatch, [BAD, second])
    with pytest.raises(ca.FramingContractError, match="자동 정정도 실패"):
        agent.process(QUESTION, [], "", supervisor=supervisor)
    assert len(calls) == 2


from test_episode3388_repairs import Runner, isolated  # noqa: E402, F401


@pytest.mark.parametrize("corrected", [GOOD, BAD])
def test_http_plan_failure_is_visible(tmp_path, monkeypatch, isolated, agent, corrected):
    import api_agents
    import thread_context as tc
    from execution_turn import current
    monkeypatch.setattr(api_agents, "project_manager", SimpleNamespace(get_project_path=lambda _: tmp_path))
    monkeypatch.setattr(ca, "system_ai_call", lambda *a, **kw: "ACHIEVED")
    calls, supervisor = replies(monkeypatch, [BAD, corrected])
    monkeypatch.setattr("supervisor_runtime.invoke", lambda owner, prompt, **kw: supervisor.plan(prompt))
    executed = []
    def stream(**kw):
        executed.append(True)
        yield {"type": "final", "content": "요청의 의미를 설명합니다."}
    runner = Runner(tmp_path, stream)
    if corrected == GOOD:
        assert api_agents._run_agent_command("p", "agent_test", runner, QUESTION) == "요청의 의미를 설명합니다."
    else:
        with pytest.raises(ca.FramingContractError):
            api_agents._run_agent_command("p", "agent_test", runner, QUESTION)
        assert not executed
    assert len(calls) == 2
    with sqlite3.connect(tmp_path / "conversations.db") as conn:
        messages = conn.execute("SELECT content FROM messages ORDER BY id").fetchall()
        status = conn.execute("SELECT status FROM tasks").fetchone()[0]
    assert len(messages) == 2 and messages[0][0] == QUESTION
    assert status == ("completed" if executed else "failed")
    assert ("의미를 설명" if executed else "자동 정정도 실패") in messages[1][0]
    assert tc.get_current_task_id() is None and current() is None


if __name__ == "__main__":
    import pytest
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))


def test_saved_framing_projects_once_without_promoting_added_conditions():
    from copy import deepcopy
    from supervisor_handoff import criteria_contract
    from prompt_builder import compile_user_command
    old = {'task_framing': '금액을 비교한다', 'achievement_criteria': '옛 요약',
           'expert_choice': '기간을 재확인한다', 'imagined_ibl': '[self:read]{}',
           'criteria': [{'text': '단위와 집계기간이 모두 같아야 비교한다', 'user_quote': '동등한 단위'}]}
    saved = deepcopy(old)
    out = ca.project_framing(old)
    assert out == ca.project_framing(out) and old == saved
    contract = criteria_contract('동등한 단위로 비교해줘', out)
    assert contract['criteria'][0]['source'] == 'consciousness'
    assert contract['user_goal'] == '동등한 단위로 비교해줘'
    command = compile_user_command(contract['user_goal'], out)
    assert command.count(old['criteria'][0]['text']) == 1
    assert '옛 요약' not in command and '기간을 재확인한다' not in command


def test_revision_accepts_single_criteria_update_and_can_clear_it():
    from reframe import merge_revision
    prior = {'task_framing': '금액 비교', 'achievement_criteria': '옛 요약',
             'criteria': [{'text': '집계기간 확인'}]}
    current = merge_revision(prior, {'criteria': [{'text': '금액 차이 제시'}]})
    assert current['criteria'] == [{'text': '금액 차이 제시'}]
    assert 'achievement_criteria' not in current
    assert merge_revision(current, {'criteria': []})['criteria'] == []
