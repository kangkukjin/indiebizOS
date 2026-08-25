"""Gemini SDK 2.x의 tool turn·lazy stream 오류 계약 회귀."""
from types import SimpleNamespace

from providers.gemini import GeminiProvider


def _provider():
    return GeminiProvider(api_key="test", model="gemini-test", system_prompt="system")


def test_function_response_uses_user_role_not_openai_tool_role():
    provider = _provider()

    class Types:
        @staticmethod
        def Content(**kwargs):
            return SimpleNamespace(**kwargs)

    provider._genai_types = Types
    content = provider._function_response_content(["result"])
    assert content.role == "user"
    assert content.parts == ["result"]


def test_function_response_preserves_gemini_call_id():
    provider = _provider()

    class Types:
        FunctionResponse = SimpleNamespace

        @staticmethod
        def Part(**kwargs):
            return SimpleNamespace(**kwargs)

    provider._genai_types = Types
    part = provider._function_response_part(
        SimpleNamespace(name="echo_probe", id="call_123"), "echo-ok")
    assert part.function_response.id == "call_123"
    assert part.function_response.name == "echo_probe"
    assert part.function_response.response == {"output": "echo-ok"}


def test_lazy_stream_400_retries_without_thinking_budget(monkeypatch):
    provider = _provider()
    provider.disable_thinking = True
    provider._thinking_off_unsupported = False
    rebuilt = []

    class BadStream:
        def __iter__(self):
            raise RuntimeError("400 INVALID_ARGUMENT")

    class Models:
        def generate_content_stream(self, **kwargs):
            rebuilt.append(kwargs["config"])
            return iter(["recovered"])

    provider._genai_client = SimpleNamespace(models=Models())
    monkeypatch.setattr(provider, "_build_config", lambda _tools: "thinking-off-removed")

    chunks = list(provider._iterate_stream_with_retry(BadStream(), ["request"], "bad-config"))
    assert chunks == ["recovered"]
    assert rebuilt == ["thinking-off-removed"]
    assert provider._thinking_off_unsupported is True


def test_empty_stream_part_has_no_payload():
    empty = SimpleNamespace(
        text=None, thought=None, thought_signature=None, function_call=None,
        function_response=None, inline_data=None, file_data=None,
        executable_code=None, code_execution_result=None)
    assert GeminiProvider._part_has_payload(empty) is False
    empty.function_call = SimpleNamespace(name="echo_probe")
    assert GeminiProvider._part_has_payload(empty) is True


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
