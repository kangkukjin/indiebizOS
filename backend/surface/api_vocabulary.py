"""런처 내 어휘의 선택. 인증된 원격 사용자 또는 로컬 앱의 사용자 요청만 허용."""
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from vocabulary_lifecycle import HUMAN_AUTHORITY, check_ready, set_package_active
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


@router.get("/vocabulary")
def list_vocabulary():
    from package_manager import package_manager
    packages = package_manager.list_available()
    for package in packages:
        package["preparation"] = check_ready(package["id"])
    return {"packages": packages, "revision": read_state()["revision"]}


@router.post("/vocabulary/{package_id}/activation")
def set_activation(package_id: str, selection: ActivationRequest, request: Request):
    authority = human_authority(request)
    try:
        return set_package_active(package_id, selection.active, authority=authority)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


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
