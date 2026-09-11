"""모델 티어가 provider 왕복 때 모델·키 기억을 잃지 않는지 검사한다."""


def test_saved_config_keeps_models_and_stashes_all_provider_keys(monkeypatch):
    import api_config_tiers as tiers

    stashed = []
    monkeypatch.setattr(tiers, "_stash_key_to_env",
                        lambda c: stashed.append((c.get("provider"), c.get("apiKey"))) or "")
    existing = {"enabled": True, "provider": "google", "model": "gemini-old", "apiKey": ""}
    incoming = {
        "enabled": True, "provider": "deepseek", "model": "deepseek-v4-pro", "apiKey": "ds-new",
        "providerModels": {"google": "gemini-new"},
        "providerApiKeys": {"google": "google-new"},
    }

    saved = tiers._saved_config(incoming, existing, tiers.get_default_system_ai_config())

    assert saved["providerModels"] == {
        "google": "gemini-new", "deepseek": "deepseek-v4-pro"}
    assert saved["apiKey"] == "" and "providerApiKeys" not in saved
    assert stashed == [("google", "google-new"), ("deepseek", "ds-new")]


def test_config_response_exposes_only_key_presence(monkeypatch):
    import api_config_tiers as tiers

    monkeypatch.setattr(tiers, "env_key_for_provider",
                        lambda provider: "secret" if provider == "google" else "")
    shown = tiers._with_provider_memory({
        "provider": "google", "model": "gemini-2.5-flash", "apiKey": "legacy-secret"})

    assert shown["apiKey"] == ""
    assert shown["providerModels"]["google"] == "gemini-2.5-flash"
    assert shown["providerHasApiKey"]["google"] is True
    assert "secret" not in repr(shown)


def test_provider_factory_preserves_options_and_owns_no_cache(monkeypatch):
    from types import SimpleNamespace
    import providers
    made = []

    def construct(name, **kwargs):
        obj = SimpleNamespace(name=name, kwargs=kwargs, disable_session_persistence=False,
                              no_tools=False, disable_thinking=False, initialized=0)

        def initialize():
            obj.initialized += 1
            return False  # 준비 실패의 기존 is_ready 계약을 생성기가 덮지 않는다.

        obj.init_client = initialize
        made.append(obj)
        return obj

    monkeypatch.setattr(providers, "get_provider", construct)
    a = providers.create_initialized_provider("codex", model="m", agent_id="a",
        isolated_session=True, no_tools=True, disable_thinking=True)
    b = providers.create_initialized_provider("codex", model="m", agent_id="b")
    assert a is not b and a.initialized == b.initialized == 1
    assert a.disable_session_persistence and a.no_tools and a.disable_thinking
    assert not b.disable_session_persistence and not b.no_tools and not b.disable_thinking
    assert a.kwargs == {"model": "m", "agent_id": "a"}
    assert b.kwargs == {"model": "m", "agent_id": "b"}


def test_resolver_keeps_oneshot_and_mutable_session_in_separate_buckets(monkeypatch):
    from types import SimpleNamespace
    import providers
    import model_resolver as models
    monkeypatch.setattr(models, "_provider_cache", {})
    monkeypatch.setattr(providers, "get_provider", lambda *a, **kw: SimpleNamespace(
        init_client=lambda: None, disable_session_persistence=False,
        no_tools=False, disable_thinking=False, kwargs=kw))
    d = {"provider": "codex", "model": "test", "api_key": ""}
    one = models._provider_from_desc(d, oneshot=True)
    session = models._provider_from_desc(d, oneshot=False)
    assert one is not session
    assert one.no_tools and one.disable_thinking and one.disable_session_persistence
    assert not session.no_tools and not session.disable_thinking
    assert models._provider_from_desc(dict(d), oneshot=True) is one
    assert models._provider_from_desc({**d, "model": "changed"}, oneshot=True) is not one


def test_provider_factory_propagates_initialization_failure(monkeypatch):
    import pytest
    import providers
    from types import SimpleNamespace

    def fail():
        raise RuntimeError("init failure")

    monkeypatch.setattr(providers, "get_provider", lambda *a, **kw: SimpleNamespace(init_client=fail))
    with pytest.raises(RuntimeError, match="init failure"):
        providers.create_initialized_provider("fake")


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
