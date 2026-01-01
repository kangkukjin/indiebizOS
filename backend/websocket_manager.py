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

    def disconnect(self, client_id: str):
        """클라이언트 연결 해제"""
        if client_id in self.active_connections:
            del self.active_connections[client_id]

    async def send_message(self, client_id: str, message: dict):
        """특정 클라이언트에 메시지 전송"""
        if client_id in self.active_connections:
            websocket = self.active_connections[client_id]
            try:
                await websocket.send_json(message)
            except Exception as e:
                print(f"[WS 전송 실패] {client_id}: {e}")
                self.disconnect(client_id)

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


# 싱글톤 인스턴스
manager = WebSocketManager()
