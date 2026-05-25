"""
KOSIS (국가통계포털) API 도구 패키지 핸들러
"""
import os
import sys
import importlib.util
from pathlib import Path

# common 유틸리티 사용
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

current_dir = Path(__file__).parent

def load_module(module_name):
    module_path = current_dir / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def execute(tool_input: dict, context):
    """IndieBiz OS에서 도구를 호출할 때 실행되는 메인 핸들러 (ToolContext 기반 신규 시그니처)."""
    tool_name = context.tool_name
    kosis_api = load_module("tool_kosis_api")

    if tool_name == "kosis_search_statistics":
        return kosis_api.search_statistics(
            keyword=tool_input.get("keyword"),
            vw_cd=tool_input.get("vw_cd", "MT_ZTITLE"),
            parent_list_id=tool_input.get("parent_list_id")
        )

    elif tool_name == "kosis_get_data":
        return kosis_api.get_statistics_data(
            org_id=tool_input.get("org_id"),
            tbl_id=tool_input.get("tbl_id"),
            itm_id=tool_input.get("itm_id", "ALL"),
            obj_l1=tool_input.get("obj_l1", "ALL"),
            obj_l2=tool_input.get("obj_l2", "ALL"),
            obj_l3=tool_input.get("obj_l3", "ALL"),
            prd_se=tool_input.get("prd_se", "Y"),
            start_prd_de=tool_input.get("start_prd_de"),
            end_prd_de=tool_input.get("end_prd_de")
        )

    elif tool_name == "kosis_get_statistics_info":
        return kosis_api.get_statistics_info(
            org_id=tool_input.get("org_id"),
            tbl_id=tool_input.get("tbl_id")
        )

    elif tool_name == "kosis_integrated_search":
        return kosis_api.integrated_search(
            keyword=tool_input.get("keyword"),
            count=tool_input.get("count", 10)
        )

    elif tool_name == "kosis_get_indicators":
        return kosis_api.get_indicators(
            indicator_id=tool_input.get("indicator_id"),
            start_prd_de=tool_input.get("start_prd_de"),
            end_prd_de=tool_input.get("end_prd_de")
        )

    else:
        return {
            "success": False,
            "error": f"Unknown tool: {tool_name}"
        }

def get_definitions():
    """모든 도구 정의 반환"""
    kosis_api = load_module("tool_kosis_api")
    return kosis_api.get_tool_definitions()
