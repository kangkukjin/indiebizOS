"""모델 티어가 provider 왕복 때 모델·키 기억을 잃지 않는지 검사한다."""
import boot_paths  # noqa: F401
import pytest


@pytest.fixture
def model_configs(monkeypatch, tmp_path):
    import model_resolver as models
    import api_config_tiers as tiers
    monkeypatch.setattr(models, "_data_path", lambda: tmp_path)
    for attr, filename in [("SYSTEM_AI_CONFIG_PATH", "system_ai_config.json"),
                           ("LIGHTWEIGHT_AI_CONFIG_PATH", "lightweight_ai_config.json"),
                           ("MIDTIER_AI_CONFIG_PATH", "midtier_ai_config.json"),
                           ("UNCONSCIOUS_AI_CONFIG_PATH", "unconscious_ai_config.json")]:
        monkeypatch.setattr(models, attr, tmp_path / filename)
        monkeypatch.setattr(tiers, attr, tmp_path / filename)
    keys = {}
    monkeypatch.setattr(models, "env_key_for_provider", lambda p: keys.get(p, ""))
    monkeypatch.setattr(tiers, "env_key_for_provider", lambda p: keys.get(p, ""))
    monkeypatch.setattr(models, "set_env_key", lambda p, k: keys.update({p: k}) or True)
    monkeypatch.setattr(models, "_provider_cache", {})
    return models, keys


def test_saved_config_keeps_models_and_stashes_all_provider_keys(monkeypatch):
    import api_config_tiers as tiers

    stashed = []
    import model_resolver as models
    monkeypatch.setattr(models, "stash_model_key",
                        lambda c: stashed.append((c.get("provider"), c.get("apiKey"))) or "")
    existing = {"enabled": True, "provider": "google", "model": "gemini-old", "apiKey": ""}
    incoming = {
        "enabled": True, "provider": "deepseek", "model": "deepseek-v4-pro", "apiKey": "ds-new",
        "providerModels": {"google": "gemini-new"},
        "providerApiKeys": {"google": "google-new"},
    }

    saved = models.merge_model_config(incoming, existing, tiers.get_default_system_ai_config())

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


def test_model_read_fallback_is_read_only_and_corruption_does_not_select_old_file(model_configs):
    models, _ = model_configs
    old, current = models.UNCONSCIOUS_AI_CONFIG_PATH, models.LIGHTWEIGHT_AI_CONFIG_PATH
    old.write_text('{"provider":"google","model":"old","apiKey":"legacy"}')
    before = old.read_bytes()
    result = models.resolve_compat_model("lightweight")
    assert result == {"provider": "google", "model": "old", "api_key": "legacy"}
    assert old.read_bytes() == before and not current.exists()
    assert models._load_tier_config("경량", models._DEFAULT_GEAR)["model"] == "old"
    current.write_text("{broken")
    with pytest.raises(ValueError):
        models.read_model_config(current, fallback_path=old, strict=True)
    assert models.read_model_config(current, {"model": "default"}, fallback_path=old) == {"model": "default"}
    assert current.read_text() == "{broken"


def test_model_descriptor_credentials_match_provider_and_env_wins(model_configs):
    models, keys = model_configs
    keys["google"] = "env-google"
    cfg = {"provider": "google", "model": "m", "apiKey": "old-key", "input_modalities": ["text", "image"]}
    d = models.describe_model_config(cfg)
    assert d["api_key"] == "env-google" and d["input_modalities"] == ["text", "image"]
    assert models.describe_model_config({**cfg, "provider": "codex"})["api_key"] == ""
    assert models.api_key_for_provider("google") == "env-google"
    assert models.api_key_for_provider("anthropic") == ""
    models.MIDTIER_AI_CONFIG_PATH.write_text('{"provider":"anthropic","model":"m"}')
    models.SYSTEM_AI_CONFIG_PATH.write_text('{"provider":"google","apiKey":"wrong-vendor"}')
    assert models.resolve_compat_model("midtier") is None
    models.SYSTEM_AI_CONFIG_PATH.write_text('{"provider":"anthropic","apiKey":"same-vendor"}')
    assert models.resolve_compat_model("midtier")["api_key"] == "same-vendor"
    models.MIDTIER_AI_CONFIG_PATH.write_text('{"enabled":false,"provider":"codex","model":"m"}')
    assert models.resolve_compat_model("midtier") is None


