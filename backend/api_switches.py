"""
api_switches.py - 스위치 관련 API
IndieBiz OS Core
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks

from api_models import SwitchCreate, PositionUpdate, RenameRequest

router = APIRouter()

# 매니저 인스턴스는 api.py에서 주입받음
switch_manager = None


def init_manager(sm):
    """매니저 인스턴스 초기화"""
    global switch_manager
    switch_manager = sm


# ============ 스위치 API ============

@router.get("/switches")
async def list_switches():
    """모든 스위치 목록"""
    try:
        switches = switch_manager.list_switches()
        return {"switches": switches}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/switches")
async def create_switch(switch: SwitchCreate):
    """새 스위치 생성"""
    try:
        result = switch_manager.create_switch(
            name=switch.name,
            command=switch.command,
            config=switch.config,
            icon=switch.icon,
            description=switch.description
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/switches/{switch_id}")
async def get_switch(switch_id: str):
    """특정 스위치 조회"""
    switch = switch_manager.get_switch(switch_id)
    if not switch:
        raise HTTPException(status_code=404, detail="Switch not found")
    return switch


@router.delete("/switches/{switch_id}")
async def delete_switch(switch_id: str):
    """스위치 삭제"""
    if switch_manager.delete_switch(switch_id):
        return {"status": "deleted", "switch_id": switch_id}
    raise HTTPException(status_code=404, detail="Switch not found")


@router.put("/switches/{switch_id}/position")
async def update_switch_position(switch_id: str, position: PositionUpdate):
    """스위치 아이콘 위치 업데이트"""
    try:
        switch_manager.update_position(switch_id, position.x, position.y)
        return {"status": "updated", "switch_id": switch_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/switches/{switch_id}/execute")
async def execute_switch(switch_id: str, background_tasks: BackgroundTasks):
    """스위치 실행"""
    from switch_runner import SwitchRunner

    switch = switch_manager.get_switch(switch_id)
    if not switch:
        raise HTTPException(status_code=404, detail="Switch not found")

    # 스위치 실행 (백그라운드)
    runner = SwitchRunner(switch)

    def on_complete(result):
        print(f"[Switch] {switch.get('name')} 완료: {result.get('success')}")

    runner.run_async(callback=on_complete)

    switch_manager.record_run(switch_id)

    return {"status": "started", "switch_id": switch_id, "switch_name": switch.get("name")}


@router.put("/switches/{switch_id}/rename")
async def rename_switch(switch_id: str, request: RenameRequest):
    """스위치 이름 변경"""
    try:
        result = switch_manager.rename_switch(switch_id, request.new_name)
        if not result:
            raise HTTPException(status_code=404, detail="스위치를 찾을 수 없습니다.")
        return {"status": "renamed", "item": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/switches/{switch_id}/copy")
async def copy_switch(switch_id: str):
    """스위치 복사"""
    try:
        result = switch_manager.copy_switch(switch_id)
        if not result:
            raise HTTPException(status_code=404, detail="스위치를 찾을 수 없습니다.")
        return {"status": "copied", "item": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/switches/{switch_id}/trash")
async def move_switch_to_trash(switch_id: str):
    """스위치를 휴지통으로 이동"""
    try:
        result = switch_manager.move_to_trash(switch_id)
        if not result:
            raise HTTPException(status_code=404, detail="스위치를 찾을 수 없습니다.")
        return {"status": "trashed", "item": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
