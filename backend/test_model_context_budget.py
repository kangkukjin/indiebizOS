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


def test_transport_bytes_json_escaping_and_images_are_separate_from_tokens():
    from model_request_budget import payload_text, check, InputTooLarge
    p = provider('openai', 'gpt-4.1')
    p.request_limits = {'bytes': 1000, 'source': 'test transport contract'}
    wire = payload_text({'messages': [{'content': '한글\\"' * 180}], 'image': {'base64': 'a' * 500}})
    assert len(wire.encode()) > len(wire)
    with pytest.raises(InputTooLarge) as exc:
        check(p, wire, images=[{}])
    assert 'bytes' in exc.value.details['exceeded']
    p.request_limits = {}
    metrics = check(p, payload_text({'images': [{'base64': 'a' * 100000}]}), images=[{}])
    assert metrics['chars'] > 100000 and metrics['estimated_tokens'] < 9000


@pytest.mark.parametrize('kind', ['deepseek_http', 'gemini_http', 'ollama', 'openai', 'anthropic'])
def test_final_api_assembly_blocks_transport_before_network(kind, monkeypatch):
    from types import SimpleNamespace
    p = provider(kind, 'fixture')
    p._client = SimpleNamespace()  # no network methods; gate must win
    p._evaluation_budget = True
    p.request_limits = {'bytes': 1, 'source': 'fixture'}
    p.context_window_tokens = 100000
    monkeypatch.setattr('requests.post', lambda *a, **k: pytest.fail('network must not run'))
    monkeypatch.setattr('situation_delivery.prepare', lambda *a, **k: None)
    try:
        p.process_message('가\\"\n')
    except RuntimeError:
        assert kind == 'openai'
    assert p.last_failure_details['exceeded']['bytes']['limit'] == 1
    assert p.last_failure_kind == 'input_too_large'


@pytest.mark.parametrize('kind', ['deepseek_http', 'gemini_http'])
def test_rest_transport_error_with_verdict_is_failure_without_size_retry(kind, monkeypatch):
    from types import SimpleNamespace
    p = provider(kind, 'fixture')
    p._client = True
    p.disable_thinking = True
    p._evaluation_budget = True
    requests = []
    def post(*a, **kw):
        requests.append(kw)
        return SimpleNamespace(status_code=400, text='input_too_large ACHIEVED')
    monkeypatch.setattr('requests.post', post)
    monkeypatch.setattr('situation_delivery.prepare', lambda *a, **k: None)
    p.process_message('기준')
    assert p.last_failure_kind == 'input_too_large'
    assert len(requests) == 1


def test_input_size_counts_do_not_match_retryable_http_status_substrings():
    from providers.base import RetryConfig
    from model_request_budget import InputTooLarge
    assert not RetryConfig().is_retryable(InputTooLarge({'chars': {'used': 500000}}))
    assert not RetryConfig().is_retryable(RuntimeError('input_too_large: 503000 characters'))


def test_gemini_sdk_final_config_is_checked_before_client_call():
    from types import SimpleNamespace
    from model_request_budget import InputTooLarge
    from providers.gemini import GeminiProvider
    p = provider('gemini', 'fixture')
    p._genai_client = SimpleNamespace()
    p._evaluation_budget = True
    p.request_limits = {'bytes': 1}
    with pytest.raises(InputTooLarge):
        GeminiProvider._create_stream_with_retry(p, [{'text': '가'}], {'system_instruction': '정책'})
