"""
api_config_tiers.py - AI 티어 설정 API (시스템AI/경량/중급)
IndieBiz OS Core

api_config.py 에서 분리 (2026-08-17, 1500줄 규칙). 세 티어의 조회·저장 엔드포인트는
서로 같은 모양이라 한 덩어리로 응집한다 — 경로 상수·프로바이더 캐시 무효화·그리고
**키를 .env 로 보내는 규칙**을 공유한다.

★자격증명: 저장으로 들어온 apiKey 는 티어 json 이 아니라 `.env` 로 간다
(model_resolver.set_env_key). 보관소는 하나다 — 도구·데이터 키가 이미 전부 거기 산다.
"""
import logging

from fastapi import APIRouter, HTTPException
from typing import Dict, Any

from model_resolver import (
    SYSTEM_AI_CONFIG_PATH,
    LIGHTWEIGHT_AI_CONFIG_PATH,
    MIDTIER_AI_CONFIG_PATH,
    UNCONSCIOUS_AI_CONFIG_PATH,
    env_key_for_provider, default_model_config, read_model_config,
    write_model_config, merge_model_config,
)

logger = logging.getLogger(__name__)
router = APIRouter()
_MODEL_PROVIDERS = ("google", "anthropic", "openai", "openrouter", "deepseek",
                    "claude_code", "codex")


# ============ 시스템 AI 설정 API ============

@router.get("/codex/models")
async def get_codex_models():
    """설치된 Codex가 공개한 모델 목록. 캐시가 없어도 직접 입력은 가능하다."""
    from providers.codex import list_available_models
    return {"items": list_available_models()}


def _with_provider_memory(config: dict) -> dict:
    """비밀은 숨기고, provider별 모델 기억과 키 존재 여부만 UI에 투영한다."""
    out = dict(config)
    out.pop("api_key", None)
    out.pop("providerApiKeys", None)
    models = dict(out.get("providerModels") or {})
    provider, model = out.get("provider", ""), out.get("model", "")
    if provider and model:
        models.setdefault(provider, model)  # 옛 단일-provider 설정의 무손실 이관
    out.update(apiKey="", providerModels=models,
               providerHasApiKey={p: bool(env_key_for_provider(p)) for p in _MODEL_PROVIDERS})
    return out


def get_default_system_ai_config() -> dict:
    return {**default_model_config("고급"), "role": ""}


@router.get("/system-ai")
async def get_system_ai_config():
    """전역 시스템 AI 설정 조회"""
    try:
        config = read_model_config(SYSTEM_AI_CONFIG_PATH, get_default_system_ai_config(), strict=True)
        return {"config": _with_provider_memory(config)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/system-ai")
async def update_system_ai_config(config: Dict[str, Any]):
    """전역 시스템 AI 설정 저장"""
    try:
        existing = read_model_config(SYSTEM_AI_CONFIG_PATH, strict=True)
        config_dict = merge_model_config(config, existing, get_default_system_ai_config(), with_role=True)
        write_model_config(SYSTEM_AI_CONFIG_PATH, config_dict)
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
    return {**default_model_config("경량")}


def _load_lightweight_config() -> dict:
    """경량 AI 설정 로드 (하위호환: unconscious_ai_config.json 폴백)"""
    return read_model_config(LIGHTWEIGHT_AI_CONFIG_PATH, get_default_lightweight_ai_config(),
                             fallback_path=UNCONSCIOUS_AI_CONFIG_PATH, strict=True)


@router.get("/lightweight-ai")
async def get_lightweight_ai_config():
    """경량 AI 설정 조회"""
    try:
        return {"config": _with_provider_memory(_load_lightweight_config())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/lightweight-ai")
async def update_lightweight_ai_config(config: Dict[str, Any]):
    """경량 설정 저장. 옛 파일은 남기고 새 경량 파일을 정본으로 쓴다."""
    try:
        config_dict = merge_model_config(config, _load_lightweight_config(), get_default_lightweight_ai_config())
        write_model_config(LIGHTWEIGHT_AI_CONFIG_PATH, config_dict)
        try:
            from consciousness_agent import reset_lightweight_provider
            reset_lightweight_provider()
        except Exception as cache_err:
            logger.warning("경량 provider 캐시 초기화 실패: %s", cache_err)
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
    return {**default_model_config("중급")}


@router.get("/midtier-ai")
async def get_midtier_ai_config():
    """중급 AI 설정 조회"""
    try:
        config = read_model_config(MIDTIER_AI_CONFIG_PATH, get_default_midtier_ai_config(), strict=True)
        return {"config": _with_provider_memory(config)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/midtier-ai")
async def update_midtier_ai_config(config: Dict[str, Any]):
    """중급 AI 설정 저장. 저장 후 provider 캐시 무효화하여 즉시 반영."""
    try:
        existing = read_model_config(MIDTIER_AI_CONFIG_PATH, strict=True)
        config_dict = merge_model_config(config, existing, get_default_midtier_ai_config())
        write_model_config(MIDTIER_AI_CONFIG_PATH, config_dict)

        # 캐시 무효화 — 다음 호출 시 새 config로 provider 재생성
        try:
            from consciousness_agent import reset_midtier_provider
            reset_midtier_provider()
        except Exception as cache_err:
            print(f"[midtier-ai] 캐시 무효화 경고: {cache_err}")

        return {"status": "saved", "config": _with_provider_memory(config_dict)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
