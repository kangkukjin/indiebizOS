"""
KOSIS (국가통계포털) API 도구 패키지 핸들러
"""
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
    kosis_api = load_module("tool_kosis_api")

    if tool_name == "kosis_search_statistics":
        return kosis_api.search_statistics(
            keyword=params.get("keyword"),
            vw_cd=params.get("vw_cd", "MT_ZTITLE"),
            parent_list_id=params.get("parent_list_id")
        )

    elif tool_name == "kosis_get_data":
        return kosis_api.get_statistics_data(
            org_id=params.get("org_id"),
            tbl_id=params.get("tbl_id"),
            itm_id=params.get("itm_id", "ALL"),
            obj_l1=params.get("obj_l1", "ALL"),
            obj_l2=params.get("obj_l2", "ALL"),
            obj_l3=params.get("obj_l3", "ALL"),
            prd_se=params.get("prd_se", "Y"),
            start_prd_de=params.get("start_prd_de"),
            end_prd_de=params.get("end_prd_de")
        )

    elif tool_name == "kosis_get_statistics_info":
        return kosis_api.get_statistics_info(
            org_id=params.get("org_id"),
            tbl_id=params.get("tbl_id")
        )

    elif tool_name == "kosis_integrated_search":
        return kosis_api.integrated_search(
            keyword=params.get("keyword"),
            count=params.get("count", 10)
        )

    elif tool_name == "kosis_get_indicators":
        return kosis_api.get_indicators(
            indicator_id=params.get("indicator_id"),
            start_prd_de=params.get("start_prd_de"),
            end_prd_de=params.get("end_prd_de")
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
