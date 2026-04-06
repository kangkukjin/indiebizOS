"""
api_system_ai.py - 시스템 AI 대화 API
IndieBiz OS Core

시스템 AI는 IndieBiz의 관리자이자 안내자입니다:
- 첫 실행 시 사용법 안내
- 도구 패키지 분석, 설치, 제거
- 에이전트 생성, 수정, 삭제 도움
- 오류 진단 및 해결

모듈화:
- system_ai_core.py: AI 에이전트 생성, 메시지 처리, 의식 통합, 설정
- system_ai_tools.py: 도구 정의, 프로젝트 에이전트/이벤트/스위치 실행
- system_ai_plans.py: 플랜 레지스트리, 플랜/스케줄 실행
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# 메모리 관련
from system_ai_memory import (
    load_user_profile,
    save_conversation,
    get_recent_conversations,
    get_history_for_ai,
    get_memory_context,
    save_memory,
    get_memories
)
# 시스템 문서 관련
from system_docs import (
    read_doc,
    init_all_docs
)

# === 하위 모듈 re-export (기존 import 호환성 유지) ===
from system_ai_core import (
    load_system_ai_config,
    save_system_ai_config,
    create_system_ai_agent,
    get_system_ai_runner,
    process_system_ai_message,
    process_system_ai_message_stream,
    execute_system_tool,
    get_system_prompt,
    get_anthropic_tools,
    get_all_system_ai_tools,
    SYSTEM_AI_CONFIG_PATH,
    DATA_PATH,
    BACKEND_PATH,
)

from system_ai_tools import (
    _execute_list_project_agents,
    _execute_call_project_agent,
    _execute_manage_events,
    _execute_list_switches,
)

from system_ai_plans import (
    register_plan_step,
    on_agent_plan_step_complete,
    _execute_schedule,
    _execute_create_plan,
    _update_plan_status,
    _parse_plan_steps,
    _execute_plan,
)

router = APIRouter()

# 시스템 AI 역할 파일 경로
SYSTEM_AI_ROLE_PATH = DATA_PATH / "system_ai_role.txt"


# ============ Pydantic 모델 ============

class ImageData(BaseModel):
    base64: str
    media_type: str


class ChatMessage(BaseModel):
    message: str
    context: Optional[Dict[str, Any]] = None
    images: Optional[List[ImageData]] = None


class ChatResponse(BaseModel):
    response: str
    timestamp: str
    provider: str
    model: str


class PromptConfigUpdate(BaseModel):
    selected_template: Optional[str] = None


class RolePromptUpdate(BaseModel):
    content: str


# ============ 시스템 문서 초기화 플래그 ============
_docs_initialized = False


# ============ 채팅 API ============

@router.post("/system-ai/chat", response_model=ChatResponse)
async def chat_with_system_ai(chat: ChatMessage):
    """
    시스템 AI와 대화

    **통합 아키텍처**: AIAgent 클래스를 사용하여 프로젝트 에이전트와
    동일한 프로바이더 코드를 공유합니다. 모든 프로바이더(Anthropic, OpenAI,
    Google, Ollama)가 자동으로 지원됩니다.

    **태스크 기반 처리**: 시스템 AI도 태스크를 생성하고 위임 체인을 지원합니다.
    - 위임이 없으면 → 즉시 응답
    - 위임이 있으면 → "위임 중" 응답, 결과는 WebSocket으로 전송
    """
    import uuid
    from thread_context import set_current_task_id, clear_current_task_id, did_call_agent, clear_called_agent
    from system_ai_memory import create_task as create_system_ai_task

    global _docs_initialized

    config = load_system_ai_config()

    if not config.get("enabled", True):
        raise HTTPException(status_code=400, detail="시스템 AI가 비활성화되어 있습니다.")

    api_key = config.get("apiKey", "")
    if not api_key:
        raise HTTPException(status_code=400, detail="API 키가 설정되지 않았습니다. 설정에서 API 키를 입력해주세요.")

    provider = config.get("provider", "anthropic")
    model = config.get("model", "claude-sonnet-4-20250514")

    # 시스템 문서 초기화 (서버 시작 후 최초 1회만)
    if not _docs_initialized:
        init_all_docs()
        _docs_initialized = True

    # 태스크 생성
    task_id = f"task_sysai_{uuid.uuid4().hex[:8]}"
    ws_client_id = chat.context.get("ws_client_id") if chat.context else None

    create_system_ai_task(
        task_id=task_id,
        requester="user@gui",
        requester_channel="gui",
        original_request=chat.message,
        delegated_to="system_ai",
        ws_client_id=ws_client_id
    )

    # 태스크 컨텍스트 설정
    set_current_task_id(task_id)
    clear_called_agent()

    # 최근 대화 히스토리 로드 (조회 + 역할 매핑 + Observation Masking 통합)
    history = get_history_for_ai(limit=7)

    # 이미지 데이터 변환
    images_data = None
    if chat.images:
        images_data = [{"base64": img.base64, "media_type": img.media_type} for img in chat.images]

    # 사용자 메시지 저장 (이미지 포함)
    save_conversation("user", chat.message, images=images_data)

    # AIAgent를 사용한 통합 처리 (모든 프로바이더 자동 지원)
    try:
        response_text, tool_images = process_system_ai_message(
            message=chat.message,
            history=history,
            images=images_data
        )
    except Exception as e:
        clear_current_task_id()
        clear_called_agent()
        raise HTTPException(status_code=500, detail=f"AI 응답 생성 실패: {str(e)}")

    # 위임 여부 확인
    called_another = did_call_agent()

    # 컨텍스트 정리
    clear_current_task_id()
    clear_called_agent()

    if called_another:
        # 위임이 발생함 → 결과는 나중에 WebSocket으로 전송
        return ChatResponse(
            response=f"[위임 중] 프로젝트 에이전트에게 작업을 위임했습니다. 결과는 잠시 후 도착합니다.\n\n{response_text}",
            timestamp=datetime.now().isoformat(),
            provider=provider,
            model=model
        )
    else:
        # 위임 없음 → 즉시 응답, 태스크 완료
        from system_ai_memory import complete_task as complete_system_ai_task
        complete_system_ai_task(task_id, response_text[:500])

        # AI 응답 저장 (도구 이미지 포함)
        save_conversation("assistant", response_text, images=tool_images)

        return ChatResponse(
            response=response_text,
            timestamp=datetime.now().isoformat(),
            provider=provider,
            model=model
        )


@router.get("/system-ai/welcome")
async def get_welcome_message():
    """
    첫 실행 시 환영 메시지
    (API 키 없이도 표시 가능한 정적 메시지)
    """
    return {
        "message": """안녕하세요! IndieBiz OS에 오신 걸 환영합니다.

