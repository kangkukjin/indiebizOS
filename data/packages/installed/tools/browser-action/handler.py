"""
browser-action 패키지 핸들러
Playwright MCP 스타일 브라우저 자동화 도구

Version: 2.0.0
"""

import json
import importlib.util
from pathlib import Path

current_dir = Path(__file__).parent

# 모듈 캐싱 (BrowserSession 싱글톤 유지를 위해 필수)
_module_cache = {}


def _load_module(module_name):
    """같은 디렉토리의 모듈을 캐싱하여 로드"""
    if module_name in _module_cache:
        return _module_cache[module_name]
    module_path = current_dir / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _module_cache[module_name] = module
    return module


async def execute(tool_name: str, params: dict, project_path: str = None):
    """메인 핸들러 (async)"""
    mod = _load_module("tool_browser_direct")

    # 프로젝트 경로 기본값
    proj_path = project_path or "."

    # 도구 함수 매핑
    func_map = {
        # 네비게이션
        "browser_navigate": lambda: mod.browser_navigate(params, proj_path),
        "browser_navigate_back": lambda: mod.browser_navigate_back(params),
        "browser_navigate_forward": lambda: mod.browser_navigate_forward(params),

        # Accessibility Snapshot (핵심!)
        "browser_snapshot": lambda: mod.browser_snapshot(params),

        # 상호작용 (ref 기반)
        "browser_click": lambda: mod.browser_click(params),
        "browser_type": lambda: mod.browser_type(params),
        "browser_select_option": lambda: mod.browser_select_option(params),
        "browser_hover": lambda: mod.browser_hover(params),
        "browser_drag": lambda: mod.browser_drag(params),
        "browser_press_key": lambda: mod.browser_press_key(params),

        # 스크롤 및 대기
        "browser_scroll": lambda: mod.browser_scroll(params),
        "browser_wait_for": lambda: mod.browser_wait_for(params),

        # 콘텐츠 및 출력
        "browser_screenshot": lambda: mod.browser_screenshot(params, proj_path),
        "browser_get_content": lambda: mod.browser_get_content(params),
        "browser_console_logs": lambda: mod.browser_console_logs(params),
        "browser_save_pdf": lambda: mod.browser_save_pdf(params, proj_path),
        "browser_evaluate": lambda: mod.browser_evaluate(params),

        # 종료
        "browser_close": lambda: mod.browser_close(params),

        # 하위 호환성 (기존 도구 이름)
        "browser_open": lambda: mod.browser_open(params, proj_path),
        "browser_get_interactive": lambda: mod.browser_get_interactive(params),
    }

    if tool_name not in func_map:
        return json.dumps({
            "success": False,
            "error": f"알 수 없는 도구: {tool_name}",
            "available_tools": list(func_map.keys())
        }, ensure_ascii=False)

    # async 함수 호출
    result = await func_map[tool_name]()
    return json.dumps(result, ensure_ascii=False, indent=2)
