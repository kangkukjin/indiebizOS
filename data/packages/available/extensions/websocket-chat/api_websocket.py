"""
api_websocket.py - WebSocket 채팅 관련 API
"""

import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import yaml

from websocket_manager import manager
from conversation_db import ConversationDB
from my_conversations import MyConversations

router = APIRouter()

# 매니저 인스턴스
project_manager = None

# 에이전트 러너 참조 (api_agents에서 가져옴)
def get_agent_runners():
    from api_agents import get_agent_runners as _get_agent_runners
    return _get_agent_runners()


def init_manager(pm):
    """매니저 인스턴스 초기화"""
    global project_manager
    project_manager = pm


# ============ WebSocket 채팅 ============

@router.websocket("/ws/chat/{client_id}")
async def websocket_chat(websocket: WebSocket, client_id: str):
    """채팅 WebSocket 엔드포인트"""
    print(f"[WS-DEBUG] 연결 시도: {client_id}")
    await manager.connect(websocket, client_id)
    print(f"[WS-DEBUG] 연결 완료, 현재 연결: {list(manager.active_connections.keys())}")

    try:
        while True:
            data = await websocket.receive_json()

            # 메시지 처리
            message_type = data.get("type", "chat")

            if message_type == "chat":
                # AI 응답 생성 (스트리밍)
                await handle_chat_message(client_id, data)
            elif message_type == "ping":
                await manager.send_message(client_id, {"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(client_id)
    except Exception as e:
        print(f"[WS 에러] {e}")
        manager.disconnect(client_id)


async def handle_chat_message(client_id: str, data: dict):
    """채팅 메시지 처리 및 AI 응답 (실행 중인 AgentRunner 사용)"""
    from tools import set_current_agent_id

    message = data.get("message", "")
    agent_name = data.get("agent_name", "")
    project_id = data.get("project_id", "")
    images = data.get("images", [])  # 이미지 데이터 배열 [{base64, media_type}, ...]

    try:
        # 시작 알림
        await manager.send_message(client_id, {
            "type": "start",
            "agent": agent_name
        })

        # 프로젝트 경로
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
                "message": f"에이전트 '{agent_name}'이(가) 실행 중이 아닙니다. '시작' 버튼을 눌러주세요."
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

        # 사용자와 연결된 에이전트로 표시 (내부 메시지 응답을 GUI로 전달하기 위해)
        runner._is_connected_to_user = True

        # 현재 에이전트 ID 설정 (call_agent가 올바르게 작동하도록)
        set_current_agent_id(agent_id)

        # 대화 DB 및 히스토리 로드
        my_conv = MyConversations("kukjin", "human")
        my_conv.db = ConversationDB(str(project_path / "conversations.db"))

        # 에이전트를 이웃으로 찾기
        target_agent_id = my_conv.find_agent_by_name(agent_name)
        if not target_agent_id:
            # 에이전트 등록
            with my_conv.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO agents (name, type)
                    VALUES (?, 'ai_agent')
                """, [agent_name])
                conn.commit()
                target_agent_id = cursor.lastrowid

        # DB에서 히스토리 로드
        raw_history = my_conv.get_history_for_ai(target_agent_id)

        # rules.json에서 규칙 히스토리 로드
        rules = MyConversations.load_rules_history(agent_name, str(project_path))

        # 규칙 + 대화 히스토리 합치기
        history = rules + raw_history

        # 사용자 메시지 DB 저장
        my_conv.send_message(
            to_agent_id=target_agent_id,
            content=message,
            contact_type='gui'
        )

        # 시스템 자동화: 사용자 메시지 수신 시 자동으로 task 생성
        task_id = f"task_{uuid.uuid4().hex[:8]}"

        # task DB에 저장 (client_id 포함 - 나중에 WebSocket으로 응답 전송용)
        try:
            my_conv.db.create_task(
                task_id=task_id,
                requester="kukjin@gui",
                requester_channel="gui",
                original_request=message,
                delegated_to=agent_name,
                ws_client_id=client_id
            )
            print(f"   [WS] task 자동 생성: {task_id} (client_id: {client_id})")
        except Exception as task_err:
            print(f"   [WS] task 생성 실패: {task_err}")

        # 실행 중인 AgentRunner의 AI 사용
        ai_agent = runner.ai

        # AI 응답 생성 (task_id를 직접 전달하여 스레드 간 공유)
        response = ai_agent.process_message_with_history(
            message_content=message,
            from_email="kukjin@gui",
            history=history,
            reply_to="kukjin@gui",
            task_id=task_id,  # 스레드 간 전달을 위해 직접 전달
            images=images  # 이미지 데이터 전달
        )

        # AI 응답 DB 저장
        message_id = my_conv.receive_message(
            from_agent_id=target_agent_id,
            content=response,
            contact_type='gui'
        )

        # 응답 전송 (message_id 포함 - 프론트엔드 폴링 중복 방지용)
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
