"""api_media.py — 미디어 세션 API 경계 (2026-10-13).

계약: docs/MEDIA_SESSION_CONTRACT.md §2(HTTP)·§5(전송). 설계: docs/MEDIA_COMMUNICATION_DESIGN_2026_10_13.md §10.
- /media/*                     로그인한 사용자(로컬=신뢰, 원격=런처 세션) — HTTP 미들웨어 + WS 는 _authorize_websocket.
- /limb/resident/media/{sid}   확장 장치 WS — 등록 자격(limb_keys.resident_auth) + 세션 grant 둘 다.
- /media/relay/{room}          릴레이 WS — 방 토큰. 중계만 하고 내용을 읽지 않는다.
- /media/content/{ref}         콘텐츠 전달 — 세션 소유 참조 + grant 토큰(Range 지원). 세션 종료 시 무효.
응답 봉투: {success, session} / {success:false, error:{code,message}} — HTTP 200·400 같은 모양.
"""
import asyncio
import json
import os
from typing import Optional

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse

import limb_keys
import media_sessions as ms
import media_store

router = APIRouter()


def _ok(session: dict, **extra) -> dict:
    return {"success": True, "session": session, **extra}


def _fail(code: str, message: str = "", status: int = 400):
    return JSONResponse({"success": False, "error": {"code": code, "message": message or code}}, status_code=status)


def _run(fn, *args, **kwargs):
    try:
        return _ok(fn(*args, **kwargs))
    except ms.MediaError as exc:
        return _fail(exc.code, exc.message)
    except (ValueError, KeyError, TypeError) as exc:
        return _fail("invalid_request", str(exc))


# ── REST ────────────────────────────────────────────────────────────────────────
@router.get("/media/capabilities")
def capabilities(target: Optional[str] = None):
    try:
        return {"success": True, "capabilities": ms.capabilities(target)}
    except ms.MediaError as exc:
        return _fail(exc.code, exc.message)


@router.get("/media/health")
def health():
    return {"success": True, "health": ms.health()}


@router.get("/media/ice-config")
def ice_config(session_id: str = ""):
    import media_signaling as sig
    return {"success": True, "ice_servers": ms.refresh_ice(session_id) if session_id else sig.ice_servers()}


@router.get("/media/sessions")
def list_sessions(active: int = 1):
    return {"success": True, "items": ms.list_sessions(bool(active))}


@router.get("/media/history")
def history(limit: int = 50, peer: Optional[str] = None, device: Optional[str] = None):
    return {"success": True, "items": media_store.history(limit, peer, device)}


@router.post("/media/sessions")
def create(req: dict):
    return _run(ms.create, str(req.get("kind") or ""), str(req.get("purpose") or ""), str(req.get("target") or ""),
                tracks=req.get("tracks"), delivery=str(req.get("delivery") or "realtime"),
                request_id=req.get("request_id"), content=req.get("content"), want_mic=bool(req.get("want_mic")),
                camera=req.get("camera"))


@router.get("/media/sessions/{sid}")
def status(sid: str):
    return _run(ms.status, sid)


@router.post("/media/sessions/{sid}/accept")
def accept(sid: str, req: dict = None):
    return _run(ms.accept, sid, str((req or {}).get("device") or "local"))


@router.post("/media/sessions/{sid}/reject")
def reject(sid: str, req: dict = None):
    req = req or {}
    return _run(ms.reject, sid, str(req.get("reason") or "rejected"), block=bool(req.get("block")))


@router.post("/media/sessions/{sid}/signal")
def signal(sid: str, frame: dict):
    why = ms.signal(sid, frame)
    if why:
        return _fail(why)
    return {"success": True}


@router.post("/media/sessions/{sid}/update")
def update(sid: str, req: dict):
    return _run(ms.update, sid, req.get("expected_revision"), req.get("changes") or {})


@router.post("/media/sessions/{sid}/end")
def end(sid: str, req: dict = None):
    return _run(ms.end, sid, str((req or {}).get("reason") or "ended"))


@router.post("/media/blocks")
def blocks(req: dict):
    pub = str(req.get("pubkey") or "")
    if not pub:
        return _fail("invalid_request", "pubkey 필요")
    if req.get("remove"):
        media_store.unblock(pub)
    else:
        media_store.block(pub, str(req.get("note") or ""))
    return {"success": True, "items": media_store.blocked()}


