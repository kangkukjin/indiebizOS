"""공동 업무 표면: 인증된 action ID와 타입 값만 받는다. 범용 code/SQL 입구 없음."""
import base64
import asyncio
import json
import secrets
import time
from urllib.parse import urlparse

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, Response, JSONResponse
from fastapi.routing import APIRoute

from common.record_contract import RecordError, fail, validate_definition
from record_policy import from_principal, require_owner
from record_facade import execute, spaces
from record_store import create_space, transaction, definition, uid

class RecordRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def guarded(request):
            try:
                response = await handler(request)
            except RecordError as exc:
                response = JSONResponse(exc.result(), status_code={
                    'forbidden': 403, 'not_found': 404, 'conflict': 409,
                    'definition_changed': 409, 'busy': 409}.get(exc.kind, 400))
            response.headers['Cache-Control'] = 'no-store'
            return response
        return guarded


router = APIRouter(route_class=RecordRoute)


def authenticate(request):
    """공개 회원 경로는 매 호출마다 기존 limb key 원장에서 재검증한다."""
    key = request.headers.get('x-member-key')
    if request.url.path.startswith('/m/') or key:
        from api_member import _member_of, _principal_for
        ident, error = _member_of(key or '')
        if error:
            raise HTTPException(401, '회원 열쇠를 확인하세요.')
        if _principal_for(*ident) is None:
            raise HTTPException(403, '회원 신원 불일치')
        from member_profile import gate
        denied = gate('self', 'record', {})
        if denied:
            raise HTTPException(403, denied.get('error', '업무 기능이 공개되지 않았습니다.'))
    if request.method != 'GET':
        origin = request.headers.get('origin')
        if origin and origin != 'null' and urlparse(origin).netloc != request.url.netloc:
            raise HTTPException(403, '다른 출처의 변경 요청은 허용하지 않습니다.')
    if '/spaces/' in request.url.path:
        from vocabulary_state import is_active
        if not is_active('record-ops'):
            raise HTTPException(403, '공동 업무 묶음이 잠들어 있습니다.')
    try:
        return from_principal(executor='record_app')
    except RecordError as exc:
        raise HTTPException(403, str(exc)) from exc


async def payload(request, limit=350000):
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(413, '입력 크기 상한 초과')
        chunks.append(chunk)
    raw = b''.join(chunks)
    try:
        body = json.loads(raw)
    except ValueError:
        raise HTTPException(400, 'JSON 객체가 필요합니다.')
    if not isinstance(body, dict):
        raise HTTPException(400, 'JSON 객체가 필요합니다.')
    return body


