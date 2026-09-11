"""WebSocket 인증·수신·명령 분기. 대화 실행은 chat_streams 서비스가 소유한다."""
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from websocket_manager import manager, set_launcher_ws, clear_launcher_ws
import chat_streams as streams
import chat_runs as runs

router = APIRouter()


def init_manager(pm):
    streams.init_manager(pm)


async def _authorize_websocket(websocket: WebSocket) -> bool:
    """HTTP와 같은 로컬/원격·세션 판정. HTTP 미들웨어는 WS에 적용되지 않는다."""
    try:
        from api_launcher_web import is_external_request, verify_session
        if not is_external_request(websocket) or verify_session(websocket):
            return True
    except Exception as exc:
        print(f"[WS] 인증 판정 실패: {type(exc).__name__}")
    await websocket.close(code=1008, reason="원격 런처 로그인이 필요합니다.")
    return False


@router.websocket("/ws/launcher")
async def websocket_launcher(websocket: WebSocket):
    """런처 전용 WebSocket — 백엔드→런처 명령 전달 채널"""
    if not await _authorize_websocket(websocket):
        return
    await websocket.accept()
    set_launcher_ws(websocket, asyncio.get_running_loop())
    print("[WS] Launcher 연결됨")

    try:
        while True:
            # Launcher→백엔드 메시지 (ping/ack 등)
            data = await websocket.receive_json()
            if not await _authorize_websocket(websocket):
                break
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        clear_launcher_ws(websocket)
        print("[WS] Launcher 연결 해제")


# ============ WebSocket 채팅 ============

@router.websocket("/ws/chat/{client_id}")
async def websocket_chat(websocket: WebSocket, client_id: str):
    """채팅 WebSocket 엔드포인트"""
    if not await _authorize_websocket(websocket):
        return
    print(f"[WS] 연결: {client_id}")
    await manager.connect(websocket, client_id)

    try:
        while True:
            data = await websocket.receive_json()
            if manager.active_connections.get(client_id) is not websocket:
                await websocket.close(code=1000, reason="연결이 교체되었습니다")
                break
            if not await _authorize_websocket(websocket):
                manager.disconnect(client_id, websocket)
                break
            message_type = data.get("type", "chat")

            if message_type == "chat":
                if runs.registry.owned(client_id, websocket) is not None:
                    await streams.accept_stream_steer(client_id, data, data.get("agent_name", ""))
                else:
                    await streams.handle_chat_message(client_id, data)
            elif message_type in {"chat_stream", "system_ai_stream"}:
                target = "system_ai" if message_type == "system_ai_stream" else data.get("agent_name", "")
                if runs.registry.owned(client_id, websocket) is not None:
                    await streams.accept_stream_steer(client_id, data, target)
                else:
                    handler = (streams.handle_system_ai_chat_stream if message_type == "system_ai_stream"
                               else streams.handle_chat_message_stream)
                    try:
                        runs.registry.start(handler, client_id, data, websocket, manager)
                    except __import__("runtime_work").AdmissionClosed as exc:
                        await manager.send_message(client_id, {"type": "error", "content": str(exc), "executed": False})
            elif message_type == "cancel":
                # 중단 요청 처리
                runs.registry.cancel(client_id, websocket)
                print(f"[WS] 중단 요청: {client_id}")
                await manager.send_message(client_id, {"type": "cancelled"})
            elif message_type == "ping":
                await manager.send_message(client_id, {"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(client_id, websocket)
        print(f"[WS] 정상 연결 해제: {client_id}")
    except Exception as e:
        error_msg = str(e)
        # 연결 관련 에러인 경우에만 disconnect
        if "closed" in error_msg.lower() or "disconnect" in error_msg.lower() or "connection" in error_msg.lower():
            print(f"[WS] 연결 에러로 해제: {client_id} - {e}")
            manager.disconnect(client_id, websocket)
        else:
            # 일시적 에러는 로그만 남기고 루프 계속 (연결 유지)
            print(f"[WS 에러] {client_id}: {e} (연결 유지 시도)")
            # 하지만 여기서는 while 루프가 끝나므로 결국 연결 해제됨
            manager.disconnect(client_id, websocket)
    finally:
        # 조향 태스크 레지스트리 정리 — 스트림 태스크 자체는 계속 돌게 둔다(백그라운드
        # 완주가 기존 계약: 타임아웃 후에도 작업은 완료되어 대화 저장·재접속 회수).
        manager.disconnect(client_id, websocket)
        runs.registry.detach(client_id, websocket)
