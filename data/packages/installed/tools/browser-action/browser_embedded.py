"""Authenticated local bridge to the owner's Electron tabs. No cookies/passwords cross it."""
import asyncio
import json
import os
import stat
import time
import uuid
from pathlib import Path

from runtime_utils import get_base_path

CAPABILITIES = {"tab", "navigate", "snapshot", "content", "google_results", "click", "type", "press_key",
                "select", "check", "scroll", "wait", "iframe", "auth", "close"}
_choices = {}


def supported(args):
    op = args.get("op")
    return (op in CAPABILITIES and not any(args.get(k) for k in ("selector", "path", "dialog", "dialog_text", "headless"))
            and not (op == "content" and args.get("mode", "text") != "text")
            and not (op == "click" and args.get("mode", "single") != "single")
            and not (op == "navigate" and (args.get("wait") not in (None, "load", "stable")
                                           or args.get("wait_for") not in (None, "load")))
            and not (op == "wait" and any(args.get(k) for k in ("url", "network_idle", "selector"))))


def state_path():
    root = os.environ.get("INDIEBIZ_RUNTIME_STATE_DIR")
    return (Path(root) if root else get_base_path() / "data" / "runtime") / "embedded-browser.json"


def connection():
    """Do not accept symlinks, group-readable credentials, or another OS user's endpoint."""
    if os.name == "nt":
        return None
    try:
        path = state_path()
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            return None
        data = json.loads(path.read_text())
        sock = Path(data["socket"])
        si = sock.lstat()
        if not stat.S_ISSOCK(si.st_mode) or si.st_uid != os.getuid() or si.st_mode & 0o077:
            return None
        if data.get("version") != 1 or len(data.get("token", "")) != 64:
            return None
        return data
    except (OSError, ValueError, KeyError, TypeError):
        return None


def normalize(params, tool_name):
    args = dict(params)
    if tool_name == "browser_op":
        args.setdefault("op", "snapshot")
    else:
        mapping = {"browser_navigate": ("navigate", "goto"), "browser_snapshot": ("snapshot", None),
                   "browser_get_content": ("content", "text"), "browser_close": ("close", None),
                   "browser_auth": ("auth", None)}
        if tool_name in mapping:
            op, mode = mapping[tool_name]
            args["op"] = op
            if mode:
                args.setdefault("mode", mode)
        else:
            args.setdefault("op", tool_name.removeprefix("browser_"))
    return args


def error(code, message):
    return {"success": False, "driver": "embedded", "error_code": code, "error": message}


async def request(args, owner, endpoint):
    timeout = min(45, max(1, float(args.get("timeout", 30000)) / 1000))
    rid = str(uuid.uuid4())
    message = {"id": rid, "owner": owner, "instance_id": endpoint["instance_id"],
               "token": endpoint["token"], "deadline": int((time.time() + timeout) * 1000), "params": args}
    writer = None
    sent = False
    try:
        async with asyncio.timeout(timeout + 1):
            reader, writer = await asyncio.open_unix_connection(endpoint["socket"], limit=1048576)
            wire = (json.dumps(message, ensure_ascii=False) + "\n").encode()
            if len(wire) > 1048576:
                return error("REQUEST_TOO_LARGE", "요청 크기를 줄여 주세요.")
            writer.write(wire)
            await writer.drain()
            sent = True
            reply = json.loads(await reader.readline())
            if reply.get("id") != rid:
                return error("INVALID_RESPONSE", "브라우저 응답 식별자가 일치하지 않습니다.")
            return reply["result"]
    except (TimeoutError, OSError, ValueError, KeyError, asyncio.IncompleteReadError):
        result = error("BROWSER_UNAVAILABLE", "내장 브라우저 연결이 끊겼습니다. 앱과 탭 상태를 확인하세요.")
        result["outcome_unknown"] = sent and args.get("op") not in {"snapshot", "content", "google_results", "status"}
        return result
    finally:
        if writer:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass


async def route(params, tool_name, owner, is_owner, chrome_connected):
    """Return (resolved driver, embedded result or None). Pin each task, including auto."""
    args = normalize(params, tool_name)
    explicit = args.get("driver", "auto")
    prior = _choices.get(owner)
    if explicit not in {"auto", "embedded", "playwright", "chrome"}:
        return explicit, error("INVALID_DRIVER", "지원하지 않는 브라우저 드라이버입니다.")
    if prior and explicit not in {"auto", prior[0]}:
        return prior[0], error("DRIVER_PINNED", "현재 작업의 브라우저를 먼저 close한 뒤 전환하세요.")
    if args.get("op") == "chrome" or tool_name.startswith("browser_chrome_"):
        if prior and prior[0] == "embedded":
            return "embedded", error("UNSUPPORTED_OPERATION", "내장 작업을 close한 뒤 Chrome을 연결하세요.")
        return "chrome", None
    endpoint = await asyncio.to_thread(connection) if is_owner and explicit in {"auto", "embedded"} else None
    # Recheck after endpoint IO: concurrent first calls must share one driver decision.
    prior = _choices.get(owner)
    if prior and explicit not in {"auto", prior[0]}:
        return prior[0], error("DRIVER_PINNED", "현재 작업을 close한 뒤 전환하세요.")
    driver = prior[0] if prior else explicit
    if driver == "auto":
        driver = "embedded" if endpoint and supported(args) else "chrome" if chrome_connected else "playwright"
    if driver == "embedded":
        if not is_owner:
            return driver, error("FORBIDDEN", "내장 브라우저는 소유자 작업에서만 사용할 수 있습니다.")
        if not supported(args):
            return driver, error("UNSUPPORTED_OPERATION", "이 동작/옵션은 내장 브라우저에서 지원하지 않습니다.")
        if args.get("op") == "close":
            _choices.pop(owner, None)
        if not endpoint:
            return driver, error("BROWSER_UNAVAILABLE", "데스크톱 앱을 실행해 내장 브라우저를 연결하세요.")
        if prior and prior[1] != endpoint["instance_id"] and args.get("op") != "close":
            return driver, error("BROWSER_RESTARTED", "앱이 재기동됐습니다. close 후 새 탭에서 다시 시작하세요.")
        if args.get("op") != "close":
            _choices[owner] = (driver, endpoint["instance_id"])
        return driver, await request(args, owner, endpoint)
    if args.get("op") == "auth":
        return driver, error("UNSUPPORTED_OPERATION", "auth는 내장 브라우저에서만 지원합니다.")
    if args.get("op") == "close":
        _choices.pop(owner, None)
    else:
        _choices[owner] = (driver, None)
    return driver, None


async def browser_auth(params):
    """Legacy direct dispatch cannot bypass task identity routing."""
    return error("AUTH_CONTEXT_REQUIRED", "auth는 browser_op의 작업 문맥에서 실행하세요.")
