"""
api_websocket.py - WebSocket 채팅 API
IndieBiz OS Core
"""

import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import yaml

from websocket_manager import manager
from conversation_db import ConversationDB

router = APIRouter()

# 매니저 인스턴스
project_manager = None


def get_agent_runners():
    from api_agents import get_agent_runners as _get
    return _get()


def init_manager(pm):
    global project_manager
    project_manager = pm


# ============ WebSocket 채팅 ============

@router.websocket("/ws/chat/{client_id}")
async def websocket_chat(websocket: WebSocket, client_id: str):
    """채팅 WebSocket 엔드포인트"""
    print(f"[WS] 연결: {client_id}")
    await manager.connect(websocket, client_id)

    try:
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type", "chat")

            if message_type == "chat":
                await handle_chat_message(client_id, data)
            elif message_type == "ping":
                await manager.send_message(client_id, {"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(client_id)
        print(f"[WS] 연결 해제: {client_id}")
    except Exception as e:
        print(f"[WS 에러] {e}")
        manager.disconnect(client_id)


async def handle_chat_message(client_id: str, data: dict):
    """채팅 메시지 처리"""
    message = data.get("message", "")
    agent_name = data.get("agent_name", "")
    project_id = data.get("project_id", "")
    images = data.get("images", [])

    try:
        # 시작 알림
        await manager.send_message(client_id, {
            "type": "start",
            "agent": agent_name
        })

        project_path = project_manager.get_project_path(project_id)

        # 에이전트 설정 로드
        agents_file = project_path / "agents.yaml"
        if not agents_file.exists():
            await manager.send_message(client_id, {
                "type": "error",
                "message": "에이전트 설정을 찾을 수 없습니다."
            })
            return

        with open(agents_file, 'r', encoding='utf-8') as f:
            agents_data = yaml.safe_load(f)

        # 에이전트 찾기
        agent_config = None
        agent_id = None
        for agent in agents_data.get("agents", []):
            if agent.get("name") == agent_name:
                agent_config = agent
                agent_id = agent.get("id")
                break

        if not agent_config:
            await manager.send_message(client_id, {
                "type": "error",
                "message": f"에이전트 '{agent_name}'을(를) 찾을 수 없습니다."
            })
            return

        # 실행 중인 AgentRunner 확인
        agent_runners = get_agent_runners()
        if project_id not in agent_runners or agent_id not in agent_runners[project_id]:
            await manager.send_message(client_id, {
                "type": "error",
                "message": f"에이전트 '{agent_name}'이(가) 실행 중이 아닙니다. 먼저 시작해주세요."
            })
            return

        runner_info = agent_runners[project_id][agent_id]
        runner = runner_info.get("runner")

        if not runner or not runner.ai:
            await manager.send_message(client_id, {
                "type": "error",
                "message": f"에이전트 '{agent_name}'의 AI가 준비되지 않았습니다."
            })
            return

        # 대화 DB
        db = ConversationDB(str(project_path / "conversations.db"))

        # 사용자 및 에이전트 ID
        user_id = db.get_or_create_agent("user", "human")
        target_agent_id = db.get_or_create_agent(agent_name, "ai_agent")

        # 히스토리 로드
        history = db.get_history_for_ai(target_agent_id, user_id)

        # 사용자 메시지 저장
        db.save_message(user_id, target_agent_id, message)

        # 태스크 생성
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        try:
            db.create_task(
                task_id=task_id,
                requester="user@gui",
                requester_channel="gui",
                original_request=message,
                delegated_to=agent_name,
                ws_client_id=client_id
            )
        except Exception as e:
            print(f"[WS] 태스크 생성 실패: {e}")

        # AI 응답 생성
        response = runner.ai.process_message_with_history(
            message_content=message,
            from_email="user@gui",
            history=history,
            reply_to="user@gui",
            task_id=task_id,
            images=images
        )

        # AI 응답 저장
        message_id = db.save_message(target_agent_id, user_id, response)

        # 응답 전송
        await manager.send_message(client_id, {
            "type": "response",
            "content": response,
            "agent": agent_name,
            "message_id": message_id
        })

        # 완료 알림
        await manager.send_message(client_id, {
            "type": "end",
            "agent": agent_name
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        await manager.send_message(client_id, {
            "type": "error",
            "message": str(e)
        })
