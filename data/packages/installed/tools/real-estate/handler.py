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
    모든 도구가 기간 범위 조회를 지원 (start_month/end_month)
    """
    if tool_name == "apt_trade_price":
        tool = load_module("tool_apt_trade_range")
        region_code = params.get("region_code")
        start_month = params.get("start_month")
        end_month = params.get("end_month")
        count_per_month = params.get("count_per_month", 30)
        return tool.get_apt_trade_range(region_code, start_month, end_month, count_per_month)

    elif tool_name == "apt_rent_price":
        tool = load_module("tool_apt_rent")
        region_code = params.get("region_code")
        start_month = params.get("start_month")
        end_month = params.get("end_month")
        count_per_month = params.get("count_per_month", 30)
        return tool.get_apt_rent(region_code, start_month, end_month, count_per_month)

    elif tool_name == "house_trade_price":
        tool = load_module("tool_house_trade_range")
        region_code = params.get("region_code")
        start_month = params.get("start_month")
        end_month = params.get("end_month")
        count_per_month = params.get("count_per_month", 30)
        return tool.get_house_trade_range(region_code, start_month, end_month, count_per_month)

    elif tool_name == "house_rent_price":
        tool = load_module("tool_house_rent")
        region_code = params.get("region_code")
        start_month = params.get("start_month")
        end_month = params.get("end_month")
        count_per_month = params.get("count_per_month", 30)
        return tool.get_house_rent(region_code, start_month, end_month, count_per_month)

    elif tool_name == "get_region_codes":
        tool = load_module("tool_region_codes")
        city = params.get("city", "")
        return tool.get_region_codes(city)

    else:
        return {
            "success": False,
            "error": f"Unknown tool: {tool_name}"
        }

def get_definitions():
    """모든 도구 정의 반환 - tool.json에서 읽음"""
    import json
    tool_json_path = current_dir / "tool.json"
    with open(tool_json_path, 'r', encoding='utf-8') as f:
        return json.load(f)
