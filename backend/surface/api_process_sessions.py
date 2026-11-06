"""Authenticated local process controls, sharing task/tool contracts."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from api_coding import owner
import process_sessions as service

router = APIRouter(prefix='/process-sessions', dependencies=[Depends(owner)])


class Start(BaseModel):
    command: str = Field(min_length=1, max_length=64000)
    cwd: str
    io: str = 'pipe'
    request_id: str
    yield_ms: int = Field(default=1000, ge=0, le=30000)
    lifetime: str = 'task'


class Control(BaseModel):
    action: str
    generation: str
    request_id: str
    text: str | None = None
    base64: str | None = None
    newline: bool = False
    cols: int | None = None
    rows: int | None = None


def call(fn, *args, **kwargs):
    try: return fn(*args, **kwargs)
    except (ValueError, PermissionError, OSError, RuntimeError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post('')
def start(req: Start):
    return call(service.start, **req.model_dump())


@router.get('/{task_id}')
def status(task_id: str, cursor: int = 0, limit_bytes: int = 65536, wait_ms: int = 0):
    return call(service.query, task_id, cursor=cursor, limit_bytes=limit_bytes, wait_ms=wait_ms)


@router.post('/{task_id}/control')
def control(task_id: str, req: Control):
    return call(service.query, task_id, op='control', actor='ui', **req.model_dump(exclude_none=True))


@router.delete('/{task_id}')
def cancel(task_id: str):
    return call(service.task_cancel, {'kind': 'process', 'task_id': task_id})
