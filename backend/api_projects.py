"""
api_projects.py - 프로젝트/폴더/휴지통/템플릿 API
IndieBiz OS Core
"""

from fastapi import APIRouter, HTTPException

from api_models import (
    ProjectCreate, FolderCreate, PositionUpdate,
    RenameRequest, CopyRequest
)
from system_hooks import on_project_created, on_project_deleted

router = APIRouter()

# 매니저 인스턴스는 api.py에서 주입받음
project_manager = None
switch_manager = None


def init_managers(pm, sm):
    """매니저 인스턴스 초기화"""
    global project_manager, switch_manager
    project_manager = pm
    switch_manager = sm


# ============ 프로젝트 API ============

@router.get("/projects")
async def list_projects():
    """모든 프로젝트 목록"""
    try:
        projects = project_manager.list_projects()
        return {"projects": projects}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects")
async def create_project(project: ProjectCreate):
    """새 프로젝트 생성"""
    try:
        result = project_manager.create_project(
            name=project.name,
            icon_position=project.icon_position,
            parent_folder=project.parent_folder,
            template_name=project.template_name
        )
        # 시스템 문서 업데이트
        all_projects = project_manager.list_projects()
        on_project_created(result, all_projects)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str, permanent: bool = False):
    """프로젝트 삭제"""
    try:
        project_manager.delete_project(project_id, move_to_trash=not permanent)
        # 시스템 문서 업데이트
        all_projects = project_manager.list_projects()
        on_project_deleted(project_id, all_projects)
        return {"status": "deleted", "project_id": project_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/projects/{project_id}/position")
async def update_project_position(project_id: str, position: PositionUpdate):
    """프로젝트 아이콘 위치 업데이트"""
    try:
        project_manager.update_project_position(project_id, position.x, position.y)
        return {"status": "updated", "project_id": project_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/projects/{project_id}/rename")
async def rename_project(project_id: str, request: RenameRequest):
    """프로젝트 또는 폴더 이름 변경"""
    try:
        result = project_manager.rename_item(project_id, request.new_name)
        return {"status": "renamed", "item": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/copy")
async def copy_project(project_id: str, request: CopyRequest = None):
    """프로젝트 또는 폴더 복사"""
    try:
        req = request or CopyRequest()
        result = project_manager.copy_item(
            item_id=project_id,
            new_name=req.new_name,
            parent_folder=req.parent_folder
        )
        return {"status": "copied", "item": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/trash")
async def move_project_to_trash(project_id: str):
    """프로젝트/폴더를 휴지통으로 이동"""
    try:
        result = project_manager.move_to_trash(project_id)
        return {"status": "trashed", "item": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 폴더 API ============

@router.post("/folders")
async def create_folder(folder: FolderCreate):
    """새 폴더 생성"""
    try:
        result = project_manager.create_folder(
            name=folder.name,
            icon_position=folder.icon_position,
            parent_folder=folder.parent_folder
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/folders/{folder_id}/items")
async def get_folder_items(folder_id: str):
    """폴더 안의 아이템 목록"""
    try:
        items = project_manager.get_folder_items(folder_id)
        return {"items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/items/{item_id}/move")
async def move_item(item_id: str, folder_id: str = None):
    """아이템을 폴더로 이동"""
    try:
        if folder_id:
            project_manager.move_to_folder(item_id, folder_id)
        else:
            project_manager.move_out_of_folder(item_id)
        return {"status": "moved", "item_id": item_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 휴지통 API ============

@router.get("/trash")
async def list_trash():
    """휴지통 아이템 목록"""
    try:
        project_trash = project_manager.list_trash()
        switch_trash = switch_manager.list_trashed_switches()
        return {
            "items": project_trash + switch_trash,
            "projects": project_trash,
            "switches": switch_trash
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trash/{item_id}/restore")
async def restore_from_trash(item_id: str, item_type: str = "project"):
    """휴지통에서 복원"""
    try:
        if item_type == "switch":
            result = switch_manager.restore_from_trash(item_id)
            if not result:
                raise HTTPException(status_code=404, detail="스위치를 찾을 수 없습니다.")
        else:
            result = project_manager.restore_from_trash(item_id)
        return {"status": "restored", "item": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/trash")
async def empty_trash():
    """휴지통 비우기"""
    try:
        project_manager.empty_trash()
        switch_manager.empty_trash()
        return {"status": "emptied"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 템플릿 API ============

@router.get("/templates")
async def list_templates():
    """사용 가능한 템플릿 목록"""
    try:
        templates = project_manager.list_templates()
        return {"templates": templates}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