# ── 콘텐츠 전달(Range) ───────────────────────────────────────────────────────────
@router.get("/media/content/{ref}")
def content(ref: str, request: Request, token: str = ""):
    try:
        path, name = ms.content_file(ref, token)
    except ms.MediaError as exc:
        return _fail(exc.code, exc.message, status=404 if exc.code == "content_unavailable" else 403)
    if not path or not os.path.isfile(path):
        return _fail("content_unavailable", "", status=404)
    size = os.path.getsize(path)
    start, stop = 0, size - 1
    status_code = 200
    header = request.headers.get("range", "")
    if header.startswith("bytes="):
        spec = header[6:].split(",")[0].strip()
        a, _, b = spec.partition("-")
        try:
            if a:
                start = int(a)
                stop = int(b) if b else size - 1
            else:
                start = max(0, size - int(b))
        except ValueError:
            return _fail("invalid_range", status=416)
        if start >= size or stop < start:
            return JSONResponse({"success": False, "error": {"code": "invalid_range"}}, status_code=416,
                                headers={"Content-Range": f"bytes */{size}"})
        stop = min(stop, size - 1)
        status_code = 206
    length = stop - start + 1

    def _iter():
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk
    import mimetypes
    headers = {"Accept-Ranges": "bytes", "Content-Length": str(length), "Cache-Control": "private, no-store",
               "Content-Disposition": "inline; filename*=UTF-8''" + __import__("urllib.parse").parse.quote(name or "content")}
    if status_code == 206:
        headers["Content-Range"] = f"bytes {start}-{stop}/{size}"
    return StreamingResponse(_iter(), status_code=status_code, headers=headers,
                             media_type=mimetypes.guess_type(path)[0] or "application/octet-stream")


# ── WS 공통 ─────────────────────────────────────────────────────────────────────
async def _pump(ws: WebSocket, box, on_frame, *, heartbeat: float = 5.0, close_frame=None):
    """Outbox → 소켓, 소켓 → on_frame. 어느 쪽이 끝나면 둘 다 정리."""
    wake = asyncio.Event()
    box.watch(asyncio.get_running_loop(), wake)

    async def receive():
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect":
                return
            text = message.get("text")
            if text is None:
                continue
            try:
                frame = json.loads(text)
            except ValueError:
                continue
            reply = await asyncio.to_thread(on_frame, frame)
            if reply:
                await ws.send_json(reply)

    async def send():
        while True:
            wake.clear()
            for message in box.take():
                await ws.send_json(message)
            if box.closed:
                if close_frame:
                    await ws.send_json(close_frame() if callable(close_frame) else close_frame)
                return
            try:
                await asyncio.wait_for(wake.wait(), heartbeat)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "heartbeat"})

    tasks = [asyncio.create_task(receive()), asyncio.create_task(send())]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        box.unwatch()


async def _close(ws: WebSocket):
    try:
        await ws.close()
    except (RuntimeError, WebSocketDisconnect):
        pass


@router.websocket("/media/events")
async def session_events(ws: WebSocket):
    """Always-on media notifications, independent of any open chat."""
    from api_websocket import _authorize_websocket
    from media_signaling import Outbox
    if not await _authorize_websocket(ws):
        return
    await ws.accept()
    box = Outbox()
    def changed(event, session):
        box.push({"type": "media_event", "event": event, "session": session})
    ms.subscribe(changed)
    try:
        for session in ms.list_sessions():
            changed("snapshot", session)
        await _pump(ws, box, lambda frame: None, heartbeat=15)
    except (WebSocketDisconnect, RuntimeError, ValueError):
        pass
    finally:
        ms.unsubscribe(changed)
        box.close()
        await _close(ws)


# ── 브라우저 엔진 WS ─────────────────────────────────────────────────────────────
@router.websocket("/media/sessions/{sid}/ws")
async def local_socket(ws: WebSocket, sid: str):
    from api_websocket import _authorize_websocket
    if not await _authorize_websocket(ws):
        return
    await ws.accept()
    try:
        s = await asyncio.to_thread(ms.attach_local, sid)
    except ms.MediaError as exc:
        await ws.send_json({"type": "error", "error": {"code": exc.code, "message": exc.message}})
        await _close(ws)
        return
    await ws.send_json({"type": "session", "event": "attached", "session": s.public()})

    def on_frame(frame):
        if not isinstance(frame, dict):
            return None
        if frame.get("type") == "heartbeat":
            return None
        if frame.get("type") == "session":    # 브라우저가 현재 상태를 다시 달라고 할 때
            return {"type": "session", "event": "snapshot", "session": ms.status(sid)}
        why = ms.signal(sid, frame)
        if why:
            return {"type": "rejected", "reason": why, "msg_id": frame.get("msg_id")}
        return None
    try:
        await _pump(ws, s.local_box, on_frame, close_frame=lambda: {"type": "session", "event": "ended", "session": ms.status(sid)})
    except (WebSocketDisconnect, asyncio.TimeoutError, RuntimeError, ValueError, KeyError, TypeError):
        pass
    finally:
        ms.detach_local(sid)
        await _close(ws)


