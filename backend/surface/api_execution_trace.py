"""Existing driving journal's read-only trace and document pages. Launcher-owner access."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from execution_trace import ExecutionTrace
from execution_trace_scope import TraceAccess
from runtime_utils import get_base_path

router = APIRouter()


def launcher_access(request: Request):
    # The main app also enforces this gate. Keep this private if the router is mounted elsewhere.
    try:
        from api_launcher_web import is_external_request, verify_session
        external = is_external_request(request)
    except Exception:
        raise HTTPException(503, "인증 상태를 확인하지 못했습니다") from None
    if external:
        try:
            valid = verify_session(request)
        except Exception:
            valid = False
        if not valid:
            raise HTTPException(401, "런처 로그인이 필요합니다")
    return TraceAccess(None, True)


class TracePage(BaseModel):
    project: str | None = Field(default=None, max_length=200)
    owner: str | None = Field(default=None, max_length=200)
    cursor: str | None = Field(default=None, max_length=64000)
    limit: int = Field(default=50, ge=1, le=100)


class TraceQuery(TracePage):
    episode_id: int | None = Field(default=None, ge=1)
    task_id: str | None = Field(default=None, max_length=300)
    run_id: str | None = Field(default=None, max_length=100)


class DocumentPage(BaseModel):
    source_ref: str = Field(max_length=64000)
    project: str | None = Field(default=None, max_length=200)
    owner: str | None = Field(default=None, max_length=200)
    cursor: str | None = Field(default=None, max_length=64000)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=12000, ge=1, le=12000)
    episode_id: int | None = Field(default=None, ge=1)
    task_id: str | None = Field(default=None, max_length=300)
    run_id: str | None = Field(default=None, max_length=100)


def response(value):
    status = value.get("status")
    code = {"forbidden": 403, "missing": 404, "unavailable": 503, "malformed": 422}.get(status)
    if code:
        from fastapi.responses import JSONResponse
        return JSONResponse(value, status_code=code)
    return value


@router.get("/world-pulse/episodes/{episode_id}/trace")
async def episode_trace(episode_id: int, access=Depends(launcher_access)):
    value = await asyncio.to_thread(lambda: ExecutionTrace(get_base_path()).query(access, episode_id=episode_id))
    return response(value)


@router.post("/world-pulse/episodes/{episode_id}/trace")
async def episode_trace_page(episode_id: int, page: TracePage, access=Depends(launcher_access)):
    value = await asyncio.to_thread(lambda: ExecutionTrace(get_base_path()).query(
        access, episode_id=episode_id, **page.model_dump()))
    return response(value)


@router.post("/world-pulse/execution-trace")
async def scoped_trace(page: TraceQuery, access=Depends(launcher_access)):
    value = await asyncio.to_thread(lambda: ExecutionTrace(get_base_path()).query(access, **page.model_dump()))
    return response(value)


@router.post("/world-pulse/episodes/{episode_id}/trace/document")
async def episode_document(episode_id: int, page: DocumentPage, access=Depends(launcher_access)):
    args = page.model_dump(exclude={"episode_id", "task_id", "run_id"})
    value = await asyncio.to_thread(lambda: ExecutionTrace(get_base_path()).document(access, episode_id=episode_id, **args))
    return response(value)


@router.post("/world-pulse/execution-trace/document")
async def scoped_document(page: DocumentPage, access=Depends(launcher_access)):
    value = await asyncio.to_thread(lambda: ExecutionTrace(get_base_path()).document(access, **page.model_dump()))
    return response(value)
