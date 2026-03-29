"""
browser-action 패키지 핸들러
Playwright + Chrome MCP 듀얼 드라이버 브라우저 자동화 도구

Version: 6.0.0
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

    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    _module_cache[module_name] = module
    return module


def _is_chrome_connected() -> bool:
    """Chrome MCP 드라이버 연결 상태 확인"""
    try:
        mod = _load("browser_chrome")
        driver = mod.ChromeMCPDriver.get_instance()
        return driver.is_connected()
    except Exception:
        return False


# Chrome 전용 도구 (Playwright에 없는 것들)
_CHROME_ONLY_TOOLS = {
    "browser_chrome_connect":    ("browser_chrome", "browser_chrome_connect", False),
    "browser_chrome_disconnect": ("browser_chrome", "browser_chrome_disconnect", False),
    "browser_chrome_status":     ("browser_chrome", "browser_chrome_status", False),
    "browser_find":              ("browser_chrome", "browser_find", False),
}

# Chrome 드라이버에서 project_path가 필요한 도구들
_CHROME_PROJECT_TOOLS = {"browser_navigate", "browser_screenshot", "browser_save_pdf", "browser_vision",
                         "browser_cookies_save", "browser_cookies_load"}

# 도구 이름 → (모듈명, 함수명, project_path 필요 여부) — Playwright용
_TOOL_ROUTING = {
    # 네비게이션
    "browser_navigate":         ("browser_navigate", "browser_navigate", True),
    "browser_navigate_back":    ("browser_navigate", "browser_navigate_back", False),
    "browser_navigate_forward": ("browser_navigate", "browser_navigate_forward", False),

    # 스냅샷
    "browser_snapshot":         ("browser_snapshot", "browser_snapshot", False),

    # 상호작용
    "browser_click":            ("browser_interact", "browser_click", False),
    "browser_dblclick":         ("browser_interact", "browser_dblclick", False),
    "browser_rightclick":       ("browser_interact", "browser_rightclick", False),
    "browser_type":             ("browser_interact", "browser_type", False),
    "browser_select_option":    ("browser_interact", "browser_select_option", False),
    "browser_check":            ("browser_interact", "browser_check", False),
    "browser_hover":            ("browser_interact", "browser_hover", False),
    "browser_drag":             ("browser_interact", "browser_drag", False),
    "browser_press_key":        ("browser_interact", "browser_press_key", False),
    "browser_upload_file":      ("browser_interact", "browser_upload_file", False),

    # 콘텐츠 및 출력
    "browser_scroll":           ("browser_content", "browser_scroll", False),
    "browser_wait_for":         ("browser_content", "browser_wait_for", False),
    "browser_screenshot":       ("browser_content", "browser_screenshot", True),
    "browser_get_content":      ("browser_content", "browser_get_content", False),
    "browser_get_html":         ("browser_content", "browser_get_html", False),
    "browser_console_logs":     ("browser_content", "browser_console_logs", False),
    "browser_network_logs":     ("browser_content", "browser_network_logs", False),
    "browser_dialog_info":      ("browser_content", "browser_dialog_info", False),
    "browser_save_pdf":         ("browser_content", "browser_save_pdf", True),
    "browser_evaluate":         ("browser_content", "browser_evaluate", False),
    "browser_resize":           ("browser_content", "browser_resize", False),
    "browser_vision":           ("browser_content", "browser_vision", True),
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
    """메인 핸들러 (async) — driver 파라미터로 Playwright/Chrome 분기"""
    proj_path = project_path or "."

    # Chrome 전용 도구는 항상 Chrome 모듈로 라우팅
    if tool_name in _CHROME_ONLY_TOOLS:
        module_name, func_name, needs_project = _CHROME_ONLY_TOOLS[tool_name]
        try:
            mod = _load(module_name)
            func = getattr(mod, func_name)
            result = await func(params, proj_path) if needs_project else await func(params)
            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": f"Chrome 도구 실패 ({tool_name}): {str(e)}"}, ensure_ascii=False)

    # 일반 도구: driver 파라미터로 분기
    driver = params.pop("driver", "auto")

    if driver == "auto":
        driver = "chrome" if _is_chrome_connected() else "playwright"

    all_tools = {**_TOOL_ROUTING, **_CHROME_ONLY_TOOLS}
    if tool_name not in _TOOL_ROUTING and tool_name not in _CHROME_ONLY_TOOLS:
        return json.dumps({
            "success": False,
            "error": f"알 수 없는 도구: {tool_name}",
            "available_tools": list(all_tools.keys())
        }, ensure_ascii=False)

    try:
        if driver == "chrome":
            # Chrome MCP 드라이버로 라우팅
            mod = _load("browser_chrome")
            func = getattr(mod, tool_name, None)
            if func is None:
                # Chrome에 해당 함수가 없으면 Playwright로 폴백
                driver = "playwright"
            else:
                needs_project = tool_name in _CHROME_PROJECT_TOOLS
                result = await func(params, proj_path) if needs_project else await func(params)
                return json.dumps(result, ensure_ascii=False, indent=2)

        # Playwright 드라이버 (기본 또는 폴백)
        if tool_name not in _TOOL_ROUTING:
            return json.dumps({"success": False, "error": f"Playwright 드라이버에서 지원하지 않는 도구: {tool_name}"}, ensure_ascii=False)

        module_name, func_name, needs_project = _TOOL_ROUTING[tool_name]
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
            "error": f"도구 실행 실패 ({tool_name}, driver={driver}): {str(e)}"
        }, ensure_ascii=False)
