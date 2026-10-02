"""소유자 전용 코딩 앱 API. 경로는 등록 저장소·과제 ID에서 해소한다."""
from functools import lru_cache
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from coding_git import CodingConflict, untracked
from coding_runs import CodingRuns, choices
from coding_workspace import CodingWorkspace


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
    return CodingWorkspace()


def invoke(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except CodingConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(400, str(exc)) from exc


class RepositoryRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)


class TaskRequest(BaseModel):
    repository_id: str
    goal: str = Field(min_length=1, max_length=1500)


class RunRequest(BaseModel):
    message: str = Field(min_length=1, max_length=30000)
    executor: str = "system"
    command_id: str = Field(min_length=1, max_length=128)
    selection: dict | None = None


class CommandRequest(BaseModel):
    command: str = Field(min_length=1, max_length=10000)
    command_id: str = Field(min_length=1, max_length=128)


class SaveRequest(BaseModel):
    path: str
    content: str
    expected: str | None


class ReviewRequest(BaseModel):
    selected: list[str] = Field(default_factory=list)


class ApprovalRequest(BaseModel):
    review_id: str
    fingerprint: str


class ApplyRequest(ApprovalRequest):
    command_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=1000)


@router.get("/state")
def state():
    app = service()
    return {"repositories": app.store.list("repository"), "tasks": app.store.list("task"), "executors": choices()}


@router.post("/repositories")
def open_repository(body: RepositoryRequest):
    return invoke(service().open_repository, body.path)


@router.post("/tasks")
def create_task(body: TaskRequest):
    return invoke(service().create_task, body.repository_id, body.goal)


@router.get("/tasks/{task_id}")
def task_detail(task_id: str):
    app = service()
    task = invoke(app.store.get, "task", task_id)
    operation = invoke(app.store.get, "apply", task["apply_id"]) if task.get("apply_id") else None
    return {"task": task, "files": invoke(app.files, task_id), "untracked": untracked(task["workspace"]),
            "runs": [r for r in app.store.list("run") if r["task_id"] == task_id],
            "review": app.store.get("review", task["review_id"]) if task.get("review_id") else None,
            "apply": operation, "pursuit": app.ledger.get(task["pursuit_id"])}


@router.get("/tasks/{task_id}/events")
def events(task_id: str, after: int = Query(0, ge=0), limit: int = Query(200, ge=1, le=1000)):
    invoke(service().store.get, "task", task_id)
    items = service().store.events(task_id, after, limit)
    return {"items": items, "next": items[-1]["sequence"] if items else after, "has_more": len(items) == limit}


@router.post("/tasks/{task_id}/runs")
def run(task_id: str, body: RunRequest):
    return invoke(CodingRuns(service()).start, task_id, body.message, body.executor, body.command_id, body.selection)


@router.post("/tasks/{task_id}/verify")
def verify(task_id: str, body: CommandRequest):
    return invoke(CodingRuns(service()).start, task_id, "검증: " + body.command, "", body.command_id, command=body.command)


@router.post("/tasks/{task_id}/cancel")
def cancel(task_id: str):
    return invoke(CodingRuns(service()).cancel, task_id)


@router.get("/tasks/{task_id}/file")
def read_file(task_id: str, path: str):
    return invoke(service().read_file, task_id, path)


@router.put("/tasks/{task_id}/file")
def save_file(task_id: str, body: SaveRequest):
    return invoke(service().save_file, task_id, body.path, body.content, body.expected)


@router.post("/tasks/{task_id}/review")
def review(task_id: str, body: ReviewRequest):
    return invoke(service().review, task_id, body.selected)


@router.post("/tasks/{task_id}/approve")
def approve(task_id: str, body: ApprovalRequest):
    return invoke(service().approve, task_id, body.review_id, body.fingerprint)


@router.post("/tasks/{task_id}/apply")
def apply(task_id: str, body: ApplyRequest):
    return invoke(service().apply, task_id, body.review_id, body.fingerprint, body.command_id, body.message)
