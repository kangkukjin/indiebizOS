"""폰 자체 AI도 공통 세션 저장 계약을 쓴다. 추론은 폰의 기존 실행자를 유지한다."""
import threading
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


class SessionRequest(BaseModel):
    target: str = "system_ai"
    project_id: str = ""
    agent_id: str = ""
    message: str = Field(default="", max_length=200000)
    # Android는 Pydantic 1.x: 목록 길이는 max_items로 제한해야 부팅 가능하다.
    images: list[Any] = Field(default_factory=list, max_items=20)
    title: str = Field(default="새 세션", max_length=120)


def create_router(project_manager, system_runner, agent_runner):
    router = APIRouter(prefix="/chat-sessions")
    running = {}
    lock = threading.RLock()

    def store_for(target="system_ai", project_id="", agent_id=""):
        import chat_session_service as service
        if target not in ("system_ai", "agent"):
            raise HTTPException(404, "대화 대상을 찾을 수 없습니다")
        if target == "agent":
            service.project_manager = project_manager()
        try:
            return service.store_for(target, project_id, agent_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.get("")
    def listing(target: str = "system_ai", project_id: str = "", agent_id: str = ""):
        return {"sessions": store_for(target, project_id, agent_id)[0].list()}

    @router.post("")
    def create(req: SessionRequest):
        return store_for(req.target, req.project_id, req.agent_id)[0].create(req.title, reuse_empty=True)

    @router.get("/{sid}")
    def read(sid: str, target: str = "system_ai", project_id: str = "", agent_id: str = "", before: int | None = None):
        from chat_session_service import snapshot
        try:
            return snapshot(store_for(target, project_id, agent_id)[0], sid, before)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    def work(store, config, binding, req, cancel):
        from conversation_sessions import scope
        state, error = "completed", None
        try:
            with scope(binding):
                if req.target == "system_ai":
                    system_runner(req.message, req.images, cancel_check=cancel.is_set)
                else:
                    from conversation_db import ConversationDB
                    db = ConversationDB(store.path)
                    user = db.get_or_create_agent("user", "human")
                    agent = db.get_or_create_agent(config["name"], "ai_agent")
                    history = db.get_history_for_ai(agent, user, limit=7)
                    db.save_message(user, agent, req.message, images=req.images)
                    result = agent_runner(req.project_id, req.agent_id, req.message,
                                          history=history, images=req.images, cancel_check=cancel.is_set)
                    if result.get("response"):
                        db.save_message(agent, user, result["response"])
                if cancel.is_set():
                    state = "cancelled"
        except Exception as exc:
            state, error = ("cancelled" if cancel.is_set() else "failed"), str(exc)
        finally:
            try:
                store.finish(binding, state, error)
            finally:
                with lock:
                    running.pop((store.path, binding.session_id), None)

    @router.post("/{sid}/messages", status_code=202)
    def send(sid: str, req: SessionRequest):
        if not req.message.strip():
            raise HTTPException(422, "메시지를 입력하세요")
        store, config = store_for(req.target, req.project_id, req.agent_id)
        try:
            binding = store.begin(sid)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        cancel = threading.Event()
        with lock:
            running[(store.path, sid)] = cancel
        try:
            threading.Thread(target=work, args=(store, config, binding, req, cancel), daemon=True).start()
        except Exception as exc:
            store.finish(binding, "failed", str(exc))
            with lock:
                running.pop((store.path, sid), None)
            raise HTTPException(503, str(exc)) from exc
        return {"session_id": sid, "turn_id": binding.turn_id}

    @router.post("/{sid}/cancel")
    def cancel(sid: str, req: SessionRequest):
        store = store_for(req.target, req.project_id, req.agent_id)[0]
        try:
            store.history(sid, limit=1)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        with lock:
            event = running.get((store.path, sid))
            if event:
                event.set()
        return {"cancelled": bool(event)}

    return router
