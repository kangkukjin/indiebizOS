"""api_prompt_composition.py — 프롬프트 구성 표면 라우터 (2026-09-13)

런처 안경 메뉴 '프롬프트 구성' 이 부른다. 조립 명세와 실제 조립은 cognition/prompt_composition 이
소유하고, 여기는 HTTP 껍데기만. 로컬 전용 — is_public_remote_path 등록 금지(프롬프트·기억 본문이 실린다).
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import prompt_composition as PC

router = APIRouter(prefix="/prompt-composition", tags=["prompt-composition"])


class AssembleRequest(BaseModel):
    agent_id: str
    sample_message: Optional[str] = None
    project_id: Optional[str] = None


@router.get("/agents")
def prompt_composition_agents():
    """에이전트 종류 목록 + 프로젝트 목록 + 기본 샘플 메시지."""
    return PC.list_agents()


@router.post("/assemble")
def prompt_composition_assemble(req: AssembleRequest):
    """한 에이전트의 프롬프트를 샘플 메시지로 실제 조립해 조각별로 돌려준다(LLM 0).

    sync def — 해마 회상(임베딩 검색)이 블로킹이라 FastAPI 스레드풀에서 돈다(recall_preview 와 같은 이유).
    """
    try:
        return PC.assemble(req.agent_id, req.sample_message or "", req.project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"모르는 에이전트: {req.agent_id}")
