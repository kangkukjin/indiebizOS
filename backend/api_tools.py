"""
api_tools.py - 도구 개발 API
IndieBiz OS Core

시스템 AI를 사용하여 새 도구를 개발하는 API
"""

import json
import shutil
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from system_ai import get_system_ai, DATA_PATH

router = APIRouter()

# 개발 중인 도구 경로
DEV_TOOLS_PATH = DATA_PATH / "packages" / "dev" / "tools"
INSTALLED_TOOLS_PATH = DATA_PATH / "packages" / "installed" / "tools"


class DevelopToolRequest(BaseModel):
    message: str
    history: List[Dict[str, str]] = []


class TestToolRequest(BaseModel):
    tool_name: str
    test_input: Dict[str, Any] = {}


class InstallDevToolRequest(BaseModel):
    tool_name: str


@router.post("/tools/develop")
async def develop_tool(request: DevelopToolRequest):
    """
    시스템 AI와 대화하며 도구를 개발합니다.
    """
    try:
        system_ai = get_system_ai(str(DEV_TOOLS_PATH))

        # 사용자 메시지만 전달 (히스토리는 시스템 AI 내부에서 DB 기반으로 처리됨)
        result = system_ai.execute(request.message, max_turns=15)

        # 생성된 도구 정보 추출
        tool_info = None
        if result.get("success"):
            # dev/tools 폴더에서 새로 생성된 도구 찾기
            DEV_TOOLS_PATH.mkdir(parents=True, exist_ok=True)
            for tool_dir in DEV_TOOLS_PATH.iterdir():
                if tool_dir.is_dir():
                    tool_json = tool_dir / "tool.json"
                    if tool_json.exists():
                        try:
                            with open(tool_json, 'r', encoding='utf-8') as f:
                                tool_data = json.load(f)
                                # 배열일 수도 있음
                                if isinstance(tool_data, list):
                                    tool_data = tool_data[0] if tool_data else {}
                                tool_info = {
                                    "name": tool_data.get("name", tool_dir.name),
                                    "description": tool_data.get("description", ""),
                                    "status": "generating",
                                    "files": [f.name for f in tool_dir.iterdir() if f.is_file()]
                                }
                        except:
                            pass

        return {
            "success": result.get("success", False),
            "result": result.get("result", ""),
            "tool_calls": result.get("tool_calls", []),
            "tool_info": tool_info
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tools/test")
async def test_tool(request: TestToolRequest):
    """
    개발 중인 도구를 테스트합니다.
    """
    try:
        system_ai = get_system_ai(str(DEV_TOOLS_PATH))

        result = system_ai.test_tool(request.tool_name, request.test_input)

        return {
            "success": result.get("success", False),
            "result": result.get("result", ""),
            "error": result.get("error"),
            "tool_calls": result.get("tool_calls", [])
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tools/install-dev")
async def install_dev_tool(request: InstallDevToolRequest):
    """
    개발 중인 도구를 설치합니다 (dev -> installed로 이동)
    """
    try:
        dev_tool_path = DEV_TOOLS_PATH / request.tool_name

        if not dev_tool_path.exists():
            raise HTTPException(status_code=404, detail=f"도구를 찾을 수 없습니다: {request.tool_name}")

        # tool.json 확인
        tool_json = dev_tool_path / "tool.json"
        if not tool_json.exists():
            raise HTTPException(status_code=400, detail="tool.json이 없습니다")

        # handler.py 확인
        handler_py = dev_tool_path / "handler.py"
        if not handler_py.exists():
            raise HTTPException(status_code=400, detail="handler.py가 없습니다")

        # installed로 복사
        INSTALLED_TOOLS_PATH.mkdir(parents=True, exist_ok=True)
        installed_path = INSTALLED_TOOLS_PATH / request.tool_name

        if installed_path.exists():
            shutil.rmtree(installed_path)

        shutil.copytree(dev_tool_path, installed_path)

        # 개발 폴더에서 삭제
        shutil.rmtree(dev_tool_path)

        return {
            "success": True,
            "message": f"'{request.tool_name}' 도구가 설치되었습니다"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools/dev")
async def list_dev_tools():
    """
    개발 중인 도구 목록을 조회합니다.
    """
    try:
        DEV_TOOLS_PATH.mkdir(parents=True, exist_ok=True)
        tools = []

        for tool_dir in DEV_TOOLS_PATH.iterdir():
            if tool_dir.is_dir():
                tool_json = tool_dir / "tool.json"
                tool_info = {
                    "name": tool_dir.name,
                    "description": "",
                    "files": [f.name for f in tool_dir.iterdir() if f.is_file()],
                    "has_handler": (tool_dir / "handler.py").exists()
                }

                if tool_json.exists():
                    try:
                        with open(tool_json, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            if isinstance(data, list):
                                data = data[0] if data else {}
                            tool_info["name"] = data.get("name", tool_dir.name)
                            tool_info["description"] = data.get("description", "")
                    except:
                        pass

                tools.append(tool_info)

        return {"tools": tools}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tools/dev/{tool_name}")
async def delete_dev_tool(tool_name: str):
    """
    개발 중인 도구를 삭제합니다.
    """
    try:
        dev_tool_path = DEV_TOOLS_PATH / tool_name

        if not dev_tool_path.exists():
            raise HTTPException(status_code=404, detail=f"도구를 찾을 수 없습니다: {tool_name}")

        shutil.rmtree(dev_tool_path)

        return {
            "success": True,
            "message": f"'{tool_name}' 도구가 삭제되었습니다"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
