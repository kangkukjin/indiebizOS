"""
Web Builder & Homepage Manager 통합 핸들러
웹사이트 제작 + 등록/관리/점검 도구
"""

import json
import os
import importlib.util
from pathlib import Path

# 패키지 디렉토리
PACKAGE_DIR = Path(__file__).parent
TOOLS_DIR = PACKAGE_DIR / "tools"

# homepage-manager 도구는 모듈 파일명과 도구 이름이 다름
_TOOL_MODULE_MAP = {
    "site_registry": "registry",
    "site_list": "registry",
    "site_register": "registry",
    "site_remove": "registry",
    "site_update": "registry",
    "site_snapshot": "snapshot",
    "site_live_check": "live_check",
}


# 2026-06-03 dispatcher 표준화 — 단일 액션 op 키 메타데이터.
# 값 None — 분기는 execute() 상단에서 내부 tool_name으로 변환. --check 가 키로 src.ops.values 와 정확 비교.
_OP_DISPATCHERS = {
    "web_site": {"list": None, "register": None, "remove": None, "update": None},
    "web_op": {"create": None, "build": None, "deploy": None, "preview": None, "snapshot": None, "check": None, "styles": None},
    "web_component_op": {"catalog": None, "fetch": None, "add": None},
}
_OP_DEFAULTS = {"web_site": "list", "web_op": "preview", "web_component_op": "fetch"}


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


def execute(tool_input: dict, context) -> str:
    """도구 실행 진입점 (ToolContext 기반 신규 시그니처)."""
    tool_name = context.tool_name

    # 단일 액션 op 분기 — IBL 진입점을 내부 tool_name으로 디스패치.
    # (2026-06-03 어휘 정리: web 9개 → web/web_component/web_site 3개)
    if tool_name == "web_site":
        op = (tool_input.get("op") or _OP_DEFAULTS["web_site"]).lower()
        tool_name = {
            "list": "site_list", "register": "site_register",
            "remove": "site_remove", "update": "site_update",
        }.get(op, "site_list")
    elif tool_name == "web_op":
        op = (tool_input.get("op") or _OP_DEFAULTS["web_op"]).lower()
        if op == "create":
            target = (tool_input.get("target") or "site").lower()
            tool_name = "create_page" if target == "page" else "create_project"
        else:
            tool_name = {
                "build": "build_site", "deploy": "deploy_vercel",
                "preview": "preview_site", "snapshot": "site_snapshot",
                "check": "site_live_check", "styles": "edit_styles",
            }.get(op, "preview_site")
    elif tool_name == "web_component_op":
        op = (tool_input.get("op") or _OP_DEFAULTS["web_component_op"]).lower()
        if op == "catalog":
            kind = (tool_input.get("kind") or "components").lower()
            tool_name = "list_sections" if kind == "sections" else "list_components"
        elif op == "add":
            tool_name = "add_component"
        else:  # fetch
            tool_name = "fetch_component"

    # site_id → project_path 내부 해소
    # 코퍼스/사용자는 site_id로 호출(preview/build/deploy/styles 등)하나
    # 빌더 도구들은 project_path를 읽음 → 등록된 사이트면 로컬 경로로 변환.
    if not tool_input.get("project_path") and tool_input.get("site_id"):
        try:
            _snap = load_tool_module("snapshot")
            _site = _snap.find_site(tool_input["site_id"], PACKAGE_DIR) if _snap else None
            if _site and _site.get("local_path"):
                tool_input["project_path"] = _site["local_path"]
        except Exception:
            pass

    try:
        # 도구 모듈 로드
        module = load_tool_module(tool_name)

        if module is None:
            return json.dumps({
                "success": False,
                "error": f"도구를 찾을 수 없습니다: {tool_name}",
                "available_tools": TOOLS
            }, ensure_ascii=False)

        # === 사이트 관리 — 원자 액션 (각각 직접 호출) ===
        if tool_name == "site_list":
            result = module.list_sites(PACKAGE_DIR)
        elif tool_name == "site_register":
            result = module.register_site(tool_input, PACKAGE_DIR)
        elif tool_name == "site_remove":
            result = module.remove_site(tool_input.get("site_id"), PACKAGE_DIR)
        elif tool_name == "site_update":
            result = module.update_site(tool_input, PACKAGE_DIR)

        # === 사이트 관리 — 레거시 + snapshot/live_check ===
        elif tool_name in ("site_registry", "site_snapshot", "site_live_check"):
            result = module.run(tool_input, PACKAGE_DIR)

        # === 웹 빌더 도구 (개별 파라미터 전달 방식) ===
        elif tool_name == "create_project":
            raw_output_dir = tool_input.get("output_dir")
            result = module.run(
                name=tool_input.get("name"),
                template=tool_input.get("template", "blank"),
                features=tool_input.get("features", ["dark_mode", "seo"]),
                output_dir=context.resolve_path(raw_output_dir) if raw_output_dir else None
            )

        elif tool_name == "add_component":
            # 코퍼스/사용자는 component(단수 문자열)도 씀 → 리스트로 래핑.
            _comps = tool_input.get("components")
            if not _comps and tool_input.get("component"):
                _c = tool_input["component"]
                _comps = _c if isinstance(_c, list) else [_c]
            result = module.run(
                project_path=tool_input.get("project_path"),
                components=_comps or []
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
    "site_list",
    "site_register",
    "site_remove",
    "site_update",
    "site_registry",  # 레거시 호환
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
