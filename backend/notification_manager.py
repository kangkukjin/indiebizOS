"""
notification_manager.py - 알림 관리
IndieBiz OS Core

시스템과 에이전트의 알림을 관리합니다.
"""

import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from collections import deque


class NotificationManager:
    """알림 관리자"""

    def __init__(self, max_notifications: int = 100):
        """
        Args:
            max_notifications: 최대 보관 알림 수
        """
        self.max_notifications = max_notifications
        self.notifications: deque = deque(maxlen=max_notifications)
        self._listeners: List[callable] = []

    def create(
        self,
        title: str,
        message: str,
        type: str = "info",
        source: str = "system"
    ) -> Dict[str, Any]:
        """
        알림 생성

        Args:
            title: 알림 제목
            message: 알림 내용
            type: 알림 유형 (info, success, warning, error)
            source: 발생 주체 (system, 에이전트명 등)

        Returns:
            생성된 알림 정보
        """
        notification = {
            "id": str(uuid.uuid4()),
            "type": type,
            "title": title,
            "message": message,
            "source": source,
            "created_at": datetime.now().isoformat(),
            "read": False
        }

        self.notifications.appendleft(notification)

        # 리스너에게 알림
        for listener in self._listeners:
            try:
                listener(notification)
            except:
                pass

        return notification

    def get_all(self, limit: int = 50, include_read: bool = True) -> List[Dict]:
        """알림 목록 조회"""
        result = list(self.notifications)[:limit]
        if not include_read:
            result = [n for n in result if not n["read"]]
        return result

    def get_unread_count(self) -> int:
        """읽지 않은 알림 수"""
        return sum(1 for n in self.notifications if not n["read"])

    def mark_read(self, notification_id: str) -> bool:
        """읽음 표시"""
        for n in self.notifications:
            if n["id"] == notification_id:
                n["read"] = True
                return True
        return False

    def mark_all_read(self) -> int:
        """모두 읽음 표시"""
        count = 0
        for n in self.notifications:
            if not n["read"]:
                n["read"] = True
                count += 1
        return count

    def delete(self, notification_id: str) -> bool:
        """알림 삭제"""
        for i, n in enumerate(self.notifications):
            if n["id"] == notification_id:
                del self.notifications[i]
                return True
        return False

    def clear_all(self) -> int:
        """모든 알림 삭제"""
        count = len(self.notifications)
        self.notifications.clear()
        return count

    def add_listener(self, callback: callable):
        """알림 리스너 등록 (WebSocket 등에서 사용)"""
        self._listeners.append(callback)

    def remove_listener(self, callback: callable):
        """알림 리스너 제거"""
        if callback in self._listeners:
            self._listeners.remove(callback)

    # 편의 메서드
    def info(self, title: str, message: str, source: str = "system"):
        """정보 알림"""
        return self.create(title, message, "info", source)

    def success(self, title: str, message: str, source: str = "system"):
        """성공 알림"""
        return self.create(title, message, "success", source)

    def warning(self, title: str, message: str, source: str = "system"):
        """경고 알림"""
        return self.create(title, message, "warning", source)

    def error(self, title: str, message: str, source: str = "system"):
        """오류 알림"""
        return self.create(title, message, "error", source)


# 싱글톤 인스턴스
_notification_manager: Optional[NotificationManager] = None


def get_notification_manager() -> NotificationManager:
    """알림 관리자 인스턴스 반환"""
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = NotificationManager()
    return _notification_manager