저는 시스템 AI입니다. IndieBiz 사용을 도와드릴게요.

시작하려면 먼저 AI API 키를 설정해주세요:
1. 오른쪽 상단의 설정(⚙️) 버튼을 클릭
2. AI 프로바이더 선택 (Claude/GPT/Gemini)
3. API 키 입력

설정이 완료되면 저와 대화하면서 IndieBiz를 배워보세요!

무엇이든 물어보세요:
• "뭘 할 수 있어?"
• "새 프로젝트 만들어줘"
• "에이전트가 뭐야?"
• "도구 설치하려면?"
""",
        "needs_api_key": True
    }


@router.get("/system-ai/status")
async def get_system_ai_status():
    """시스템 AI 상태 확인"""
    config = load_system_ai_config()

    has_api_key = bool(config.get("apiKey", ""))

    return {
        "enabled": config.get("enabled", True),
        "provider": config.get("provider", "anthropic"),
        "model": config.get("model", "claude-sonnet-4-20250514"),
        "has_api_key": has_api_key,
        "ready": has_api_key and config.get("enabled", True)
    }


@router.get("/system-ai/providers")
async def get_available_providers():
    """사용 가능한 AI 프로바이더 목록"""
    return {
        "providers": [
            {
                "id": "anthropic",
                "name": "Anthropic Claude",
                "models": [
                    {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4 (추천)"},
                    {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet"},
                    {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku (빠름)"},
                ],
                "api_url": "https://console.anthropic.com"
            },
            {
                "id": "openai",
                "name": "OpenAI GPT",
                "models": [
                    {"id": "gpt-4o", "name": "GPT-4o (추천)"},
                    {"id": "gpt-4o-mini", "name": "GPT-4o Mini (빠름)"},
                    {"id": "gpt-4-turbo", "name": "GPT-4 Turbo"},
                ],
                "api_url": "https://platform.openai.com/api-keys"
            },
            {
                "id": "google",
                "name": "Google Gemini",
                "models": [
                    {"id": "gemini-2.0-flash-exp", "name": "Gemini 2.0 Flash (추천)"},
                    {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro"},
                    {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash (빠름)"},
                ],
                "api_url": "https://aistudio.google.com/apikey"
            }
        ]
    }


# ============ 메모리 관련 API ============

@router.get("/system-ai/conversations")
async def get_conversations(limit: int = 20):
    """시스템 AI 대화 이력 조회"""
    conversations = get_recent_conversations(limit)
    return {"conversations": conversations}


@router.get("/system-ai/conversations/recent")
async def get_conversations_recent(limit: int = 20):
    """시스템 AI 최근 대화 조회"""
    conversations = get_recent_conversations(limit)
    return {"conversations": conversations}


@router.get("/system-ai/conversations/dates")
async def get_conversation_dates():
    """대화가 있는 날짜 목록 조회 (날짜별 메시지 수 포함)"""
    import sqlite3
    from system_ai_memory import MEMORY_DB_PATH

    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT date(timestamp) as date, COUNT(*) as count
        FROM conversations
        GROUP BY date(timestamp)
        ORDER BY date DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    dates = [{"date": row[0], "count": row[1]} for row in rows if row[0]]
    return {"dates": dates}


@router.get("/system-ai/conversations/by-date/{date}")
async def get_conversations_by_date(date: str):
    """특정 날짜의 대화 조회"""
    import sqlite3
    from system_ai_memory import MEMORY_DB_PATH

    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, timestamp, role, content, summary, importance
        FROM conversations
        WHERE date(timestamp) = ?
        ORDER BY id ASC
    """, (date,))

    rows = cursor.fetchall()
    conn.close()

    conversations = []
    for row in rows:
        conversations.append({
            "id": row[0],
            "timestamp": row[1],
            "role": row[2],
            "content": row[3],
            "summary": row[4],
            "importance": row[5]
        })

    return {"conversations": conversations}


