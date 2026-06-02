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
    title: str
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
    """알림 생성"""
    manager = get_notification_manager()
    result = manager.create(
        title=notification.title,
        message=notification.message,
        type=notification.type,
        source=notification.source
    )
    return {"notification": result}


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
