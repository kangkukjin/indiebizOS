"""비전 벤더 중립화 계약 배터리 (2026-08-27).

시각 읽기·채점은 범용 능력 — 모델은 기어가 단독 결정한다(에이전트·코드별 벤더 고정 금지).
- vision_read(critic/read)와 ingest _vision_json 은 기어-해소 원샷을 탄다.
- 이미지 입력이 있으면 원샷은 기어의 비전 모달리티 슬롯(modality.image →
  vision_ai_config.json)을 0차로 우선한다 — 텍스트 축 티어(경량 deepseek)는 비전이 없다.
- 재발 방지 관문: 범용 비전 경로 소스에 벤더 API URL 직서술 금지(이미지 *생성* 등
  벤더 고유 기능 파일은 대상 아님).

★이 배터리는 backend/ 밖(data/packages)의 파일도 읽는다 — 라이브 트리에서 돌릴 것.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401 — 층 디렉토리 등재

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MP = os.path.join(ROOT, "data/packages/installed/tools/media_producer")


def _load(path, name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def vr():
    return _load(os.path.join(MP, "vision_read.py"), "mp_vision_gear_test")


@pytest.fixture()
def png(tmp_path):
    p = tmp_path / "x.png"
    p.write_bytes(b"\x89PNG-stub")
    return str(p)


# ── vision_read: 기어 라우팅 계약 ─────────────────────────────────


def test_critic_routes_evaluate_axis_with_image(vr, png, monkeypatch):
    """critic = 평가 축(role=evaluate) + 이미지 동봉 — GoalEval 평가자와 같은 눈."""
    calls = []

    def fake(prompt, system_prompt=None, images=None, role=None):
        calls.append({"images": images, "role": role})
        return '{"passed": true, "score": 9, "issues": [], "notes": "좋음"}'

    monkeypatch.setattr(vr, "_ai_call", fake)
    out = vr.critique_image({"image_path": png, "intent": "t"}, ".")
    verdict = json.loads(out.split("verdict_json:", 1)[1].strip())
    assert verdict["passed"] is True and verdict["tier"] == "vision"
    assert calls[0]["role"] == "evaluate"
    assert calls[0]["images"] and calls[0]["images"][0]["media_type"] == "image/png"


def test_read_routes_execution_axis(vr, png, monkeypatch):
    """read = 실행 중 지각 — 실행 축(role=execution)."""
    calls = []
    monkeypatch.setattr(vr, "_ai_call",
                        lambda p, system_prompt=None, images=None, role=None:
                        calls.append(role) or "화면에 숫자 42가 보입니다")
    out = vr.read_image({"image_path": png, "question": "숫자?"}, ".")
    assert out == "화면에 숫자 42가 보입니다"
    assert calls == ["execution"]


def test_gear_failure_is_honest(vr, png, monkeypatch):
    """기어 호출 실패(None) = 기어 설정을 가리키는 정직 오류 — 벤더 키 이름 없음."""
    monkeypatch.setattr(vr, "_ai_call", lambda *a, **k: None)
    for fn in (lambda: vr.critique_image({"image_path": png, "intent": "t"}, "."),
               lambda: vr.read_image({"image_path": png}, ".")):
        out = json.loads(fn())
        assert out["success"] is False
        assert "기어" in out["error"]
        assert "GEMINI" not in out["error"]


# ── 원샷의 0차: 비전 모달리티 슬롯 우선 ───────────────────────────


class _SentinelProvider:
    system_prompt = ""

    def process_message(self, message, history=None, images=None, execute_tool=None):
        assert images, "비전 프로바이더인데 이미지가 안 실렸다"
        return "SENTINEL_VISION_OK"


def test_oneshot_prefers_vision_modality_slot(monkeypatch):
    """images 가 있으면 role 축이 아니라 gear modality.image 프로바이더가 0차."""
    import model_resolver
    import consciousness_agent as ca
    monkeypatch.setattr(model_resolver, "get_vision_provider",
                        lambda oneshot=True: (_SentinelProvider(), {"source": "test"}))
    out = ca.oneshot_ai_call("설명해줘", images=[{"base64": "eA==", "media_type": "image/png"}],
                             role="classify")
    assert out == "SENTINEL_VISION_OK"
    out2 = ca.system_ai_call("평가해줘", images=[{"base64": "eA==", "media_type": "image/png"}],
                             role="evaluate")
    assert out2 == "SENTINEL_VISION_OK"


def test_vision_slot_resolves_from_gear_data():
    """라이브 기어: modality.image 예약석이 데이터로 채워져 있고 리졸버가 그걸 읽는다."""
    import model_resolver
    _prov, d = model_resolver.get_vision_provider(oneshot=True)
    assert d["source"].startswith("modality.image→"), d
    assert d["model"], "비전 슬롯 설정에 model 이 비어 있다"


# ── ingest: 두 번째 숙주도 같은 통로 ──────────────────────────────


def test_ingest_vision_json_rides_gear(monkeypatch):
    import consciousness_agent as ca
    from services import ingest_engine as ie
    calls = []
    monkeypatch.setattr(ca, "oneshot_ai_call",
                        lambda prompt, system_prompt=None, images=None, role=None:
                        calls.append({"role": role, "n": len(images or [])}) or '[{"a": 1}]')
    raw, err = ie._vision_json("추출해", [{"base64": "eA==", "media_type": "image/png"}])
    assert err is None and raw == '[{"a": 1}]'
    assert calls == [{"role": "classify", "n": 1}]


# ── 재발 방지 관문: 범용 비전 경로에 벤더 URL 금지 ────────────────


def test_no_vendor_url_in_generic_vision_paths():
    """시각 읽기·채점(범용)에 벤더 API 직서술 금지 — 벤더는 데이터(vision_ai_config)에 산다.

    이미지 *생성*(gemini_image.py 등 벤더 고유 기능)은 대상이 아니다."""
    for path in (os.path.join(MP, "vision_read.py"),
                 os.path.join(ROOT, "backend/services/ingest_engine.py")):
        src = open(path, encoding="utf-8").read()
        assert "generativelanguage.googleapis.com" not in src, f"벤더 URL 재발: {path}"
        assert "GEMINI_API_KEY" not in src, f"벤더 키 직참조 재발: {path}"


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__] + sys.argv[1:]))
