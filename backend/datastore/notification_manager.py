"""
notification_manager.py - 알림 관리
IndieBiz OS Core

시스템과 에이전트의 알림을 관리합니다.
"""

import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from collections import deque


# ============ 제목 파생 (2026-08-22, F20-5 판정) ============

_TITLE_MAX = 40


def derive_title(message: str) -> str:
    """title 이 비었을 때 message 에서 제목을 파생한다 — 단일 소스.

    ★F20-5 판정 (2026-08-22): title 을 필수로 만드는 안은 기각했다. 필수화하면
    부르는 쪽(모델 포함)이 message 를 title 에 그대로 복붙한다 — 형식만 채우고
    내용은 중복되는 토큰이 되고, `[self:notify_user]{message:}` 로 이미 쓰인
    기존 문장·코퍼스도 통째로 깨진다. 대신 message 앞머리를 제목으로 승격한다.

    파생 자리가 액션이 아니라 **관문(create)** 인 이유: 알림 입구는 18곳이고
    액션 쪽에서 고치면 나머지 우회 호출처는 여전히 빈 제목이다. 규약을 문서가
    아니라 구조로 (2026-08-22 N-1 수리가 create 를 단일 입구로 만들어 둔 자리).

    규칙: 첫 번째 비어있지 않은 줄 → 길면 낱말 경계에서 자르고 '…'.
    ※문장 부호로 자르지 않는다 — "3.5% 올랐습니다" 의 소수점이 마침표라
      숫자에서 잘린다. 예측 가능한 규칙 하나가 영리한 규칙보다 낫다.
    ※로그 절단 표식(`…(+N자)`) 규약은 여기 적용하지 않는다 — 잘린 payload 가
      아니라 표시용 요약이고, 원문(message)이 바로 아래 칸에 그대로 있다.
    """
    text = (message or "").strip()
    if not text:
        return "알림"
    line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    if not line:
        return "알림"
    if len(line) <= _TITLE_MAX:
        return line
    cut = line[:_TITLE_MAX]
    sp = cut.rfind(" ")
    if sp >= _TITLE_MAX // 2:      # 낱말 중간에서 끊기지 않게 (한글은 공백이 드물어 폴백)
        cut = cut[:sp]
    return cut.rstrip() + "…"


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
        source: str = "system",
        deliver: bool = True
    ) -> Dict[str, Any]:
        """
        알림 생성 — **기록과 전달이 한 몸이다**.

        Args:
            title: 알림 제목
            message: 알림 내용
            type: 알림 유형 (info, success, warning, error)
            source: 발생 주체 (system, 에이전트명 등)
            deliver: 사용자에게 전달까지 할지. False 는 관문
                (notify_dispatch.notify_user)이 자기 전달과 겹치지 않게 쓸 때만.

        Returns:
            생성된 알림 정보
        """
        # ★21회차 관찰 (2026-08-22): 제목도 본문도 없는 알림은 **알림이 아니다**.
        # 실측 — send_notification 이 빈 message 로 불려 제목 "알림"(derive_title 의
        # 빈 입력 기본값)·본문 "" 인 껍데기가 알림함에 남고 사용자 화면까지 갔다.
        # 파생은 내용이 있을 때 제목을 채우는 장치이지, 없는 내용을 있는 것처럼
        # 만드는 장치가 아니다. 입구가 하나이므로 여기서 한 번 막는다(호출처 18곳 불문).
        if not (title or "").strip() and not (message or "").strip():
            return {"success": False, "error": "제목도 본문도 비어 있어 알림을 만들지 않았습니다."}

        # ★F20-5 (2026-08-22): 빈 제목은 알림함에 빈칸으로 남는다. 어느 입구로
        # 들어오든 여기서 한 번 파생한다(derive_title docstring = 판정 근거).
        title = (title or "").strip() or derive_title(message)

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
            except Exception as e:
                print(f"[NotificationManager] 리스너 호출 실패: {e}")

        # ★2026-08-22: 기록과 전달을 한 몸으로 — '알림함엔 쌓이는데 사용자에겐
        # 닿지 않는' 조용한 유실을 구조가 막는다. 옛 구조는 전달이 notify_dispatch
        # 에만 있어, 관문을 안 거친 호출처 17곳(스케줄 실행 완료·자가점검 경고·
        # 손발 연결·포털 가입·설치 승인 대기 …)의 알림이 런처를 보고 있지 않으면
        # 아무 일도 안 일어난 것과 같았다. 규약을 문서가 아니라 구조로.
        if deliver:
            try:
                from notify_dispatch import deliver_notification
                deliver_notification(title, message, type)
            except Exception as e:
                print(f"[NotificationManager] 전달 실패: {e}")

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
