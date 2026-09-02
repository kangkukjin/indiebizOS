"""api_onboarding.py — 첫 성공 온보딩 표면 (2026-09-02, docs/FIRST_SUCCESS_AND_UPGRADE_GATE_HANDOFF.md ①)

    GET  /system-ai/candidates          이 기계가 이미 가진 AI 후보 (통화 = {items:[...]})
    POST /system-ai/probe               {provider, model, api_key?} → 실응답 검증 (저장 안 함)
    GET  /system-ai/onboarding          온보딩 상태 + 현재 설정의 준비 판정
    POST /system-ai/onboarding/dismiss  건너뜀 기록

로컬 전용 — probe 가 키를 받는다. is_public_remote_path 에 등록하지 말 것.
새 IBL 낱말 없음(표면 기능). 어휘로 승격하지 말 것.
"""
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

import ai_candidates
import onboarding_state

router = APIRouter()


@router.get("/system-ai/candidates")
async def get_candidates():
    try:
        items = await run_in_threadpool(ai_candidates.detect_candidates)
    except ValueError as e:      # 카탈로그가 깨짐 — 부재가 아니라 신고
        raise HTTPException(status_code=500, detail=f"ai_provider_catalog.yaml 손상: {e}")
    return {"items": items}


@router.post("/system-ai/probe")
async def probe_model(body: Dict[str, Any]):
    provider = str(body.get("provider") or "")
    model = str(body.get("model") or "")
    api_key = str(body.get("api_key") or body.get("apiKey") or "")
    timeout_s = float(body.get("timeout_s") or 60)
    return await run_in_threadpool(ai_candidates.probe, provider, model, api_key, timeout_s)


@router.get("/system-ai/onboarding")
async def get_onboarding():
    from api_system_ai import _system_ai_readiness, load_system_ai_config
    state = onboarding_state.get_state()
    return {"state": state, "completed": bool(state.get("first_reply_at")),
            "readiness": _system_ai_readiness(load_system_ai_config())}


@router.post("/system-ai/onboarding/dismiss")
async def dismiss_onboarding():
    return {"state": onboarding_state.mark_dismissed()}
