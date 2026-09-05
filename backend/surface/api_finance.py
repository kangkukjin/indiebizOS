"""api_finance.py — 재무기록(finance_records.db) 폰↔PC 동기화 API.

backend/surface/api_health.py 의 동형 미러(의료기록 대신 재무 원장). 실제 머지는
finance_ledger_sync.py (LWW + tombstone + owner_uuid 재해소).

왜 필요한가 — 2026-09-05 부터 폰이 자기 결제 알림 포획소를 직접 수거해 **자기 원장**에
적는다(USB 불요). 두 몸이 각자 원장을 갖게 됐으므로 합치는 짝이 없으면 갈라진다.

★인증: api.py 의 remote_access_guard 미들웨어가 외부(터널) 요청에 런처 세션을 강제한다
(localhost=데스크탑·USB 포워드는 통과). 재무 원장 전체를 노출하는 데이터 엔드포인트라
public 화이트리스트에 넣지 않는다 → 외부는 반드시 로그인 후 접근.
"""
from fastapi import APIRouter, HTTPException, Body

router = APIRouter(prefix="/finance")


@router.get("/sync/export")
async def finance_sync_export():
    """이 몸의 finance_records.db 동기화 스냅샷(owners·transactions·holdings, tombstone 포함)."""
    try:
        from finance_ledger_sync import export_finance_db
        return {"success": True, "data": export_finance_db()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/merge")
async def finance_sync_merge(payload: dict = Body(...)):
    """다른 몸의 export 를 이 몸에 합집합 머지(LWW+tombstone) 후, 머지된 이 몸의 최신
    스냅샷을 반환 → 호출자가 그걸 다시 머지하면 1왕복 양방향 동기화(교환·멱등).
    payload = {"data": {table: [rows]}} 또는 직접."""
    try:
        from finance_ledger_sync import export_finance_db, merge_finance_db
        remote = payload.get("data") if isinstance(payload, dict) and "data" in payload else payload
        if not isinstance(remote, dict):
            raise HTTPException(status_code=400, detail="sync 페이로드 형식 오류(dict 필요)")
        stats = merge_finance_db(remote)
        return {"success": True, "stats": stats, "data": export_finance_db()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
