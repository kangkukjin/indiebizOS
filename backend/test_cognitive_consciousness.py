"""요청 분류와 해마 회상은 분리한다. 고점수도 분류·기억 주입을 우회하지 않는다."""
import boot_paths  # noqa: F401
from types import SimpleNamespace

import pytest

from cognitive_consciousness import CognitiveConsciousnessMixin
from agent_pipeline import CognitivePipelineMixin


@pytest.mark.parametrize("score", [0.0, 0.85, 0.99, 1.0])
@pytest.mark.parametrize("decision", ["EXECUTE", "THINK", "SESSION_RESET"])
def test_high_recall_keeps_classifier_decision(monkeypatch, score, decision):
    runner = CognitiveConsciousnessMixin()
    calls = []
    monkeypatch.setattr("model_resolver.consciousness_enabled", lambda: True)
    runner._classify_request = lambda message: calls.append(message) or decision
    assert runner._decide_request_type("티비꺼줘", score, "return [self:time]{}") == (decision, None)
    assert len(calls) == 1 and "티비꺼줘" in calls[0]


@pytest.mark.parametrize("message,decision", [("#think 확인해", "THINK"), ("#execute 확인해", "EXECUTE"),
                                             ("#repair 고쳐", "REPAIR")])
def test_explicit_route_remains_authoritative(monkeypatch, message, decision):
    runner = CognitiveConsciousnessMixin()
    runner._classify_request = lambda _: pytest.fail("명시 태그는 분류를 우회한다")
    assert runner._decide_request_type(message, 1.0, "return [self:time]{}") == (decision, None)


def test_consciousness_off_keeps_ordinary_execute(monkeypatch):
    runner = CognitiveConsciousnessMixin()
    monkeypatch.setattr("model_resolver.consciousness_enabled", lambda: False)
    runner._classify_request = lambda _: pytest.fail("의식 OFF는 분류를 우회한다")
    assert runner._decide_request_type("티비꺼줘", 1.0, "return [self:time]{}") == ("EXECUTE", None)


@pytest.mark.parametrize("system", [False, True])
def test_execution_prompt_preserves_recalled_memory_and_provider(system):
    memory = '<execution_memory>검증된 TV 끄기 스크립트</execution_memory>'
    runner = CognitivePipelineMixin()
    runner.config = {"_is_system_ai": system}
    provider = SimpleNamespace(system_prompt="old")
    runner.ai = SimpleNamespace(system_prompt="old", _provider=provider)
    runner._load_role = lambda: "역할"
    seen = []
    def build(role, consciousness, recalled, **kwargs):
        seen.append(recalled)
        return "기본 규칙", recalled
    runner._build_system_ai_prompt_split = build
    runner._build_system_prompt_split = build
    message = runner._refresh_execution_prompt("티비꺼줘", execution_memory=memory)
    assert seen == [memory] and message.count(memory) == 1
    assert runner.ai._provider is provider
    assert provider.system_prompt == "기본 규칙"
    assert "reflex_hint" not in message and "Reflex 매칭" not in message


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
