"""과제 도구 브리지와 조종실 원장 표면."""
import asyncio
import json
import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter()


class ToolRequest(BaseModel):
    agent_id: str
    task_id: str
    payload: dict


@router.post("/pursuit")
async def bridge(req: ToolRequest):
    from pursuit_tools import execute_pursuit
    return json.loads(await asyncio.to_thread(execute_pursuit, req.payload, req.agent_id, req.task_id))


def _find(pid):
    from pursuit_maintenance import ledgers
    for ledger in ledgers():
        try:
            return ledger, ledger.get(pid)
        except KeyError:
            continue
    raise HTTPException(404, "과제를 찾을 수 없습니다")


@router.get("/pursuits")
def list_pursuits(archived: bool = False, offset: int = Query(0, ge=0),
                  limit: int = Query(30, ge=1, le=100)):
    from pursuit_maintenance import ledgers
    from pursuit_bind import public_row
    rows = []
    for ledger in ledgers():
        page = 0
        while True:
            result = ledger.list(statuses=("done", "abandoned") if archived else ("active", "parked"), offset=page, limit=100)
            rows.extend(public_row(r) for r in result["items"])
            if result["next_offset"] is None:
                break
            page = result["next_offset"]
    rows.sort(key=lambda r: r["last_turn_at"], reverse=True)
    return {"items": rows[offset:offset + limit], "total": len(rows)}


@router.get("/pursuits/{pid}")
def read_pursuit(pid: str, offset: int = Query(0, ge=0)):
    from pursuit_bind import public_row
    ledger, row = _find(pid)
    return {"pursuit": public_row(row), "events": ledger.events(pid, offset),
            "pending_turns": ledger.turns(pid, pending_only=True)}


class ChangeRequest(BaseModel):
    version: int
    status: str = ""
    why: str = Field(min_length=1)


@router.patch("/pursuits/{pid}")
def change_pursuit(pid: str, req: ChangeRequest):
    from pursuit_ledger import Conflict
    from pursuit_bind import public_row
    ledger, row = _find(pid)
    task = "panel:" + uuid.uuid4().hex
    try:
        seq = ledger.begin_turn(pid, task, req.why)
        result = ledger.apply(pid, task, req.version, {"status": req.status}, task, seq,
                              kind="panel.status", why=req.why)
        return public_row(result)
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        with ledger.connect(True) as c:
            c.execute("UPDATE pursuit_turn SET state='applied' WHERE pursuit_id=? AND task_id=?", (pid, task))


@router.delete("/pursuits/{pid}")
def delete_pursuit(pid: str, version: int):
    from pursuit_ledger import Conflict
    ledger, _ = _find(pid)
    try:
        ledger.delete(pid, version)
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"deleted": True}
