"""코딩 앱의 엔진 I/O — 프로젝트 명령 실행(시작·출력 스트림·중지)만 남았다 (2026-10-07).

화면의 나머지(프로젝트 목록·열기·파일·기록·되돌리기)는 선언(data/instruments/coding.yaml)과 코드 엔진이
`[self:workspace]` 로 부른다 — 여기는 선언이 부르지 않는 길이다(문서 앱의 `/documents/engine/*` 과 같은 기준).
AI 코딩은 `[others:delegate]{scope:"system", role:"coding"}` 이라 HTTP 가 없다.
"""
from functools import lru_cache
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from coding_git import CodingConflict


def owner(request: Request):
    import principal
    if not principal.is_owner():
        raise HTTPException(403, "코딩 앱은 소유자 전용입니다")
    origin = request.headers.get("origin")
    host = request.url.hostname
    if origin and origin != "null":
        source = urlsplit(origin).hostname
        if source != host and not {source, host}.issubset({"localhost", "127.0.0.1", "::1"}):
            raise HTTPException(403, "다른 사이트에서 코딩 명령을 보낼 수 없습니다")


router = APIRouter(prefix="/coding", tags=["coding"], dependencies=[Depends(owner)])


@lru_cache(maxsize=1)
def service():
    from coding_projects import CodingProjects
    return CodingProjects()


def invoke(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except CodingConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except (ValueError, OSError, PermissionError) as exc:
        raise HTTPException(400, str(exc)) from exc


class RunRequest(BaseModel):
    command: str = Field(min_length=1, max_length=4000)
    serve: bool = False   # 서버형 실행(포트를 연다) — 샌드박스가 로컬 네트워크를 허용한다


@router.post("/projects/{resource}/run")
def start_run(resource: str, body: RunRequest):
    app = service()
    row = invoke(app.project, resource)
    rec = invoke(app.run, row, body.command, body.serve)
    import task_receipts
    return task_receipts.receipt("coding_run", rec["id"], owner=row["id"], state=task_receipts.RUNNING, run=rec)


@router.get("/projects/{resource}/runs")
def latest_run(resource: str):
    app = service()
    row = invoke(app.project, resource)
    return {"run": app.latest_run(row)}


@router.get("/runs/{run_id}")
def run_output(run_id: str, offset: int = Query(0, ge=0), limit: int = Query(200000, ge=1, le=1000000)):
    return invoke(service().output, run_id, offset, limit)


@router.post("/runs/{run_id}/stop")
def stop_run(run_id: str):
    return invoke(service().stop, run_id)
