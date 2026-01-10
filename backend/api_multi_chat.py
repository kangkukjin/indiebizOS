"""
api_multi_chat.py - 다중채팅방 API
IndieBiz OS
"""

from typing import List, Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# 매니저 인스턴스
multi_chat_manager = None


class CreateRoomRequest(BaseModel):
    name: str
    description: str = ""


class AddAgentRequest(BaseModel):
    project_id: str
    agent_id: str


class SendMessageRequest(BaseModel):
    message: str
    response_count: int = 2  # 응답할 에이전트 수


class UpdatePositionRequest(BaseModel):
    x: int
    y: int


class ActivateAllRequest(BaseModel):
    tools: List[str] = []


def init_manager(ai_config: dict = None):
    """매니저 인스턴스 초기화"""
    global multi_chat_manager
    from multi_chat_manager import MultiChatManager
    multi_chat_manager = MultiChatManager(ai_config=ai_config)


def get_manager():
    """매니저 인스턴스 반환"""
    if multi_chat_manager is None:
        init_manager()
    return multi_chat_manager


# ============ 채팅방 관리 ============

@router.get("/multi-chat/rooms")
async def list_rooms():
    """모든 채팅방 목록"""
    try:
        manager = get_manager()
        rooms = manager.list_rooms()
        return {"rooms": rooms}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/multi-chat/rooms")
async def create_room(request: CreateRoomRequest):
    """채팅방 생성"""
    try:
        manager = get_manager()
        room = manager.create_room(request.name, request.description)
        return {"room": room}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/multi-chat/rooms/{room_id}")
async def get_room(room_id: str):
    """채팅방 정보"""
    try:
        manager = get_manager()
        room = manager.get_room(room_id)
        if not room:
            raise HTTPException(status_code=404, detail="채팅방을 찾을 수 없습니다")

        # 참여자 정보 추가
        participants = manager.get_room_participants(room_id)
        room['participants'] = participants

        return {"room": room}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/multi-chat/rooms/{room_id}")
async def delete_room(room_id: str):
    """채팅방 삭제"""
    try:
        manager = get_manager()
        success = manager.delete_room(room_id)
        if not success:
            raise HTTPException(status_code=404, detail="채팅방을 찾을 수 없습니다")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/multi-chat/rooms/{room_id}/position")
async def update_room_position(room_id: str, request: UpdatePositionRequest):
    """채팅방 아이콘 위치 업데이트"""
    try:
        manager = get_manager()
        success = manager.update_room_position(room_id, request.x, request.y)
        if not success:
            raise HTTPException(status_code=404, detail="채팅방을 찾을 수 없습니다")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 에이전트 소환 ============

@router.get("/multi-chat/available-agents")
async def list_available_agents():
    """소환 가능한 에이전트 목록 (모든 프로젝트에서)"""
    try:
        manager = get_manager()
        agents = manager.list_available_agents()
        return {"agents": agents}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/multi-chat/rooms/{room_id}/participants")
async def get_room_participants(room_id: str):
    """채팅방 참여자 목록"""
    try:
        manager = get_manager()
        participants = manager.get_room_participants(room_id)
        return {"participants": participants}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/multi-chat/rooms/{room_id}/participants")
async def add_agent_to_room(room_id: str, request: AddAgentRequest):
    """채팅방에 에이전트 추가"""
    try:
        manager = get_manager()
        success = manager.add_agent_to_room(
            room_id=room_id,
            project_id=request.project_id,
            agent_id=request.agent_id
        )
        if not success:
            raise HTTPException(status_code=400, detail="에이전트 추가 실패 (이미 참여 중이거나 존재하지 않음)")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/multi-chat/rooms/{room_id}/participants/{agent_name}")
async def remove_agent_from_room(room_id: str, agent_name: str):
    """채팅방에서 에이전트 제거"""
    try:
        manager = get_manager()
        success = manager.remove_agent_from_room(room_id, agent_name)
        if not success:
            raise HTTPException(status_code=404, detail="참여자를 찾을 수 없습니다")
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 대화 ============

@router.get("/multi-chat/rooms/{room_id}/messages")
async def get_messages(room_id: str, limit: int = 50):
    """채팅방 메시지 조회"""
    try:
        manager = get_manager()
        messages = manager.get_messages(room_id, limit)
        return {"messages": messages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/multi-chat/rooms/{room_id}/messages")
async def send_message(room_id: str, request: SendMessageRequest):
    """
    메시지 전송 및 에이전트 응답 받기

    - @에이전트이름 으로 특정 에이전트 지목 가능
    - 지목 없으면 response_count 만큼 랜덤 응답
    """
    try:
        manager = get_manager()

        # 방 존재 확인
        room = manager.get_room(room_id)
        if not room:
            raise HTTPException(status_code=404, detail="채팅방을 찾을 수 없습니다")

        # 메시지 전송 및 응답 받기
        responses = manager.send_message(
            room_id=room_id,
            message=request.message,
            response_count=request.response_count
        )

        return {
            "user_message": request.message,
            "responses": responses
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/multi-chat/rooms/{room_id}/messages")
async def clear_messages(room_id: str):
    """채팅방 메시지 전체 삭제"""
    try:
        manager = get_manager()
        count = manager.clear_messages(room_id)
        return {"deleted_count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 에이전트 활성화/비활성화 ============

@router.post("/multi-chat/rooms/{room_id}/activate-all")
async def activate_all_agents(room_id: str, request: ActivateAllRequest):
    """
    채팅방의 모든 에이전트 활성화
    - 선택된 도구를 모든 에이전트에게 할당
    """
    try:
        manager = get_manager()
        room = manager.get_room(room_id)
        if not room:
            raise HTTPException(status_code=404, detail="채팅방을 찾을 수 없습니다")

        activated = manager.activate_all_agents(room_id, request.tools)
        return {"success": True, "activated": activated}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/multi-chat/rooms/{room_id}/deactivate-all")
async def deactivate_all_agents(room_id: str):
    """채팅방의 모든 에이전트 비활성화"""
    try:
        manager = get_manager()
        deactivated = manager.deactivate_all_agents(room_id)
        return {"success": True, "deactivated": deactivated}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
