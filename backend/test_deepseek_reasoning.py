"""DeepSeek thinking+tools의 reasoning_content 보존 및 compaction 회귀.

실행: .venv/bin/python -m pytest backend/test_deepseek_reasoning.py
외부 API를 부르지 않고 실제 provider 메시지 조립 경로를 가짜 응답으로 검증한다.
"""
from types import SimpleNamespace as NS

import boot_paths  # noqa: F401

from providers.deepseek import DeepSeekProvider
from providers.deepseek_http import DeepSeekHTTPProvider


def _sdk_provider(cls=DeepSeekProvider):
    return cls(api_key="test", model="deepseek-v4-pro", system_prompt="system", tools=[])


class _FakeCompletions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            tool = NS(id="call_1", function=NS(name="demo", arguments="{}"))
            return iter([
                NS(choices=[NS(delta=NS(content=None, tool_calls=None,
                                        reasoning_content="private-reasoning"),
                              finish_reason=None)], usage=None),
                NS(choices=[NS(delta=NS(content=None, tool_calls=[tool],
                                        reasoning_content=None),
                              finish_reason=None)], usage=None),
                NS(choices=[NS(delta=NS(content=None, tool_calls=None,
                                        reasoning_content=None),
                              finish_reason="tool_calls")], usage=None),
            ])
        return iter([
            NS(choices=[NS(delta=NS(content="done", tool_calls=None,
                                    reasoning_content="final-reasoning"),
                          finish_reason="stop")], usage=None),
        ])


def test_sdk_tool_loop_replays_reasoning_content():
    provider = _sdk_provider()
    completions = _FakeCompletions()
    provider._client = NS(chat=NS(completions=completions))

    events = list(provider._agentic_loop(
        [{"role": "user", "content": "run"}],
        [{"type": "function"}],
        lambda *_args: "ok",
    ))

    assert any(e.get("type") == "final" and e.get("content") == "done" for e in events)
    second_messages = completions.calls[1]["messages"]
    assistant = next(m for m in second_messages
                     if m.get("role") == "assistant" and m.get("tool_calls"))
    assert assistant["reasoning_content"] == "private-reasoning"


class _Reasoning400Completions:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            raise RuntimeError(
                "The `reasoning_content` in the thinking mode must be passed back to the API.")
        return iter([
            NS(choices=[NS(delta=NS(content="recovered", tool_calls=None,
                                    reasoning_content=None),
                          finish_reason="stop")], usage=None),
        ])


def test_sdk_reasoning_400_falls_back_to_non_thinking_once():
    provider = _sdk_provider()
    completions = _Reasoning400Completions()
    provider._client = NS(chat=NS(completions=completions))

    events = list(provider._agentic_loop(
        [{"role": "user", "content": "run"}], [{"type": "function"}],
        lambda *_args: "ok",
    ))

    assert any(e.get("type") == "final" and e.get("content") == "recovered"
               for e in events)
    assert completions.calls[1]["extra_body"] == {"thinking": {"type": "disabled"}}


class _CompactSDK(DeepSeekProvider):
    def _summarize_for_compaction(self, _summary_input):
        return "summary"


class _CompactHTTP(DeepSeekHTTPProvider):
    def _summarize_for_compaction(self, _summary_input):
        return "summary"


def _compaction_messages():
    messages = [{"role": "system", "content": "system"}]
    for i in range(8):
        messages.extend([
            {"role": "user", "content": f"user-{i}"},
            {"role": "assistant", "content": f"assistant-{i}"},
        ])
    messages.extend([
        {"role": "assistant", "content": None,
         "reasoning_content": "recent-reasoning",
         "tool_calls": [{"id": "call_recent", "type": "function",
                         "function": {"name": "demo", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "call_recent", "content": "ok"},
    ])
    return messages


def test_deepseek_compaction_has_no_synthetic_assistant_ack():
    for cls in (_CompactSDK, _CompactHTTP):
        provider = cls(api_key="test", model="deepseek-v4-pro",
                       system_prompt="system", tools=[])
        compacted = provider._compact_openai_shape(_compaction_messages(), cls.__name__)

        assert compacted[0]["role"] == "system"
        assert compacted[1]["role"] == "user"
        assert not any(m.get("content") == provider._COMPACTION_ACK for m in compacted)
        recent = next(m for m in compacted if m.get("tool_calls"))
        assert recent["reasoning_content"] == "recent-reasoning"


class _HTTPProbe(DeepSeekHTTPProvider):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calls = []
        self._client = True

    def _chat(self, messages, tools, force_thinking_off=False):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools,
                           "force_thinking_off": force_thinking_off})
        if len(self.calls) == 1:
            return {"choices": [{"message": {
                "content": "",
                "reasoning_content": "http-reasoning",
                "tool_calls": [{"id": "call_http", "type": "function",
                                "function": {"name": "demo", "arguments": "{}"}}],
            }}]}
        return {"choices": [{"message": {"content": "done", "tool_calls": []}}]}


def test_http_tool_loop_replays_reasoning_content():
    provider = _HTTPProbe(
        api_key="test", model="deepseek-v4-pro", system_prompt="system",
        tools=[{"name": "demo", "description": "demo", "input_schema": {}}],
    )
    result = provider.process_message("run", execute_tool=lambda *_args: "ok")

    assert result == "done"
    assistant = next(m for m in provider.calls[1]["messages"]
                     if m.get("role") == "assistant" and m.get("tool_calls"))
    assert assistant["reasoning_content"] == "http-reasoning"


class _HTTPReasoning400(_HTTPProbe):
    def _chat(self, messages, tools, force_thinking_off=False):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools,
                           "force_thinking_off": force_thinking_off})
        if len(self.calls) == 1:
            raise RuntimeError(
                "The `reasoning_content` in the thinking mode must be passed back to the API.")
        return {"choices": [{"message": {"content": "recovered", "tool_calls": []}}]}


def test_http_reasoning_400_falls_back_to_non_thinking_once():
    provider = _HTTPReasoning400(
        api_key="test", model="deepseek-v4-pro", system_prompt="system", tools=[])
    result = provider.process_message("run")

    assert result == "recovered"
    assert provider.calls[1]["force_thinking_off"] is True


def test_v4_compaction_threshold_uses_one_million_context():
    assert DeepSeekProvider.COMPACTION_CHAR_THRESHOLD == 1_600_000
    assert DeepSeekHTTPProvider.COMPACTION_CHAR_THRESHOLD == 1_600_000
