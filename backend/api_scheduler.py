"""
api_scheduler.py - 스케줄러/캘린더 API
IndieBiz OS Core
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from calendar_manager import get_calendar_manager

router = APIRouter(prefix="/scheduler")


class TaskCreate(BaseModel):
    name: str
    description: str = ""
    time: str  # HH:MM 형식
    action: str = "test"
    enabled: bool = True
    repeat: str = "daily"
    weekdays: Optional[List[int]] = None
    date: Optional[str] = None
    month: Optional[int] = None
    day: Optional[int] = None
    interval_hours: Optional[int] = None
    action_params: Optional[dict] = None


class TaskUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    time: Optional[str] = None
    action: Optional[str] = None
    enabled: Optional[bool] = None
    repeat: Optional[str] = None
    weekdays: Optional[List[int]] = None
    date: Optional[str] = None
    month: Optional[int] = None
    day: Optional[int] = None
    interval_hours: Optional[int] = None
    action_params: Optional[dict] = None


# ============ 스케줄러 상태 ============

@router.get("/status")
async def get_scheduler_status():
    """스케줄러 상태"""
    cm = get_calendar_manager()
    return {
        "running": cm.is_running(),
        "task_count": len(cm.get_tasks()),
        "available_actions": list(cm.actions.keys())
    }


@router.post("/start")
async def start_scheduler():
    """스케줄러 시작"""
    cm = get_calendar_manager()
    cm.start()
    return {"status": "started"}


@router.post("/stop")
async def stop_scheduler():
    """스케줄러 중지"""
    cm = get_calendar_manager()
    cm.stop()
    return {"status": "stopped"}


# ============ 액션 목록 ============

@router.get("/actions")
async def get_actions():
    """사용 가능한 액션 목록"""
    cm = get_calendar_manager()
    action_names = {
        "test": "테스트",
        "run_switch": "스위치 실행",
        "send_notification": "알림 전송",
    }
    actions = []
    for action_id in cm.actions.keys():
        actions.append({
            "id": action_id,
            "name": action_names.get(action_id, action_id)
        })
    return {"actions": actions}


# ============ 작업 관리 ============

@router.get("/tasks")
async def list_tasks():
    """작업 목록 (실행 가능한 이벤트만)"""
    cm = get_calendar_manager()
    return {"tasks": cm.get_tasks()}


@router.post("/tasks")
async def create_task(task: TaskCreate):
    """작업 추가"""
    cm = get_calendar_manager()

    # 시간 형식 검증
    try:
        parts = task.time.split(":")
        if len(parts) != 2:
            raise ValueError()
        hour, minute = int(parts[0]), int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError()
    except:
        raise HTTPException(status_code=400, detail="시간 형식이 잘못되었습니다. HH:MM 형식으로 입력하세요.")

    # 반복 유형 검증
    valid_repeats = ["daily", "weekly", "none", "yearly", "interval", "monthly"]
    if task.repeat not in valid_repeats:
        raise HTTPException(status_code=400, detail=f"반복 유형이 잘못되었습니다. {valid_repeats} 중 하나를 선택하세요.")

    new_task = cm.add_task(
        name=task.name,
        description=task.description,
        time_str=task.time,
        action=task.action,
        enabled=task.enabled,
        repeat=task.repeat,
        weekdays=task.weekdays,
        date=task.date,
        month=task.month,
        day=task.day,
        interval_hours=task.interval_hours,
        action_params=task.action_params
    )
    return {"task": new_task}


@router.put("/tasks/{task_id}")
async def update_task(task_id: str, task: TaskUpdate):
    """작업 수정"""
    cm = get_calendar_manager()

    updates = {}
    if task.name is not None:
        updates["name"] = task.name
    if task.description is not None:
        updates["description"] = task.description
    if task.time is not None:
        updates["time"] = task.time
    if task.action is not None:
        updates["action"] = task.action
    if task.enabled is not None:
        updates["enabled"] = task.enabled
    if task.repeat is not None:
        updates["repeat"] = task.repeat
    if task.weekdays is not None:
        updates["weekdays"] = task.weekdays
    if task.date is not None:
        updates["date"] = task.date
    if task.month is not None:
        updates["month"] = task.month
    if task.day is not None:
        updates["day"] = task.day
    if task.interval_hours is not None:
        updates["interval_hours"] = task.interval_hours
    if task.action_params is not None:
        updates["action_params"] = task.action_params

    if cm.update_task(task_id, **updates):
        return {"status": "updated"}
    raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """작업 삭제"""
    cm = get_calendar_manager()
    if cm.delete_task(task_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")


@router.post("/tasks/{task_id}/toggle")
async def toggle_task(task_id: str):
    """작업 활성화/비활성화 토글"""
    cm = get_calendar_manager()
    result = cm.toggle_task(task_id)
    if result is not None:
        return {"enabled": result}
    raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")


@router.post("/tasks/{task_id}/run")
async def run_task_now(task_id: str):
    """작업 즉시 실행"""
    cm = get_calendar_manager()
    if cm.run_task_now(task_id):
        return {"status": "running"}
    raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")


# ============ 캘린더 ============

@router.get("/calendar/events")
async def get_calendar_events(year: int = None, month: int = None):
    """캘린더 이벤트 목록 (모든 이벤트)"""
    cm = get_calendar_manager()
    events = cm.list_events(year=year, month=month)
    return {"events": events, "count": len(events)}


@router.get("/calendar/view")
async def view_calendar(year: int = None, month: int = None):
    """캘린더 HTML 생성 후 브라우저에서 열기"""
    cm = get_calendar_manager()
    file_path = cm.open_in_browser(year=year, month=month)
    return {"status": "opened", "file": file_path}
