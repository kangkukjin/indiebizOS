"""Resident transport uses installation credentials; /remote-pcs uses launcher auth."""
import base64
import io
import json
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field

import limb_keys
import resident_pcs as pcs
import resident_store

from api_resident_screen import router as screen_router

router = APIRouter()
router.include_router(screen_router)


class DeviceMessage(BaseModel):
    key: str
    installation_id: str
    events: list[dict] = Field(default_factory=list, max_length=64)
    capabilities: dict | None = None
    wait: float = 0
    alias: str | None = Field(default=None, max_length=80)


def checked(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post('/limb/resident/enroll')
def enroll(req: DeviceMessage):
    rec = checked(limb_keys.resident_enroll, req.key, req.installation_id, req.alias)
    return {k: rec[k] for k in ('key', 'device_id', 'alias', 'expires_at', 'registration')}


@router.post('/limb/resident/sync')
def sync(req: DeviceMessage):
    return checked(pcs.sync, req.key, req.installation_id, req.events, req.capabilities, req.wait)


@router.post('/limb/resident/removed')
def removed(req: DeviceMessage):
    rec = checked(limb_keys.resident_auth, req.key, req.installation_id, cleanup=True)
    if rec['registration']['state'] not in ('removal_pending', 'removed'):
        raise HTTPException(409, 'removal_not_requested')
    return checked(limb_keys.resident_update, rec['device_id'], state='removed',
                   removal_receipt={'installation_id': req.installation_id})


@router.post('/limb/resident/local-state')
def local_state(req: dict):
    rec = checked(limb_keys.resident_auth, req.get('key'), req.get('installation_id'), cleanup=True)
    if req.get('remove'):
        return checked(pcs.remove, rec['device_id'])
    return checked(limb_keys.resident_update, rec['device_id'], paused=bool(req.get('paused')))


@router.get('/remote-pcs')
def devices():
    return {'items': pcs.devices(), 'usb': pcs.usb_status(),
            'hardware_extensions': ['android', 'ios', 'ipados', 'web']}


@router.post('/remote-pcs/usb')
def prepare_usb():
    return checked(pcs.prepare_usb)


@router.post('/remote-pcs/usb/revoke')
def revoke_usb():
    limb_keys.resident_installer_revoke()
    return pcs.usb_status()


@router.get('/remote-pcs/history')
def history(device: str | None = None, job: str | None = None, cursor: int = 0):
    return checked(resident_store.history, device, job, cursor)


@router.post('/remote-pcs/command')
def command(req: dict):
    return checked(pcs.submit, req.get('target'), req.get('command', {}), req.get('request_id'))


@router.post('/remote-pcs/cancel')
def cancel(req: dict):
    return {'cancel_requested': checked(resident_store.cancel, req.get('job_id'))}


@router.post('/remote-pcs/state')
def state(req: dict):
    if req.get('remove'):
        return checked(pcs.remove, req.get('target'))
    rec = checked(pcs.resolve, req.get('target'), active=False)
    out = checked(limb_keys.resident_update, rec['device_id'], paused=bool(req.get('paused')))
    if req.get('paused'):
        pcs.media_sessions_end(rec['device_id'], 'relation_paused')
    return out


@router.put('/remote-pcs/context')
def device_context(req: dict):
    """소유자가 알려준 배치·용도. 장치 sync의 능력 보고와 별도로 보존한다."""
    rec = checked(pcs.resolve, req.get('target'), active=False)
    return checked(limb_keys.resident_update, rec['device_id'], context=req.get('context'))


@router.post('/remote-pcs/helper-update')
def helper_update(req: dict):
    return checked(pcs.update_helper, req.get('target'))


@router.post('/remote-pcs/phone-update')
def phone_update(req: dict):
    import phone_updates
    return checked(phone_updates.submit, req.get('target'))


@router.get('/remote-pcs/desktop/{device}')
def desktop_get(device: str):
    import resident_desktop
    return checked(resident_desktop.get, device)


@router.put('/remote-pcs/desktop/{device}')
def desktop_save(device: str, req: dict):
    import resident_desktop
    return checked(resident_desktop.save, device, req)


@router.post('/remote-pcs/wake')
def wake(req: dict):
    if req.get('mac'):
        return checked(pcs.configure_wake, req.get('target'), req['mac'], req.get('broadcast'), req.get('relay'))
    return checked(pcs.wake, req.get('target'))


@router.post('/remote-pcs/bundle')
def bundle(req: dict):
    base = req.get('base') or pcs.public_base()
    if not base or not base.startswith('https://'):
        raise HTTPException(400, '외부 PC가 접속할 HTTPS 중앙 주소를 설정하세요')
    names = {'windows': 'win-resident.exe', 'mac-arm64': 'mac-arm64', 'mac-amd64': 'mac-amd64',
             'mac-legacy': 'mac-amd64-legacy', 'linux': 'linux'}
    suffix = names.get(req.get('platform'))
    binary = Path(__file__).resolve().parents[2] / 'helper' / 'dist' / ('indiebiz-helper-' + (suffix or 'missing'))
    if not suffix or not binary.is_file():
        raise HTTPException(400, 'helper_binary_not_available')
    invited = checked(limb_keys.resident_invite, req.get('alias') or '원격 PC', req.get('ttl_days', 0))
    config = {'mode': 'enroll', 'base': base.rstrip('/'), 'key': invited['key'], 'alias': invited['alias']}
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        entry = zipfile.ZipInfo(binary.name)
        entry.external_attr = 0o100755 << 16
        binary_data = binary.read_bytes()
        z.writestr(entry, binary_data)
        import hashlib
        z.writestr("SHA256SUMS", hashlib.sha256(binary_data).hexdigest() + "  " + binary.name + "\n")
        z.writestr('indiebiz-helper.json', json.dumps(config, ensure_ascii=False))
        z.writestr('설치안내.txt', '이 폴더를 대상 PC에 복사하고 실행파일을 실행하세요.\n'
                   '설치 화면에서 상주 등록을 선택합니다. 사용자 로그인 시 자동 시작합니다.\n'
                   '초대는 24시간 이내 한 PC에서 사용합니다. USB 원본은 자동 삭제하지 않습니다.\n'
                   '맥/리눅스에서 실행 권한이 없으면 chmod +x indiebiz-helper-* 후 실행하세요.\n'
                   '등록 해제는 중앙 런처 또는 설치 PC의 로컬 관리 화면에서 합니다.\n')
    return Response(output.getvalue(), media_type='application/zip',
                    headers={'Content-Disposition': 'attachment; filename="indiebiz-resident.zip"', 'Cache-Control': 'no-store'})


@router.post('/remote-pcs/transfers')
def transfer_create(req: dict):
    return checked(pcs.transfer_create, req.get('target'), req.get('direction'), req.get('name'),
                   req.get('size'), req.get('sha256'))


def transfer_action(tid, req, device=False):
    row = checked(pcs.transfer_info, tid)
    if device:
        rec = checked(limb_keys.resident_auth, req.get('key'), req.get('installation_id'))
        if row['device'] != rec['device_id']:
            raise HTTPException(403, 'transfer_not_owned')
    action = req.get('action', 'info')
    uploading = row['direction'] == ('from_pc' if device else 'to_pc')
    if action in ('meta', 'write', 'commit') and not uploading:
        raise HTTPException(403, 'transfer_wrong_direction')
    if action == 'meta':
        return checked(pcs.transfer_meta, tid, req.get('size'), req.get('sha256'))
    if action == 'write':
        encoded = req.get('data', '')
        if len(encoded) > 1400000:
            raise HTTPException(413, 'chunk_too_large')
        try:
            data = base64.b64decode(encoded, validate=True)
        except ValueError as exc:
            raise HTTPException(400, 'invalid_base64') from exc
        return checked(pcs.transfer_write, tid, req.get('offset'), data)
    if action == 'commit':
        return checked(pcs.transfer_commit, tid)
    if action == 'read':
        if row['state'] != 'committed':
            raise HTTPException(409, 'transfer_not_committed')
        offset = req.get('offset', 0)
        if not isinstance(offset, int) or not 0 <= offset <= row['size']:
            raise HTTPException(400, 'invalid_offset')
        chunk_size = req.get('chunk_size', 512 * 1024)
        if not isinstance(chunk_size, int) or not 1 <= chunk_size <= 512 * 1024:
            raise HTTPException(400, 'invalid_chunk_size')
        with pcs.transfer_path(tid).open('rb') as f:
            f.seek(offset)
            data = f.read(chunk_size)
        return {'data': base64.b64encode(data).decode(), 'offset': offset + len(data)}
    if action != 'info':
        raise HTTPException(400, 'invalid_transfer_action')
    return row


@router.post('/limb/resident/transfers/{tid}')
def device_transfer(tid: str, req: dict):
    return transfer_action(tid, req, device=True)


@router.post('/remote-pcs/transfers/{tid}')
def owner_transfer(tid: str, req: dict):
    return transfer_action(tid, req)


@router.get('/remote-pcs/app', include_in_schema=False)
def app():
    # Previously shared links now return to the launcher; no parallel operations app.
    return RedirectResponse('/launcher/app')


@router.websocket('/limb/resident/ws')
async def resident_socket(socket: WebSocket):
    """The same authenticated sync transaction over a persistent TLS connection."""
    import asyncio
    from fastapi import WebSocketDisconnect
    await socket.accept()
    try:
        while True:
            raw = await asyncio.wait_for(socket.receive_json(), timeout=60)
            req = DeviceMessage.model_validate(raw)
            result = await asyncio.to_thread(pcs.sync, req.key, req.installation_id,
                                             req.events, req.capabilities, req.wait)
            await socket.send_json(result)
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    except (ValueError, TypeError):
        try:
            await socket.close(code=1008)
        except WebSocketDisconnect:
            pass


@router.post('/remote-pcs/terminals')
def terminal_create(req: dict):
    import resident_terminal as terminal
    import resident_terminal_lan as lan
    return checked(terminal.create, req.get('target'), req.get('id'),
                   req.get('cols', 100), req.get('rows', 30), lan.offer(terminal_socket))


@router.get('/remote-pcs/terminals/{sid}')
def terminal_poll(sid: str, cursor: int = 0):
    import resident_terminal as terminal
    return checked(terminal.poll, sid, cursor)


@router.post('/remote-pcs/terminals/{sid}')
def terminal_input(sid: str, req: dict):
    import resident_terminal as terminal
    return checked(terminal.input_message, sid, req)


@router.delete('/remote-pcs/terminals/{sid}')
def terminal_close(sid: str):
    import resident_terminal as terminal
    return checked(terminal.close, sid)


@router.websocket('/limb/resident/terminal/{sid}')
async def terminal_socket(socket: WebSocket, sid: str):
    import asyncio
    import time
    import resident_terminal as terminal
    from fastapi import WebSocketDisconnect

    await socket.accept()
    attached = False
    tasks = []
    wake = None
    try:
        auth = await asyncio.wait_for(socket.receive_json(), 10)
        rec = await asyncio.to_thread(limb_keys.resident_auth, auth.get('key'), auth.get('installation_id'))
        await asyncio.to_thread(terminal.attach, sid, rec['device_id'],
                                'lan' if socket.scope.get('terminal_lan') else 'relay')
        attached = True
        wake = terminal.watch(sid, 'input', asyncio.get_running_loop())
        await socket.send_json({'type': 'ready'})

        async def receive():
            while True:
                data = await socket.receive_bytes()
                if len(data) > 65536:
                    raise ValueError('terminal_frame_too_large')
                await asyncio.to_thread(terminal.output, sid, data)

        async def send():
            last_check = 0
            while True:
                wake.clear()
                if time.monotonic() - last_check >= 1:
                    await asyncio.to_thread(limb_keys.resident_auth, auth.get('key'), auth.get('installation_id'))
                    await socket.send_json({'type': 'heartbeat'})
                    last_check = time.monotonic()
                messages = await asyncio.to_thread(terminal.take, sid)
                for message in messages:
                    await socket.send_json(message)
                    if message['type'] == 'close':
                        return
                try:
                    await asyncio.wait_for(wake.wait(), 1)
                except asyncio.TimeoutError:
                    pass

        tasks = [asyncio.create_task(receive()), asyncio.create_task(send())]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except (WebSocketDisconnect, asyncio.TimeoutError, ValueError, TypeError, KeyError, RuntimeError):
        pass
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if attached:
            terminal.unwatch(sid, 'input')
            await asyncio.to_thread(terminal.detached, sid)
        try:
            await socket.close()
        except (WebSocketDisconnect, RuntimeError):
            pass


@router.websocket('/remote-pcs/terminals/{sid}/stream')
async def terminal_owner_socket(socket: WebSocket, sid: str):
    """Owner authentication is explicit: HTTP middleware does not guard sockets."""
    import asyncio
    import resident_terminal as terminal
    from api_websocket import _authorize_websocket
    from fastapi import WebSocketDisconnect

    if not await _authorize_websocket(socket):
        return
    await socket.accept()
    tasks, wake = [], None
    try:
        wake = terminal.watch(sid, 'output', asyncio.get_running_loop())

        async def receive():
            while True:
                data = await socket.receive_json()
                if not await _authorize_websocket(socket):
                    return
                await asyncio.to_thread(terminal.input_message, sid, data)

        async def send():
            cursor = 0
            while True:
                wake.clear()
                if not await _authorize_websocket(socket):
                    return
                state = await asyncio.to_thread(terminal.poll, sid, cursor)
                await socket.send_json(state)
                cursor = state['cursor']
                if state['state'] == 'closed' and not state['data']:
                    return
                if state['data']:
                    continue
                try:
                    await asyncio.wait_for(wake.wait(), 1)
                except asyncio.TimeoutError:
                    pass

        tasks = [asyncio.create_task(receive()), asyncio.create_task(send())]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except (WebSocketDisconnect, ValueError, TypeError, KeyError, RuntimeError):
        pass
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if wake is not None:
            terminal.unwatch(sid, 'output')
            await asyncio.to_thread(terminal.close, sid)
        try:
            await socket.close()
        except (WebSocketDisconnect, RuntimeError):
            pass
