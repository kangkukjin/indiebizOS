"""
안드로이드 폰 화면 조작 핸들러 (얇은 센터피스)

2026-06-05 부활: 옛 45개 bespoke 액션을 폐기하고, computer-use/desktop(limbs:screen)과
같은 결의 단일 op 액션 [limbs:android]{op} 하나로 재설계.
핵심 원칙: snapshot(화면 독해)으로 요소를 읽고 → ref/좌표로 탭 (눈대중 좌표 금지).
SMS/통화/연락처 등 구조화 기능은 백업(data/packages/_archive/)에 보존, 추후 선별 부활.

표준 ToolContext 시그니처 + _OP_DISPATCHERS (radio 패턴, --check 삼각 검증 대상).
"""

import sys
from pathlib import Path

_current_dir = Path(__file__).parent
if str(_current_dir) not in sys.path:
    sys.path.insert(0, str(_current_dir))

import ui_control as _ui


# 2026-06-05 dispatcher 표준 — src.ops.values 와 AST 정확 비교 대상.
_OP_DISPATCHERS = {
    "android_op": {
        "snapshot": None,
        "tap": None,
        "type": None,
        "swipe": None,
        "key": None,
        "long_press": None,
        "open_app": None,
    },
    # 2026-06-06 폰 컴패니언 sense 피드 ([sense:phone]). limbs:android(제어)와
    # 짝을 이루는 입력측 — 폰 에이전트가 NIP-17로 보낸 알림/위치/걸음을 읽는다.
    # raw ADB dumpsys 우회 대신 이 액션이 "지금 폰에 오는 연락"의 정답 소스.
    "phone_op": {
        "notifications": None,
        "location": None,
        "steps": None,
    },
}
_OP_DEFAULTS = {"android_op": "snapshot", "phone_op": "notifications"}


def _snapshot(tool_input: dict) -> dict:
    """화면 독해 — 누를 수 있는/의미 있는 요소를 라벨+좌표로 반환 (탭 전 필수).

    limbs:screen 의 snapshot 데스크톱판. uiautomator dump → 요소를 ref 번호와 함께 제공.
    AI는 라벨을 보고 tap{query} 또는 tap{x,y} 로 누른다.
    """
    device_id = tool_input.get("device_id")
    elements = _ui._parse_ui_elements(device_id)
    if not elements:
        return {
            "success": False,
            "message": "화면 독해 실패 (uiautomator dump 비었음). 애니메이션 중이면 잠시 후 다시 snapshot.",
        }

    out = []
    for el in elements:
        label = (el.get("text") or "").strip() or (el.get("content_desc") or "").strip()
        rid = el.get("resource_id", "") or ""
        cls = el.get("class", "") or ""
        clickable = bool(el.get("clickable"))
        is_input = ("edit" in cls.lower()) or ("edit" in rid.lower())
        # 의미 없는 요소(라벨 없고 클릭 불가하고 입력칸도 아님)는 노이즈라 제외
        if not (clickable or label or is_input):
            continue
        center = el.get("center")
        if not center:
            continue
        out.append({
            "ref": len(out),
            "label": label,
            "id": rid.split("/")[-1] if rid else "",
            "class": cls,
            "clickable": clickable,
            "input": is_input,
            "x": center["x"],
            "y": center["y"],
        })

    return {
        "success": True,
        "count": len(out),
        "elements": out,
        "hint": "tap은 query(라벨/id 일부)로 누르는 게 가장 견고. 또는 위 x,y 사용. "
                "입력 후 전송류 버튼은 동적 생성되니 type 다음 반드시 snapshot 재실행.",
    }


def _swipe(tool_input: dict) -> dict:
    """방향(direction) 또는 좌표(x1,y1,x2,y2)로 스와이프/스크롤."""
    device_id = tool_input.get("device_id")
    direction = (tool_input.get("direction") or "").strip().lower()

    if direction:
        info = _ui.get_screen_info(device_id)
        if not info.get("success"):
            return info
        w, h = info.get("width", 1080), info.get("height", 2400)
        cx, cy = w // 2, h // 2
        dx, dy = int(w * 0.35), int(h * 0.35)
        # 스크롤 방향과 스와이프 방향: "down"=아래로 스크롤=손가락 위로
        moves = {
            "down": (cx, cy + dy, cx, cy - dy),
            "up": (cx, cy - dy, cx, cy + dy),
            "left": (cx + dx, cy, cx - dx, cy),
            "right": (cx - dx, cy, cx + dx, cy),
        }
        if direction not in moves:
            return {"success": False, "message": f"알 수 없는 direction '{direction}'. up/down/left/right."}
        x1, y1, x2, y2 = moves[direction]
        return _ui.swipe(x1, y1, x2, y2, tool_input.get("duration_ms", 300), device_id)

    # 좌표 기반
    try:
        x1 = int(tool_input["x1"]); y1 = int(tool_input["y1"])
        x2 = int(tool_input["x2"]); y2 = int(tool_input["y2"])
    except (KeyError, TypeError, ValueError):
        return {"success": False, "message": "swipe엔 direction(up/down/left/right) 또는 x1,y1,x2,y2 필요."}
    return _ui.swipe(x1, y1, x2, y2, tool_input.get("duration_ms", 300), device_id)


