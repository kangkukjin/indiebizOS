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


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
