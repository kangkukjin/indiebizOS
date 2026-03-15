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
        return json.loads(result) if isinstance(result, str) else result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
