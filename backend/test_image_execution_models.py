"""이미지 채점 모델의 실제 선택·실패·설정 노출 계약. 외부 호출 없이 검증한다."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import boot_paths  # noqa: F401
import model_resolver as models


@pytest.fixture
def config(tmp_path, monkeypatch):
    catalog = Path(models._data_path()) / "model_input_capabilities.yaml"
    (tmp_path / catalog.name).write_text(catalog.read_text())
    monkeypatch.setattr(models, "_data_path", lambda: tmp_path)
    monkeypatch.setattr(models, "env_key_for_provider", lambda p: "SECRET_ENV_KEY")
    files = {"light.json": {"provider": "deepseek", "model": "deepseek-v4-flash"},
             "high.json": {"provider": "claude_code", "model": "opus"},
             "vision.json": {"provider": "claude_code", "model": "sonnet", "api_key": "SECRET_FILE_KEY"}}
    for name, body in files.items():
        (tmp_path / name).write_text(json.dumps(body))
    gear = {"current_gear": "최대", "tiers": {"경량": "light.json", "고급": "high.json"},
            "presets": {"최대": {"실행": "고급"}, "절약": {"실행": "경량"}},
            "role_axis": {"execution": "실행"}, "overrides": {},
            "modality": {"image": "vision.json", "video": None, "embedding": "local/embedding"}}
    monkeypatch.setattr(models, "_load_gear", lambda: gear)
    return gear


def test_gear_switch_and_pin_choose_execution_or_fallback(config):
    assert models.resolve_image_execution()["model"] == "opus"
    config["current_gear"] = "절약"
    fallback = models.resolve_image_execution()
    assert fallback["model"] == "sonnet" and fallback["image_route"] == "fallback"
    config["overrides"]["project:worker"] = "고급"
    pinned = models.resolve_image_execution("project:worker")
    assert pinned["model"] == "opus" and pinned["image_route"] == "execution"
    assert "override:project:worker" in pinned["source"]


def test_runtime_model_takes_precedence_over_later_gear(config):
    config["current_gear"] = "절약"
    current = {"provider": "claude_code", "model": "opus", "api_key": ""}
    assert models.resolve_image_execution(execution=current)["model"] == "opus"


def test_unknown_model_and_explicit_capability(config):
    config["overrides"]["execution"] = {"provider": "ollama", "model": "custom"}
    unknown = models.resolve_image_execution()
    assert unknown["image_route"] == "fallback" and "미확인" in unknown["image_reason"]
    config["overrides"]["execution"]["input_modalities"] = ["text", "image"]
    assert models.resolve_image_execution()["model"] == "custom"
    assert models.resolve_agent_ai({}, "", "")["input_modalities"] == ["text", "image"]


def test_missing_fallback_does_not_select_text_model(config):
    config["current_gear"] = "절약"
    config["modality"]["image"] = None
    assert models.resolve_image_execution()["image_route"] == "unavailable"
    assert not models.resolve_image_execution()["model"]


def test_declared_nonvisual_fallback_is_rejected(config):
    config["current_gear"] = "절약"
    config["modality"]["image"] = "light.json"
    assert models.resolve_image_execution()["image_route"] == "unavailable"


def test_adapter_that_drops_images_cannot_be_declared_visual(config):
    d = {"provider": "deepseek_http", "model": "deepseek-v4-flash-vision-exp", "input_modalities": ["image"]}
    assert models.image_input_support(d) is False


def test_execution_oneshot_keeps_runtime_pin_and_image(monkeypatch):
    import consciousness_agent as ca
    import supervision_bus
    seen = {}
    active = {"provider": "claude_code", "model": "opus", "api_key": ""}
    controller = SimpleNamespace(owner="p:a", runner=SimpleNamespace(ai=SimpleNamespace(config=active)))
    monkeypatch.setattr(supervision_bus, "current", lambda: controller)

    class Provider:
        system_prompt = "original"

        def process_message(self, **kwargs):
            seen.update(kwargs)
            assert self.system_prompt == "rubric"
            return "VERDICT"

    provider = Provider()

    def select(agent_id=None, execution=None):
        assert agent_id == "p:a" and execution == active
        return provider, {"image_route": "execution"}

    monkeypatch.setattr(models, "get_image_execution_provider", select)
    monkeypatch.setattr(ca, "_resolve_oneshot_provider", lambda *a: pytest.fail("text fallback"))
    images = [{"base64": "eA==", "media_type": "image/png"}]
    assert ca.system_ai_call("inspect", "rubric", images, role="execution") == "VERDICT"
    assert seen["images"] == images and seen["history"] == [] and seen["execute_tool"] is None
    assert provider.system_prompt == "original"


def test_no_image_provider_means_honest_failure(monkeypatch):
    import consciousness_agent as ca
    monkeypatch.setattr(ca, "_execution_image_provider", lambda: None)
    monkeypatch.setattr(ca, "_resolve_oneshot_provider", lambda *a: pytest.fail("image silently discarded"))
    assert ca.system_ai_call("inspect", images=[{"base64": "eA=="}], role="execution") is None


def test_settings_use_same_resolver_without_provider_or_secrets(config, monkeypatch, tmp_path):
    import api_config
    import model_settings_view as view
    monkeypatch.setattr(view, "get_base_path", lambda: tmp_path)
    monkeypatch.setattr(models, "_provider_from_desc", lambda *a, **k: pytest.fail("settings created provider"))
    path = tmp_path / "data/packages/installed/tools/android/audio_models.yaml"
    path.parent.mkdir(parents=True)
    path.write_text("provider: google\napi_key: SECRET_AUDIO_KEY\ntranscribe:\n  model: asr-test\nanalyze:\n  model: ear-test\n")
    state = api_config._describe_gear()
    assert "SECRET" not in json.dumps(state)
    rows = {r["id"]: r for r in state["sensory_models"]}
    assert rows["image_execution"]["model"] == models.resolve_image_execution()["model"]
    assert rows["audio_transcribe"]["model"] == "asr-test"
    assert rows["audio_analyze"]["model"] == "ear-test"
    assert rows["modality_video"]["model"] == ""
    assert state["axis_info"]["평가"]["label"] == "보조 AI"
    config["current_gear"] = "절약"
    rows = {r["id"]: r for r in api_config._describe_gear()["sensory_models"]}
    assert rows["image_execution"]["model"] == "sonnet"
    assert "미지원" in rows["image_execution"]["detail"]


def test_missing_audio_settings_do_not_break_cockpit(config, monkeypatch, tmp_path):
    import model_settings_view as view
    monkeypatch.setattr(view, "get_base_path", lambda: tmp_path)
    rows = view.describe_model_settings(config)["sensory_models"]
    audio = next(r for r in rows if r["id"] == "audio_transcribe")
    assert audio["model"] == "" and "읽을 수 없습니다" in audio["detail"]


def test_slow_image_model_does_not_block_other_model_classification(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    import consciousness_agent as ca
    started, finish = Event(), Event()

    class ImageProvider:
        system_prompt = ""

        def process_message(self, **kwargs):
            started.set()
            assert finish.wait(5)
            return "image done"

    class TextProvider:
        system_prompt = ""

        def process_message(self, **kwargs):
            return "EXECUTE"

    monkeypatch.setattr(ca, "_execution_image_provider", lambda: ImageProvider())
    monkeypatch.setattr(ca, "_resolve_oneshot_provider", lambda *a: TextProvider())
    with ThreadPoolExecutor(max_workers=2) as pool:
        image = pool.submit(ca.system_ai_call, "inspect", images=[{"base64": "x"}], role="execution")
        try:
            assert started.wait(2)
            classify = pool.submit(ca.oneshot_ai_call, "classify")
            assert classify.result(timeout=2) == "EXECUTE"
        finally:
            finish.set()
        assert image.result(timeout=2) == "image done"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
