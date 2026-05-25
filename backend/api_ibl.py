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
