"""시스템AI·프로젝트 에이전트의 영속 대화 세션 API."""
import uuid
from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import chat_session_service as service
from conversation_sessions import scope

router = APIRouter(prefix="/chat-sessions")


class Target(BaseModel):
    target: str = "system_ai"
    project_id: str = ""
    agent_id: str = ""


class Change(Target):
    title: str | None = Field(default=None, max_length=120)


class Message(Target):
    message: str = Field(min_length=1, max_length=200000)
    images: list = Field(default_factory=list, max_length=20)
    documents: list = Field(default_factory=list, max_length=20)
    action_hint: str | None = None
    panel_action: Literal["answer", "approve", "reject"] | None = None


def get_store(target="system_ai", project_id="", agent_id=""):
    try:
        return service.store_for(target, project_id, agent_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("")
def list_sessions(target: str = "system_ai", project_id: str = "", agent_id: str = ""):
    return {"sessions": get_store(target, project_id, agent_id)[0].list()}


@router.post("")
def create_session(req: Change):
    return get_store(req.target, req.project_id, req.agent_id)[0].create(req.title or "새 세션")


@router.patch("/{sid}")
def update_session(sid: str, req: Change):
    try:
        return get_store(req.target, req.project_id, req.agent_id)[0].update(sid, req.title)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/{sid}")
def get_session(sid: str, target: str = "system_ai", project_id: str = "", agent_id: str = "", before: int | None = None):
    try:
        return service.snapshot(get_store(target, project_id, agent_id)[0], sid, before)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/{sid}/messages", status_code=202)
async def send(sid: str, req: Message):
    from chat_runs import registry
    import chat_streams
    from websocket_manager import manager
    store, config = get_store(req.target, req.project_id, req.agent_id)
    try:
        binding = store.begin(sid)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    data = req.model_dump()
    data.update(session_id=sid, _session_binding=binding)
    if req.target == "agent":
        data["agent_name"] = config["name"]
    elif req.target == "appmaker":
        data["role"] = "appmaker"
    handler = chat_streams.handle_chat_message_stream if req.target == "agent" else chat_streams.handle_system_ai_chat_stream
    try:
        if req.panel_action:
            service.respond_panel(binding, req.panel_action, req.message)
        registry.start(handler, "session_" + uuid.uuid4().hex, data, None, manager)
    except Exception as exc:
        store.finish(binding, "failed", str(exc))
        raise HTTPException(503, str(exc)) from exc
    return {"turn_id": binding.turn_id, "session_id": sid}


@router.post("/{sid}/cancel")
def cancel(sid: str, req: Target):
    try:
        return {"cancelled": service.cancel(get_store(req.target, req.project_id, req.agent_id)[0], sid)}
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
