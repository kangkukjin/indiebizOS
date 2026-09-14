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
from pydantic import BaseModel, Field

import limb_keys

router = APIRouter()


class MemberChat(BaseModel):
    key: str
    message: str
    name: str = ""


class MemberKey(BaseModel):
    key: str
    body_session: str = ""


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
    if req.body_session and req.body_session != rec.get("session"):
        return {"success": False, "error": "stale_browser_session"}
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
    from client_agent import EPOCH, TTL, VERSION
    return {"success": True, "client_protocol": {"version": VERSION, "epoch": EPOCH, "retry_window_s": TTL}, "neighbor_id": nid, "level": level, "device_id": rec["device_id"],
            "open_words": sorted(open_words), "turns_today": mgr.turns_today(nid),
            "policy": {k: load_policy().get(k) for k in ("daily_turns", "max_sessions_per_member")},
            "notice": load_policy().get("notice", "")}


@router.get("/m/app", response_class=HTMLResponse)
def member_app():
    from member_entry import entry_html
    return HTMLResponse(entry_html(), headers={"Cache-Control": "no-store"})


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


class MemberRun(MemberChat):
    message: str = ""
    body_session: str = ""
    task_id: str
    code: Optional[str] = None
    version: int = 1
    request_id: str = ""
    reply_to: str = ""
    epoch: str = ""
    action_id: str = ""
    args: dict = Field(default_factory=dict)
    capabilities: dict = Field(default_factory=dict)
    attachments: list = Field(default_factory=list)
    local_apps: list = Field(default_factory=list)


@router.post('/m/requests')
@router.post('/m/run')
async def member_run(req: MemberRun):
    """로컬 작업 원장으로 보내는 NDJSON 이벤트. 허브에 작업 기록을 저장하지 않는다."""
    import json
    import queue
    import re
    import threading
    import time
    from fastapi.responses import StreamingResponse
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', req.task_id):
        return {'success': False, 'error': 'invalid_task_id'}
    ident, err = _member_of(req.key)
    if err:
        return err
    rec, nid, level = ident
    if req.body_session and req.body_session != rec.get("session"):
        return {"success": False, "error": "stale_browser_session"}
    if _principal_for(rec, nid, level) is None:
        return {'success': False, 'error': 'principal_mismatch'}
    from member_session import MemberSessionManager
    mgr = MemberSessionManager.instance()
    resolved = None
    if req.request_id:
        import hashlib
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', req.request_id):
            return {'success': False, 'error': 'invalid_request_id'}
        if req.action_id and (req.code or req.message.strip()):
            return {'success': False, 'error': 'ambiguous_client_request'}
        if len(req.attachments) > 5:
            return {'success': False, 'error': 'attachment_limit'}
        for attachment in req.attachments:
            if not isinstance(attachment, dict) or set(attachment) - {'id', 'name', 'text', 'sha256'}:
                return {'success': False, 'error': 'invalid_attachment'}
            content = attachment.get('text', '')
            if not isinstance(content, str) or len(content.encode()) > 256000 or hashlib.sha256(content.encode()).hexdigest() != attachment.get('sha256'):
                return {'success': False, 'error': 'attachment_integrity'}
        try:
            if req.action_id:
                from member_apps import resolve_request
                resolved = await asyncio.to_thread(resolve_request, req.action_id, req.args, req.local_apps) if req.local_apps else await asyncio.to_thread(resolve_request, req.action_id, req.args)
            else:
                resolved = {'message': req.message, 'code': req.code}
        except ValueError as exc:
            return {'success': False, 'error': str(exc)}
    events = queue.Queue(maxsize=128)
    stopped = threading.Event()
    def emit(value):
        while not stopped.is_set():
            try:
                events.put(value, timeout=.25)
                return
            except queue.Full:
                pass
    async def stream():
        if resolved is not None:
            from client_agent import run
            envelope = {'version': req.version, 'epoch': req.epoch, 'request_id': req.request_id,
                        'conversation_id': req.task_id, 'reply_to': req.reply_to, 'message': req.message, 'code': req.code,
                        'action_id': req.action_id, 'args': req.args, 'capabilities': req.capabilities,
                        'attachments': req.attachments, 'local_apps': req.local_apps}
            work = asyncio.create_task(asyncio.to_thread(run, envelope, resolved,
                name=rec.get('alias', ''), body_session=req.body_session, on_event=emit, manager=mgr))
        else:
            work = asyncio.create_task(asyncio.to_thread(mgr.turn, nid, rec['device_id'], level,
                rec.get('alias', ''), req.message or '앱 실행', local_task_id=req.task_id, code=req.code, on_event=emit, body_session=req.body_session))
        last_sent = time.monotonic()
        try:
            while not work.done() or not events.empty():
                try:
                    event = events.get_nowait()
                    yield json.dumps({'type': 'event', 'event': event}, ensure_ascii=False, default=str) + '\n'
                except queue.Empty:
                    if time.monotonic() - last_sent >= 10:
                        yield '{"type":"heartbeat"}\n'
                        last_sent = time.monotonic()
                    await asyncio.wait({work}, timeout=.1)
            yield json.dumps({'type': 'result', 'result': await work}, ensure_ascii=False, default=str) + '\n'
        finally:
            stopped.set()
            if not work.done():
                mgr.close(nid, rec['device_id'])
                try:
                    await asyncio.shield(work)
                except asyncio.CancelledError:
                    pass
    return StreamingResponse(stream(), media_type='application/x-ndjson', headers={'Cache-Control': 'no-store'})


