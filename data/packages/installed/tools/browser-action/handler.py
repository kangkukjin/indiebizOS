"""
browser-action 패키지 핸들러
내장 Electron + Playwright + Chrome MCP 드라이버 브라우저 자동화 도구

Version: 6.0.0
"""

import json
import hashlib
import os
import sys
from pathlib import Path

_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.pkg_utils import load_singleton

current_dir = Path(__file__).parent

# 모듈 캐싱 (BrowserSession 싱글톤 유지를 위해 필수)
_module_cache = {}


def _load(module_name):
    """같은 디렉토리의 모듈을 캐싱하여 로드.

    형제 모듈들이 서로를 `import browser_session` 식으로 참조하므로 sys.modules 등록이
    필요하다 — 그 등록의 레이스 안전은 common/pkg_utils.load_singleton 이 맡는다
    (반쯤 실행된 모듈이 동시 호출자에게 넘어가던 부류의 수리).
    """
    if module_name in _module_cache:
        return _module_cache[module_name]

    # browser_session을 먼저 로드하여 다른 모듈에서 import 가능하게 설정
    if module_name != "browser_session" and "browser_session" not in _module_cache:
        _load("browser_session")

    if module_name in {"browser_content", "browser_chrome"}:
        _load("browser_paths")
    module = load_singleton(__file__, module_name)
    _module_cache[module_name] = module
    return module


def _is_chrome_connected() -> bool:
    """Chrome MCP 드라이버 연결 상태 확인"""
    try:
        mod = _load("browser_chrome")
        driver = mod.ChromeMCPDriver.get_instance()
        return driver.is_connected()
    except Exception:
        return False


# Chrome 전용 도구 (Playwright에 없는 것들)
_CHROME_ONLY_TOOLS = {
    "browser_chrome_connect":    ("browser_chrome", "browser_chrome_connect", False),
    "browser_chrome_disconnect": ("browser_chrome", "browser_chrome_disconnect", False),
    "browser_chrome_status":     ("browser_chrome", "browser_chrome_status", False),
    "browser_find":              ("browser_chrome", "browser_find", False),
}

# Chrome 드라이버에서 project_path가 필요한 도구들
_CHROME_PROJECT_TOOLS = {"browser_navigate", "browser_screenshot", "browser_save_pdf", "browser_vision",
                         "browser_cookies_save", "browser_cookies_load"}

# 도구 이름 → (모듈명, 함수명, project_path 필요 여부) — Playwright용
_TOOL_ROUTING = {
    "browser_auth": ("browser_embedded", "browser_auth", False),
    # 네비게이션
    "browser_navigate":         ("browser_navigate", "browser_navigate", True),
    "browser_navigate_back":    ("browser_navigate", "browser_navigate_back", False),
    "browser_navigate_forward": ("browser_navigate", "browser_navigate_forward", False),

    # 스냅샷
    "browser_snapshot":         ("browser_snapshot", "browser_snapshot", False),

    # 상호작용
    "browser_click":            ("browser_interact", "browser_click", False),
    "browser_dblclick":         ("browser_interact", "browser_dblclick", False),
    "browser_rightclick":       ("browser_interact", "browser_rightclick", False),
    "browser_type":             ("browser_interact", "browser_type", False),
    "browser_select_option":    ("browser_interact", "browser_select_option", False),
    "browser_check":            ("browser_interact", "browser_check", False),
    "browser_hover":            ("browser_interact", "browser_hover", False),
    "browser_drag":             ("browser_interact", "browser_drag", False),
    "browser_press_key":        ("browser_interact", "browser_press_key", False),
    "browser_upload_file":      ("browser_interact", "browser_upload_file", False),

    # 콘텐츠 및 출력
    "browser_scroll":           ("browser_content", "browser_scroll", False),
    "browser_wait_for":         ("browser_content", "browser_wait_for", False),
    "browser_screenshot":       ("browser_content", "browser_screenshot", True),
    "browser_get_content":      ("browser_content", "browser_get_content", False),
    "browser_get_html":         ("browser_content", "browser_get_html", False),
    "browser_console_logs":     ("browser_content", "browser_console_logs", False),
    "browser_network_logs":     ("browser_content", "browser_network_logs", False),
    "browser_dialog_info":      ("browser_content", "browser_dialog_info", False),
    "browser_save_pdf":         ("browser_content", "browser_save_pdf", True),
    "browser_evaluate":         ("browser_content", "browser_evaluate", False),
    "browser_resize":           ("browser_content", "browser_resize", False),
    "browser_vision":           ("browser_content", "browser_vision", True),
    "browser_close":            ("browser_content", "browser_close", False),

    # 탭/iframe 관리
    "browser_tab_list":         ("browser_tabs", "browser_tab_list", False),
    "browser_tab_new":          ("browser_tabs", "browser_tab_new", False),
    "browser_tab_switch":       ("browser_tabs", "browser_tab_switch", False),
    "browser_tab_close":        ("browser_tabs", "browser_tab_close", False),
    "browser_iframe_list":      ("browser_tabs", "browser_iframe_list", False),
    "browser_iframe_switch":    ("browser_tabs", "browser_iframe_switch", False),
    "browser_iframe_reset":     ("browser_tabs", "browser_iframe_reset", False),

    # 쿠키/인증 상태
    "browser_cookies_save":     ("browser_storage", "browser_cookies_save", True),
    "browser_cookies_load":     ("browser_storage", "browser_cookies_load", True),
}


