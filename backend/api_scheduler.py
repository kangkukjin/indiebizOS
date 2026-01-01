"""
api_scheduler.py - 스케줄러 API
IndieBiz OS Core
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from scheduler import get_scheduler

router = APIRouter(prefix="/scheduler")


class TaskCreate(BaseModel):
    name: str
    description: str = ""
    time: str  # HH:MM 형식
    action: str = "test"
    enabled: bool = True


class TaskUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    time: Optional[str] = None
    action: Optional[str] = None
    enabled: Optional[bool] = None


# ============ 스케줄러 상태 ============

@router.get("/status")
async def get_scheduler_status():
    """스케줄러 상태"""
    scheduler = get_scheduler()
    return {
        "running": scheduler.is_running(),
        "task_count": len(scheduler.get_tasks()),
        "available_actions": list(scheduler.actions.keys())
    }


@router.post("/start")
async def start_scheduler():
    """스케줄러 시작"""
    scheduler = get_scheduler()
    scheduler.start()
    return {"status": "started"}


@router.post("/stop")
async def stop_scheduler():
    """스케줄러 중지"""
    scheduler = get_scheduler()
    scheduler.stop()
    return {"status": "stopped"}


# ============ 작업 관리 ============

@router.get("/tasks")
async def list_tasks():
    """작업 목록"""
    scheduler = get_scheduler()
    return {"tasks": scheduler.get_tasks()}


@router.post("/tasks")
async def create_task(task: TaskCreate):
    """작업 추가"""
    scheduler = get_scheduler()

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

    new_task = scheduler.add_task(
        name=task.name,
        description=task.description,
        time_str=task.time,
        action=task.action,
        enabled=task.enabled
    )
    return {"task": new_task}


@router.put("/tasks/{task_id}")
async def update_task(task_id: str, task: TaskUpdate):
    """작업 수정"""
    scheduler = get_scheduler()

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

    if scheduler.update_task(task_id, **updates):
        return {"status": "updated"}
    raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """작업 삭제"""
    scheduler = get_scheduler()
    if scheduler.delete_task(task_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")


@router.post("/tasks/{task_id}/toggle")
async def toggle_task(task_id: str):
    """작업 활성화/비활성화 토글"""
    scheduler = get_scheduler()
    result = scheduler.toggle_task(task_id)
    if result is not None:
        return {"enabled": result}
    raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")


@router.post("/tasks/{task_id}/run")
async def run_task_now(task_id: str):
    """작업 즉시 실행"""
    scheduler = get_scheduler()
    if scheduler.run_task_now(task_id):
        return {"status": "running"}
    raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
