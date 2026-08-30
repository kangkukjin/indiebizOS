"""
api_config_tiers.py - AI 티어 설정 API (시스템AI/경량/중급)
IndieBiz OS Core

api_config.py 에서 분리 (2026-08-17, 1500줄 규칙). 세 티어의 조회·저장 엔드포인트는
서로 같은 모양이라 한 덩어리로 응집한다 — 경로 상수·프로바이더 캐시 무효화·그리고
**키를 .env 로 보내는 규칙**을 공유한다.

★자격증명: 저장으로 들어온 apiKey 는 티어 json 이 아니라 `.env` 로 간다
(model_resolver.set_env_key). 보관소는 하나다 — 도구·데이터 키가 이미 전부 거기 산다.
"""
import json
import logging

from fastapi import APIRouter, HTTPException
from typing import Dict, Any

from model_resolver import (
    SYSTEM_AI_CONFIG_PATH,
    LIGHTWEIGHT_AI_CONFIG_PATH,
    MIDTIER_AI_CONFIG_PATH,
    UNCONSCIOUS_AI_CONFIG_PATH,
    env_key_for_provider,
)

logger = logging.getLogger(__name__)
router = APIRouter()
_MODEL_PROVIDERS = ("google", "anthropic", "openai", "openrouter", "deepseek",
                    "claude_code", "codex")


# ============ 시스템 AI 설정 API ============

def _stash_key_to_env(config: dict) -> str:
    """설정 저장 시 들어온 apiKey 를 `.env` 로 옮기고, json 에는 빈 값을 남긴다.

    ★왜: API 키의 보관소는 `.env` 하나다(도구·데이터 키가 이미 전부 거기 산다).
    모델 키만 티어 json 에 따로 살면 같은 키가 여러 파일로 복사되고, 티어의 provider 를
    바꿔도 옛 키가 남아 엉뚱한 벤더로 실려 간다(실측). UI 는 그대로 두고 착지점만 바꾼다.
    빈 값이면 아무것도 안 한다 — 사용자가 키 칸을 비우고 저장해도 기존 .env 를 지우지
    않는다(설정 저장이 자격증명을 지우는 건 놀라운 부작용이다)."""
    key = (config.get("apiKey") or "").strip()
    if not key:
        return ""
    try:
        from model_resolver import set_env_key
        set_env_key(config.get("provider", ""), key)
    except Exception as e:
        print(f"[api_config] .env 키 저장 실패(무시): {e}")
    return ""


def _with_provider_memory(config: dict) -> dict:
    """비밀은 숨기고, provider별 모델 기억과 키 존재 여부만 UI에 투영한다."""
    out = dict(config)
    models = dict(out.get("providerModels") or {})
    provider, model = out.get("provider", ""), out.get("model", "")
    if provider and model:
        models.setdefault(provider, model)  # 옛 단일-provider 설정의 무손실 이관
    out.update(apiKey="", providerModels=models,
               providerHasApiKey={p: bool(env_key_for_provider(p)) for p in _MODEL_PROVIDERS})
    return out


def _saved_config(config: dict, existing: dict, defaults: dict, *, with_role=False) -> dict:
    """활성 설정 + provider별 모델 이력을 병합한다. 키는 종전처럼 .env에만 저장."""
    provider = config.get("provider") or defaults["provider"]
    model = config.get("model") or defaults["model"]
    models = dict(existing.get("providerModels") or {})
    old_provider, old_model = existing.get("provider"), existing.get("model")
    if old_provider and old_model:
        models.setdefault(old_provider, old_model)
    models.update(config.get("providerModels") or {})
    if model:
        models[provider] = model
    # 한 번의 편집 중 여러 provider 키를 바꾼 경우도 모두 착지시킨다. 응답/JSON에는 안 남긴다.
    for key_provider, key in (config.get("providerApiKeys") or {}).items():
        if key_provider != provider and str(key or "").strip():
            _stash_key_to_env({"provider": key_provider, "apiKey": key})
    out = {"enabled": config.get("enabled", True), "provider": provider, "model": model,
           "apiKey": _stash_key_to_env(config), "providerModels": models}
    if with_role:
        out["role"] = config.get("role", existing.get("role", ""))
    return out


def get_default_system_ai_config() -> dict:
    """기본 시스템 AI 설정"""
    return {
        "enabled": True,
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        "apiKey": "",
        "role": ""
    }