# 2026-05-27 단일 액션 통합: [limbs:tab|iframe|cookies|chrome|click|navigate|content|logs]{op}
# 디스패처 도구는 _TOOL_ROUTING의 실제 도구로 op 분기
_OP_DISPATCHERS = {
    "browser_tab_op": {
        "list": "browser_tab_list",
        "new": "browser_tab_new",
        "switch": "browser_tab_switch",
        "close": "browser_tab_close",
    },
    "browser_iframe_op": {
        "list": "browser_iframe_list",
        "switch": "browser_iframe_switch",
        "reset": "browser_iframe_reset",
    },
    "browser_cookies_op": {
        "save": "browser_cookies_save",
        "load": "browser_cookies_load",
    },
    "browser_chrome_op": {
        "connect": "browser_chrome_connect",
        "disconnect": "browser_chrome_disconnect",
        "status": "browser_chrome_status",
    },
    # limbs 라운드 2 (2026-05-27)
    "browser_click_op": {
        "single": "browser_click",
        "double": "browser_dblclick",
        "right": "browser_rightclick",
    },
    "browser_navigate_op": {
        "goto": "browser_navigate",
        "back": "browser_navigate_back",
        "forward": "browser_navigate_forward",
    },
    "browser_content_op": {
        "text": "browser_get_content",
        "html": "browser_get_html",
    },
    "browser_logs_op": {
        "console": "browser_console_logs",
        "network": "browser_network_logs",
    },
    # 2026-06-04 모달리티 통합: [limbs:browser]{op: <동작>} 단일 액션.
    # op = 26개 동작. 단순 동작 → 내부 도구, 복합 동작 → 위 *_op 디스패처(2차 mode 분기).
    "browser_op": {
        "snapshot": "browser_snapshot",
        "auth": "browser_auth",
        "navigate": "browser_navigate_op",
        "click": "browser_click_op",
        "type": "browser_type",
        "press_key": "browser_press_key",
        "hover": "browser_hover",
        "drag": "browser_drag",
        "select": "browser_select_option",
        "check": "browser_check",
        "upload_file": "browser_upload_file",
        "scroll": "browser_scroll",
        "wait": "browser_wait_for",
        "content": "browser_content_op",
        "screenshot": "browser_screenshot",
        "vision": "browser_vision",
        "evaluate": "browser_evaluate",
        "pdf": "browser_save_pdf",
        "find": "browser_find",
        "logs": "browser_logs_op",
        "dialog_info": "browser_dialog_info",
        "resize": "browser_resize",
        "close": "browser_close",
        "tab": "browser_tab_op",
        "iframe": "browser_iframe_op",
        "cookies": "browser_cookies_op",
        "chrome": "browser_chrome_op",
    },
}

