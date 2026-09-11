"""로컬 제어자 전용 상태 계약과 HTTP 실행 경계. 프록시 주소를 로컬로 신뢰하지 않는다."""
import hmac
import os
import time

from fastapi import APIRouter, HTTPException, Request
from runtime_work import registry

router = APIRouter(prefix="/runtime", tags=["runtime"])


def authorize(request):
    secret = os.environ.get("INDIEBIZ_RUNTIME_CONTROL", "")
    headers = request.headers
    if (not secret or not request.client or request.client.host not in {"127.0.0.1", "::1"}
            or any(k in headers for k in ("forwarded", "x-forwarded-for", "x-forwarded-host", "cf-connecting-ip"))
            or not hmac.compare_digest(headers.get("x-runtime-control", ""), secret)):
        raise HTTPException(403, "로컬 제어자 인증이 필요합니다")
    if registry() is None:
        raise HTTPException(503, "실행 소유 관측이 준비되지 않았습니다")


def runtime_status():
    import boot_status
    work = registry()
    if work is None:
        return {"ownership": "unknown", "readiness": "unknown", "observed_at": time.time()}
    status = work.snapshot()
    status["code_digest"] = os.environ.get("INDIEBIZ_RUNTIME_DIGEST")
    boot = boot_status.snapshot()
    entries = {e["name"]: e["ok"] for e in boot["entries"]}
    # 설치 공통 필수: 공통 부팅/IBL/수명 완료. 나머지는 부팅 원장에 degraded로 보고.
    required = {"boot", "IBL", "lifespan"}
    if any(entries.get(k) is False for k in required):
        ready = "failed"
    elif any(k not in entries for k in required):
        ready = "starting"
    else:
        ready = "degraded" if boot["failed"] else "ready"
    status.update(readiness=ready, required=sorted(required), errors=status.get("errors", []) + boot["failed"])
    try:
        from episode_logger import live_episode_ids
        status["live_episode_ids"] = live_episode_ids()
        if status["live_episode_ids"] and not status["owners"]:
            status.update(ownership="unknown", errors=status["errors"] + ["등록되지 않은 활성 에피소드"])
    except Exception as exc:
        status.update(ownership="unknown", errors=status["errors"] + [str(exc)])
    return status


@router.get("/status")
def status(request: Request):
    authorize(request)
    return runtime_status()


@router.post("/{action}")
async def control(action: str, request: Request):
    authorize(request)
    body = await request.json()
    work = registry()
    if body.get("generation") != work.generation:
        raise HTTPException(409, "오래된 generation의 명령입니다")
    if action not in {"drain", "activate"}:
        raise HTTPException(404, "알 수 없는 제어 명령")
    if action == "activate" and runtime_status()["readiness"] not in {"ready", "degraded"}:
        raise HTTPException(409, "실행 준비가 완료되지 않았습니다")
    before = work.phase
    result = work.gate("DRAINING" if action == "drain" else "ACTIVE")
    if action == "activate" and before == "STARTING":
        import sys
        import threading
        import runtime_work
        queue_module = sys.modules.get("distill_queue")
        queue = queue_module.DistillQueue._instance if queue_module else None
        if queue is not None and queue._resume_armed:
            callback = runtime_work.bind_lease(queue.resume, "distill-resume", kind="finalizer")
            with runtime_work.service_scope():
                threading.Thread(target=callback, daemon=True, name="distill-resume").start()
    return result


class RuntimeAdmission:
    """HTTP 제출 수명. 제어/조회/취소와 MCP 세션 운용은 drain 중에도 유지한다.

    MCP 실제 실행은 /ibl/execute로 재진입하며 같은 부모 capability를 나른다.
    ASGI 응답의 background까지 완료되기 전에는 이 예약을 반환하지 않는다.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        import runtime_work
        from starlette.responses import JSONResponse
        path = scope.get("path", "")
        safe = (scope.get("method") in {"GET", "HEAD", "OPTIONS"}
                or path.startswith(("/runtime/", "/mcp"))
                or path in {"/ibl/recover", "/ibl/guide", "/ibl/read-guide", "/ibl/reframe"}
                or any(p in {"cancel", "steer", "stop", "interrupt", "recover"} for p in path.split("/")))
        if scope["type"] == "http" and path == "/ibl/execute" and not safe:
            # 기존 원문 회수/정적 계약 조회는 실행을 새로 승인하지 않는다.
            import json
            messages, chunks = [], []
            while True:
                message = await receive()
                messages.append(message)
                chunks.append(message.get("body", b""))
                if not message.get("more_body", False):
                    break
            try:
                body = json.loads(b"".join(chunks))
                safe = isinstance(body, dict) and bool(body.get("read_result") or body.get("describe") or body.get("check"))
            except (ValueError, UnicodeError):
                pass
            original_receive = receive
            async def replay():
                return messages.pop(0) if messages else await original_receive()
            receive = replay
        if scope["type"] != "http" or safe or runtime_work.registry() is None:
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        parent = headers.get(b"x-runtime-parent", b"").decode("ascii", "replace") or None
        try:
            lease = runtime_work.reserve("http:" + path, parent=parent)
        except runtime_work.AdmissionClosed as exc:
            response = JSONResponse({"detail": str(exc), "executed": False}, status_code=503)
            return await response(scope, receive, send)
        try:
            with lease.activate():
                return await self.app(scope, receive, send)
        finally:
            lease.close()
