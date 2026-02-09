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

from package_manager import (
    package_manager, INSTALLED_PATH, NOT_INSTALLED_PATH,
    encode_package, decode_package, install_package_from_text
)

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


class PublishPackageRequest(BaseModel):
    """패키지 공개 요청"""
    package_id: str
    install_instructions: Optional[str] = None  # 커스텀 설치 방법
    signature: Optional[str] = None  # 사인


class SearchPackagesRequest(BaseModel):
    """패키지 검색 요청"""
    query: Optional[str] = None
    limit: int = 20


class EncodePackageRequest(BaseModel):
    """패키지 인코딩 요청 (Nostr 공유용)"""
    package_id: str


class DecodePackageRequest(BaseModel):
    """패키지 디코딩 요청 (Nostr에서 수신)"""
    encoded_text: str


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

class AIInstallRequest(BaseModel):
    use_ai: bool = True  # True면 AI 기반 설치, False면 단순 복사


@router.post("/packages/{package_id}/install")
async def install_package(package_id: str, request: AIInstallRequest = None):
    """
    도구 패키지 설치

    - use_ai=True (기본값): AI가 README 분석, 필요한 라이브러리 설치, handler.py/tool.json 자동 생성
    - use_ai=False: 단순 파일 복사만
    """
    try:
        use_ai = request.use_ai if request else True

        if use_ai:
            # AI 기반 설치
            from api_system_ai import load_system_ai_config
            config = load_system_ai_config()

            if not config.get("enabled", True):
                # AI 비활성화면 단순 설치
                result = package_manager.install_package(package_id)
            else:
                api_key = config.get("apiKey", "")
                if not api_key:
                    # API 키 없으면 단순 설치
                    result = package_manager.install_package(package_id)
                else:
                    provider = config.get("provider", "google")
                    model = config.get("model")
                    result = await package_manager.install_package_with_ai(
                        package_id, api_key, provider, model
                    )
        else:
            # 단순 복사
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


# ============ 패키지 공개/검색 API (Nostr 기반) ============

@router.post("/packages/{package_id}/publish")
async def publish_package_to_nostr(package_id: str, request: PublishPackageRequest = None):
    """
    패키지를 Nostr에 공개 발행
    - 패키지 정보를 #indiebizOS-package 해시태그와 함께 발행
    """
    try:
        # 패키지 정보 가져오기
        info = package_manager.get_package_info(package_id)
        if not info:
            raise HTTPException(status_code=404, detail=f"패키지를 찾을 수 없습니다: {package_id}")

        # Nostr 채널 초기화
        from channels.nostr import NostrChannel
        nostr = NostrChannel({})
        if not nostr.authenticate():
            raise HTTPException(status_code=500, detail="Nostr 인증 실패")

        # 풍부한 설명 생성
        description_parts = []

        # 기본 설명
        if info.get('description'):
            description_parts.append(info.get('description'))

        # 도구 목록이 있으면 추가
        tools = info.get('tools', [])
        if tools:
            tool_names = [t.get('name', '') for t in tools if t.get('name')]
            if tool_names:
                description_parts.append(f"제공 도구: {', '.join(tool_names)}")

        final_description = ' | '.join(description_parts) if description_parts else '설명 없음'

        # 패키지 정보 구성
        package_info = {
            'name': info.get('name', package_id),
            'description': final_description,
            'version': info.get('version', '1.0.0'),
            'install': request.install_instructions if request and request.install_instructions else f"indiebizOS 도구 관리에서 '{info.get('name', package_id)}' 검색 후 설치",
            'signature': request.signature if request and request.signature else None
        }

        # 발행
        success = nostr.publish_package(package_info)

        if success:
            return {
                "status": "published",
                "package_id": package_id,
                "message": f"'{info.get('name', package_id)}' 패키지가 Nostr에 공개되었습니다."
            }
        else:
            raise HTTPException(status_code=500, detail="Nostr 발행 실패")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/packages/nostr/search")
