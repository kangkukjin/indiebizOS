"""
api_switches.py - 스위치 관련 API
IndieBiz OS Core
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks

from api_models import SwitchCreate, SwitchUpdate, PositionUpdate, RenameRequest

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
    """새 스위치 생성 — 프로젝트 설정 복사 규칙은 ibl_launcher_ops.build_switch_config([self:switch]{op:create} 와 같은 함수)"""
    from launcher_ops import build_switch_config
    try:
        return switch_manager.create_switch(name=switch.name, command=switch.command,
                                            config=build_switch_config(switch.config or {}),
                                            icon=switch.icon, description=switch.description)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/switches/{switch_id}")
async def get_switch(switch_id: str):
    """특정 스위치 조회"""
    switch = switch_manager.get_switch(switch_id)
    if not switch:
        raise HTTPException(status_code=404, detail="Switch not found")
    return switch


@router.put("/switches/{switch_id}")
async def update_switch(switch_id: str, switch: SwitchUpdate):
    """스위치 편집 - 이름, 명령어, 아이콘 등 수정"""
    try:
        # None이 아닌 필드만 업데이트
        updates = {}
        if switch.name is not None:
            updates["name"] = switch.name
        if switch.command is not None:
            updates["command"] = switch.command
        if switch.icon is not None:
            updates["icon"] = switch.icon
        if switch.description is not None:
            updates["description"] = switch.description
        if switch.config is not None:
            updates["config"] = switch.config

        if not updates:
            raise HTTPException(status_code=400, detail="수정할 내용이 없습니다.")

        result = switch_manager.update_switch(switch_id, updates)
        if not result:
            raise HTTPException(status_code=404, detail="스위치를 찾을 수 없습니다.")
        return {"status": "updated", "switch": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    """스위치 실행 - 저장된 설정을 그대로 사용 (프로젝트 독립적)"""
    from switch_runner import SwitchRunner

    switch = switch_manager.get_switch(switch_id)
    if not switch:
        raise HTTPException(status_code=404, detail="Switch not found")

    # 스위치에 저장된 설정 그대로 사용 (이미 생성 시 복사됨)
    config = switch.get("config", {})

    # ★api_key 유무로 막지 않는다 — 모델은 실행 시점에 기어가 정하고, 현재 고급 티어
    # (claude_code)처럼 **키가 원래 없는** 프로바이더가 있다. 키 없음은 오류가 아니다.
    # 해소 실패는 SwitchRunner 가 실행 시점에 정직하게 보고한다.

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
