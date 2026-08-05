"""api_health.py — 의료기록(health_records.db) 폰↔PC 동기화 API.

backend/api_business.py 의 sync 엔드포인트 동형 미러. 실제 머지는 health_sync.py
(LWW + tombstone + 이미지 base64 전송).

★인증: api.py 의 remote_access_guard 미들웨어가 외부(터널) 요청에 launcher 세션
(X-Launcher-Session)을 강제한다(localhost=데스크탑은 통과). 의료기록 전체를 노출하는
데이터 엔드포인트라 public 화이트리스트(is_public_remote_path)에 넣지 않는다 →
외부는 반드시 로그인 후 접근.
"""
from fastapi import APIRouter, HTTPException, Body

router = APIRouter(prefix="/health")


@router.get("/sync/export")
async def health_sync_export():
    """이 기기의 health_records.db 동기화 스냅샷(5테이블 + 문서 이미지 base64, tombstone 포함)."""
    try:
        from health_sync import export_health_db
        return {"success": True, "data": export_health_db()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/merge")
async def health_sync_merge(payload: dict = Body(...)):
    """다른 기기의 export 를 이 기기에 합집합 머지(LWW+tombstone+이미지) 후, 머지된 이 기기의
    최신 스냅샷을 반환 → 호출자가 그걸 다시 머지하면 1왕복 양방향 동기화(교환·멱등).
    payload = {"data": {table: [rows], "images": {...}}} 또는 직접."""
    try:
        from health_sync import export_health_db, merge_health_db
        remote = payload.get("data") if isinstance(payload, dict) and "data" in payload else payload
        if not isinstance(remote, dict):
            raise HTTPException(status_code=400, detail="sync 페이로드 형식 오류(dict 필요)")
        stats = merge_health_db(remote)
        return {"success": True, "stats": stats, "data": export_health_db()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
