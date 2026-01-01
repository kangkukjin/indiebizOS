"""
api_prompt_generator.py - 프롬프트 생성 API
IndieBiz OS Core
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter(prefix="/prompt-generator")

# 프로젝트 매니저는 api.py에서 주입
project_manager = None


def init_manager(pm):
    global project_manager
    project_manager = pm


class AgentInfo(BaseModel):
    name: str
    type: str = "internal"
    description: str = ""


class GenerateRequest(BaseModel):
    project_purpose: str
    agents: List[AgentInfo]
    ai_config: dict  # {"provider": "anthropic", "api_key": "...", "model": "..."}
    project_id: Optional[str] = None  # 저장할 프로젝트 ID


@router.post("/generate")
async def generate_prompts(request: GenerateRequest):
    """프롬프트 자동 생성"""
    from prompt_generator import PromptGenerator

    try:
        generator = PromptGenerator(request.ai_config)

        agents = [{"name": a.name, "type": a.type, "description": a.description} for a in request.agents]

        result = generator.generate_prompts(
            project_purpose=request.project_purpose,
            agents=agents
        )

        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        # 프로젝트에 저장 요청이 있으면 저장
        if request.project_id and project_manager:
            project_path = project_manager.get_project_path(request.project_id)
            generator.save_to_project(str(project_path), result)
            result["saved_to"] = str(project_path)

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
