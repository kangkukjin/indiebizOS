"""조종실의 어휘 선택. 인증된 원격 사용자 또는 로컬 앱의 사용자 요청만 허용."""
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
            raise HTTPException(status_code=403, detail="조종실에서 어휘 선택을 변경해 주세요")
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
