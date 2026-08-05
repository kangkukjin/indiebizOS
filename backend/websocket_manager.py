"""
websocket_manager.py - WebSocket 연결 관리
IndieBiz OS Core
"""

import asyncio
from typing import Dict, Optional
from fastapi import WebSocket


class WebSocketManager:
    """WebSocket 연결 관리자"""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None  # 서버 이벤트 루프 (워커 스레드 발신용)

    async def connect(self, websocket: WebSocket, client_id: str):
        """클라이언트 연결"""
        await websocket.accept()
        self._loop = asyncio.get_running_loop()
        self.active_connections[client_id] = websocket
        print(f"[WS] 연결 등록: {client_id} (총 {len(self.active_connections)}개)")

    def disconnect(self, client_id: str):
        """클라이언트 연결 해제"""
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            print(f"[WS] 연결 해제: {client_id} (총 {len(self.active_connections)}개)")

    def is_connected(self, client_id: str) -> bool:
        """클라이언트 연결 상태 확인"""
        return client_id in self.active_connections

    async def send_message(self, client_id: str, message: dict):
        """특정 클라이언트에 메시지 전송"""
        if client_id not in self.active_connections:
            print(f"[WS 경고] 연결 없음: {client_id} - 메시지 전송 건너뜀")
            return False

        websocket = self.active_connections[client_id]
        try:
            await websocket.send_json(message)
            return True
        except Exception as e:
            error_msg = str(e)
            # 연결이 닫힌 경우 disconnect
            if any(keyword in error_msg.lower() for keyword in ["closed", "close", "disconnect"]):
                print(f"[WS] 연결 끊김 감지: {client_id}")
                self.disconnect(client_id)
            else:
                # 일시적 에러는 로그만 남기고 연결 유지
                print(f"[WS 전송 에러] {client_id}: {e} (연결 유지)")
            return False

    async def send_message_safe(self, client_id: str, message: dict):
        """
        안전한 메시지 전송 - 실패해도 예외 발생 안 함
        에이전트 응답 전송 등에 사용
        """
        try:
            return await self.send_message(client_id, message)
        except Exception as e:
            print(f"[WS 전송 실패 (무시)] {client_id}: {e}")
            return False

    async def broadcast(self, message: dict):
        """모든 클라이언트에 브로드캐스트"""
        disconnected = []
        for client_id, websocket in self.active_connections.items():
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.append(client_id)

        for client_id in disconnected:
            self.disconnect(client_id)

    async def send_to_agent_chat(self, project_id: str, agent_id: str, message: dict) -> bool:
        """
        특정 프로젝트/에이전트의 열린 대화창에 메시지 전송.
        client_id가 "{project_id}-{agent_id}-" 로 시작하는 연결을 찾아 전송.

        Returns:
            True if 전송 성공 (하나 이상의 클라이언트에 전달), False if 연결 없음
        """
        prefix = f"{project_id}-{agent_id}-"
        sent = False
        disconnected = []

        for client_id, websocket in self.active_connections.items():
            if client_id.startswith(prefix):
                try:
                    await websocket.send_json(message)
                    sent = True
                except Exception:
                    disconnected.append(client_id)

        for client_id in disconnected:
            self.disconnect(client_id)

        return sent

    def find_agent_connections(self, project_id: str, agent_id: str) -> list:
        """특정 프로젝트/에이전트의 활성 WS 연결 목록"""
        prefix = f"{project_id}-{agent_id}-"
        return [cid for cid in self.active_connections if cid.startswith(prefix)]

    async def send_to_system_ai_chat(self, message: dict) -> bool:
        """시스템 AI 대화창에 메시지 전송 (client_id가 'system_ai_'로 시작하는 연결)"""
        sent = False
        disconnected = []
        for client_id, websocket in self.active_connections.items():
            if client_id.startswith("system_ai_"):
                try:
                    await websocket.send_json(message)
                    sent = True
                except Exception:
                    disconnected.append(client_id)
        for client_id in disconnected:
            self.disconnect(client_id)
        return sent

    def find_system_ai_connections(self) -> list:
        """시스템 AI의 활성 WS 연결 목록"""
        return [cid for cid in self.active_connections if cid.startswith("system_ai_")]

    def get_connection_count(self) -> int:
        """현재 연결 수"""
        return len(self.active_connections)

    def list_connections(self) -> list:
        """연결된 클라이언트 ID 목록"""
        return list(self.active_connections.keys())


# 싱글톤 인스턴스
manager = WebSocketManager()


