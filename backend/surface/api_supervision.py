"""CLI의 감독 작업대·도구 경계. MCP 재진입도 같은 턴/같은 권한 문맥을 사용한다."""
import asyncio
import json

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class Request(BaseModel):
    agent_id: str
    task_id: str
    payload: dict = {}


def dispatch(agent_id, task_id, payload, boundary=False):
    from supervision_bus import current
    from thread_context import snapshot, restore, set_current_agent_id
    supervisor = current(agent_id, task_id)
    if not supervisor:
        return {"active": False} if boundary else {"success": False, "error": "활성 감독 턴이 없습니다"}
    previous = snapshot()
    try:
        restore(supervisor.context)
        set_current_agent_id(agent_id)
        from providers.base import adopt_turn_token_ledger
        from episode_logger import trajectory_scope
        with adopt_turn_token_ledger(supervisor.owner, task_id), \
                trajectory_scope(task_id=task_id, episode_id=getattr(supervisor, "episode_id", None)):
            if boundary:
                return {"active": True, "instruction": supervisor.boundary()}
            return json.loads(supervisor.tool(payload))
    finally:
        restore(previous)


@router.post("/supervision")
async def bridge(req: Request):
    return await asyncio.to_thread(dispatch, req.agent_id, req.task_id, req.payload)


@router.post("/supervision/boundary")
async def boundary(req: Request):
    return await asyncio.to_thread(dispatch, req.agent_id, req.task_id, req.payload, True)