def test_model_save_migrates_old_key_only_on_save_and_recovers_after_failed_write(model_configs, monkeypatch):
    models, keys = model_configs
    path = models.SYSTEM_AI_CONFIG_PATH
    path.write_text('{"provider":"google","model":"old","apiKey":"legacy"}')
    before = path.read_bytes()
    existing = models.read_model_config(path, strict=True)
    assert keys == {}  # 조회는 .env를 바꾸지 않는다.
    merged = models.merge_model_config({"provider": "google", "model": "new", "apiKey": ""},
                                       existing, models.default_model_config("고급"))
    assert keys == {"google": "legacy"} and merged["apiKey"] == ""
    real_replace = models.os.replace
    monkeypatch.setattr(models.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("disk unavailable")))
    with pytest.raises(OSError, match="disk unavailable"):
        models.write_model_config(path, merged)
    assert path.read_bytes() == before
    assert not list(path.parent.glob("*.tmp"))
    monkeypatch.setattr(models.os, "replace", real_replace)
    models.write_model_config(path, merged)
    assert "legacy" not in path.read_text()
    assert models.describe_model_config(models.read_model_config(path))["api_key"] == "legacy"


def test_key_write_failure_does_not_report_saved_or_replace_config(model_configs, monkeypatch):
    import asyncio
    import api_config_tiers as tiers
    from fastapi import HTTPException
    models, _ = model_configs
    path = models.MIDTIER_AI_CONFIG_PATH
    path.write_text('{"provider":"google","model":"old"}')
    before = path.read_bytes()
    monkeypatch.setattr(models, "set_env_key", lambda *a: False)
    with pytest.raises(HTTPException) as error:
        asyncio.run(tiers.update_midtier_ai_config({"provider": "google", "model": "new", "apiKey": "test-key"}))
    assert error.value.status_code == 500
    assert path.read_bytes() == before


def test_tier_routes_keep_compatibility_and_corrupt_file_is_not_overwritten(model_configs):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import api_config_tiers as tiers
    models, _ = model_configs
    app = FastAPI()
    app.include_router(tiers.router)
    with TestClient(app) as client:
        for path in ["/system-ai", "/lightweight-ai", "/midtier-ai", "/unconscious-ai"]:
            assert client.get(path).status_code == 200
            response = client.put(path, json={"provider": "codex", "model": "test"})
            assert response.status_code == 200 and response.json()["config"]["model"] == "test"
        models.LIGHTWEIGHT_AI_CONFIG_PATH.write_text("[broken")
        assert client.put("/lightweight-ai", json={"provider": "codex", "model": "new"}).status_code == 500
        assert models.LIGHTWEIGHT_AI_CONFIG_PATH.read_text() == "[broken"


def test_compatibility_getters_resolve_env_credentials_through_shared_owner(model_configs, monkeypatch):
    from types import SimpleNamespace
    import consciousness_agent as cognition
    import providers
    models, keys = model_configs
    keys["google"] = "env-key"
    for path in [models.SYSTEM_AI_CONFIG_PATH, models.LIGHTWEIGHT_AI_CONFIG_PATH, models.MIDTIER_AI_CONFIG_PATH]:
        path.write_text('{"provider":"google","model":"fake","apiKey":""}')
    monkeypatch.setattr(providers, "create_initialized_provider", lambda name, **kw: SimpleNamespace(name=name, kwargs=kw))
    for field, getter in [("_lightweight_provider", cognition._get_lightweight_provider),
                          ("_midtier_provider", cognition._get_midtier_provider_legacy),
                          ("_system_oneshot_provider", cognition._get_system_oneshot_provider)]:
        monkeypatch.setattr(cognition, field, None)
        monkeypatch.setattr(cognition, field + "_initialized", False)
        assert getter().kwargs["api_key"] == "env-key"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