def broadcast_message(message: dict) -> bool:
    """동기·스레드 안전 브로드캐스트 — 워커 스레드(IBL 실행 등)에서 호출 가능.

    ibl_executors._output_gui 등이 이 이름으로 import 하지만 실제 함수가 없어
    [out:gui]의 WS 푸시가 조용히 전멸하던 결함의 수선(2026-07-28).
    루프 스레드면 예약, 워커 스레드면 run_coroutine_threadsafe로 넘긴다.
    """
    loop = manager._loop
    if loop is None or loop.is_closed() or not manager.active_connections:
        return False
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    try:
        if running is loop:
            asyncio.ensure_future(manager.broadcast(message))
        else:
            asyncio.run_coroutine_threadsafe(manager.broadcast(message), loop)
        return True
    except Exception as e:
        print(f"[WS] broadcast_message 실패: {e}")
        return False


# ============ Launcher 전용 WS 허브 ============
# api_websocket 에서 이동 (2026-08-05 감사 ⑦): 상태(연결·루프)와 송신 함수는 연결
# 허브(데이터층)의 것 — 아래층(ibl_routing·notify_dispatch·핸들러)이 라우터를
# import 하지 않게 한다. /ws/launcher 엔드포인트(수락·수신 루프)는 api_websocket 에
# 남고, 연결·해제 시 set_launcher_ws()/clear_launcher_ws() 로 여기 등록만 한다.

_launcher_ws = None  # Launcher 전용 WS 연결 (1개)
_launcher_loop = None  # 런처 WS가 붙은 이벤트 루프 (워커 스레드 발신용)


def set_launcher_ws(websocket, loop) -> None:
    """런처 WS 연결 등록 (api_websocket 엔드포인트가 수락 직후 호출)"""
    global _launcher_ws, _launcher_loop
    _launcher_ws = websocket
    _launcher_loop = loop


def clear_launcher_ws() -> None:
    """런처 WS 연결 해제"""
    global _launcher_ws
    _launcher_ws = None


async def send_launcher_command(command: str, params: dict = None) -> bool:
    """백엔드에서 Launcher로 명령 전송 (예: 프로젝트 창 열기)"""
    global _launcher_ws
    if not _launcher_ws:
        print(f"[WS] Launcher 미연결, 명령 전달 불가: {command}")
        return False
    try:
        await _launcher_ws.send_json({
            "type": "launcher_command",
            "command": command,
            "params": params or {}
        })
        return True
    except Exception as e:
        print(f"[WS] Launcher 명령 전달 실패: {e}")
        _launcher_ws = None
        return False


def get_launcher_ws():
    """Launcher WS 연결 상태 확인 (동기 호출용)"""
    return _launcher_ws


def send_launcher_command_sync(command: str, params: dict = None, timeout: float = 3.0) -> bool:
    """워커 스레드(채널 폴러·IBL 실행 등)에서 런처 명령 전송 — 동기 래퍼.

    런처 미연결이면 False (호출부가 OS 알림 등으로 폴백 판단).
    루프 스레드에서 불리면 결과를 기다리지 않고 예약만 한다(자기교착 방지).
    """
    if not _launcher_ws or not _launcher_loop or _launcher_loop.is_closed():
        return False
    coro = send_launcher_command(command, params)
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    try:
        if running is _launcher_loop:
            asyncio.ensure_future(coro)
            return True  # 전송 예약됨 — 결과 확인 불가 지점이라 낙관 반환
        fut = asyncio.run_coroutine_threadsafe(coro, _launcher_loop)
        return bool(fut.result(timeout=timeout))
    except Exception as e:
        print(f"[WS] Launcher 동기 명령 전달 실패: {e}")
        return False


# ============ 채팅 스트림 진입점 주입 슬롯 ============
# calendar_actions(서비스층)가 예약 작업을 "프론트가 보낸 것과 동일한 경로"로
# 주입하는데, 그 핸들러(handle_chat_message_stream 등)는 라우터 모듈(api_websocket)에
# 산다. 핸들러를 옮기는 대신 진입점만 주입(의존 역전) — api_websocket 이 로드
# 말미에 등록한다 (ibl_parser ↔ ibl_parser_blocks 와 같은 패턴, 2026-08-05 ⑦).

_chat_stream_entry = None        # async (client_id, data) — 프로젝트 에이전트 채팅
_system_ai_stream_entry = None   # async (client_id, data) — 시스템 AI 채팅


def register_chat_streams(chat_entry, system_ai_entry) -> None:
    """채팅 스트림 핸들러 주입 (api_websocket 로드 말미에 1회)"""
    global _chat_stream_entry, _system_ai_stream_entry
    _chat_stream_entry = chat_entry
    _system_ai_stream_entry = system_ai_entry


def get_chat_stream_entry():
    return _chat_stream_entry


def get_system_ai_stream_entry():
    return _system_ai_stream_entry