# 디스패처별 기본값 (selector 미지정 시 — 가장 흔한 동작)
_OP_DEFAULTS = {
    "browser_op": "snapshot",
    "browser_click_op": "single",
    "browser_navigate_op": "goto",
    "browser_content_op": "text",
    "browser_logs_op": "console",
    "browser_iframe_op": "list",
}

# 디스패처가 읽는 selector 파라미터 키 (기본 "op").
# browser_op는 op(=동작)로 분기, 복합 *_op는 2차 mode로 분기 — 두 단계 키 충돌 방지.
_OP_SELECTOR = {
    "browser_navigate_op": "mode",
    "browser_click_op": "mode",
    "browser_content_op": "mode",
    "browser_logs_op": "mode",
    "browser_tab_op": "mode",
    "browser_iframe_op": "mode",
    "browser_cookies_op": "mode",
    "browser_chrome_op": "mode",
}


async def _execute(tool_input: dict, context):
    """메인 핸들러 (ToolContext 기반 신규 시그니처, async) — driver 파라미터로 Playwright/Chrome 분기"""
    tool_name = context.tool_name
    proj_path = context.project_path

    # 단일 액션 통합 디스패치 (2026-05-27, 2026-06-04 browser_op 2단계 확장).
    # browser_op는 op(=동작)로 분기 → 복합 동작은 *_op로 가서 다시 mode로 분기 (2단계 루프).
    while tool_name in _OP_DISPATCHERS:
        sel_key = _OP_SELECTOR.get(tool_name, "op")
        mapping = _OP_DISPATCHERS[tool_name]
        sel = (tool_input.pop(sel_key, "") or "").strip()
        if not sel:
            sel = _OP_DEFAULTS.get(tool_name, "")
        if not sel:
            return json.dumps({
                "success": False,
                "error": f"{sel_key} 파라미터 필요 ({tool_name}). 사용 가능: {sorted(mapping.keys())}"
            }, ensure_ascii=False)
        if sel not in mapping:
            return json.dumps({
                "success": False,
                "error": f"알 수 없는 {sel_key} '{sel}' ({tool_name}). 사용 가능: {sorted(mapping.keys())}"
            }, ensure_ascii=False)
        tool_name = mapping[sel]

    # Chrome 전용 도구는 항상 Chrome 모듈로 라우팅
    if tool_name in _CHROME_ONLY_TOOLS:
        module_name, func_name, needs_project = _CHROME_ONLY_TOOLS[tool_name]
        try:
            mod = _load(module_name)
            func = getattr(mod, func_name)
            result = await func(tool_input, proj_path) if needs_project else await func(tool_input)
            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": f"Chrome 도구 실패 ({tool_name}): {str(e)}"}, ensure_ascii=False)

    # 일반 도구: driver 파라미터로 분기
    driver = tool_input.pop("driver", "auto")

    if driver == "auto":
        driver = "chrome" if _is_chrome_connected() else "playwright"

    all_tools = {**_TOOL_ROUTING, **_CHROME_ONLY_TOOLS}
    if tool_name not in _TOOL_ROUTING and tool_name not in _CHROME_ONLY_TOOLS:
        return json.dumps({
            "success": False,
            "error": f"알 수 없는 도구: {tool_name}",
            "available_tools": list(all_tools.keys())
        }, ensure_ascii=False)

    try:
        if driver == "chrome":
            # Chrome MCP 드라이버로 라우팅
            mod = _load("browser_chrome")
            func = getattr(mod, tool_name, None)
            if func is None:
                return json.dumps({"success": False, "error_code": "UNSUPPORTED_OPERATION",
                                   "error": "Chrome에서 지원하지 않는 동작입니다. close 후 드라이버를 명시하세요."}, ensure_ascii=False)
            else:
                needs_project = tool_name in _CHROME_PROJECT_TOOLS
                result = await func(tool_input, proj_path) if needs_project else await func(tool_input)
                return json.dumps(result, ensure_ascii=False, indent=2)

        # Playwright 드라이버 (기본 또는 폴백)
        if tool_name not in _TOOL_ROUTING:
            return json.dumps({"success": False, "error": f"Playwright 드라이버에서 지원하지 않는 도구: {tool_name}"}, ensure_ascii=False)

        module_name, func_name, needs_project = _TOOL_ROUTING[tool_name]
        mod = _load(module_name)
        func = getattr(mod, func_name)

        if needs_project:
            result = await func(tool_input, proj_path)
        else:
            result = await func(tool_input)

        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"도구 실행 실패 ({tool_name}, driver={driver}): {str(e)}"
        }, ensure_ascii=False)