def _phone(tool_input: dict) -> dict:
    """폰 컴패니언 sense 피드 조회 ([sense:phone]). op: notifications/location/steps.

    폰 에이전트(NotificationListenerService)가 NIP-17 DM 으로 보내 60초마다 폴링·저장된
    데이터를 읽는다 (backend/phone_notifications.py). USB-ADB 불필요 — 폰이 켜져 있고
    컴패니언 앱이 살아 있기만 하면 됨. "지금 폰에 연락/알림 오나"의 정답 소스.
    """
    import time as _time
    try:
        import phone_notifications as _pn
    except Exception as e:
        return {"success": False, "error": f"phone_notifications 모듈 로드 실패: {e}"}

    op = (tool_input.get("op") or _OP_DEFAULTS["phone_op"]).strip()
    limit = int(tool_input.get("limit", 20))
    now_ms = int(_time.time() * 1000)

    def _ago(ts):
        try:
            v = int(ts or 0)
        except (TypeError, ValueError):
            return "?"
        if not v:
            return "?"
        if v < 1_000_000_000_000:  # 초 단위로 들어온 값 방어 (혼합 단위)
            v *= 1000
        mins = max(0, (now_ms - v) // 60000)
        if mins < 1:
            return "방금"
        if mins < 60:
            return f"{mins}분 전"
        if mins < 1440:
            return f"{mins // 60}시간 전"
        return f"{mins // 1440}일 전"

    if op == "notifications":
        pkg = tool_input.get("pkg") or tool_input.get("package_name")
        rows = _pn.recent(limit=limit, pkg=pkg)
        items = []
        for r in rows:
            ts = r.get("posted_at") or r.get("received_at") or 0
            items.append({
                "pkg": r.get("pkg"),
                "title": r.get("title"),
                "body": r.get("body"),
                "ago": _ago(ts),
                "posted_at": ts,
            })
        latest_ago = items[0]["ago"] if items else None
        return {
            "success": True,
            "count": len(items),
            "latest_ago": latest_ago,
            "notifications": items,
            "hint": "ago='방금'/'N분 전'이면 방금 온 연락. 가장 최근이 수시간/수일 전이면 지금 오는 연락은 없음.",
        }

    if op == "location":
        rows = _pn.recent_locations(limit=limit)
        for r in rows:
            r["ago"] = _ago(r.get("captured_at") or r.get("received_at"))
        return {"success": True, "count": len(rows), "locations": rows}

    if op == "steps":
        rows = _pn.recent_steps(limit=limit)
        return {"success": True, "count": len(rows), "steps": rows}

    return {
        "success": False,
        "error": f"알 수 없는 op '{op}'. 사용 가능: notifications/location/steps",
    }


def execute(tool_input: dict, context) -> dict:
    """ToolContext 기반 표준 시그니처. limbs:android(제어) + sense:phone(컴패니언 피드) 디스패처."""
    tool_name = context.tool_name
    if tool_name == "phone_op":
        return _phone(tool_input)
    if tool_name != "android_op":
        raise ValueError(f"Unknown tool: {tool_name}")

    op = (tool_input.get("op") or _OP_DEFAULTS["android_op"]).strip()
    device_id = tool_input.get("device_id")

    if op == "snapshot":
        return _snapshot(tool_input)

    if op == "tap":
        query = tool_input.get("query")
        if query:
            return _ui.find_and_tap(query, tool_input.get("index", 0), device_id)
        x, y = tool_input.get("x"), tool_input.get("y")
        if x is None or y is None:
            return {"success": False, "message": "tap엔 query(요소 라벨/id 일부) 또는 x,y 좌표가 필요합니다."}
        return _ui.tap(int(x), int(y), device_id)

    if op == "long_press":
        x, y = tool_input.get("x"), tool_input.get("y")
        if x is None or y is None:
            return {"success": False, "message": "long_press엔 x,y 좌표가 필요합니다."}
        return _ui.long_press(int(x), int(y), tool_input.get("duration_ms", 1000), device_id)

    if op == "type":
        return _ui.type_text(tool_input.get("text", ""), device_id)

    if op == "swipe":
        return _swipe(tool_input)

    if op == "key":
        return _ui.press_key(tool_input.get("key") or tool_input.get("keycode", ""), device_id)

    if op == "open_app":
        pkg = tool_input.get("package_name") or tool_input.get("package", "")
        return _ui.open_app(pkg, device_id)

    return {
        "success": False,
        "error": f"알 수 없는 op '{op}'. 사용 가능: snapshot/tap/type/swipe/key/long_press/open_app",
    }