async def search_packages_on_nostr(query: str = None, limit: int = 20):
    """
    Nostr에서 공개된 패키지 검색
    - #indiebizOS-package 해시태그로 필터링
    """
    try:
        # Nostr 채널 초기화
        from channels.nostr import NostrChannel
        nostr = NostrChannel({})
        if not nostr.authenticate():
            raise HTTPException(status_code=500, detail="Nostr 인증 실패")

        # 검색
        packages = nostr.search_packages(query=query, limit=limit)

        return {
            "packages": packages,
            "count": len(packages),
            "query": query
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/packages/nostr/search")
async def search_packages_on_nostr_post(request: SearchPackagesRequest):
    """Nostr에서 공개된 패키지 검색 (POST)"""
    return await search_packages_on_nostr(query=request.query, limit=request.limit)


@router.get("/packages/{package_id}/generate-install")
async def generate_install_instructions(package_id: str):
    """
    패키지를 Nostr 공유용 텍스트로 인코딩
    코드 파일 전체가 포함되어 다른 IndieBiz OS에서 바로 디코딩 가능
    """
    try:
        encoded = encode_package(package_id)
        return {
            "instructions": encoded,
            "format": "encoded_package",
            "package_id": package_id,
            "length": len(encoded)
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 도구 API (에이전트용) ============

def _load_tool_definitions(tools_path: Path):
    """도구 패키지에서 tool.json을 읽어 도구 정의 목록과 패키지 메타 정보 반환"""
    tools: List[Dict[str, Any]] = []
    packages_info: List[Dict[str, Any]] = []

    if not tools_path.exists():
        return tools, packages_info

    for pkg_dir in tools_path.iterdir():
        if not pkg_dir.is_dir() or pkg_dir.name.startswith('.'):
            continue

        tool_json = pkg_dir / "tool.json"
        if not tool_json.exists():
            continue

        try:
            with open(tool_json, 'r', encoding='utf-8') as f:
                tool_data = json.load(f)

            # tool.json 형식 처리:
            # 1. 배열인 경우: [{...}, {...}]
            # 2. 객체 안에 tools 배열: {"tools": [{...}, {...}]}
            # 3. 단일 도구 객체: {"name": "...", ...}

            pkg_tools_count = 0

            if isinstance(tool_data, list):
                # 형식 1: 직접 배열
                for tool in tool_data:
                    tool["_package_id"] = pkg_dir.name
                    tools.append(tool)
                pkg_tools_count = len(tool_data)
                pkg_name = pkg_dir.name
                pkg_desc = ""
            elif isinstance(tool_data, dict) and "tools" in tool_data and isinstance(tool_data["tools"], list):
                # 형식 2: {"tools": [...]} 구조
                for tool in tool_data["tools"]:
                    tool["_package_id"] = pkg_dir.name
                    tools.append(tool)
                pkg_tools_count = len(tool_data["tools"])
                pkg_name = tool_data.get("name", pkg_dir.name)
                pkg_desc = tool_data.get("description", "")
            elif isinstance(tool_data, dict) and "name" in tool_data:
                # 형식 3: 단일 도구 객체
                tool_data["_package_id"] = pkg_dir.name
                tools.append(tool_data)
                pkg_tools_count = 1
                pkg_name = tool_data.get("name", pkg_dir.name)
                pkg_desc = tool_data.get("description", "")
            else:
                print(f"[api_packages] Unknown tool.json format in {pkg_dir.name}")
                continue

            # 패키지 메타 정보 수집
            packages_info.append({
                "id": pkg_dir.name,
                "name": pkg_name,
                "description": pkg_desc,
                "tool_count": pkg_tools_count
            })
        except Exception as e:
            print(f"[api_packages] Failed to load {tool_json}: {e}")

    return tools, packages_info


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
        installed_tools, packages_info = _load_tool_definitions(INSTALLED_PATH / "tools")

        # 시스템 기본 도구 이름 목록
        base_tools = [t["name"] for t in system_tools]

        # 전체 도구 = 시스템 도구 + 설치된 도구
        all_tools = system_tools + installed_tools

        return {
            "tools": all_tools,
            "base_tools": base_tools,
            "packages": packages_info
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools/available")
async def get_available_tools():
    """
    모든 도구 목록 (not_installed + installed)
    """
    try:
        not_installed_tools, _ = _load_tool_definitions(NOT_INSTALLED_PATH / "tools")
        installed_tools, _ = _load_tool_definitions(INSTALLED_PATH / "tools")

        # 설치 여부 표시
        for tool in not_installed_tools:
            tool["installed"] = False
        for tool in installed_tools:
            tool["installed"] = True

        all_tools = installed_tools + not_installed_tools

        return {
            "tools": all_tools,
            "total": len(all_tools)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 패키지 인코더/디코더 API (Nostr 공유용) ============

@router.post("/packages/encode")
async def encode_package_api(request: EncodePackageRequest):
    """
    패키지를 Nostr 공유용 텍스트로 인코딩

    인코딩된 텍스트는 다른 IndieBiz OS 인스턴스에서
    decode API로 패키지 폴더로 복원할 수 있습니다.
    """
    try:
        encoded = encode_package(request.package_id)
        return {
            "success": True,
            "package_id": request.package_id,
            "encoded_text": encoded,
            "length": len(encoded),
            "message": f"'{request.package_id}' 패키지가 인코딩되었습니다. Nostr에 게시할 수 있습니다."
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/packages/{package_id}/encode")
async def encode_package_get(package_id: str):
    """패키지 인코딩 (GET 방식)"""
    try:
        encoded = encode_package(package_id)
        return {
            "success": True,
            "package_id": package_id,
            "encoded_text": encoded,
            "length": len(encoded)
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/packages/decode")
async def decode_package_api(request: DecodePackageRequest):
    """
    인코딩된 텍스트를 패키지 폴더로 디코딩

    Nostr에서 받은 패키지 텍스트를 not_installed/tools/ 폴더에
    패키지로 저장합니다.
    """
    try:
        result = decode_package(request.encoded_text)

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"])

        return {
            "success": True,
            "package_id": result["package_id"],
            "package_path": result["package_path"],
            "files_created": result["files_created"],
            "message": f"'{result['package_id']}' 패키지가 생성되었습니다. 설치하려면 install API를 사용하세요."
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/packages/install-from-text")
async def install_from_text_api(request: DecodePackageRequest):
    """
    인코딩된 텍스트에서 패키지 디코딩 + 검증

    Nostr에서 받은 패키지를 바로 설치 준비 상태로 만듭니다.
    """
    try:
        result = install_package_from_text(request.encoded_text)

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"])

        return {
            "success": True,
            "package_id": result["package_id"],
            "package_path": result["package_path"],
            "files_created": result["files_created"],
            "validation": result.get("validation"),
            "warnings": result.get("warnings", []),
            "message": f"'{result['package_id']}' 패키지가 준비되었습니다."
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