@router.get("/system-ai")
async def get_system_ai_config():
    """전역 시스템 AI 설정 조회"""
    try:
        if SYSTEM_AI_CONFIG_PATH.exists():
            with open(SYSTEM_AI_CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            config = get_default_system_ai_config()
        return {"config": _with_provider_memory(config)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/system-ai")
async def update_system_ai_config(config: Dict[str, Any]):
    """전역 시스템 AI 설정 저장"""
    try:
        existing = json.loads(SYSTEM_AI_CONFIG_PATH.read_text(encoding="utf-8")) \
            if SYSTEM_AI_CONFIG_PATH.exists() else {}
        config_dict = _saved_config(config, existing, get_default_system_ai_config(), with_role=True)
        with open(SYSTEM_AI_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, ensure_ascii=False, indent=2)
        # 수동모드 번역용 본격 원샷 프로바이더 캐시 무효화 (모델 변경 즉시 반영)
        try:
            from consciousness_agent import reset_system_oneshot_provider
            reset_system_oneshot_provider()
        except Exception:
            pass
        return {"status": "saved", "config": _with_provider_memory(config_dict)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 경량 AI 설정 API ============

def get_default_lightweight_ai_config() -> dict:
    """기본 경량 AI 설정"""
    return {
        "enabled": True,
        "provider": "google",
        "model": "gemini-2.5-flash-lite",
        "apiKey": ""
    }


def _load_lightweight_config() -> dict:
    """경량 AI 설정 로드 (하위호환: unconscious_ai_config.json 폴백)"""
    if LIGHTWEIGHT_AI_CONFIG_PATH.exists():
        with open(LIGHTWEIGHT_AI_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    elif UNCONSCIOUS_AI_CONFIG_PATH.exists():
        with open(UNCONSCIOUS_AI_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return get_default_lightweight_ai_config()


@router.get("/lightweight-ai")
async def get_lightweight_ai_config():
    """경량 AI 설정 조회"""
    try:
        config = _load_lightweight_config()
        return {"config": _with_provider_memory(config)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/lightweight-ai")
async def update_lightweight_ai_config(config: Dict[str, Any]):
    """경량 AI 설정 저장"""
    try:
        existing = _load_lightweight_config()
        config_dict = _saved_config(config, existing, get_default_lightweight_ai_config())
        with open(LIGHTWEIGHT_AI_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, ensure_ascii=False, indent=2)
        return {"status": "saved", "config": _with_provider_memory(config_dict)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 하위호환: /unconscious-ai 엔드포인트 유지
@router.get("/unconscious-ai")
async def get_unconscious_ai_config_compat():
    """무의식 AI 설정 조회 (하위호환 → 경량 AI로 리다이렉트)"""
    return await get_lightweight_ai_config()


@router.put("/unconscious-ai")
async def update_unconscious_ai_config_compat(config: Dict[str, Any]):
    """무의식 AI 설정 저장 (하위호환 → 경량 AI로 리다이렉트)"""
    return await update_lightweight_ai_config(config)


# ============ 중급 AI 설정 API ============

def get_default_midtier_ai_config() -> dict:
    """기본 중급 AI 설정"""
    return {
        "enabled": True,
        "provider": "google",
        "model": "gemini-2.5-flash",
        "apiKey": ""
    }


@router.get("/midtier-ai")
async def get_midtier_ai_config():
    """중급 AI 설정 조회"""
    try:
        if MIDTIER_AI_CONFIG_PATH.exists():
            with open(MIDTIER_AI_CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            config = get_default_midtier_ai_config()
        return {"config": _with_provider_memory(config)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/midtier-ai")
async def update_midtier_ai_config(config: Dict[str, Any]):
    """중급 AI 설정 저장. 저장 후 provider 캐시 무효화하여 즉시 반영."""
    try:
        existing = json.loads(MIDTIER_AI_CONFIG_PATH.read_text(encoding="utf-8")) \
            if MIDTIER_AI_CONFIG_PATH.exists() else {}
        config_dict = _saved_config(config, existing, get_default_midtier_ai_config())
        with open(MIDTIER_AI_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, ensure_ascii=False, indent=2)

        # 캐시 무효화 — 다음 호출 시 새 config로 provider 재생성
        try:
            from consciousness_agent import reset_midtier_provider
            reset_midtier_provider()
        except Exception as cache_err:
            print(f"[midtier-ai] 캐시 무효화 경고: {cache_err}")

        return {"status": "saved", "config": _with_provider_memory(config_dict)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
