"""폰 컴패니언 알림 조회 API.

시스템 AI 가 사용자와 대화할 때 최근 폰 알림을 참조한다 (run_command 로 호출).
"""
from fastapi import APIRouter
from typing import Optional

import phone_notifications

router = APIRouter()


@router.get("/phone/notifications")
async def get_phone_notifications(limit: int = 30, pkg: Optional[str] = None):
    """최근 폰 알림 목록 (시간 내림차순). pkg 로 앱 필터."""
    items = phone_notifications.recent(limit=limit, pkg=pkg)
    return {"notifications": items, "count": len(items)}


@router.get("/phone/locations")
async def get_phone_locations(limit: int = 50):
    """최근 위치 기록 (시간 내림차순). lat/lng/accuracy/captured_at."""
    items = phone_notifications.recent_locations(limit=limit)
    return {"locations": items, "count": len(items)}


@router.get("/phone/steps")
async def get_phone_steps(limit: int = 30):
    """일별 걸음수 기록 (날짜 내림차순). date/steps/cumulative."""
    items = phone_notifications.recent_steps(limit=limit)
    return {"steps": items, "count": len(items)}


@router.post("/phone/notifications/poll")
async def poll_now():
    """릴레이에서 즉시 폴링(테스트/온디맨드). 새로 저장된 개수 반환."""
    n = phone_notifications.ingest_once()
    return {"stored": n}
