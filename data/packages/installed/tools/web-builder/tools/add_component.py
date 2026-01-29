"""
add_component.py
shadcn/ui 컴포넌트를 프로젝트에 추가합니다.
"""

import subprocess
import json
import os

TOOL_NAME = "add_component"
TOOL_DESCRIPTION = "shadcn/ui 컴포넌트를 프로젝트에 추가합니다"
TOOL_PARAMETERS = {
    "project_path": {
        "type": "string",
        "description": "프로젝트 경로",
        "required": True
    },
    "components": {
        "type": "array",
        "description": "추가할 컴포넌트 목록",
        "items": {"type": "string"},
        "required": True
    }
}

# 모든 shadcn/ui 컴포넌트 목록
AVAILABLE_COMPONENTS = [
    "accordion", "alert", "alert-dialog", "aspect-ratio", "avatar",
    "badge", "breadcrumb", "button", "calendar", "card", "carousel",
    "chart", "checkbox", "collapsible", "combobox", "command",
    "context-menu", "data-table", "date-picker", "dialog", "drawer",
    "dropdown-menu", "form", "hover-card", "input", "input-otp",
    "label", "menubar", "navigation-menu", "pagination", "popover",
    "progress", "radio-group", "resizable", "scroll-area", "select",
    "separator", "sheet", "skeleton", "slider", "sonner", "switch",
    "table", "tabs", "textarea", "toast", "toggle", "toggle-group",
    "tooltip"
]


def run_command(cmd: list, cwd: str = None, timeout: int = 60) -> dict:
    """명령어 실행"""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "시간 초과"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def update_project_info(project_path: str, added_components: list) -> None:
    """프로젝트 정보 파일 업데이트"""
    info_path = os.path.join(project_path, ".web-builder.json")

    if os.path.exists(info_path):
        with open(info_path, "r") as f:
            info = json.load(f)
    else:
        info = {"shadcn_components": []}

    existing = set(info.get("shadcn_components", []))
    existing.update(added_components)
    info["shadcn_components"] = sorted(list(existing))

    with open(info_path, "w") as f:
        json.dump(info, f, indent=2)


def run(project_path: str, components: list) -> dict:
    """
    shadcn/ui 컴포넌트 추가

    Args:
        project_path: 프로젝트 경로
        components: 추가할 컴포넌트 목록

    Returns:
        추가 결과
    """
    # 프로젝트 존재 확인
    if not os.path.exists(project_path):
        return {
            "success": False,
            "error": f"프로젝트를 찾을 수 없습니다: {project_path}"
        }

    # components.json 확인
    config_path = os.path.join(project_path, "components.json")
    if not os.path.exists(config_path):
        return {
            "success": False,
            "error": "shadcn 설정 파일(components.json)이 없습니다. create_project로 먼저 프로젝트를 생성하세요."
        }

    # 유효한 컴포넌트 필터링
    valid_components = []
    invalid_components = []

    for comp in components:
        comp_lower = comp.lower().strip()
        if comp_lower in AVAILABLE_COMPONENTS:
            valid_components.append(comp_lower)
        else:
            invalid_components.append(comp)

    if not valid_components:
        return {
            "success": False,
            "error": f"유효한 컴포넌트가 없습니다. 잘못된 입력: {invalid_components}",
            "available_components": AVAILABLE_COMPONENTS
        }

    results = {
        "added": [],
        "failed": [],
        "skipped": invalid_components
    }

    # 컴포넌트 추가
    for component in valid_components:
        cmd = ["npx", "shadcn@latest", "add", component, "--yes"]
        result = run_command(cmd, cwd=project_path)

        if result["success"]:
            results["added"].append(component)
        else:
            results["failed"].append({
                "component": component,
                "error": result.get("stderr", result.get("error", ""))[:200]
            })

    # 프로젝트 정보 업데이트
    if results["added"]:
        update_project_info(project_path, results["added"])

    success = len(results["added"]) > 0

    return {
        "success": success,
        "project_path": project_path,
        "results": results,
        "summary": f"추가됨: {len(results['added'])}, 실패: {len(results['failed'])}, 건너뜀: {len(results['skipped'])}"
    }


if __name__ == "__main__":
    result = run(
        project_path="/Users/kangkukjin/Desktop/AI/outputs/web-projects/test-project",
        components=["card", "dialog", "invalid-component"]
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
