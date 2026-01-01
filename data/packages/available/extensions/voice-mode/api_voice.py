"""
api_voice.py - 음성 모드 관련 API
"""

from typing import Dict, Any

from fastapi import APIRouter

from api_models import VoiceModeRequest, VoiceSpeakRequest
from websocket_manager import manager

router = APIRouter()

# 음성 모드 상태 관리 (프로젝트별, 에이전트별)
voice_mode_state: Dict[str, Dict[str, Any]] = {}
# 구조: { "project_id:agent_id": { "active": bool, "listening": bool, "thread": thread } }


# ============ 음성 모드 API ============

@router.post("/voice/start")
async def start_voice_mode(request: VoiceModeRequest):
    """음성 모드 시작"""
    import threading
    from tool_voice_io import get_voice_io

    key = f"{request.project_id}:{request.agent_id}"

    # 이미 활성화된 경우
    if key in voice_mode_state and voice_mode_state[key].get("active"):
        return {"status": "already_active", "message": "음성 모드가 이미 활성화되어 있습니다."}

    try:
        # VoiceIO 초기화 (Whisper 모델 로드)
        voice_io = get_voice_io()

        voice_mode_state[key] = {
            "active": True,
            "listening": False,
            "project_id": request.project_id,
            "agent_id": request.agent_id
        }

        # 시작 알림 음성 출력
        voice_io.speak("음성 모드가 시작되었습니다.")

        return {
            "status": "started",
            "message": "음성 모드가 시작되었습니다."
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/voice/stop")
async def stop_voice_mode(request: VoiceModeRequest):
    """음성 모드 중지"""
    from tool_voice_io import get_voice_io

    key = f"{request.project_id}:{request.agent_id}"

    if key not in voice_mode_state or not voice_mode_state[key].get("active"):
        return {"status": "not_active", "message": "음성 모드가 활성화되어 있지 않습니다."}

    try:
        voice_io = get_voice_io()

        # 상태 업데이트
        voice_mode_state[key]["active"] = False
        voice_mode_state[key]["listening"] = False

        # 종료 알림 음성 출력
        voice_io.speak("음성 모드가 종료되었습니다.")

        # 상태 제거
        del voice_mode_state[key]

        return {
            "status": "stopped",
            "message": "음성 모드가 종료되었습니다."
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/voice/listen")
async def voice_listen(request: VoiceModeRequest):
    """음성 입력 받기 (한 번)"""
    from tool_voice_io import tool_voice_io

    key = f"{request.project_id}:{request.agent_id}"

    # 음성 모드가 활성화되어 있는지 확인
    if key not in voice_mode_state or not voice_mode_state[key].get("active"):
        return {"status": "error", "message": "음성 모드가 활성화되어 있지 않습니다."}

    try:
        # 듣기 상태 표시
        voice_mode_state[key]["listening"] = True

        # WebSocket으로 듣기 시작 알림
        await manager.broadcast({
            "type": "voice_status",
            "status": "listening",
            "project_id": request.project_id,
            "agent_id": request.agent_id
        })

        # 음성 입력 받기 (동기 호출)
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: tool_voice_io("listen", timeout=10)
        )

        voice_mode_state[key]["listening"] = False

        # WebSocket으로 듣기 완료 알림
        await manager.broadcast({
            "type": "voice_status",
            "status": "idle",
            "project_id": request.project_id,
            "agent_id": request.agent_id,
            "text": result[3].get("text") if result[3].get("status") == "success" else None
        })

        return result[3]  # {status, text, message}

    except Exception as e:
        voice_mode_state[key]["listening"] = False
        return {"status": "error", "message": str(e)}


@router.post("/voice/speak")
async def voice_speak(request: VoiceSpeakRequest):
    """텍스트를 음성으로 출력"""
    from tool_voice_io import tool_voice_io

    try:
        # WebSocket으로 말하기 시작 알림
        await manager.broadcast({
            "type": "voice_status",
            "status": "speaking"
        })

        # 음성 출력 (동기 호출)
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: tool_voice_io("speak", text=request.text)
        )

        # WebSocket으로 말하기 완료 알림
        await manager.broadcast({
            "type": "voice_status",
            "status": "idle"
        })

        return result[3]  # {status, message}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/voice/status")
async def get_voice_status(project_id: str, agent_id: str):
    """음성 모드 상태 조회"""
    key = f"{project_id}:{agent_id}"

    if key not in voice_mode_state:
        return {
            "active": False,
            "listening": False
        }

    return {
        "active": voice_mode_state[key].get("active", False),
        "listening": voice_mode_state[key].get("listening", False)
    }
