"""EXAONE의 SDK 와이어·도구 왕복·키 조회·모델 능력 계약."""
import json
from types import SimpleNamespace

import boot_paths  # noqa: F401
import httpx
import pytest

from providers import get_provider
from providers.base import normalize_usage


@pytest.fixture
def provider():
    p = get_provider("exaone", api_key="test-key", model="k-exaone_v2.5",
                     system_prompt="system", tools=[])
    assert p.init_client()
    yield p
    p._client.close()


@pytest.mark.parametrize("disable_thinking", [False, True])
def test_stream_tool_roundtrip(provider, disable_thinking):
    requests = []
    executed = []

    def respond(request):
        assert str(request.url) == "https://api.exaone.ai/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        requests.append(body)
        assert body["temperature"] == 1.0 and body["top_p"] == 0.95
        assert body["chat_template_kwargs"]["preserve_thinking"] is True
        assert body.get("reasoning_effort") == ("low" if disable_thinking else None)
        assert "enable_thinking" not in body
        if len(requests) == 1:
            deltas = [
                ({"reasoning_content": "private trace"}, None),
                ({"tool_calls": [{"index": 0, "id": "call_1", "type": "function",
                                  "function": {"name": "echo", "arguments": '{"text":'}}]}, None),
                ({"tool_calls": [{"index": 0, "function": {"arguments": '"ok"}'}}]}, "tool_calls"),
            ]
        else:
            assistant = next(m for m in body["messages"] if m.get("tool_calls"))
            assert assistant["reasoning_content"] == "private trace"
            assert any(m.get("role") == "tool" and m["tool_call_id"] == "call_1"
                       for m in body["messages"])
            deltas = [({"content": "done"}, "stop")]
        chunks = [{"id": "test", "object": "chat.completion.chunk", "created": 1,
                   "model": provider.model,
                   "choices": [{"index": 0, "delta": delta, "finish_reason": reason}]}
                  for delta, reason in deltas]
        chunks.append({"id": "test", "object": "chat.completion.chunk", "created": 1,
                       "model": provider.model, "choices": [],
                       "usage": {"prompt_tokens": 20, "completion_tokens": 10,
                                 "total_tokens": 30, "reasoning_tokens": 8}})
        wire = "".join("data: " + json.dumps(c) + "\n\n" for c in chunks) + "data: [DONE]\n\n"
        return httpx.Response(200, text=wire, headers={"content-type": "text/event-stream"})

    provider._client.close()
    import openai
    provider._client = openai.OpenAI(
        api_key="test-key", base_url="https://api.exaone.ai/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(respond)))
    provider.disable_thinking = disable_thinking
    events = list(provider._agentic_loop(
        [{"role": "user", "content": "echo ok"}], [{"type": "function"}],
        lambda name, args, *_: executed.append((name, args)) or "ok"))
    assert executed == [("echo", {"text": "ok"})]
    assert len(requests) == 2
    assert any(e.get("type") == "final" and e.get("content") == "done" for e in events)
    assert not any("private trace" in e.get("content", "") for e in events)


def test_nonstream_helpers_use_low_reasoning(provider):
    calls = []

    def create(**params):
        calls.append(params)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="summary"))])

    provider._client.close()
    provider._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
                                       close=lambda: None)
    assert provider._final_turn_text([{"role": "user", "content": "report"}], 2048) == "summary"
    assert provider._summarize_for_compaction("history") == "summary"
    assert all(c["extra_body"]["reasoning_effort"] == "low" for c in calls)
    assert provider._openai_compaction_ack() is None


def test_catalog_key_presence_and_capabilities(provider, monkeypatch):
    from ai_candidates import detect_candidates
    from api_config_tiers import _with_provider_memory
    from model_context import context_window
    from model_resolver import env_key_for_provider, image_input_support

    monkeypatch.setenv("EXAONE_API_KEY", "test-secret")
    assert env_key_for_provider("exaone") == "test-secret"
    shown = _with_provider_memory({"provider": "exaone", "model": provider.model})
    assert shown["providerHasApiKey"]["exaone"] is True
    assert "test-secret" not in repr(shown)
    candidates = detect_candidates(env={"EXAONE_API_KEY": "test-secret"}, which=lambda _: None,
                                   glob_fn=lambda _: [], fetch_json=lambda *_: {})
    assert [(c["provider"], c["model"]) for c in candidates] == [("exaone", provider.model)]
    assert context_window(provider) == 524288
    assert image_input_support({"provider": "exaone", "model": provider.model}) is False


@pytest.mark.parametrize("as_object", [False, True])
def test_reasoning_usage_is_subset_of_output(as_object):
    usage = {"prompt_tokens": 22, "completion_tokens": 218, "reasoning_tokens": 209}
    result = normalize_usage(SimpleNamespace(**usage) if as_object else usage)
    assert result == {"input": 22, "output": 218, "reasoning": 209,
                      "cache_read": 0, "cache_create": 0}


def test_missing_key_is_not_ready():
    p = get_provider("exaone", api_key="", model="k-exaone_v2.5", system_prompt="", tools=[])
    assert p.init_client() is False
    assert not p.is_ready
