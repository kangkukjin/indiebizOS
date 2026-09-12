"""Codex 카탈로그 → 설정 선택값 → CLI 인자의 연결을 검증한다."""
import boot_paths  # noqa: F401
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_catalog_selection_reaches_cli(monkeypatch, tmp_path):
    import api_config_tiers
    from providers.codex import CodexProvider

    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    cache = tmp_path / "models_cache.json"
    cache.write_text(json.dumps({"models": [
        {"slug": "gpt-6-astra", "display_name": "GPT-6-Astra", "visibility": "list",
         "supported_reasoning_levels": [{"effort": "high"}, {"effort": "ultra"}],
         "internal_instructions": "must not be returned"},
        {"slug": "hidden-model", "visibility": "hide"},
    ]}))
    app = FastAPI()
    app.include_router(api_config_tiers.router)
    with TestClient(app) as client:
        response = client.get("/codex/models")
        assert response.status_code == 200
        assert response.json() == {"items": [{"slug": "gpt-6-astra",
            "display_name": "GPT-6-Astra", "reasoning_efforts": ["high", "ultra"]}]}
        item = response.json()["items"][0]
        for effort in item["reasoning_efforts"]:
            provider = CodexProvider(api_key="", model=f'{item["slug"]}:{effort}', system_prompt="")
            provider._binary_path = "/fake/codex"
            command = provider._build_command(stream=True)
            assert command[command.index("-m") + 1] == item["slug"]
            assert f'model_reasoning_effort="{effort}"' in command
        # 직접 입력한 표시명도 모델 ID로 전달한다. fresh/resume 모두 같은 경계다.
        for selector in ("GPT-6-Astra", " GPT-6-Astra : HIGH ", "gPt-6-AsTrA:ultra"):
            provider = CodexProvider(api_key="", model=selector, system_prompt="")
            provider._binary_path = "/fake/codex"
            for session in (None, "existing-session"):
                command = provider._build_command(stream=True, resume_session_id=session)
                assert command[command.index("-m") + 1] == item["slug"]
                if ":" in selector:
                    effort = selector.rsplit(":", 1)[1].strip().lower()
                    assert f'model_reasoning_effort="{effort}"' in command
        # 표시명과 ID가 대소문자 외에도 다른 모델, 미등록 사용자 ID를 구별한다.
        from providers.codex import canonical_model_slug
        assert canonical_model_slug("My-Custom-ID") == "My-Custom-ID"
        cache.write_text(json.dumps({"models": [{"slug": "model-id", "visibility": "list",
                                                 "display_name": "Friendly Model"}]}))
        assert canonical_model_slug("friendly model") == "model-id"
        # 다음 조회에서 새 카탈로그를 읽는다(서버 재기동 불필요).
        cache.write_text('{"models": []}')
        assert client.get("/codex/models").json() == {"items": []}


@pytest.mark.parametrize("content", [None, "invalid", "null", "[]", '{"models": null}',
                                    '{"models": [null, {}, {"slug": "x", "visibility": "hide"}]}'])
def test_missing_or_invalid_catalog_keeps_manual_input_available(monkeypatch, tmp_path, content):
    from providers.codex import list_available_models

    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    if content is not None:
        (tmp_path / "models_cache.json").write_text(content)
    assert list_available_models() == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
