"""Owner-only document sessions. Remote callers use registered IDs, not paths."""
from functools import lru_cache
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

import principal
from document_workspace import DocumentWorkspace, DocumentConflict, DocumentUnsupported

LOOPBACK = {"localhost", "127.0.0.1", "::1", "testclient"}


def authorize(request: Request):
    if not principal.is_owner():
        raise HTTPException(403, "문서 작업 공간은 소유자 전용입니다")
    origin = request.headers.get("origin")
    if origin == "null":
        if not request.client or request.client.host not in LOOPBACK:
            raise HTTPException(403, "허용되지 않은 문서 요청 출처입니다")
    elif origin:
        source, target = urlsplit(origin), urlsplit(str(request.url))
        local = source.hostname in LOOPBACK and target.hostname in LOOPBACK
        if not local and (source.scheme, source.netloc) != (target.scheme, target.netloc):
            raise HTTPException(403, "다른 사이트에서 문서 작업을 시작할 수 없습니다")


router = APIRouter(prefix="/documents", tags=["documents"], dependencies=[Depends(authorize)])


@lru_cache(maxsize=1)
def service():
    return DocumentWorkspace()


def invoke(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except DocumentConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except DocumentUnsupported as exc:
        raise HTTPException(422, str(exc)) from exc
    except (TypeError, ValueError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc


class OpenRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    encoding: str | None = None


class Command(BaseModel):
    args: dict = Field(default_factory=dict)


# Closed operation dispatch; neither arbitrary getattr nor executable code.
OPERATIONS = {
    "sessions": DocumentWorkspace.acquire, "draft": DocumentWorkspace.draft,
    "snapshots": DocumentWorkspace.snapshot, "proposals": DocumentWorkspace.propose,
    "ai": DocumentWorkspace.generate_proposal,
    "apply": DocumentWorkspace.apply, "save": DocumentWorkspace.save,
    "export": DocumentWorkspace.export_copy, "restore": DocumentWorkspace.restore,
    "recover": DocumentWorkspace.recover, "close": DocumentWorkspace.close,
    "reclaim": DocumentWorkspace.reclaim,
}


@router.get("")
def documents():
    return {"items": invoke(service().list), "release_complete": False}


@router.post("/open")
def open_document(body: OpenRequest, request: Request):
    if (not request.client or request.client.host not in LOOPBACK
            or request.headers.get("x-forwarded-for") or request.headers.get("cf-connecting-ip")):
        raise HTTPException(403, "원격에서는 등록된 문서 ID를 사용하세요. 로컬 경로 열기는 로컬 앱 전용입니다")
    return invoke(service().open, **body.model_dump())


@router.get("/{document_id}")
def detail(document_id: str):
    return invoke(service().detail, document_id)


@router.get("/{document_id}/capabilities")
def capabilities(document_id: str):
    return invoke(service().capabilities, document_id)


@router.get("/{document_id}/versions")
def versions(document_id: str):
    return {"items": invoke(service().versions, document_id)}


@router.get("/{document_id}/snapshots/{snapshot_id}")
def read(document_id: str, snapshot_id: str):
    return invoke(service().read, document_id, snapshot_id)


@router.get("/{document_id}/events")
def events(document_id: str, after: int = Query(0, ge=0)):
    invoke(service().detail, document_id)
    items = service().store.events(document_id, after)
    return {"items": items, "next": items[-1]["sequence"] if items else after, "has_more": len(items) == 200}


@router.post("/{document_id}/{operation}")
async def command(document_id: str, operation: str, request: Request):
    if operation not in OPERATIONS:
        raise HTTPException(404, "지원하지 않는 문서 작업입니다")
    # Stream a bounded body before JSON parsing; do not trust Content-Length.
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 30 * 1024 * 1024:
            raise HTTPException(413, "문서 요청 크기 상한을 초과했습니다")
    try:
        body = Command.model_validate_json(data)
    except ValueError as exc:
        raise HTTPException(422, "문서 작업 인자가 올바르지 않습니다") from exc
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(invoke, OPERATIONS[operation], service(), document_id, **body.args)
