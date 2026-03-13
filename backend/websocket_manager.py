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
