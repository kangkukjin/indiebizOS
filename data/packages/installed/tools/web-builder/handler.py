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


def _require_module(tool_name: str):
    mod = load_tool_module(tool_name)
    if mod is None:
        raise ValueError(f"도구 모듈을 찾을 수 없습니다: {tool_name}")
    return mod


# --- op 핸들러 (각 op = 모듈 로드 + 파라미터 셰이핑 후 직접 호출·return) ---
# 2026-07-02: 옛 `tool_name = {...}[op]` 재할당+fall-through(변종2)를 직접-return(변종1)으로
# 전환. 레거시 내부 tool명(site_list·create_project·preview_site 등)은 더 이상 tool_name으로
# 부활하지 않으므로 tool.json에서도 은퇴 — web_site/web_op/web_component_op 3개만 IBL 진입점.
# (내부 tool명은 여전히 load_tool_module 의 모듈 파일 식별자로만 쓰임.)

def _h_site_list(ti, ctx):
    return _require_module("site_list").list_sites(PACKAGE_DIR)


def _h_site_register(ti, ctx):
    return _require_module("site_register").register_site(ti, PACKAGE_DIR)


def _h_site_remove(ti, ctx):
    return _require_module("site_remove").remove_site(ti.get("site_id"), PACKAGE_DIR)


def _h_site_update(ti, ctx):
    return _require_module("site_update").update_site(ti, PACKAGE_DIR)


def _h_site_snapshot(ti, ctx):
    return _require_module("site_snapshot").run(ti, PACKAGE_DIR)


def _h_site_live_check(ti, ctx):
    return _require_module("site_live_check").run(ti, PACKAGE_DIR)


def _h_create_project(ti, ctx):
    raw_output_dir = ti.get("output_dir")
    return _require_module("create_project").run(
        name=ti.get("name"),
        template=ti.get("template", "blank"),
        features=ti.get("features", ["dark_mode", "seo"]),
        output_dir=ctx.resolve_path(raw_output_dir) if raw_output_dir else None,
    )


def _h_create_page(ti, ctx):
    return _require_module("create_page").run(
        project_path=ti.get("project_path"),
        page_name=ti.get("page_name"),
        sections=ti.get("sections", []),
        metadata=ti.get("metadata"),
    )


def _h_add_component(ti, ctx):
    # 코퍼스/사용자는 component(단수 문자열)도 씀 → 리스트로 래핑.
    _comps = ti.get("components")
    if not _comps and ti.get("component"):
        _c = ti["component"]
        _comps = _c if isinstance(_c, list) else [_c]
    return _require_module("add_component").run(
        project_path=ti.get("project_path"),
        components=_comps or [],
    )


def _h_list_components(ti, ctx):
    return _require_module("list_components").run(
        project_path=ti.get("project_path"),
        category=ti.get("category", "all"),
    )


def _h_list_sections(ti, ctx):
    return _require_module("list_sections").run(
        category=ti.get("category", "all"),
    )


def _h_edit_styles(ti, ctx):
    return _require_module("edit_styles").run(
        project_path=ti.get("project_path"),
        theme=ti.get("theme", "default"),
        custom_colors=ti.get("custom_colors"),
        border_radius=ti.get("border_radius", "md"),
    )


def _h_preview_site(ti, ctx):
    return _require_module("preview_site").run(
        project_path=ti.get("project_path"),
        port=ti.get("port", 3000),
        action=ti.get("action", "start"),
    )


def _h_build_site(ti, ctx):
    return _require_module("build_site").run(
        project_path=ti.get("project_path"),
        analyze=ti.get("analyze", False),
    )


def _h_deploy_vercel(ti, ctx):
    return _require_module("deploy_vercel").run(
        project_path=ti.get("project_path"),
        production=ti.get("production", False),
        project_name=ti.get("project_name"),
    )


def _h_fetch_component(ti, ctx):
    return _require_module("fetch_component").run(
        component=ti.get("component"),
        style=ti.get("style", "new-york"),
        project_path=ti.get("project_path"),
        output_format=ti.get("output_format", "code"),
    )


def _h_web_create(ti, ctx):
    # target: page → create_page, 그 외 → create_project (사이트)
    target = (ti.get("target") or "site").lower()
    return _h_create_page(ti, ctx) if target == "page" else _h_create_project(ti, ctx)


def _h_web_catalog(ti, ctx):
    # kind: sections → list_sections, 그 외 → list_components
    kind = (ti.get("kind") or "components").lower()
    return _h_list_sections(ti, ctx) if kind == "sections" else _h_list_components(ti, ctx)


# 2026-06-03 dispatcher 표준화 — 단일 액션 op 키 메타데이터 겸 디스패치 테이블.
#   --check 는 inner dict 의 키(op)만 src.ops.values 와 AST 비교(값 타입 무관).
_OP_DISPATCHERS = {
    "web_site": {
        "list": _h_site_list, "register": _h_site_register,
        "remove": _h_site_remove, "update": _h_site_update,
    },
    "web_op": {
        "create": _h_web_create, "build": _h_build_site, "deploy": _h_deploy_vercel,
        "preview": _h_preview_site, "snapshot": _h_site_snapshot,
        "check": _h_site_live_check, "styles": _h_edit_styles,
    },
    "web_component_op": {
        "catalog": _h_web_catalog, "fetch": _h_fetch_component, "add": _h_add_component,
    },
}
_OP_DEFAULTS = {"web_site": "list", "web_op": "preview", "web_component_op": "fetch"}


def execute(tool_input: dict, context) -> str:
    """도구 실행 진입점 (ToolContext 기반 신규 시그니처)."""
    tool_name = context.tool_name

    mapping = _OP_DISPATCHERS.get(tool_name)
    if mapping is None:
        return json.dumps({
            "success": False,
            "error": f"알 수 없는 도구: {tool_name}",
        }, ensure_ascii=False)

    # site_id → project_path 내부 해소 (모든 op 공통 전처리)
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

    # op 해소 — 미지의 op 는 _OP_DEFAULTS 핸들러로 폴백(옛 .get(op, 기본) 관용 보존).
    op = (tool_input.get("op") or _OP_DEFAULTS[tool_name]).lower()
    handler = mapping.get(op, mapping[_OP_DEFAULTS[tool_name]])

    try:
        result = handler(tool_input, context)
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
            "tool": f"{tool_name}:{op}",
        }, ensure_ascii=False)


# 도구 목록 (검색/참조용 — IBL 진입점은 _OP_DISPATCHERS 3개, 아래는 내부 모듈 식별자)
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
