"""phone_finance_sync.py — 결제 알림이 뜨면 폰 원장을 갱신하고 그때마다 PC 원장과 합친다.

고리 전체: NotificationCaptureService(t=0 원문 포획) → POST /finance/sync/run →
① 자기 포획소 수거(`[self:finance]{op:"sync"}`, source=capture-local — 파서·ext_id 는 패키지 정본)
② 폰 export → PC `/finance/sync/merge` → PC 스냅샷을 폰에 머지(1왕복 양방향, health/business 동형).

2026-09-06 에 ①의 능력과 PC 쪽 머지 API 는 지어졌지만 **둘을 돌리는 주체가 없어서**
USB 수거만이 PC 원장을 갱신하고 있었다(09-18 실측: 폰 원장 09-05 이후 0건). 이 모듈이 그 주체다.

★전송 경로 = 기존 맥 위임 채널(INDIEBIZ_MAC_URL, LAN/터널 + 런처 세션 인증) 직결.
  공개 릴레이(Nostr)로 결제 내역을 밀던 옛 방식(2026-06-15 제거)의 복귀가 아니다.
★PC 미도달은 실패가 아니라 보류다 — 수거분은 폰 원장에 이미 있고, 머지는 멱등이므로
  pending 을 세워 두고 뒤에서 따라잡는다(다음 알림·앱 기동·주기 재시도).

phone_api 와의 순환 import 를 피하려고 필요한 것(맥 POST·scratch 경로)은 install() 로 주입받는다.
"""
import asyncio
import threading
import time

from fastapi.responses import JSONResponse

RETRY_SECONDS = 600          # PC 미도달 상태에서의 재시도 주기
_wake = threading.Event()    # 워커 깨우기(새 알림·기동)
_pending = True              # 기동 직후 1회는 무조건 따라잡는다(꺼져 있던 동안의 포획분)
_busy = threading.Lock()     # 워커 스레드와 HTTP 경로가 겹쳐 돌지 않게(비차단 획득만 — 루프를 막지 않는다)
_last = {"at": None, "collect": None, "pushed": None, "error": None}

_mac_post_json = None
_get_scratch = None


def _collect_local() -> str:
    """자기 포획소 → 자기 원장. 정본 IBL 경로로 부른다(수거 규칙을 여기 복제하지 않는다)."""
    from system_tools import _execute_ibl_unified
    out = _execute_ibl_unified({"code": '[self:finance]{op: "sync"}'}, _get_scratch(), agent_id="phone")
    return out if isinstance(out, str) else str(out)


async def _exchange_with_pc() -> dict:
    """폰 export → PC merge → PC 스냅샷을 폰에 merge. PC 미도달이면 pushed=False."""
    from finance_ledger_sync import export_finance_db, merge_finance_db
    phone_export = await asyncio.to_thread(export_finance_db)
    r = await _mac_post_json("/finance/sync/merge", {"data": phone_export}, timeout=60.0)
    if r is None or getattr(r, "status_code", 0) != 200:
        return {"pushed": False, "status": getattr(r, "status_code", None)}
    pc = r.json() or {}
    stats = await asyncio.to_thread(merge_finance_db, pc.get("data") or {})
    return {"pushed": True, "merged_from_pc": stats, "pc_received_from_phone": pc.get("stats")}


async def run_once() -> dict:
    """수거 + 교환 한 번. 어느 단계가 실패해도 다음 단계는 시도한다(수거 실패 ≠ 머지 불가).

    이미 도는 중이면 기다리지 않고 pending 만 세운다 — 연속 알림은 뒤따르는 한 번으로 접힌다."""
    global _pending
    if not _busy.acquire(blocking=False):
        _pending = True
        _wake.set()
        return {"success": True, "queued": True}
    result = {"success": True}
    try:
        _pending = False   # 이 실행 도중 온 알림은 다시 True 로 세운다 → 워커가 한 번 더 돈다
        try:
            result["collect"] = (await asyncio.to_thread(_collect_local))[:400]
        except Exception as e:
            result["collect_error"] = str(e)
        try:
            result.update(await _exchange_with_pc())
        except Exception as e:
            result.update({"pushed": False, "error": str(e)})
    finally:
        _busy.release()
    if not result.get("pushed"):
        _pending = True
    _last.update({"at": int(time.time()), "collect": result.get("collect"),
                  "pushed": result.get("pushed"),
                  "error": result.get("error") or result.get("collect_error")})
    return result


def _worker():
    """기동 직후 1회 + pending 인 동안 주기 재시도. 평소엔 잠들어 있다(알림이 깨운다).

    ★깨움 신호는 실행 *전에* 지운다 — 실행 도중 온 신호를 잃지 않으려고. 그리고 run_once 는
    스스로 깨우지 않는다(미도달 때 자기를 깨우면 재시도 주기 없이 헛돈다)."""
    time.sleep(20)   # 백엔드·패키지 로딩이 끝난 뒤에
    while True:
        _wake.clear()
        if _pending:
            try:
                asyncio.run(run_once())
            except Exception as e:
                print(f"[phone_finance_sync] 워커 실행 오류: {e}")
        _wake.wait(timeout=RETRY_SECONDS if _pending else None)


def install(app, mac_post_json, get_scratch):
    """phone_api 가 부른다 — 엔드포인트 등록 + 따라잡기 워커 기동."""
    global _mac_post_json, _get_scratch
    _mac_post_json, _get_scratch = mac_post_json, get_scratch

    @app.post("/finance/sync/run")
    async def finance_sync_run():
        """결제 알림 포획 직후 포획소(Kotlin)가 부른다. 수동 호출도 같은 길."""
        result = await run_once()
        if _pending:
            _wake.set()   # PC 미도달·실행 중 겹침 → 워커가 이어받는다(재시도 주기 시작)
        return JSONResponse(result)

    @app.get("/finance/sync/status")
    async def finance_sync_status():
        return {"pending": _pending, "last": _last}

    # ★phone_api 의 catch-all(`/{full_path:path}`)이 모듈 로드 때 이미 등록돼 있어, 뒤에 붙은
    # 라우트는 가려진다(09-18 실측: "이 몸에 없는 기능"). 방금 붙인 둘을 맨 앞으로 옮긴다.
    routes = app.router.routes
    mine = [r for r in routes if getattr(r, "path", "") in ("/finance/sync/run", "/finance/sync/status")]
    for r in mine:
        routes.remove(r)
    routes[0:0] = mine

    threading.Thread(target=_worker, daemon=True, name="finance-sync").start()
