"""큰 IBL 기본 문맥과 정상 검색 결과를 조기 압축하지 않는 모델별 경계."""
import boot_paths  # noqa: F401
import pytest

from providers import get_provider
from model_context import context_window, input_budget, request_chars, discover_context_window


def provider(kind, model, **kwargs):
    return get_provider(kind, api_key="", model=model, system_prompt="", **kwargs)


@pytest.mark.parametrize("kind,model,window", [
    ("openai", "gpt-4.1-mini", 1047576),
    ("openrouter", "openai/gpt-4.1", 1047576),
    ("openrouter", "anthropic/claude-sonnet-4.6", 1000000),
    ("openai", "gpt-4o", 128000),
    ("anthropic", "claude-opus-5", 1000000),
    ("anthropic", "claude-haiku-4-5", 200000),
    ("gemini", "gemini-2.5-flash", 1048576),
    ("gemini_http", "gemini-2.5-pro", 1048576),
    ("deepseek", "deepseek-v4-flash", 1000000),
    ("deepseek_http", "deepseek-v4-pro", 1000000),
])
def test_model_capacity_not_provider_legacy_threshold(kind, model, window):
    p = provider(kind, model)
    assert context_window(p) == window
    assert input_budget(p) == window * 95 // 100
    messages = [{"role": "user", "content": "가" * 270000}]
    if window >= 1000000:
        assert not p._should_compact(messages, 20)
        assert not p._should_prune(messages, 20)
    boundary = [{"role": "user", "content": "가" * (window * 2)}]
    assert p._should_compact(boundary, 20)


def test_system_and_tools_count_once_and_output_space_is_reserved():
    p = provider("anthropic", "claude-haiku-4-5", tools=[{"name": "read"}])
    p.system_prompt = "시스템" * 100
    body = [{"role": "user", "content": "본문"}]
    with_system = [{"role": "system", "content": p.system_prompt}, *body]
    # 메시지 래퍼 크기를 제외하면 별도 system을 중복 계산하지 않는다.
    assert request_chars(p, with_system) - request_chars(p, body) < 100
    assert request_chars(p, body) > p._estimate_content_size(body) + len(p.system_prompt)
    assert input_budget(p, 64000) == 200000 - 64000 - 1024


def test_explicit_window_applies_to_unknown_and_local_models():
    p = provider("ollama", "local-model", context_window_tokens=131072)
    assert context_window(p) == 131072
    assert not p._should_prune([{"role": "user", "content": "가" * 60000}], 10)


def test_router_metadata_overrides_model_name_and_default(monkeypatch):
    import model_context
    monkeypatch.setattr(model_context, "_router_models", lambda: [
        {"id": "vendor/new-model", "context_length": 900000}])
    p = provider("openrouter", "vendor/new-model")
    discover_context_window(p)
    assert context_window(p) == 900000


def test_router_initialization_loads_metadata_and_failure_keeps_client(monkeypatch):
    import model_context
    import openai
    import requests
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: object())
    monkeypatch.setattr(model_context, "_router_models", lambda: [
        {"id": "vendor/new-model", "context_length": 900000}])
    p = get_provider("openrouter", api_key="test", model="vendor/new-model", system_prompt="")
    assert p.init_client()
    assert context_window(p) == 900000

    def unavailable():
        raise requests.Timeout()

    monkeypatch.setattr(model_context, "_router_models", unavailable)
    q = get_provider("openrouter", api_key="test", model="openai/gpt-4.1", system_prompt="")
    assert q.init_client()
    assert context_window(q) == 1047576


def test_ollama_uses_allocated_context_not_theoretical_capacity(monkeypatch):
    from types import SimpleNamespace
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"models": [{"name": "qwen2.5:latest", "context_length": 65536}]}))
    p = provider("ollama", "qwen2.5")
    p._client = SimpleNamespace(base_url="http://localhost:11434/v1/")
    discover_context_window(p)
    assert context_window(p) == 65536


def test_small_local_window_still_has_usable_input_budget():
    p = provider("ollama", "local-model", context_window_tokens=4096)
    assert input_budget(p) == 3072


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