# ── 동작별 실행 조건 (CONTROL_DRIVER_DESIGN_2026_10_20 §6·§8) ──
# 격리는 도구가 아니라 자원 단위다. 내장 Playwright 의 전용 프로필은 화면·포커스·세션이 분리되지만
# 같은 계정으로 로그인했으면 계정 데이터는 공유다. Chrome MCP 는 사용자의 탭·세션을 그대로 쓴다 —
# 사용자와 공유하는 상태를 바꾸는 동작(shared_state)을 화면 없는 문맥(정기·배경)에서 사용자 Chrome 으로
# 보내는 것은 요청된 효과가 아니라 부수 간섭(L48-1 활성 탭 전환)이다. 그래서 auto 는 간섭 없는 통로
# (Playwright)를 먼저 고르고, Chrome 을 명시한 호출만 거절한다.
_SHARED_STATE_OPS = frozenset({
    "navigate", "click", "dblclick", "rightclick", "type", "press_key", "select", "select_option",
    "check", "hover", "drag", "upload_file", "scroll", "evaluate", "tab", "cookies", "auth", "wait", "resize",
})
_DRIVER_CONDITIONS = {
    "playwright": {"needs_front": False, "shared_state": False, "isolated_resources": ["screen", "focus", "session"]},
    "embedded":   {"needs_front": False, "shared_state": False, "isolated_resources": ["screen", "focus", "session"]},
    "chrome":     {"needs_front": False, "shared_state": True,  "isolated_resources": []},
}


def _op_name(params, tool_name):
    op = params.get("op") or tool_name.removeprefix("browser_")
    return str(op).split("_", 1)[0] if str(op).startswith(("tab_", "iframe_", "cookies_", "chrome_")) else str(op)


def _screen_context():
    try:
        import control_conditions
        return control_conditions.screen_context()
    except Exception:
        return {"available": True, "origin": "unknown", "reason": None}


def _site_notice(url):
    """snapshot 의 현재 URL 도메인에 드라이버(사이트 실행 부품·관측)가 있으면 알린다(§5.2 발견 (a))."""
    try:
        from urllib.parse import urlsplit
        host = (urlsplit(str(url or "")).hostname or "").lower()
        if not host:
            return None
        from guide_registry import surface_control_guide
        found = surface_control_guide("site", host)
        if not found:
            return None
        import control_observations
        found["observations"] = control_observations.count(found["surface"])
        found["note"] = "이 사이트에는 계약 통로(드라이버·관측)가 있습니다. ref 조작 전에 control_guide 를 한 번 읽으세요."
        return found
    except Exception:
        return None


def execute(tool_input: dict, context):
    """Capture trusted identity before dispatch moves from a worker to the async loop."""
    from principal import cache_key, is_owner
    from episode_logger import current_trajectory_identity
    from thread_context import get_invocation
    trace = current_trajectory_identity()
    run = (getattr(context, "task_id", None) or trace.get("run_id")
           or (get_invocation() or {}).get("run_id") or "manual")
    identity = [cache_key(), context.project_path, getattr(context, "agent_id", None), run]
    owner = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    # 실행 문맥은 스레드 로컬이라 async 루프로 넘어가기 전에 여기서 읽는다.
    return _route_execute(dict(tool_input), context, owner, is_owner(), _screen_context())


