"""api_ibl.py - IBL 직접 실행 API (MCP/외부 도구용)"""
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/ibl", tags=["ibl"])

class IBLRequest(BaseModel):
    code: str
    project_path: str = "."

@router.post("/execute")
async def execute_ibl_code(req: IBLRequest):
    try:
        from system_tools import _execute_ibl_unified
        result = _execute_ibl_unified({"code": req.code}, req.project_path)

        # 결과가 str이면 JSON 파싱 시도. 실패 시 plain text로 wrap.
        # (일부 IBL 액션은 JSON이 아닌 평문/markdown/빈문자열을 반환)
        if isinstance(result, str):
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                return {"result": result}
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/actions/catalog")
async def get_actions_catalog():
    """IBL 액션 카탈로그 — 마법책 UI 데이터 소스.

    5개 노드(sense, self, limbs, others, engines)별로 분류된
    전체 IBL 액션 목록을 반환한다. 프론트의 액션 사전 모달이
    이 데이터로 책장을 그린다.
    """
    from ibl_access import _load_nodes_data
    data = _load_nodes_data()
    if not data:
        raise HTTPException(status_code=500, detail="ibl_nodes.yaml 로드 실패")

    nodes_out: dict = {}
    total = 0
    for node_name, node_config in (data.get("nodes") or {}).items():
        actions: dict = {}
        for action_name, action_config in (node_config.get("actions") or {}).items():
            actions[action_name] = {
                "description": action_config.get("description", ""),
                "target_description": action_config.get("target_description", ""),
                "target_key": action_config.get("target_key", ""),
                "implementation": action_config.get("implementation", ""),
                "keywords": action_config.get("keywords") or [],
                "group": action_config.get("group", ""),
            }
        nodes_out[node_name] = {"actions": actions, "count": len(actions)}
        total += len(actions)

    return {"nodes": nodes_out, "total": total}
