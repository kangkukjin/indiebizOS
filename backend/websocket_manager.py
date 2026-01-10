"""
websocket_manager.py - WebSocket 연결 관리
IndieBiz OS Core
"""

from typing import Dict
from fastapi import WebSocket


class WebSocketManager:
    """WebSocket 연결 관리자"""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        """클라이언트 연결"""
        await websocket.accept()
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
            # 연결이 닫힌 경우에만 disconnect
            if "closed" in error_msg.lower() or "disconnect" in error_msg.lower():
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

    def get_connection_count(self) -> int:
        """현재 연결 수"""
        return len(self.active_connections)

    def list_connections(self) -> list:
        """연결된 클라이언트 ID 목록"""
        return list(self.active_connections.keys())


# 싱글톤 인스턴스
manager = WebSocketManager()