# ── 확장 장치 WS(헬퍼·폰) ─────────────────────────────────────────────────────────
@router.websocket("/limb/resident/media/{sid}")
async def device_socket(ws: WebSocket, sid: str):
    await ws.accept()
    attached = False
    try:
        auth = await asyncio.wait_for(ws.receive_json(), 10)
        try:
            rec = await asyncio.to_thread(limb_keys.resident_auth, auth.get("key"), auth.get("installation_id"))
        except ValueError as exc:
            await ws.send_json({"type": "error", "error": {"code": "invalid_registration", "message": str(exc)}})
            raise
        try:
            s = await asyncio.to_thread(ms.attach_device, sid, rec["device_id"], auth.get("grant"))
        except ms.MediaError as exc:
            # 장치가 왜 못 붙는지 알려 준다(session_ended 면 재접속을 멈춘다) — 토큰은 되돌려 보내지 않는다
            await ws.send_json({"type": "error", "error": {"code": exc.code, "message": exc.message}})
            raise
        attached = True
        await ws.send_json({"type": "ready", "session_id": sid, "lease": {"lease_s": s.lease.lease_s,
                                                                         "keepalive_s": s.lease.keepalive_s}})
        key, iid = auth.get("key"), auth.get("installation_id")

        def on_frame(frame):
            if not isinstance(frame, dict) or frame.get("type") == "heartbeat":
                return None
            if frame.get("type") == "ready":          # 장치 능력 신고(시그널 아님)
                ms.device_ready(sid, frame.get("capabilities") or (frame.get("payload") or {}).get("capabilities"))
                return None
            try:
                limb_keys.resident_auth(key, iid)   # 등록이 중지·폐기되면 즉시 끊는다
            except ValueError:
                ms.end(sid, "relation_revoked", error={"code": "relation_revoked", "message": "확장관계가 유효하지 않습니다"})
                return None
            why = ms.receive_remote(frame, source="device", device_session=sid, device_id=rec["device_id"])
            if why and why != "session_ended":
                return {"type": "rejected", "reason": why, "msg_id": frame.get("msg_id")}
            return None
        await _pump(ws, s.remote_box, on_frame, close_frame=lambda: {"type": "end", "payload": {"reason": ms.status(sid).get("end_reason")}})
    except (WebSocketDisconnect, asyncio.TimeoutError, RuntimeError, ValueError, KeyError, TypeError, ms.MediaError):
        pass
    finally:
        if attached:
            ms.detach_device(sid)
        await _close(ws)


# ── 릴레이 방 ───────────────────────────────────────────────────────────────────
@router.websocket("/media/relay/{room}")
async def relay_socket(ws: WebSocket, room: str, token: str = ""):
    import secrets
    member = secrets.token_hex(4)
    try:
        box = ms.rooms.join(room, token, member)
    except ValueError:
        await ws.close(code=1008, reason="relay_unauthorized")
        return
    await ws.accept()
    try:
        def on_frame(frame):
            if isinstance(frame, dict) and frame.get("type") != "heartbeat":
                ms.rooms.publish(room, member, frame)
            return None
        await _pump(ws, box, on_frame, heartbeat=15.0)
    except (WebSocketDisconnect, asyncio.TimeoutError, RuntimeError, ValueError, KeyError, TypeError):
        pass
    finally:
        ms.rooms.leave(room, member)
        await _close(ws)


# ── 브라우저 전체 푸시(수신 벨·상태) ─────────────────────────────────────────────────
def _broadcast(event: str, session: dict) -> None:
    if event not in ("ringing", "ended", "accepted", "active"):
        return
    try:
        from websocket_manager import broadcast_message
        broadcast_message({"type": "media_event", "event": event, "session": session})
    except Exception:  # noqa: BLE001
        pass


ms.subscribe(_broadcast)
ms.device_socket_handler = device_socket
