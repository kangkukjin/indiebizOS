"""
browser-action 패키지 핸들러
Playwright MCP 스타일 브라우저 자동화 도구

Version: 3.0.0
"""

import json
import sys
import importlib.util
from pathlib import Path

current_dir = Path(__file__).parent

# 모듈 캐싱 (BrowserSession 싱글톤 유지를 위해 필수)
_module_cache = {}


def _load(module_name):
    """같은 디렉토리의 모듈을 캐싱하여 로드"""
    if module_name in _module_cache:
        return _module_cache[module_name]

    # browser_session을 먼저 로드하여 다른 모듈에서 import 가능하게 설정
    if module_name != "browser_session" and "browser_session" not in _module_cache:
        _load("browser_session")

    module_path = current_dir / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)

    # sys.modules에 등록하여 다른 모듈에서 import 가능하게 함
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    _module_cache[module_name] = module
    return module


# 도구 이름 → (모듈명, 함수명, project_path 필요 여부)
_TOOL_ROUTING = {
    # 네비게이션
    "browser_navigate":         ("browser_navigate", "browser_navigate", True),
    "browser_navigate_back":    ("browser_navigate", "browser_navigate_back", False),
    "browser_navigate_forward": ("browser_navigate", "browser_navigate_forward", False),
    "browser_open":             ("browser_navigate", "browser_open", True),

    # 스냅샷
    "browser_snapshot":         ("browser_snapshot", "browser_snapshot", False),
    "browser_get_interactive":  ("browser_snapshot", "browser_get_interactive", False),

    # 상호작용
    "browser_click":            ("browser_interact", "browser_click", False),
    "browser_type":             ("browser_interact", "browser_type", False),
    "browser_select_option":    ("browser_interact", "browser_select_option", False),
    "browser_hover":            ("browser_interact", "browser_hover", False),
    "browser_drag":             ("browser_interact", "browser_drag", False),
    "browser_press_key":        ("browser_interact", "browser_press_key", False),

    # 콘텐츠 및 출력
    "browser_scroll":           ("browser_content", "browser_scroll", False),
    "browser_wait_for":         ("browser_content", "browser_wait_for", False),
    "browser_screenshot":       ("browser_content", "browser_screenshot", True),
    "browser_get_content":      ("browser_content", "browser_get_content", False),
    "browser_console_logs":     ("browser_content", "browser_console_logs", False),
    "browser_save_pdf":         ("browser_content", "browser_save_pdf", True),
    "browser_evaluate":         ("browser_content", "browser_evaluate", False),
    "browser_close":            ("browser_content", "browser_close", False),

    # 탭/iframe 관리
    "browser_tab_list":         ("browser_tabs", "browser_tab_list", False),
    "browser_tab_new":          ("browser_tabs", "browser_tab_new", False),
    "browser_tab_switch":       ("browser_tabs", "browser_tab_switch", False),
    "browser_tab_close":        ("browser_tabs", "browser_tab_close", False),
    "browser_iframe_list":      ("browser_tabs", "browser_iframe_list", False),
    "browser_iframe_switch":    ("browser_tabs", "browser_iframe_switch", False),
    "browser_iframe_reset":     ("browser_tabs", "browser_iframe_reset", False),

    # 쿠키/인증 상태
    "browser_cookies_save":     ("browser_storage", "browser_cookies_save", True),
    "browser_cookies_load":     ("browser_storage", "browser_cookies_load", True),
}


async def execute(tool_name: str, params: dict, project_path: str = None):
    """메인 핸들러 (async)"""
    proj_path = project_path or "."

    if tool_name not in _TOOL_ROUTING:
        return json.dumps({
            "success": False,
            "error": f"알 수 없는 도구: {tool_name}",
            "available_tools": list(_TOOL_ROUTING.keys())
        }, ensure_ascii=False)

    module_name, func_name, needs_project = _TOOL_ROUTING[tool_name]

    try:
        mod = _load(module_name)
        func = getattr(mod, func_name)

        if needs_project:
            result = await func(params, proj_path)
        else:
            result = await func(params)

        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"도구 실행 실패 ({tool_name}): {str(e)}"
        }, ensure_ascii=False)
