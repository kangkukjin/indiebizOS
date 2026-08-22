"""
api_notifications.py - 알림 API
IndieBiz OS Core
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from notification_manager import get_notification_manager

router = APIRouter(prefix="/notifications")


class NotificationCreate(BaseModel):
    title: str = ""          # 비우면 message 앞머리에서 파생 (F20-5)
    message: str
    type: str = "info"  # info, success, warning, error
    source: str = "system"


# ============ 알림 조회 ============

@router.get("")
async def list_notifications(limit: int = 50, include_read: bool = True):
    """알림 목록"""
    manager = get_notification_manager()
    return {
        "notifications": manager.get_all(limit, include_read),
        "unread_count": manager.get_unread_count()
    }


@router.get("/unread")
async def get_unread_count():
    """읽지 않은 알림 수"""
    manager = get_notification_manager()
    return {"unread_count": manager.get_unread_count()}


# ============ 알림 생성 ============

@router.post("")
async def create_notification(notification: NotificationCreate):
    """알림 생성 — **단일 관문(notify_dispatch)** 을 지난다.

    ★2026-08-22: 옛 코드는 notification_manager 에 곧장 적재해 알림함에는 남는데
    런처 푸시도 OS 폴백도 없었다 — 화면을 보고 있지 않으면 아무 일도 안 일어난 것과
    같았고(조용한 유실), notify_dispatch 의 '단일 관문' 계약도 이 입구에서만 깨져 있었다.
    이 라우트는 백그라운드 러너·외부 프로세스가 알림을 넣는 유일한 통로라 특히 아팠다.
    """
    from notify_dispatch import notify_user
    delivered = notify_user(title=notification.title, body=notification.message,
                            kind=notification.type, source=notification.source)
    manager = get_notification_manager()
    latest = manager.get_all(limit=1)
    return {"notification": (latest[0] if latest else None),
            "delivered_to_launcher": delivered}


# ============ 알림 상태 변경 ============

@router.put("/{notification_id}/read")
async def mark_read(notification_id: str):
    """읽음 표시"""
    manager = get_notification_manager()
    if manager.mark_read(notification_id):
        return {"status": "read"}
    raise HTTPException(status_code=404, detail="알림을 찾을 수 없습니다.")


@router.put("/read-all")
async def mark_all_read():
    """모두 읽음 표시"""
    manager = get_notification_manager()
    count = manager.mark_all_read()
    return {"status": "read", "count": count}


# ============ 알림 삭제 ============

@router.delete("/{notification_id}")
async def delete_notification(notification_id: str):
    """알림 삭제"""
    manager = get_notification_manager()
    if manager.delete(notification_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="알림을 찾을 수 없습니다.")


@router.delete("")
async def clear_all_notifications():
    """모든 알림 삭제"""
    manager = get_notification_manager()
    count = manager.clear_all()
    return {"status": "cleared", "count": count}