def invoke(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except RecordError as exc:
        return JSONResponse(exc.result(), status_code={'forbidden': 403, 'not_found': 404, 'conflict': 409, 'definition_changed': 409}.get(exc.kind, 400))


@router.get('/records/app', response_class=HTMLResponse)
@router.get('/m/records/app', response_class=HTMLResponse)
def app_page():
    from record_app_page import page
    nonce = secrets.token_urlsafe(32)
    response = HTMLResponse(page(nonce), headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
    response.set_cookie('record_csrf', nonce, httponly=True, samesite='strict')
    return response


@router.get('/records/spaces')
@router.get('/m/records/spaces')
def list_spaces(request: Request):
    return invoke(spaces, authenticate(request))


@router.post('/records/spaces/{space}/actions/{action_id}')
@router.post('/m/records/spaces/{space}/actions/{action_id}')
async def action(space: str, action_id: str, request: Request):
    auth = await asyncio.to_thread(authenticate, request)
    data = await payload(request)
    if action_id.startswith('command:'):
        if set(data) - {'definition_revision', 'input', 'expected', 'request_id', 'reason', 'confirmation'}:
            raise HTTPException(400, '선언되지 않은 명령 입력')
        args = {**data, 'space': space, 'op': 'apply', 'command': action_id[8:]}
    elif action_id in {'describe', 'query', 'detail', 'history', 'inbox', 'receipt'}:
        args = {**data, 'space': space, 'op': action_id}
    else:
        raise HTTPException(404, '공개되지 않은 앱 동작')
    # 동기 DB 확정은 이벤트 루프 밖에서 실행. contextvars는 to_thread가 승계한다.
    return await asyncio.to_thread(invoke, execute, args, auth)


@router.post('/records/spaces/{space}/confirm')
@router.post('/m/records/spaces/{space}/confirm')
async def confirm(space: str, request: Request):
    auth = await asyncio.to_thread(authenticate, request)
    csrf = request.headers.get('x-record-csrf', '')
    if not csrf or not secrets.compare_digest(csrf, request.cookies.get('record_csrf', '')):
        raise HTTPException(403, '업무 화면에서 확인하세요.')
    data = await payload(request)
    return await asyncio.to_thread(issue_confirmation, space, data, auth)


def issue_confirmation(space, data, auth):
    from record_commands import request_hash
    from record_policy import roles, allowed
    with transaction(space, write=True) as conn:
        member_roles = roles(conn, auth)
        defn, revision = definition(conn, data.get('definition_revision'))
        current, _ = definition(conn)
        command = defn['commands'].get(data.get('command'))
        current_command = current['commands'].get(data.get('command'))
        if data.get('definition_revision') != revision or not command or not current_command or not any(c.get('confirmation') == 'human' for c in (command, current_command)):
            raise HTTPException(409, '현재 확인할 명령이 아닙니다.')
        if not allowed({k: v for k, v in command['allow'].items() if k not in {'where', 'deny_self'}}, auth, member_roles):
            raise HTTPException(403, '승인 권한이 없습니다.')
        token = secrets.token_urlsafe(32)
        conn.execute('INSERT INTO confirmations(token,subject,hash,expires) VALUES (?,?,?,?)',
                     (token, auth.subject, request_hash(data), time.time() + 120))
    return {'success': True, 'confirmation': token}


@router.get('/records/admin/{space}/state')
def admin_state(space: str, request: Request):
    auth = authenticate(request)
    require_owner(auth)
    from record_policy import roles
    from record_store import meta
    with transaction(space) as conn:
        roles(conn, auth)
        return {'success': True, 'admin_revision': meta(conn, 'admin_revision'),
                'paused': meta(conn, 'paused'), 'recovery_required': meta(conn, 'recovery_required'),
                'items': [dict(row) for row in conn.execute('SELECT id,kind,state,attempt,result FROM deliveries ORDER BY due DESC LIMIT 200')]}


@router.post('/records/admin/{space}/{operation}')
async def management(space: str, operation: str, request: Request):
    auth = await asyncio.to_thread(authenticate, request)
    require_owner(auth)
    data = await payload(request, 150 * 1024 * 1024 if operation == 'import' else 600000)
    if operation == 'validate':
        return await asyncio.to_thread(invoke, lambda: {'success': True, 'definition': validate_definition(data.get('definition'))})
    if operation == 'create':
        return await asyncio.to_thread(invoke, create_space, space, data.get('definition'), auth)
    if operation == 'export':
        from record_assets import export_space
        value = await asyncio.to_thread(export_space, space, auth)
        return Response(value, media_type='application/zip', headers={'Content-Disposition': 'attachment; filename="record-space.zip"'})
    if operation == 'import':
        from record_assets import import_space
        try:
            content = base64.b64decode(data.get('content', ''), validate=True)
        except ValueError:
            raise HTTPException(400, '잘못된 내보내기 파일')
        return await asyncio.to_thread(invoke, import_space, space, content, auth)
    from record_admin import administer
    return await asyncio.to_thread(invoke, administer, space, operation, data, auth)


@router.post('/records/spaces/{space}/assets')
@router.post('/m/records/spaces/{space}/assets')
async def upload_asset(space: str, request: Request):
    auth = await asyncio.to_thread(authenticate, request)
    data = await payload(request, 28 * 1024 * 1024)
    from record_assets import upload
    try:
        content = base64.b64decode(data.get('content', ''), validate=True)
    except ValueError:
        raise HTTPException(400, '잘못된 파일 내용')
    return await asyncio.to_thread(invoke, upload, space, content, data.get('filename', 'attachment'), auth)


@router.post('/records/spaces/{space}/assets/{ident}')
@router.post('/m/records/spaces/{space}/assets/{ident}')
def download_asset(space: str, ident: str, request: Request):
    from record_assets import download
    value = invoke(download, space, ident, authenticate(request))
    if isinstance(value, JSONResponse):
        return value
    content, filename = value
    from urllib.parse import quote
    return Response(content, media_type='application/octet-stream', headers={'Content-Disposition': "attachment; filename*=UTF-8''" + quote(filename), 'Cache-Control': 'no-store'})
