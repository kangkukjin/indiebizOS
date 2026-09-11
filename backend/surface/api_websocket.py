"""WebSocket 인증·수신·명령 분기. 대화 실행은 chat_streams 서비스가 소유한다."""
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from websocket_manager import manager, set_launcher_ws, clear_launcher_ws
import chat_streams as streams

router = APIRouter()
_stream_tasks: dict = {}


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
        clear_launcher_ws()
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
            if not await _authorize_websocket(websocket):
                manager.disconnect(client_id)
                break
            message_type = data.get("type", "chat")

            if message_type == "chat":
                await streams.handle_chat_message(client_id, data)
            elif message_type == "chat_stream":
                # (2026-08-15 조향 확장) 에이전트 스트림도 태스크로 — 시스템 AI 와 동일
                # 원리. 실행 중 같은 에이전트로 온 메시지 = 조향, 다른 에이전트 = 정직
                # 거절(같은 client 의 이벤트 스트림을 두 턴이 나눠 쓰는 혼선 방지).
                # 신원 안전 근거: run_stream 이 워커 스레드 안에서 클로저 변수로 신원을
                # 재설정하므로("별도 스레드이므로 컨텍스트 재설정") 태스크 교차와 무관.
                _prev_task = _stream_tasks.get(client_id)
                if _prev_task is not None and not _prev_task.done():
                    await streams.accept_stream_steer(client_id, data, data.get("agent_name", ""))
                else:
                    streams.clear_stream_target(client_id)
                    _t = asyncio.create_task(streams.handle_chat_message_stream(client_id, data))
                    _stream_tasks[client_id] = _t
                    _t.add_done_callback(lambda t: t.cancelled() or (
                        t.exception() and print(f"[WS] 에이전트 스트림 태스크 예외: {t.exception()}")))
            elif message_type == "system_ai_stream":
                # (2026-08-15 조향) 스트림을 태스크로 띄워 수신 루프를 비워 둔다 — 이전엔
                # await 가 루프를 막아 스트림 중 cancel·추가 메시지가 턴 종료까지 WS 버퍼에
                # 잠들었다(중단 버튼도 실은 스트림 중 무효였던 구조). 실행 중 도착한
                # system_ai_stream 은 새 턴이 아니라 **조향(steer)** 으로 접수된다 —
                # 같은 채팅창이 곧 조향 입력창(steer_inbox → 다음 도구 결과에 부록 배달).
                _prev_task = _stream_tasks.get(client_id)
                if _prev_task is not None and not _prev_task.done():
                    await streams.accept_stream_steer(client_id, data, "system_ai")
                else:
                    streams.clear_stream_target(client_id)
                    _t = asyncio.create_task(streams.handle_system_ai_chat_stream(client_id, data))
                    _stream_tasks[client_id] = _t
                    _t.add_done_callback(lambda t: t.cancelled() or (
                        t.exception() and print(f"[WS] 시스템AI 스트림 태스크 예외: {t.exception()}")))
            elif message_type == "cancel":
                # 중단 요청 처리
                streams.set_cancel(client_id, True)
                print(f"[WS] 중단 요청: {client_id}")
                await manager.send_message(client_id, {"type": "cancelled"})
            elif message_type == "ping":
                await manager.send_message(client_id, {"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(client_id)
        print(f"[WS] 정상 연결 해제: {client_id}")
    except Exception as e:
        error_msg = str(e)
        # 연결 관련 에러인 경우에만 disconnect
        if "closed" in error_msg.lower() or "disconnect" in error_msg.lower() or "connection" in error_msg.lower():
            print(f"[WS] 연결 에러로 해제: {client_id} - {e}")
            manager.disconnect(client_id)
        else:
            # 일시적 에러는 로그만 남기고 루프 계속 (연결 유지)
            print(f"[WS 에러] {client_id}: {e} (연결 유지 시도)")
            # 하지만 여기서는 while 루프가 끝나므로 결국 연결 해제됨
            manager.disconnect(client_id)
    finally:
        # 조향 태스크 레지스트리 정리 — 스트림 태스크 자체는 계속 돌게 둔다(백그라운드
        # 완주가 기존 계약: 타임아웃 후에도 작업은 완료되어 대화 저장·재접속 회수).
        _stream_tasks.pop(client_id, None)
        streams.clear_stream_target(client_id)
