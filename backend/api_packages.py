"""
api_packages.py - 도구 패키지 관리 API
IndieBiz OS Core

도구 패키지만 관리 (extensions 개념 폐기)
AI 기반 폴더 분석 및 README 자동 생성 지원
"""

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from package_manager import package_manager, INSTALLED_PATH, AVAILABLE_PATH

router = APIRouter()


class InstallRequest(BaseModel):
    package_type: Optional[str] = "tools"  # 하위 호환성, 무시됨


class UpdateMetadataRequest(BaseModel):
    package_type: Optional[str] = "tools"  # 하위 호환성, 무시됨
    name: Optional[str] = None
    description: Optional[str] = None


class AnalyzeFolderRequest(BaseModel):
    folder_path: str


class AnalyzeFolderWithAIRequest(BaseModel):
    folder_path: str


class RegisterFolderRequest(BaseModel):
    folder_path: str
    name: Optional[str] = None
    description: Optional[str] = None
    readme_content: Optional[str] = None
    package_type: Optional[str] = "tools"  # 하위 호환성, 무시됨


class RemovePackageRequest(BaseModel):
    package_type: Optional[str] = "tools"  # 하위 호환성, 무시됨


# ============ 패키지 목록 API ============

@router.get("/packages")
async def list_all_packages(package_type: Optional[str] = None):
    """모든 도구 패키지 목록 (설치 가능 + 설치됨)"""
    try:
        available = package_manager.list_available()
        installed = package_manager.list_installed()

        return {
            "available": available,
            "installed": installed,
            "total_available": len(available),
            "total_installed": len(installed)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/packages/available")
async def list_available_packages(package_type: Optional[str] = None):
    """설치 가능한 도구 패키지 목록"""
    try:
        packages = package_manager.list_available()
        return {"packages": packages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/packages/installed")
async def list_installed_packages(package_type: Optional[str] = None):
    """설치된 도구 패키지 목록"""
    try:
        packages = package_manager.list_installed()
        return {"packages": packages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/packages/tools")
async def list_tool_packages():
    """도구 패키지 조회 (하위 호환성)"""
    try:
        available = package_manager.list_available()
        installed = package_manager.list_installed()
        return {
            "available": available,
            "installed": installed
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 패키지 정보 API ============

@router.get("/packages/{package_id}")
async def get_package_info(package_id: str, package_type: Optional[str] = None):
    """패키지 상세 정보"""
    try:
        info = package_manager.get_package_info(package_id)
        if not info:
            raise HTTPException(status_code=404, detail=f"패키지를 찾을 수 없습니다: {package_id}")
        return info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/packages/{package_id}/files")
async def get_package_files(package_id: str, package_type: Optional[str] = None):
    """패키지 내 파일 목록"""
    try:
        files = package_manager.get_package_files(package_id)
        return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/packages/{package_id}/file")
async def read_package_file(package_id: str, file_path: str, package_type: Optional[str] = None):
    """패키지 내 특정 파일 읽기"""
    try:
        content = package_manager.read_package_file(package_id, "tools", file_path)
        if content is None:
            raise HTTPException(status_code=404, detail=f"파일을 찾을 수 없습니다: {file_path}")
        return {"content": content}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 패키지 메타데이터 API ============

@router.put("/packages/{package_id}")
async def update_package_metadata(package_id: str, request: UpdateMetadataRequest):
    """패키지 메타데이터 업데이트 (이름, 설명)"""
    try:
        result = package_manager.update_package_metadata(
            package_id,
            name=request.name,
            description=request.description
        )
        return {"status": "updated", "package": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 패키지 설치/제거 API ============

@router.post("/packages/{package_id}/install")
async def install_package(package_id: str, request: InstallRequest = None):
    """도구 패키지 설치"""
    try:
        result = package_manager.install_package(package_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/packages/{package_id}/uninstall")
async def uninstall_package(package_id: str, request: InstallRequest = None):
    """도구 패키지 제거"""
    try:
        result = package_manager.uninstall_package(package_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 폴더 분석 및 패키지 등록 API ============

@router.post("/packages/analyze-folder")
async def analyze_folder(request: AnalyzeFolderRequest):
    """폴더 기본 분석 (AI 없이)"""
    try:
        result = package_manager.analyze_folder_basic(request.folder_path)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/packages/analyze-folder-ai")
async def analyze_folder_with_ai(request: AnalyzeFolderWithAIRequest):
    """AI를 사용하여 폴더 분석 및 패키지 유효성 판별"""
    try:
        # 시스템 AI 설정 로드
        from api_system_ai import load_system_ai_config
        config = load_system_ai_config()

        if not config.get("enabled", True):
            raise HTTPException(status_code=400, detail="시스템 AI가 비활성화되어 있습니다.")

        api_key = config.get("apiKey", "")
        if not api_key:
            raise HTTPException(status_code=400, detail="AI API 키가 설정되지 않았습니다.")

        provider = config.get("provider", "anthropic")
        model = config.get("model")

        result = await package_manager.analyze_folder_with_ai(
            request.folder_path,
            api_key,
            provider,
            model
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/packages/register")
async def register_folder(request: RegisterFolderRequest):
    """폴더를 도구 패키지로 등록"""
    try:
        result = package_manager.register_folder(
            request.folder_path,
            name=request.name,
            description=request.description,
            readme_content=request.readme_content
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/packages/{package_id}/remove")
async def remove_package(package_id: str, request: RemovePackageRequest = None):
    """패키지를 목록에서 제거 (available에서 삭제)"""
    try:
        result = package_manager.remove_package(package_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 도구 API (에이전트용) ============

def _load_tool_definitions(tools_path: Path) -> List[Dict[str, Any]]:
    """도구 패키지에서 tool.json을 읽어 도구 정의 목록 반환"""
    tools = []

    if not tools_path.exists():
        return tools

    for pkg_dir in tools_path.iterdir():
        if not pkg_dir.is_dir() or pkg_dir.name.startswith('.'):
            continue

        tool_json = pkg_dir / "tool.json"
        if not tool_json.exists():
            continue

        try:
            with open(tool_json, 'r', encoding='utf-8') as f:
                tool_data = json.load(f)

            # tool.json이 배열인 경우 (여러 도구 포함)
            if isinstance(tool_data, list):
                for tool in tool_data:
                    tool["_package_id"] = pkg_dir.name
                    tools.append(tool)
            else:
                # 단일 도구
                tool_data["_package_id"] = pkg_dir.name
                tools.append(tool_data)
        except Exception as e:
            print(f"[api_packages] Failed to load {tool_json}: {e}")

    return tools


@router.get("/tools")
async def get_tools():
    """
    사용 가능한 도구 목록 조회 (시스템 기본 도구 + 설치된 도구)

    Returns:
        tools: 시스템 기본 도구 + 설치된 도구 정의 목록
        base_tools: 시스템 기본 도구 이름 목록 (항상 활성화)
    """
    try:
        # 시스템 기본 도구 (ai_agent.py의 SYSTEM_TOOLS와 동일)
        system_tools = [
            {
                "name": "call_agent",
                "description": "다른 에이전트를 호출하여 작업을 요청합니다.",
                "_is_system": True
            },
            {
                "name": "list_agents",
                "description": "현재 프로젝트에서 사용 가능한 에이전트 목록을 가져옵니다.",
                "_is_system": True
            },
            {
                "name": "send_notification",
                "description": "사용자에게 알림을 보냅니다.",
                "_is_system": True
            },
            {
                "name": "get_project_info",
                "description": "현재 프로젝트의 정보를 가져옵니다.",
                "_is_system": True
            }
        ]

        # 설치된 도구 패키지에서 tool.json 로드
        installed_tools = _load_tool_definitions(INSTALLED_PATH / "tools")

        # 시스템 기본 도구 이름 목록
        base_tools = [t["name"] for t in system_tools]

        # 전체 도구 = 시스템 도구 + 설치된 도구
        all_tools = system_tools + installed_tools

        return {
            "tools": all_tools,
            "base_tools": base_tools
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools/available")
async def get_available_tools():
    """
    설치 가능한 모든 도구 목록 (tool.json 포함)
    """
    try:
        available_tools = _load_tool_definitions(AVAILABLE_PATH / "tools")
        installed_tools = _load_tool_definitions(INSTALLED_PATH / "tools")

        # 설치 여부 표시
        installed_names = {t["name"] for t in installed_tools}
        for tool in available_tools:
            tool["installed"] = tool["name"] in installed_names

        return {
            "tools": available_tools,
            "total": len(available_tools)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
