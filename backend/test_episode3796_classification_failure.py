"""ep3796: API 오류/빈 응답이 THINK 판단으로 둔갑하지 않는다. 외부 호출 없는 재현."""
from types import SimpleNamespace as NS

import boot_paths  # noqa: F401
import httpx
import pytest

from cognitive_consciousness import CognitiveConsciousnessMixin
from providers.deepseek import DeepSeekProvider
from providers.openai import OpenAIProvider


def _provider(cls=DeepSeekProvider):
    provider = cls(api_key="test", model="test", system_prompt="", tools=[])
    provider._client = object()
    return provider


@pytest.mark.parametrize("cls", [OpenAIProvider, DeepSeekProvider])
@pytest.mark.parametrize("partial", ["", "THINK"])
def test_sync_error_rejects_even_valid_looking_partial_answer(cls, partial, monkeypatch):
    provider = _provider(cls)
    events = ([{"type": "text", "content": partial}] if partial else [])
    events.append({"type": "error", "content": "connection interrupted"})
    monkeypatch.setattr(provider, "process_message_stream", lambda *a: iter(events))
    with pytest.raises(RuntimeError, match="connection interrupted"):
        provider.process_message("분류")
    assert provider.last_failure_kind == "provider_error"


@pytest.mark.parametrize("events", [[], [{"type": "final", "content": " \n\t"}]])
def test_sync_empty_response_is_failure(events, monkeypatch):
    provider = _provider()
    monkeypatch.setattr(provider, "process_message_stream", lambda *a: iter(events))
    with pytest.raises(RuntimeError, match="비어"):
        provider.process_message("분류")
    assert provider.last_failure_kind == "empty_response"


def test_uninitialized_provider_does_not_return_error_as_answer():
    provider = DeepSeekProvider(api_key="test", model="test", system_prompt="", tools=[])
    with pytest.raises(RuntimeError, match="초기화"):
        provider.process_message("분류")
    assert provider.last_failure_kind == "unavailable"


def test_success_resets_previous_failure_and_keeps_final_response(monkeypatch):
    provider = _provider()
    provider.last_failure_kind = "provider_error"
    monkeypatch.setattr(provider, "process_message_stream", lambda *a: iter([
        {"type": "text", "content": "TH"},
        {"type": "text", "content": "INK"},
        {"type": "final", "content": "THINK"},
    ]))
    assert provider.process_message("분류") == "THINK"
    assert provider.last_failure_kind is None


@pytest.mark.parametrize("answer, expected", [
    (None, "EXECUTE"), ("", "EXECUTE"), (" \n", "EXECUTE"),
    ("API error: THINK unavailable", "EXECUTE"),
    ("REPAIR failed", "EXECUTE"), ("TH", "EXECUTE"),
    ("THINK or EXECUTE", "EXECUTE"), (42, "EXECUTE"),
    ("EXECUTE", "EXECUTE"), (" think\n", "THINK"),
    ("REPAIR", "REPAIR"), ("CONTEXT_UPDATE", "CONTEXT_UPDATE"),
    ("SESSION_RESET", "SESSION_RESET"), ("RESET", "SESSION_RESET"),
])
def test_only_valid_classification_tokens_are_decisions(answer, expected, monkeypatch):
    import consciousness_agent as ca
    monkeypatch.setattr(ca, "get_unconscious_prompt", lambda: "classify")
    monkeypatch.setattr(ca, "oneshot_ai_call", lambda *a, **k: answer)
    runner = CognitiveConsciousnessMixin()
    messages = []
    runner._log = messages.append
    assert runner._classify_request("AI 동향 보고서 써줘.") == expected
    valid = isinstance(answer, str) and answer.strip().upper() in {
        "EXECUTE", "THINK", "REPAIR", "CONTEXT_UPDATE", "SESSION_RESET", "RESET"}
    assert bool(messages) is not valid
    if messages:
        assert "분류 실패" in messages[0]


class _InterruptedStream:
    def __init__(self, partial=False):
        self.partial = partial
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if self.partial:
            yield NS(choices=[NS(delta=NS(content="THINK", tool_calls=None,
                                         reasoning_content=None),
                                 finish_reason=None)], usage=None)
        raise httpx.RemoteProtocolError("incomplete chunked read")


@pytest.mark.parametrize("partial", [False, True])
def test_episode_path_stream_error_to_oneshot_to_classifier(partial, monkeypatch):
    """실제 SDK 프로바이더·원샷·분류기 연결. 응답 도중 끊겨도 부분 THINK는 폐기한다."""
    import consciousness_agent as ca
    provider = _provider()
    stream = _InterruptedStream(partial)
    provider._client = NS(chat=NS(completions=stream))
    monkeypatch.setattr(ca, "_resolve_oneshot_provider", lambda role: provider)
    monkeypatch.setattr(ca, "get_unconscious_prompt", lambda: "classify")
    runner = CognitiveConsciousnessMixin()
    messages = []
    runner._log = messages.append

    assert runner._classify_request("AI 동향 보고서 써줘.") == "EXECUTE"
    assert ca.last_oneshot_failure() == "provider_error"
    assert stream.calls == 1
    assert any("분류 실패" in message for message in messages)
    # oneshot_view는 호출별 상태를 격리한다.
    assert provider.last_failure_kind is None


def test_streaming_consumer_still_receives_error_event():
    provider = _provider()
    provider._client = NS(chat=NS(completions=_InterruptedStream()))
    events = list(provider.process_message_stream("분류"))
    assert any(e["type"] == "error" and "incomplete chunked read" in e["content"]
               for e in events)
    assert not any(e["type"] == "final" for e in events)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
