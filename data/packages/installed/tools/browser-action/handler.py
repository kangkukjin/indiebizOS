"""
browser-action 패키지 핸들러
Playwright 직접 제어 브라우저 도구
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


def execute(tool_name: str, params: dict, project_path: str = None):
    """메인 핸들러"""
    mod = _load_module("tool_browser_direct")

    func_map = {
        "browser_open": lambda: mod.browser_open(params, project_path or "."),
        "browser_click": lambda: mod.browser_click(params),
        "browser_type": lambda: mod.browser_type(params),
        "browser_screenshot": lambda: mod.browser_screenshot(params, project_path or "."),
        "browser_get_content": lambda: mod.browser_get_content(params),
        "browser_get_interactive": lambda: mod.browser_get_interactive(params),
        "browser_scroll": lambda: mod.browser_scroll(params),
        "browser_evaluate": lambda: mod.browser_evaluate(params),
        "browser_close": lambda: mod.browser_close(params),
    }

    if tool_name not in func_map:
        return json.dumps({"success": False, "error": f"알 수 없는 도구: {tool_name}"}, ensure_ascii=False)

    result = func_map[tool_name]()
    return json.dumps(result, ensure_ascii=False, indent=2)
