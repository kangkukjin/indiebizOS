"""
Web Builder & Homepage Manager 통합 핸들러
웹사이트 제작 + 등록/관리/점검 도구
"""

import json
import importlib.util
from pathlib import Path

# 패키지 디렉토리
PACKAGE_DIR = Path(__file__).parent
TOOLS_DIR = PACKAGE_DIR / "tools"

# homepage-manager 도구는 모듈 파일명과 도구 이름이 다름
_TOOL_MODULE_MAP = {
    "site_registry": "registry",
    "site_snapshot": "snapshot",
    "site_live_check": "live_check",
}


def load_tool_module(tool_name: str):
    """도구 모듈 동적 로드"""
    # 모듈명 매핑 (site_registry → registry.py 등)
    module_name = _TOOL_MODULE_MAP.get(tool_name, tool_name)
    module_path = TOOLS_DIR / f"{module_name}.py"
    if not module_path.exists():
        return None

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def execute(tool_name: str, tool_input: dict, project_path: str = None) -> str:
    """
    도구 실행 진입점

    Args:
        tool_name: 실행할 도구 이름
        tool_input: 도구 입력 파라미터
        project_path: 프로젝트 경로 (컨텍스트)

    Returns:
        JSON 형식의 결과 문자열
    """
    try:
        # 도구 모듈 로드
        module = load_tool_module(tool_name)

        if module is None:
            return json.dumps({
                "success": False,
                "error": f"도구를 찾을 수 없습니다: {tool_name}",
                "available_tools": TOOLS
            }, ensure_ascii=False)

        # === 사이트 관리 도구 (package_dir 전달 방식) ===
        if tool_name in ("site_registry", "site_snapshot", "site_live_check"):
            result = module.run(tool_input, PACKAGE_DIR)

        # === 웹 빌더 도구 (개별 파라미터 전달 방식) ===
        elif tool_name == "create_project":
            result = module.run(
                name=tool_input.get("name"),
                template=tool_input.get("template", "blank"),
                features=tool_input.get("features", ["dark_mode", "seo"]),
                output_dir=tool_input.get("output_dir")
            )

        elif tool_name == "add_component":
            result = module.run(
                project_path=tool_input.get("project_path"),
                components=tool_input.get("components", [])
            )

        elif tool_name == "list_components":
            result = module.run(
                project_path=tool_input.get("project_path"),
                category=tool_input.get("category", "all")
            )

        elif tool_name == "list_sections":
            result = module.run(
                category=tool_input.get("category", "all")
            )

        elif tool_name == "create_page":
            result = module.run(
                project_path=tool_input.get("project_path"),
                page_name=tool_input.get("page_name"),
                sections=tool_input.get("sections", []),
                metadata=tool_input.get("metadata")
            )

        elif tool_name == "edit_styles":
            result = module.run(
                project_path=tool_input.get("project_path"),
                theme=tool_input.get("theme", "default"),
                custom_colors=tool_input.get("custom_colors"),
                border_radius=tool_input.get("border_radius", "md")
            )

        elif tool_name == "preview_site":
            result = module.run(
                project_path=tool_input.get("project_path"),
                port=tool_input.get("port", 3000),
                action=tool_input.get("action", "start")
            )

        elif tool_name == "build_site":
            result = module.run(
                project_path=tool_input.get("project_path"),
                analyze=tool_input.get("analyze", False)
            )

        elif tool_name == "deploy_vercel":
            result = module.run(
                project_path=tool_input.get("project_path"),
                production=tool_input.get("production", False),
                project_name=tool_input.get("project_name")
            )

        elif tool_name == "fetch_component":
            result = module.run(
                component=tool_input.get("component"),
                style=tool_input.get("style", "new-york"),
                project_path=tool_input.get("project_path"),
                output_format=tool_input.get("output_format", "code")
            )

        else:
            return json.dumps({
                "success": False,
                "error": f"알 수 없는 도구: {tool_name}"
            }, ensure_ascii=False)

        # 결과 반환
        if isinstance(result, dict):
            return json.dumps(result, ensure_ascii=False)
        elif isinstance(result, str):
            return result
        else:
            return json.dumps({"success": True, "result": str(result)}, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
            "tool": tool_name
        }, ensure_ascii=False)


# 도구 목록 (검색용)
TOOLS = [
    # 사이트 관리
    "site_registry",
    "site_snapshot",
    "site_live_check",
    # 웹 빌더
    "create_project",
    "add_component",
    "list_components",
    "list_sections",
    "create_page",
    "edit_styles",
    "preview_site",
    "build_site",
    "deploy_vercel",
    "fetch_component",
]


if __name__ == "__main__":
    print("Web Builder & Homepage Manager 도구 목록:", TOOLS)
    print(f"총 {len(TOOLS)}개 도구")
