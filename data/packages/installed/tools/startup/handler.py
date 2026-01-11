import importlib.util
from pathlib import Path

current_dir = Path(__file__).parent

def load_module(module_name):
    module_path = current_dir / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def execute(tool_name: str, params: dict, project_path: str = None):
    """
    IndieBiz OS에서 도구를 호출할 때 실행되는 메인 핸들러
    """
    if tool_name == "search_kstartup":
        tool = load_module("tool_kstartup")
        keyword = params.get("keyword", "")
        count = params.get("count", 10)
        return tool.search_kstartup(keyword, count)

    elif tool_name == "search_mss_biz":
        tool = load_module("tool_mss_biz")
        keyword = params.get("keyword", "")
        count = params.get("count", 10)
        return tool.search_mss_biz(keyword, count)

    else:
        return {
            "success": False,
            "error": f"Unknown tool: {tool_name}"
        }

def get_definitions():
    """모든 도구 정의 반환"""
    tool_kstartup = load_module("tool_kstartup")
    tool_mss = load_module("tool_mss_biz")
    return [
        tool_kstartup.get_tool_definition(),
        tool_mss.get_tool_definition()
    ]
