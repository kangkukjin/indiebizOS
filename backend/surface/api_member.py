"""api_member.py — 외부 서비스 앱 회원 표면(/m/*): 회원 열쇠(limb key + neighbor_id) 자체 인증.

정본: docs/EXTERNAL_SERVICE_APP_HANDOFF.md §3-3·§3-8 (2026-09-14, 1단계 — HTTP 턴. WS·로컬 셸은 2단계).
- 인증 = limb key 원장의 `neighbor_id` 결합 + body_trust 레벨. 런처 세션·허브 비밀번호 없음.
- 주체는 이 라우트가 세운다(principal.authenticate — 기저가 owner/anonymous 일 때만).
- 프로젝트·설정·조종실 API 는 이 인증으로 라우트가 없다(부재).
"""
from typing import Optional

import asyncio
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import limb_keys

router = APIRouter()


class MemberChat(BaseModel):
    key: str
    message: str
    name: str = ""


class MemberKey(BaseModel):
    key: str


def _member_of(key: str):
    """회원 열쇠 → (rec, neighbor_id, level) 또는 (None, 오류 봉투)."""
    rec = limb_keys.validate(key)
    if not rec:
        return None, {"success": False, "error": "invalid_or_expired_key"}
    nid = rec.get("neighbor_id")
    if nid in (None, ""):
        return None, {"success": False, "error": "not_member_key",
                      "message": "이 열쇠는 손발 키이지 회원 열쇠가 아닙니다 — [self:limb]{op:issue, neighbor_id} 로 발급하세요."}
    from body_trust import get_body_level, get_body_neighbor_id
    level = get_body_level(rec["device_id"])
    if level is None or str(get_body_neighbor_id(rec["device_id"])) != str(nid):
        return None, {"success": False, "error": "unlinked_device",
                      "message": "기기가 이웃 명부에 결합돼 있지 않습니다."}
    if not rec.get("approved"):
        return None, {"success": False, "error": "device_not_approved"}
    return (rec, str(nid), int(level)), None


def _principal_for(rec: dict, nid: str, level: int):
    import principal
    p = principal.member(nid, level, rec["device_id"])
    if not principal.authenticate(p, "m/chat"):
        return None
    return p


@router.post("/m/chat")
async def member_chat(req: MemberChat, request: Request):
    """회원 한 턴(동기 def — LLM 파이프라인이 이벤트 루프를 막지 않게 스레드풀에서)."""
    ident, err = _member_of(req.key)
    if err:
        return err
    rec, nid, level = ident
    if _principal_for(rec, nid, level) is None:
        return {"success": False, "error": "principal_mismatch"}
    from member_session import MemberSessionManager
    name = req.name or rec.get("alias") or ""
    mgr = MemberSessionManager.instance()
    work = asyncio.create_task(asyncio.to_thread(mgr.turn, nid, rec["device_id"], level, name, req.message))
    while not work.done():
        if await request.is_disconnected():
            mgr.close(nid, rec["device_id"])
            break
        await asyncio.wait({work}, timeout=0.25)
    return await work


@router.post("/m/session/close")
def member_close(req: MemberKey):
    ident, err = _member_of(req.key)
    if err:
        return err
    rec, nid, level = ident
    from member_session import MemberSessionManager
    return {"success": True, "closed": MemberSessionManager.instance().close(nid, rec["device_id"])}


@router.post("/m/profile")
def member_profile(req: MemberKey):
    """회원이 보는 자기 프로파일 — 레벨·열린 낱말 수·오늘 사용량·고지."""
    ident, err = _member_of(req.key)
    if err:
        return err
    rec, nid, level = ident
    if _principal_for(rec, nid, level) is None:
        return {"success": False, "error": "principal_mismatch"}
    import member_profile as mp
    from member_session import MemberSessionManager, load_policy
    from ibl_registry import load_nodes_installed
    nodes = (load_nodes_installed() or {}).get("nodes", {})
    open_words = []
    for node, ncfg in nodes.items():
        for action, cfg in (ncfg.get("actions") or {}).items():
            if isinstance(cfg, dict) and mp.visible(node, action, cfg):
                open_words.append(f"{node}:{action}")
    mgr = MemberSessionManager.instance()
    return {"success": True, "neighbor_id": nid, "level": level, "device_id": rec["device_id"],
            "open_words": sorted(open_words), "turns_today": mgr.turns_today(nid),
            "policy": {k: load_policy().get(k) for k in ("daily_turns", "max_sessions_per_member")},
            "notice": load_policy().get("notice", "")}


@router.get("/m/app", response_class=HTMLResponse)
def member_app():
    from member_shell import member_html
    return HTMLResponse(member_html(), headers={"Cache-Control": "no-store"})


@router.websocket("/m/chat")
async def member_socket(ws: WebSocket):
    """키는 URL에 넣지 않고 첫 프레임에서 인증한다. 연결 종료는 신규 작업을 막는다."""
    import principal
    token = principal.set_transport(principal.ANONYMOUS)
    await ws.accept()
    mgr = None
    rec = None
    task = None
    try:
        hello = await asyncio.wait_for(ws.receive_json(), timeout=10)
        key = hello.get("key", "")
        ident, error = _member_of(key)
        if error:
            await ws.send_json(error)
            await ws.close(code=4401)
            return
        rec, nid, level = ident
        if _principal_for(rec, nid, level) is None:
            await ws.close(code=4403)
            return
        from member_session import MemberSessionManager
        mgr = MemberSessionManager.instance()
        await ws.send_json({"type": "ready", "neighbor_id": nid})
        while True:
            payload = await ws.receive_json()
            refreshed, error = _member_of(key)
            if error or refreshed[1:] != (nid, level):
                await ws.close(code=4401)
                return
            task = asyncio.create_task(asyncio.to_thread(mgr.turn, nid, rec["device_id"], level,
                                       rec.get("alias", ""), str(payload.get("message", ""))))
            while not task.done():
                receiving = asyncio.create_task(ws.receive_json())
                done, _ = await asyncio.wait({task, receiving}, return_when=asyncio.FIRST_COMPLETED)
                if receiving in done:
                    try:
                        control = receiving.result()
                        if control.get("type") == "cancel":
                            mgr.close(nid, rec["device_id"])
                        else:
                            await ws.send_json({"type": "busy", "error": "진행 중에는 취소만 가능합니다"})
                    except WebSocketDisconnect:
                        mgr.close(nid, rec["device_id"])
                        await task
                        return
                else:
                    receiving.cancel()
                    try:
                        await receiving
                    except asyncio.CancelledError:
                        pass
            await ws.send_json({"type": "final", **(await task)})
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        if mgr and rec:
            mgr.close(nid, rec["device_id"])
        if task:
            await task
        principal.reset_transport(token)
