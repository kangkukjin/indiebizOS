"""회원 설치 교환과 재접속 가능한 데스크톱 요청 표면."""
from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from member_device_auth import MemberRoute

router = APIRouter(route_class=MemberRoute)


class Enrollment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    code: str = Field(max_length=16)
    request_id: str = Field(max_length=36)
    installation_id: str = Field(max_length=36)
    public_key: str = Field(max_length=64)
    signature: str = Field(max_length=100)


@router.post('/m/enroll/exchange')
def exchange(req: Enrollment):
    from member_enrollment import exchange
    try:
        return exchange(**req.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class DesktopRequest(BaseModel):
    version: Literal[2] = 2
    key: str
    request_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    task_id: str = Field(default='', max_length=80)
    body_session: str = ''
    message: str = Field(default='', max_length=100000)
    code: str | None = Field(default=None, max_length=100000)
    action_id: str = Field(default='', max_length=200)
    args: dict = Field(default_factory=dict)
    local_apps: list = Field(default_factory=list, max_length=100)
    after: int = Field(default=0, ge=0)


def identity(req):
    from api_member import _member_of, _principal_for
    ident, error = _member_of(req.key)
    if error:
        raise HTTPException(401, error['error'])
    if not ident[0].get('desktop') or _principal_for(*ident) is None:
        raise HTTPException(403, '등록된 데스크톱이 필요합니다')
    return ident[0]


@router.post('/m/desktop/submit')
def submit(req: DesktopRequest):
    import re
    import member_desktop_requests as service
    rec = identity(req)
    if req.body_session != rec.get('session'):
        raise HTTPException(409, '실행부 연결이 바뀌었습니다')
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', req.task_id) or not (req.message.strip() or req.code or req.action_id):
        raise HTTPException(400, '작업 ID와 요청이 필요합니다')
    if req.action_id and (req.code or req.message.strip()):
        raise HTTPException(400, '앱 동작과 일반 요청은 함께 보낼 수 없습니다')
    resolved = {'message': req.message, 'code': req.code}
    if req.action_id:
        from member_apps import resolve_request
        try:
            resolved = resolve_request(req.action_id, req.args, req.local_apps) if req.local_apps else resolve_request(req.action_id, req.args)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    envelope = {'version': 2, 'request_id': req.request_id, 'conversation_id': req.task_id,
                'message': req.message, 'code': req.code, 'action_id': req.action_id, 'args': req.args, 'local_apps': req.local_apps, 'capabilities': {'files': True}}
    return service.submit(rec, envelope, resolved)


@router.post('/m/desktop/status')
def status(req: DesktopRequest):
    import member_desktop_requests as service
    return service.status(identity(req), req.request_id, req.after)


@router.post('/m/desktop/cancel')
def cancel(req: DesktopRequest):
    import member_desktop_requests as service
    return service.cancel(identity(req), req.request_id)


INSTALLERS = {'mac-arm64': ('IndieBizMember-mac-arm64.zip', 'macOS · Apple Silicon'),
              'mac-x64': ('IndieBizMember-mac-x64.zip', 'macOS · Intel'),
              'win-x64': ('IndieBizMember-win-x64.exe', 'Windows · 64비트')}


def installer_path(target):
    from pathlib import Path
    if target not in INSTALLERS:
        raise HTTPException(404, '지원하지 않는 설치물')
    path = Path(__file__).resolve().parents[2] / 'member-desktop' / 'dist' / INSTALLERS[target][0]
    if not path.is_file() or path.is_symlink():
        raise HTTPException(404, '이 OS의 설치물이 아직 준비되지 않았습니다')
    return path


@router.get('/m/desktop/installers')
def installers():
    rows = []
    for target, (_, label) in INSTALLERS.items():
        try:
            path = installer_path(target)
            rows.append({'target': target, 'label': label, 'bytes': path.stat().st_size,
                         'url': '/m/desktop/download?target=' + target})
        except HTTPException:
            pass
    return {'installers': rows, 'notice': '개발 미리보기 설치물입니다. 외부 배포 전에 배포자 서명과 OS별 인수를 완료해야 합니다.'}


@router.get('/m/desktop/download')
def download(target: str):
    from fastapi.responses import FileResponse
    path = installer_path(target)
    return FileResponse(path, filename=path.name, headers={'Cache-Control': 'no-store'})