async def _route_execute(params, context, owner, owner_allowed, screen_ctx=None):
    screen_ctx = screen_ctx or {"available": True}
    shared = _op_name(params, context.tool_name) in _SHARED_STATE_OPS
    chrome_connected = _is_chrome_connected()
    if shared and not screen_ctx.get("available"):
        if params.get("driver") == "chrome":
            import control_conditions
            refused = control_conditions.refusal(_op_name(params, context.tool_name), _DRIVER_CONDITIONS["chrome"]
                                                 | {"needs_front": True}, screen_ctx, surface="[limbs:browser] driver:chrome")
            refused["error"] = ("Chrome MCP 는 사용자의 탭·세션을 그대로 쓰므로 화면 없는 문맥(" + str(screen_ctx.get("origin"))
                                + ")에서 공유 상태를 바꾸는 동작은 부수 간섭입니다. 실행하지 않았습니다. "
                                "격리된 내장 Playwright(driver 생략 또는 playwright)를 쓰거나 사용자가 입회한 턴에서 실행하세요.")
            refused["condition"] = _DRIVER_CONDITIONS["chrome"]
            return json.dumps(refused, ensure_ascii=False)
        chrome_connected = False   # auto 는 간섭 없는 통로를 먼저 고른다
    driver, result = await load_singleton(__file__, "browser_embedded").route(
        params, context.tool_name, owner, owner_allowed, chrome_connected)
    if result is not None:
        return json.dumps(result, ensure_ascii=False)
    params["driver"] = driver
    if shared and not screen_ctx.get("available") and params.get("driver") == "auto":
        params["driver"] = "playwright"
    return await _owned_execute(params, context, owner)


async def _owned_execute(params, context, owner):
    module = _load("browser_session")
    with module.owner_scope(owner):
        session = module.BrowserSession.get_instance()
        async with session._operation_lock:
            policy = params.get("dialog", "dismiss")
            if policy not in ("accept", "dismiss"):
                return json.dumps({"success": False, "error": "dialog는 accept 또는 dismiss입니다."})
            # Chrome does not implement this policy; never silently ignore an approval request.
            driver = params.get("driver", "auto")
            chrome = driver == "chrome" or (driver == "auto" and _is_chrome_connected())
            if chrome and any(key in params for key in ("dialog", "dialog_text", "wait")):
                return json.dumps({"success": False, "error": "dialog/dialog_text/wait는 driver:playwright 전용입니다."})
            op = params.get("op", context.tool_name.removeprefix("browser_"))
            if chrome and op in {"click", "press_key", "evaluate", "type"} and "path" in params:
                return json.dumps({"success": False, "error_code": "UNSUPPORTED_OPERATION",
                                   "error": "내려받기 path 저장은 driver:playwright 전용입니다."})
            session._dialog_policy = policy
            session._dialog_text = params.get("dialog_text", "")
            session._operation_dialogs = []
            if not chrome:
                session.events.begin(params, context.project_path)
            settle = op in {
                "click", "evaluate", "type", "check", "select", "hover", "drag", "upload_file"
            } or (op == "press_key" and params.get("key") in {"Enter", "Space", " "})
            try:
                result = json.loads(await _execute(params, context))
                if op == "snapshot" and isinstance(result, dict) and result.get("url"):
                    if notice := _site_notice(result.get("url")):
                        result["control_guide"] = notice["control_guide"]
                        result["driver_surface"] = notice
                if not chrome:
                    result.setdefault("session_owner", owner)
                    result.setdefault("tab_id", session.events.before_tab or session.active_tab_id)
                    result = await session.events.finish(result, settle=settle)
                    dialogs = list(session._operation_dialogs)
                    if dialogs:
                        result["dialogs"] = dialogs
                        dismissed = any(d["action"] == "dismiss" and d["type"] in ("confirm", "prompt", "beforeunload") for d in dialogs)
                        result["dialog_dismissed"] = dismissed
                        if any(not d.get("handled") for d in dialogs) or (dismissed and "dialog" not in params):
                            result.update(success=False, error="확인창이 승인되지 않았습니다. 대상 상태를 확인하고 필요한 조작에 dialog:accept를 명시하세요.", error_code="DIALOG_NOT_ACCEPTED")
                return json.dumps(result, ensure_ascii=False)
            finally:
                session.events.destination = None
                session._dialog_policy = "dismiss"
                session._dialog_text = ""
                if session._playwright is not None:
                    session._reset_timer()
                # Weak registry keeps the same instance while queued calls hold it.
                # Closed instances without callers disappear without a timer.