class MemberAppsRequest(MemberKey):
    local_apps: list = Field(default_factory=list)


@router.post('/m/apps')
def member_apps(req: MemberAppsRequest):
    ident, err = _member_of(req.key)
    if err:
        return err
    rec, nid, level = ident
    if _principal_for(rec, nid, level) is None:
        return {'success': False, 'error': 'principal_mismatch'}
    from member_apps import catalogue, web_catalogue
    try:
        return web_catalogue(req.local_apps) if (rec.get('env') or {}).get('client') == 'web' else catalogue()
    except ValueError as exc:
        return {'success': False, 'error': str(exc)}


class MemberBootstrap(MemberKey):
    platform: str
    base: str


@router.post('/m/bootstrap')
def member_bootstrap(req: MemberBootstrap):
    import io
    import json
    import zipfile
    from pathlib import Path
    from urllib.parse import urlsplit
    from fastapi import HTTPException
    from fastapi.responses import Response
    from runtime_utils import get_base_path
    ident, err = _member_of(req.key)
    if err:
        raise HTTPException(403, err['error'])
    targets = {'mac-arm64': 'indiebiz-helper-mac-arm64', 'mac-amd64': 'indiebiz-helper-mac-amd64',
               'win': 'indiebiz-helper-win.exe', 'linux': 'indiebiz-helper-linux'}
    if req.platform not in targets:
        raise HTTPException(400, '지원하지 않는 플랫폼')
    url = urlsplit(req.base)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ('', '/'):
        raise HTTPException(400, 'HTTPS 허브 주소가 필요합니다')
    binary = Path(get_base_path()) / 'helper' / 'dist' / targets[req.platform]
    if not binary.is_file():
        raise HTTPException(503, '연결 프로그램 배포 파일이 없습니다')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        info = zipfile.ZipInfo(binary.name)
        info.external_attr = 0o100755 << 16
        z.writestr(info, binary.read_bytes())
        z.writestr('indiebiz-helper.json', json.dumps({'mode':'member','base':req.base.rstrip('/'),'key':req.key,'alias':ident[0].get('alias','회원')}, ensure_ascii=False))
        z.writestr('시작하기.txt', '실행파일과 설정파일을 같은 폴더에 두고 실행파일을 여세요. 브라우저의 회원 작업 공간에서 작업 폴더를 선택하세요. 설정파일에는 회원 키가 있으므로 다른 사람에게 보내지 마세요.')
    return Response(buf.getvalue(), media_type='application/zip', headers={'Cache-Control':'no-store','Content-Disposition':'attachment; filename="indiebiz-member.zip"'})


class ArtifactReceipt(MemberKey):
    request_id: str
    artifact_id: str
    sha256: str
    size: int
    epoch: str


@router.post('/m/receipts')
def member_receipt(req: ArtifactReceipt):
    ident, error = _member_of(req.key)
    if error:
        return error
    rec, nid, level = ident
    if req.body_session and req.body_session != rec.get('session'):
        return {'success': False, 'error': 'stale_browser_session'}
    if _principal_for(rec, nid, level) is None:
        return {'success': False, 'error': 'principal_mismatch'}
    from client_agent import receipt
    try:
        return receipt(req.request_id, req.artifact_id, req.sha256, req.size,
                       body_session=req.body_session, epoch=req.epoch)
    except (ValueError, PermissionError):
        return {'success': False, 'error': 'invalid_receipt'}
