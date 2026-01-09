"""
system_ai.py - 시스템 AI 도구 로딩 유틸리티
IndieBiz OS Core

시스템 AI가 사용하는 도구를 패키지에서 동적으로 로딩합니다.
"""

import json
from pathlib import Path
from typing import List, Dict

from ai_agent import execute_tool as execute_package_tool

# 경로 설정
BACKEND_PATH = Path(__file__).parent
DATA_PATH = BACKEND_PATH.parent / "data"
INSTALLED_TOOLS_PATH = DATA_PATH / "packages" / "installed" / "tools"

# 시스템 AI 기본 패키지 목록
SYSTEM_AI_DEFAULT_PACKAGES = ["system_essentials", "python-exec", "nodejs"]


def load_tools_from_packages(package_names: List[str] = None) -> List[Dict]:
    """
    설치된 패키지에서 도구 정의 로드

    Args:
        package_names: 로드할 패키지 이름 목록 (None이면 기본 패키지)

    Returns:
        도구 정의 목록
    """
    if package_names is None:
        package_names = SYSTEM_AI_DEFAULT_PACKAGES

    tools = []

    for pkg_name in package_names:
        pkg_path = INSTALLED_TOOLS_PATH / pkg_name / "tool.json"
        if pkg_path.exists():
            try:
                with open(pkg_path, 'r', encoding='utf-8') as f:
                    pkg_data = json.load(f)

                    # tools 배열이 있으면 여러 도구 패키지
                    if "tools" in pkg_data:
                        for tool in pkg_data["tools"]:
                            tools.append(tool)
                    # 단일 도구 패키지 (name 필드가 있으면)
                    elif "name" in pkg_data:
                        tools.append(pkg_data)
            except Exception as e:
                print(f"[시스템AI] 패키지 로드 실패 {pkg_name}: {e}")

    return tools


def execute_system_tool(tool_name: str, tool_input: dict, work_dir: str = ".") -> str:
    """
    시스템 AI 도구 실행 - 모든 도구를 패키지에서 동적 로딩
    """
    return execute_package_tool(tool_name, tool_input, work_dir)
