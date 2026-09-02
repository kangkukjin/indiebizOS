r"""시스템 AI 준비 판정 — "키가 있나"로 "쓸 수 있나"를 재지 않는다 (2026-09-02, 첫 성공 온보딩 ① A)

배경: /system-ai/status 가 `ready = bool(apiKey) and enabled` 로 판정했다. claude_code(구독
OAuth)·codex·ollama(로컬)는 키가 원래 없는데, 이 자리가 provider 를 안 보면 무키 프로바이더가
멀쩡히 잡혀 있어도 "키를 넣으라"고 한다 — 2026-08-17 채팅 3 진입점 사고와 같은 부류의 잔존.
판정 정본 = model_resolver.provider_needs_api_key. 이 자리 하나를 고치고, 같은 부류가 다시
생기지 않게 surface 층 전체를 훑는 부류 관문(T4)을 함께 둔다(사람이 고른 grep 범위는 샌다).

    T1. provider=claude_code · 키 빈칸 → ready True, needs_api_key False
    T2. provider=anthropic · 키 빈칸 → ready False, needs_api_key True
    T3. enabled=False 면 키가 있어도 ready False
    T4. surface 층에서 apiKey/api_key 로 bool 판정을 만드는 자리는 provider_needs_api_key 를 지난다
    T5. /system-ai/welcome 의 needs_api_key 는 고정값이 아니라 판정에서 파생한다

실행: python3 -m pytest backend/test_system_ai_ready.py
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401

import api_system_ai as sa


def test_t1_no_key_provider_is_ready_without_key():
    st = sa._system_ai_readiness({"provider": "claude_code", "model": "sonnet", "apiKey": "", "enabled": True})
    assert st["ready"] is True
    assert st["needs_api_key"] is False
    assert st["has_api_key"] is False       # 사실은 사실대로 — 키 칸은 비어 있다


def test_t2_key_provider_without_key_is_not_ready():
    st = sa._system_ai_readiness({"provider": "anthropic", "model": "x", "apiKey": "", "enabled": True})
    assert st["ready"] is False
    assert st["needs_api_key"] is True


def test_t3_disabled_is_never_ready():
    st = sa._system_ai_readiness({"provider": "anthropic", "model": "x", "apiKey": "sk-1", "enabled": False})
    assert st["ready"] is False


def test_t4_surface_layer_key_judgments_go_through_resolver():
    """부류 관문: `x = bool(cfg.get("apiKey"))` 로 만든 값이 `ready` 판정에 들어가는 파일은
    같은 파일 안에서 provider_needs_api_key 를 참조해야 한다. (has_api_key 를 '키 설정됨' 표시로만
    노출하는 자리는 준비 판정이 아니므로 대상이 아니다.)"""
    surface = Path(__file__).resolve().parent / "surface"
    assign = re.compile(r'(\w+)\s*=\s*bool\(\s*[\w\.]*\.get\(\s*["\'](?:apiKey|api_key)["\']')
    offenders = []
    for f in sorted(surface.glob("api_*.py")):
        text = f.read_text(encoding="utf-8")
        for m in assign.finditer(text):
            var = m.group(1)
            if re.search(r'ready["\']?\s*[:=]\s*[^\n]*\b' + re.escape(var) + r'\b', text) \
                    and "provider_needs_api_key" not in text:
                offenders.append(f.name)
                break
    assert offenders == [], f"apiKey 존재로 준비를 판정하는 자리: {offenders}"


def test_t5_welcome_needs_key_is_derived(monkeypatch):
    import asyncio
    monkeypatch.setattr(sa, "load_system_ai_config",
                        lambda: {"provider": "ollama", "model": "llama3", "apiKey": "", "enabled": True})
    out = asyncio.run(sa.get_welcome_message())
    assert out["needs_api_key"] is False and out["ready"] is True
    monkeypatch.setattr(sa, "load_system_ai_config",
                        lambda: {"provider": "openai", "model": "gpt", "apiKey": "", "enabled": True})
    out = asyncio.run(sa.get_welcome_message())
    assert out["needs_api_key"] is True and out["ready"] is False


if __name__ == "__main__":
    # 직접 실행도 pytest 로 위임 — 두 번째 러너는 드리프트한다(test_single_runner R2)
    import pytest as _pytest
    sys.exit(_pytest.main([__file__]))
