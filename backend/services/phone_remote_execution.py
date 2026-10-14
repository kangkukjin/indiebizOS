"""Phone app execution bridge. No ADB privilege or desktop fallback."""
import json
import os
import threading
from pathlib import Path

from phone_execution_contract import VERSION, validate

_bridge_factory = None


def bridge():
    if _bridge_factory is not None:
        return _bridge_factory()
    try:
        from java import jclass
        return jclass("com.indiebiz.phoneagent.execution.RemoteExecutionBridge")
    except Exception:
        return None


def capabilities():
    impl = bridge()
    if impl is None:
        return {}
    try:
        result = json.loads(str(impl.capabilities()))
        return result if result.get("execution_contract") == VERSION else {}
    except Exception:
        return {}


def require_owner():
    import principal
    import member_runtime
    import repair_context
    if not principal.is_owner() or member_runtime.is_member():
        raise PermissionError("phone_execution_owner_required")
    if repair_context.active():
        raise PermissionError("phone_execution_has_no_repair_sandbox")


def execute(job_id, command, cancelled=None):
    try:
        require_owner()
    except PermissionError as exc:
        return {"success": False, "error": str(exc)}
    impl = bridge()
    if impl is None:
        return {"success": False, "error": "unsupported_on_this_body"}
    done = threading.Event()
    started = False

    def watch_cancel():
        while not done.wait(0.05):
            if cancelled.is_set():
                try:
                    impl.cancel(str(job_id))
                except Exception:
                    pass  # Retry until the native call completes or cancellation is accepted.

    try:
        command = validate(command)
        if cancelled is not None:
            if cancelled.is_set():
                return {"success": False, "cancelled": True, "error": "cancelled"}
            threading.Thread(target=watch_cancel, daemon=True).start()
        from thread_context import ISOLATED_ORIGINS, get_isolated_origin
        origin = get_isolated_origin() or command.get("origin")
        if isinstance(origin, str) and origin in ISOLATED_ORIGINS:
            command["origin"] = origin
        else:
            command.pop("origin", None)
        started = True
        raw = impl.execute(str(job_id), json.dumps(command, ensure_ascii=False, allow_nan=False))
        result = json.loads(str(raw))
        if not isinstance(result, dict) or type(result.get("success")) is not bool:
            raise ValueError("invalid_worker_result")
        return result
    except Exception as exc:
        return {"success": False, "error": str(exc), "exception_type": type(exc).__name__,
                "unknown": started, "side_effects_possible": started}
    finally:
        done.set()


def cancel(job_id):
    impl = bridge()
    return bool(impl is not None and impl.cancel(str(job_id)))


def workspace():
    root = Path(os.environ.get("INDIEBIZ_USERDATA") or Path.home()) / "remote_work"
    root.mkdir(parents=True, exist_ok=True)
    return root


def run_local(tool_input):
    """Local owner AI uses the same disposable service, without limb registration."""
    import uuid
    runtime = tool_input.get("runtime", "shell")
    envelope = {"op": runtime, "code" if runtime == "python" else "cmd": tool_input.get("command", ""),
                "timeout": tool_input.get("timeout", 120)}
    for key in ("inputs", "cwd"):
        if key in tool_input:
            envelope[key] = tool_input[key]
    from supervision_bus import current
    from types import SimpleNamespace
    controller = current()
    cancelled = SimpleNamespace(is_set=controller.cancelled) if controller else None
    return execute("local_" + uuid.uuid4().hex, envelope, cancelled)
