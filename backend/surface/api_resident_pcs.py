"""Resident transport uses installation credentials; /remote-pcs uses launcher auth."""
import base64
import io
import json
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

import limb_keys
import resident_pcs as pcs
import resident_store

router = APIRouter()


class DeviceMessage(BaseModel):
    key: str
    installation_id: str
    events: list[dict] = Field(default_factory=list, max_length=64)
    capabilities: dict | None = None
    wait: float = 0


def checked(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post('/limb/resident/enroll')
def enroll(req: DeviceMessage):
    rec = checked(limb_keys.resident_enroll, req.key, req.installation_id)
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
    return {'items': pcs.devices(), 'hardware_extensions': ['android', 'ios', 'ipados', 'web']}


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
    return checked(limb_keys.resident_update, rec['device_id'], paused=bool(req.get('paused')))


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
        with pcs.transfer_path(tid).open('rb') as f:
            f.seek(offset)
            data = f.read(512 * 1024)
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


@router.get('/remote-pcs/app', response_class=HTMLResponse)
def app():
    return (Path(__file__).with_name('resident_pcs.html')).read_text(encoding='utf-8')


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