@router.delete("/system-ai/conversations")
async def clear_conversations():
    """시스템 AI 대화 이력 삭제"""
    import sqlite3
    from system_ai_memory import MEMORY_DB_PATH

    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM conversations")
    conn.commit()
    conn.close()

    return {"status": "cleared"}


# ============ 프롬프트 설정 API ============

@router.get("/system-ai/prompts/config")
async def get_prompt_config():
    """프롬프트 설정 조회"""
    config = load_system_ai_config()
    return {
        "selected_template": config.get("selected_template", "default")
    }


@router.put("/system-ai/prompts/config")
async def update_prompt_config(data: PromptConfigUpdate):
    """프롬프트 설정 업데이트"""
    config = load_system_ai_config()

    if data.selected_template is not None:
        config["selected_template"] = data.selected_template

    save_system_ai_config(config)
    return {"status": "updated", "config": {
        "selected_template": config.get("selected_template")
    }}


@router.get("/system-ai/prompts/role")
async def get_role_prompt():
    """역할 프롬프트 조회 (별도 파일에서 로드)"""
    if SYSTEM_AI_ROLE_PATH.exists():
        content = SYSTEM_AI_ROLE_PATH.read_text(encoding='utf-8')
    else:
        content = ""
    return {"content": content}


@router.put("/system-ai/prompts/role")
async def update_role_prompt(data: RolePromptUpdate):
    """역할 프롬프트 업데이트 (별도 파일에 저장)"""
    SYSTEM_AI_ROLE_PATH.write_text(data.content, encoding='utf-8')
    return {"status": "updated"}
