"""런처 내 어휘의 선택. 인증된 원격 사용자 또는 로컬 앱의 사용자 요청만 허용.

② 권한 연결(2026-10-05): `human_authority` 는 "이 요청이 사람이 보는 표면에서 왔다"는 **증명** 하나만 맡는다.
어휘 활성(activation)은 IBL `[self:package]{op: activate|deactivate}` 의 `requires`(owner + human_confirm) 관문 위를
지나는 **얇은 통로**다 — 라우트가 HUMAN_AUTHORITY 를 직접 건네지 않고, 사람 통로임이 증명된 뒤 그 요청 지문에 승인
토큰을 발급해 실행기로 보낸다(관문이 소비). 어휘 낱말이 없는 바탕화면·가져오기 라우트는 ⑩(몸의 명사 생애주기 어휘)
전까지 human_authority 만으로 남는다.
"""
import json
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from vocabulary_lifecycle import HUMAN_AUTHORITY, check_ready
from vocabulary_state import read_state

router = APIRouter()


def human_authority(request: Request):
    from api_launcher_web import is_external_request, verify_session
    if is_external_request(request):
        if not verify_session(request):
            raise HTTPException(status_code=403, detail="사용자 로그인이 필요합니다")
    else:
        # 로컬 무인 HTTP/IBL은 사용자 선택으로 간주하지 않는다.
        # 브라우저가 부착하는 출처/Fetch Metadata를 확인한다. OS 권한 자체의 격리는 별개다.
        origin = request.headers.get("origin", "")
        parsed = urlsplit(origin)
        local_origin = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        app_origin = origin in {"app://.", "file://", "null"}
        if (not (local_origin or app_origin)
                or request.headers.get("sec-fetch-mode") not in {"cors", "same-origin"}):
            raise HTTPException(status_code=403, detail="런처의 내 어휘에서 선택을 변경해 주세요")
    return HUMAN_AUTHORITY


class ActivationRequest(BaseModel):
    active: bool
    profile: str = "owner"


@router.get("/vocabulary")
def list_vocabulary():
    from package_manager import package_manager
    packages = package_manager.list_available()
    from member_profile import manifest
    from vocabulary_state import is_active
    declarations = manifest().get("actions", {})
    for package in packages:
        package["preparation"] = check_ready(package["id"])
        package["member_active"] = is_active(package["id"], profile="member")
        package["member_words"] = sorted(k for k, v in declarations.items() if v.get("package") == package["id"])
    return {"packages": packages, "revision": read_state()["revision"]}


def run_ibl_as_human(code: str, action_key: str, op: str = None) -> dict:
    """사람 통로(human_authority 통과 뒤)의 요청을 IBL 실행기 관문 위로 보낸다 — HTTP 라우트는 얇은 통로.

    human_confirm 액션이 요구하는 승인 토큰을 **여기서**(사람이 보는 표면이 증명된 뒤) 그 요청 지문(code+inputs)에
    대해 발급해 싣는다 — /ibl/approve 가 하는 일과 같고, 관문(action_requires.gate)이 한 번 소비한다. 주체는
    전송 관문이 세운 것 그대로다(넓히지 않음) — requires.principal 은 관문이 대조하므로 회원 세션이면 거절된다.
    반환은 판본 2 봉투(success/value 또는 error)."""
    import approval_tokens
    import principal as _principal
    from thread_context import set_approval, get_approval
    from project_manager import ProjectManager
    from ibl_v2_entry import handle_request
    digest = approval_tokens.request_digest(code, {}, [])
    token = approval_tokens.issue(approval_tokens.challenge(_principal.current().key(), action_key, digest, op))["token"]
    prev = get_approval()
    try:
        set_approval(token, digest)
        return handle_request({"code": code, "edition": 2, "inputs": {}, "declared_inputs": []},
                              str(ProjectManager().get_project_path("앱모드")), None)
    finally:
        set_approval(*prev)


@router.post("/vocabulary/{package_id}/activation")
def set_activation(package_id: str, selection: ActivationRequest, request: Request):
    """얇은 통로: 사람 통로 증명 → `[self:package]{op: activate|deactivate, package_id, profile}` → requires 관문(owner + 승인 토큰)."""
    human_authority(request)
    if selection.profile not in ("owner", "member"):
        raise HTTPException(status_code=400, detail="지원하지 않는 프로파일")
    op = "activate" if selection.active else "deactivate"
    code = (f'[self:package]{{op: "{op}", package_id: {json.dumps(package_id, ensure_ascii=False)}, '
            f'profile: "{selection.profile}"}}')
    r = run_ibl_as_human(code, "self:package", op)
    if r.get("success") and isinstance(r.get("value"), dict):
        return r["value"]
    err = r.get("error") or "어휘 활성 변경 실패"
    kind = ((r.get("diagnostic") or {}).get("kind") if isinstance(r.get("diagnostic"), dict) else None) or r.get("error_type")
    raise HTTPException(status_code=503 if kind == "capability" else 400, detail=err)


@router.get("/vocabulary/{package_id}/export")
def export_vocabulary(package_id: str):
    from fastapi.responses import Response
    from vocabulary_archive import export_package
    try:
        content = export_package(package_id)
        return Response(content, media_type="application/octet-stream",
                        headers={"Content-Disposition": f'attachment; filename="{package_id}.iblpack"'})
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/vocabulary/import")
async def import_vocabulary(request: Request):
    import asyncio
    from vocabulary_archive import MAX_ARCHIVE
    from vocabulary_import import import_package
    from package_manager import decode_package_bytes
    human_authority(request)
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_ARCHIVE:
            raise HTTPException(status_code=413, detail="어휘 파일은 최대 20MB입니다")
        chunks.append(chunk)
    def receive():
        content = decode_package_bytes(b''.join(chunks))
        return import_package(content)
    try:
        return await asyncio.to_thread(receive)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


class DesktopEdit(BaseModel):
    op: str
    item: str | None = None
    parent: str = "desktop"
    name: str | None = None
    x: float = 24
    y: float = 24
    columns: int = 5


@router.get("/vocabulary/desktop")
def read_desktop():
    from vocabulary_desktop import get_desktop
    return get_desktop()


@router.post("/vocabulary/desktop")
def update_desktop(edit: DesktopEdit, request: Request):
    from vocabulary_desktop import edit_desktop
    authority = human_authority(request)
    try:
        return edit_desktop(**edit.model_dump(), authority=authority)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (RuntimeError, OSError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/vocabulary/{package_id}/words")
def list_words(package_id: str):
    from vocabulary_desktop import package_words
    try:
        return {"words": package_words(package_id)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
