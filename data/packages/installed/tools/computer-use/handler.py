"""
computer-use 도구 패키지 핸들러
macOS 데스크톱 자동화: 스크린샷 캡처 + 마우스/키보드 제어

좌표 시스템:
- AI는 항상 1280x800 가상 좌표로 작업
- handler가 실제 화면 해상도로 자동 변환
- Retina 디스플레이 포함 모든 해상도 대응

의존성: pyautogui, Pillow
안전: pyautogui.FAILSAFE=True (마우스를 화면 모서리로 이동하면 긴급 정지)
"""

import json
import base64
import io
import re
import time
import platform
import subprocess
import tempfile
import os

# ── 상수 ──
VIRTUAL_WIDTH = 1280
VIRTUAL_HEIGHT = 800
ACTION_PAUSE = 0.1  # 액션 간 최소 딜레이 (초)
SCREENSHOT_WAIT = 0.4  # 액션 후 스크린샷 대기 (초)

# ── Lazy import (필요할 때만 로드) ──
_pyautogui = None
_Image = None


def _get_pyautogui():
    """pyautogui lazy import + 안전 설정"""
    global _pyautogui
    if _pyautogui is None:
        import pyautogui
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = ACTION_PAUSE
        _pyautogui = pyautogui
    return _pyautogui


def _get_pil_image():
    """Pillow Image lazy import"""
    global _Image
    if _Image is None:
        from PIL import Image
        _Image = Image
    return _Image


# ── 좌표 변환 ──

def _get_screen_size():
    """실제 화면 크기 반환"""
    pag = _get_pyautogui()
    return pag.size()


def _virtual_to_actual(x, y):
    """1280x800 가상 좌표 → 실제 화면 좌표"""
    aw, ah = _get_screen_size()
    return int(x * aw / VIRTUAL_WIDTH), int(y * ah / VIRTUAL_HEIGHT)


def _actual_to_virtual(x, y):
    """실제 화면 좌표 → 1280x800 가상 좌표"""
    aw, ah = _get_screen_size()
    return int(x * VIRTUAL_WIDTH / aw), int(y * VIRTUAL_HEIGHT / ah)


def _validate_coords(x, y):
    """좌표 범위 검증"""
    if not (0 <= x <= VIRTUAL_WIDTH and 0 <= y <= VIRTUAL_HEIGHT):
        raise ValueError(f"좌표 ({x},{y})가 범위를 벗어났습니다 (0~{VIRTUAL_WIDTH}, 0~{VIRTUAL_HEIGHT})")


# ── 스크린샷 캡처 ──

def _capture_screenshot(region=None):
    """화면 캡처 → 1280x800 리사이즈 → base64 반환

    Returns:
        dict: {"base64": str, "media_type": "image/png"}
    """
    Image = _get_pil_image()
    tmp_path = os.path.join(tempfile.gettempdir(), "indiebiz_cu_screenshot.png")

    try:
        if platform.system() == "Darwin":
            # macOS: screencapture (Retina 대응)
            if region:
                ax, ay = _virtual_to_actual(region["x"], region["y"])
                aw = int(region["width"] * _get_screen_size()[0] / VIRTUAL_WIDTH)
                ah = int(region["height"] * _get_screen_size()[1] / VIRTUAL_HEIGHT)
                r = subprocess.run(
                    ["screencapture", "-x", "-R", f"{ax},{ay},{aw},{ah}", tmp_path],
                    capture_output=True, timeout=5
                )
            else:
                r = subprocess.run(
                    ["screencapture", "-x", tmp_path],
                    capture_output=True, timeout=5
                )

            if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) < 100:
                raise PermissionError(
                    "스크린샷 캡처 실패. 시스템 환경설정 > 개인정보 보호 > 화면 기록에서 "
                    "Python(또는 터미널 앱)에 권한을 부여하세요."
                )
            img = Image.open(tmp_path)
        else:
            # Windows/Linux
            from PIL import ImageGrab
            img = ImageGrab.grab()

        # 1280x800으로 리사이즈
        img_resized = img.resize((VIRTUAL_WIDTH, VIRTUAL_HEIGHT), Image.LANCZOS)

        # base64 변환
        buffer = io.BytesIO()
        img_resized.save(buffer, format="PNG", optimize=True)
        b64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")

        return {"base64": b64_data, "media_type": "image/png"}

    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _make_image_result(text, img_data, extra_details=None):
    """이미지를 포함한 도구 결과 생성

    Args:
        text: AI에게 보낼 텍스트 설명
        img_data: _capture_screenshot() 반환값
        extra_details: UI용 추가 정보

    Returns:
        dict: {"content": str, "images": list, "details": dict}
    """
    details = {"resolution": f"{VIRTUAL_WIDTH}x{VIRTUAL_HEIGHT}"}
    if extra_details:
        details.update(extra_details)

    return {
        "content": text,
        "images": [img_data],
        "details": details
    }


# ── 도구 구현 ──

def _do_screenshot(tool_input):
    """computer_screenshot: 화면 캡처"""
    region = tool_input.get("region")
    img_data = _capture_screenshot(region)

    text = f"현재 화면 스크린샷입니다 ({VIRTUAL_WIDTH}x{VIRTUAL_HEIGHT}). 이미지를 분석하여 UI 요소의 위치를 파악하세요."
    return _make_image_result(text, img_data, {
        "actual_resolution": f"{_get_screen_size()[0]}x{_get_screen_size()[1]}",
        "has_region": region is not None
    })


def _click_by_ref(ref, tool_input):
    """ref 기반 클릭 — AXPress(좌표 0) → stale 재탐색 → center 좌표 폴백."""
    info = _AX_SESSION.get(ref)
    if not info:
        return json.dumps({
            "success": False,
            "error": f"알 수 없는 ref: {ref}. [limbs:screen]{{op:\"snapshot\"}}을 먼저 호출하세요.",
        }, ensure_ascii=False)

    method = None
    if _ax_press(info["el"]):
        method = "AXPress"
    else:
        el2 = _ax_refind(info.get("pid"), info.get("role"), info.get("title"))
        if el2 is not None and _ax_press(el2):
            method = "AXPress(재탐색)"

    if method:
        if tool_input.get("screenshot_after", False):
            try:
                time.sleep(SCREENSHOT_WAIT)
                return _make_image_result(
                    f"ref {ref}({info.get('title')}) {method} 완료. 클릭 후 화면:",
                    _capture_screenshot(), {"action": "click", "ref": ref, "method": method})
            except Exception:
                pass
        return json.dumps({"success": True, "action": "click", "ref": ref,
                           "title": info.get("title"), "method": method}, ensure_ascii=False)

    # 폴백: 저장된 center 좌표로 일반 클릭
    if info.get("center"):
        ti = dict(tool_input)
        ti["x"], ti["y"] = info["center"]
        ti.pop("ref", None)
        return _do_click(ti)
    return json.dumps({
        "success": False,
        "error": f"ref {ref} 클릭 실패 (AXPress 미지원 + 좌표 없음). center 있는 다른 요소나 OCR 좌표 사용.",
    }, ensure_ascii=False)


def _do_click(tool_input):
    """computer_click: 요소 ref(좌표 0) 우선, 없으면 가상좌표(x,y)."""
    ref = (tool_input.get("ref") or "").strip()
    if ref:
        return _click_by_ref(ref, tool_input)
    pag = _get_pyautogui()
    vx, vy = tool_input["x"], tool_input["y"]
    button = tool_input.get("button", "left")
    clicks = tool_input.get("clicks", 1)
    screenshot_after = tool_input.get("screenshot_after", True)

    _validate_coords(vx, vy)
    ax, ay = _virtual_to_actual(vx, vy)
    pag.click(ax, ay, clicks=clicks, button=button)

    action_desc = f"({vx},{vy}) {button}클릭" + (f" x{clicks}" if clicks > 1 else "")

    if screenshot_after:
        time.sleep(SCREENSHOT_WAIT)
        img_data = _capture_screenshot()
        return _make_image_result(
            f"{action_desc} 완료. 클릭 후 화면:",
            img_data,
            {"action": "click", "virtual": {"x": vx, "y": vy}}
        )

    return json.dumps({"success": True, "action": "click", "virtual": {"x": vx, "y": vy}}, ensure_ascii=False)


def _do_type(tool_input):
    """computer_type: 입력칸 ref면 AXValue 직접 설정(좌표 0), 아니면 현재 포커스에 키 입력."""
    ref = (tool_input.get("ref") or "").strip()
    if ref:
        info = _AX_SESSION.get(ref)
        if info:
            if _ax_set_value(info["el"], tool_input.get("text", "")):
                return json.dumps({"success": True, "action": "type", "ref": ref,
                                   "method": "AXValue", "length": len(tool_input.get("text", ""))},
                                  ensure_ascii=False)
            # 폴백: 요소를 눌러 포커스 후 키 입력
            if info.get("center"):
                _do_click({"x": info["center"][0], "y": info["center"][1], "screenshot_after": False})
        tool_input = dict(tool_input)
        tool_input.pop("ref", None)
    pag = _get_pyautogui()
    text = tool_input["text"]
    interval = tool_input.get("interval", 0.02)
    screenshot_after = tool_input.get("screenshot_after", False)

    # macOS에서 한글/유니코드: pbcopy + Cmd+V
    if platform.system() == "Darwin" and any(ord(c) > 127 for c in text):
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
        pag.hotkey("command", "v")
    else:
        pag.write(text, interval=interval)

    result_text = f"'{text[:50]}{'...' if len(text) > 50 else ''}' 입력 완료 ({len(text)}자)"

    if screenshot_after:
        time.sleep(SCREENSHOT_WAIT)
        img_data = _capture_screenshot()
        return _make_image_result(
            f"{result_text}. 입력 후 화면:",
            img_data,
            {"action": "type", "length": len(text)}
        )

    return json.dumps({"success": True, "action": "type", "length": len(text)}, ensure_ascii=False)


def _do_key(tool_input):
    """computer_key: 단축키/특수키"""
    pag = _get_pyautogui()
    key_combo = tool_input["key"]
    screenshot_after = tool_input.get("screenshot_after", False)

    # 키 이름 매핑
    key_map = {
        "cmd": "command", "ctrl": "control", "alt": "option",
        "win": "command", "super": "command",
        "return": "enter", "esc": "escape", "del": "delete",
    }

    parts = [key_map.get(k.strip().lower(), k.strip().lower()) for k in key_combo.split("+")]

    if len(parts) == 1:
        pag.press(parts[0])
    else:
        pag.hotkey(*parts)

    result_text = f"키 입력: {key_combo}"

    if screenshot_after:
        time.sleep(SCREENSHOT_WAIT)
        img_data = _capture_screenshot()
        return _make_image_result(
            f"{result_text}. 키 입력 후 화면:",
            img_data,
            {"action": "key", "key": key_combo}
        )

    return json.dumps({"success": True, "action": "key", "key": key_combo}, ensure_ascii=False)


def _do_mouse_move(tool_input):
    """computer_mouse_move: 마우스 이동"""
    pag = _get_pyautogui()
    vx, vy = tool_input["x"], tool_input["y"]
    duration = tool_input.get("duration", 0.3)

    _validate_coords(vx, vy)
    ax, ay = _virtual_to_actual(vx, vy)
    pag.moveTo(ax, ay, duration=duration)

    return json.dumps({"success": True, "action": "move", "virtual": {"x": vx, "y": vy}}, ensure_ascii=False)


def _do_drag(tool_input):
    """computer_drag: 마우스 드래그"""
    pag = _get_pyautogui()
    sx, sy = tool_input["start_x"], tool_input["start_y"]
    ex, ey = tool_input["end_x"], tool_input["end_y"]
    duration = tool_input.get("duration", 0.5)
    button = tool_input.get("button", "left")
    screenshot_after = tool_input.get("screenshot_after", True)

    _validate_coords(sx, sy)
    _validate_coords(ex, ey)

    asx, asy = _virtual_to_actual(sx, sy)
    aex, aey = _virtual_to_actual(ex, ey)

    pag.moveTo(asx, asy, duration=0.1)
    pag.drag(aex - asx, aey - asy, duration=duration, button=button)

    action_desc = f"({sx},{sy}) → ({ex},{ey}) 드래그"

    if screenshot_after:
        time.sleep(SCREENSHOT_WAIT)
        img_data = _capture_screenshot()
        return _make_image_result(
            f"{action_desc} 완료. 드래그 후 화면:",
            img_data,
            {"action": "drag", "from": {"x": sx, "y": sy}, "to": {"x": ex, "y": ey}}
        )

    return json.dumps({"success": True, "action": "drag"}, ensure_ascii=False)


def _do_scroll(tool_input):
    """computer_scroll: 스크롤"""
    pag = _get_pyautogui()
    direction = tool_input.get("direction", "down")
    amount = tool_input.get("amount", 3)
    screenshot_after = tool_input.get("screenshot_after", True)

    # 위치 지정이 있으면 이동
    vx = tool_input.get("x")
    vy = tool_input.get("y")
    if vx is not None and vy is not None:
        _validate_coords(vx, vy)
        ax, ay = _virtual_to_actual(vx, vy)
        pag.moveTo(ax, ay, duration=0.1)

    # 스크롤 실행
    if direction == "up":
        pag.scroll(amount)
    elif direction == "down":
        pag.scroll(-amount)
    elif direction == "left":
        pag.hscroll(-amount)
    elif direction == "right":
        pag.hscroll(amount)

    action_desc = f"{direction} 방향으로 {amount}칸 스크롤"

    if screenshot_after:
        time.sleep(SCREENSHOT_WAIT)
        img_data = _capture_screenshot()
        return _make_image_result(
            f"{action_desc} 완료. 스크롤 후 화면:",
            img_data,
            {"action": "scroll", "direction": direction, "amount": amount}
        )

    return json.dumps({"success": True, "action": "scroll", "direction": direction, "amount": amount}, ensure_ascii=False)


def _do_cursor_position(tool_input):
    """computer_cursor_position: 현재 커서 위치"""
    pag = _get_pyautogui()
    ax, ay = pag.position()
    vx, vy = _actual_to_virtual(ax, ay)

    return json.dumps({
        "success": True,
        "virtual": {"x": vx, "y": vy},
        "actual": {"x": ax, "y": ay}
    }, ensure_ascii=False)


def _do_screen_info(tool_input):
    """computer_screen_info: 화면 정보 + 권한 확인"""
    aw, ah = _get_screen_size()

    info = {
        "success": True,
        "virtual_resolution": {"width": VIRTUAL_WIDTH, "height": VIRTUAL_HEIGHT},
        "actual_resolution": {"width": aw, "height": ah},
        "scale_factor": round(aw / VIRTUAL_WIDTH, 2),
        "platform": platform.system(),
        "failsafe": "마우스를 화면 모서리로 이동하면 긴급 정지됩니다"
    }

    # macOS 권한 체크
    if platform.system() == "Darwin":
        # 스크린샷 권한 테스트
        try:
            tmp = os.path.join(tempfile.gettempdir(), "indiebiz_cu_test.png")
            r = subprocess.run(["screencapture", "-x", tmp], capture_output=True, timeout=3)
            if os.path.exists(tmp):
                size = os.path.getsize(tmp)
                os.unlink(tmp)
                info["screenshot_permission"] = "OK" if size > 100 else "화면 기록 권한 필요"
            else:
                info["screenshot_permission"] = "화면 기록 권한 필요"
        except Exception:
            info["screenshot_permission"] = "확인 불가"

        info["note"] = "시스템 환경설정 > 개인정보 보호 > 화면 기록 & 손쉬운 사용에서 Python에 권한을 부여하세요"

    return json.dumps(info, ensure_ascii=False, indent=2)


# ── 화면 독해 (snapshot): AX 접근성 트리(구조) + Vision OCR(글자) ──
# 브라우저 snapshot의 데스크톱 판. 좌표는 click과 같은 1280x800 가상공간으로 통일.

_AX_ROLES = {
    "AXButton", "AXTextField", "AXTextArea", "AXCheckBox", "AXRadioButton",
    "AXMenuItem", "AXMenuButton", "AXPopUpButton", "AXLink", "AXStaticText",
    "AXTab", "AXSlider", "AXComboBox",
}

# snapshot이 부여한 ref → AX 요소 핸들 (브라우저 세션과 동형, 호출 간 유지).
# 좌표 없이 요소를 직접 누르기/입력하기 위한 저장소. snapshot마다 초기화.
_AX_SESSION = {}


def _ax_press(el):
    """좌표 없이 요소를 누름 (AXPress). 브라우저 locator.click()의 데스크톱 판."""
    from ApplicationServices import AXUIElementPerformAction
    try:
        return AXUIElementPerformAction(el, "AXPress") == 0
    except Exception:
        return False


def _ax_set_value(el, text):
    """좌표 없이 입력칸에 값 직접 설정 (AXValue)."""
    from ApplicationServices import AXUIElementSetAttributeValue
    try:
        return AXUIElementSetAttributeValue(el, "AXValue", text) == 0
    except Exception:
        return False


def _ax_refind(pid, role, title):
    """role+title 로 AX 요소 재탐색 (핸들 stale 대응 — 브라우저 stale-ref 처리와 동일 취지)."""
    if not (pid and title):
        return None
    from ApplicationServices import AXUIElementCreateApplication, AXUIElementCopyAttributeValue
    app = AXUIElementCreateApplication(pid)
    found = [None]

    def attr(el, name):
        try:
            err, val = AXUIElementCopyAttributeValue(el, name, None)
            return val if err == 0 else None
        except Exception:
            return None

    def walk(el, depth):
        if found[0] is not None or depth > 18:
            return
        if attr(el, "AXRole") == role and (attr(el, "AXTitle") or attr(el, "AXDescription")) == title:
            found[0] = el
            return
        for k in (attr(el, "AXChildren") or []):
            walk(k, depth + 1)

    walk(app, 0)
    return found[0]


def _frontmost_app():
    from AppKit import NSWorkspace
    a = NSWorkspace.sharedWorkspace().frontmostApplication()
    return {"name": a.localizedName(), "pid": int(a.processIdentifier())}


def _ax_elements(pid, max_elems=80, max_depth=18):
    """활성 앱의 AX 접근성 트리 → [{role,title,value,center(가상좌표)}]."""
    from ApplicationServices import (
        AXUIElementCreateApplication, AXUIElementCopyAttributeValue, AXValueGetValue,
    )
    out = []
    app = AXUIElementCreateApplication(pid)

    def attr(el, name):
        try:
            err, val = AXUIElementCopyAttributeValue(el, name, None)
            return val if err == 0 else None
        except Exception:
            return None

    def pt(axval, is_size=False):
        """AXValue(CGPoint/CGSize) → (a,b). AXValueGetValue 우선, 실패 시 repr 파싱 폴백."""
        if axval is None:
            return None
        try:
            ok, s = AXValueGetValue(axval, 2 if is_size else 1, None)
            if ok:
                return (float(s.width), float(s.height)) if is_size else (float(s.x), float(s.y))
        except Exception:
            pass
        # 폴백: "<AXValue ... {value = x:100.0 y:200.0 ...}>" / "w:.. h:.." 파싱
        m = re.search(r'w:(-?[\d.]+)\s+h:(-?[\d.]+)' if is_size
                      else r'x:(-?[\d.]+)\s+y:(-?[\d.]+)', str(axval))
        return (float(m.group(1)), float(m.group(2))) if m else None

    def walk(el, depth):
        if len(out) >= max_elems or depth > max_depth:
            return
        role = attr(el, "AXRole")
        title = attr(el, "AXTitle") or attr(el, "AXDescription")
        value = attr(el, "AXValue")
        if isinstance(value, str) and len(value) > 80:
            value = value[:80] + "…"
        if role in _AX_ROLES and (title or (isinstance(value, str) and value)):
            pos = pt(attr(el, "AXPosition"), False)
            sz = pt(attr(el, "AXSize"), True)
            center = None
            if pos and sz:
                center = list(_actual_to_virtual(pos[0] + sz[0] / 2, pos[1] + sz[1] / 2))
            t = title if isinstance(title, str) else None
            ref = f"e{len(_AX_SESSION)}"
            _AX_SESSION[ref] = {"el": el, "pid": pid, "role": role, "title": t, "center": center}
            out.append({
                "ref": ref,
                "role": role,
                "title": t,
                "value": value if isinstance(value, str) else None,
                "center": center,
            })
        for k in (attr(el, "AXChildren") or []):
            walk(k, depth + 1)

    walk(app, 0)
    return out


def _ocr_lines(png_path, langs=("ko-KR", "en-US"), limit=120):
    """Vision OCR → [{text,center(가상좌표),conf}]. 정규화 bbox를 1280x800으로 직접 매핑."""
    import Quartz
    import Vision
    from Cocoa import NSURL
    src = Quartz.CGImageSourceCreateWithURL(NSURL.fileURLWithPath_(png_path), None)
    cg = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLanguages_(list(langs))
    req.setRecognitionLevel_(0)          # 0=accurate
    req.setUsesLanguageCorrection_(True)
    h = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg, {})
    h.performRequests_error_([req], None)
    out = []
    for obs in (req.results() or [])[:limit]:
        cand = obs.topCandidates_(1)
        if not cand:
            continue
        bb = obs.boundingBox()           # 정규화, 좌하단 원점
        vx = (bb.origin.x + bb.size.width / 2) * VIRTUAL_WIDTH
        vy = (1 - bb.origin.y - bb.size.height / 2) * VIRTUAL_HEIGHT
        out.append({
            "text": cand[0].string(),
            "center": [round(vx), round(vy)],
            "conf": round(float(cand[0].confidence()), 2),
        })
    return out


def _capture_png():
    p = os.path.join(tempfile.gettempdir(), "indiebiz_cu_snapshot.png")
    subprocess.run(["screencapture", "-x", p], capture_output=True, timeout=8)
    if not os.path.exists(p) or os.path.getsize(p) < 100:
        raise PermissionError("화면 기록 권한 필요 (시스템 설정 > 개인정보 보호 > 화면 기록)")
    return p


def _do_snapshot(tool_input):
    """computer_snapshot: 화면 독해 — AX 구조 + OCR 글자. 요소엔 ref(좌표 없이 누르기용)."""
    _AX_SESSION.clear()  # 이전 snapshot의 ref 무효화
    result = {
        "app": None, "elements": [], "elements_note": None,
        "ocr_lines": [], "ocr_note": None,
        "resolution": f"{VIRTUAL_WIDTH}x{VIRTUAL_HEIGHT}",
        "hint": "요소는 ref로 [limbs:screen]{op:click, ref:\"e3\"} — 좌표 없이 누름(강건). "
                "OCR 글자는 ref가 없으니 center로 [limbs:screen]{op:click, x, y}.",
    }
    try:
        app = _frontmost_app()
        result["app"] = app["name"]
        try:
            els = _ax_elements(app["pid"])
            result["elements"] = els
            if not els:
                result["elements_note"] = "AX 0개 — 손쉬운 사용 권한 미부여 또는 앱 a11y 미노출. OCR 폴백."
        except Exception as e:
            result["elements_note"] = f"AX 실패: {e}"
    except Exception as e:
        result["elements_note"] = f"활성 앱 조회 실패: {e}"

    png = None
    try:
        png = _capture_png()
        result["ocr_lines"] = _ocr_lines(png)
    except Exception as e:
        result["ocr_note"] = str(e)
    finally:
        if png and os.path.exists(png):
            try:
                os.unlink(png)
            except Exception:
                pass
    return json.dumps(result, ensure_ascii=False, indent=2)


# ── 라우팅 테이블 ──

_TOOLS = {
    "computer_snapshot": _do_snapshot,
    "computer_screenshot": _do_screenshot,
    "computer_click": _do_click,
    "computer_type": _do_type,
    "computer_key": _do_key,
    "computer_mouse_move": _do_mouse_move,
    "computer_drag": _do_drag,
    "computer_scroll": _do_scroll,
    "computer_cursor_position": _do_cursor_position,
    "computer_screen_info": _do_screen_info,
}

# 2026-05-27 단일 액션 통합: [limbs:screen]{op} → 내부 op 분기
# 2026-05-28 dispatcher 표준화: browser-action 패턴(_OP_DISPATCHERS 두 단계 dict).
_OP_DISPATCHERS = {
    "computer_op": {
        "snapshot": "computer_snapshot",
        "screenshot": "computer_screenshot",
        "click": "computer_click",
        "type": "computer_type",
        "key": "computer_key",
        "mouse_move": "computer_mouse_move",
        "drag": "computer_drag",
        "scroll": "computer_scroll",
        "cursor_position": "computer_cursor_position",
        "screen_info": "computer_screen_info",
    },
}
# computer_op은 op 필수 — _OP_DEFAULTS에 항목 없음.


def _do_op(tool_input: dict):
    """단일 액션 통합 디스패처. op 파라미터로 9개 함수에 위임."""
    op = (tool_input.get("op") or "").strip()
    mapping = _OP_DISPATCHERS["computer_op"]
    if not op:
        return json.dumps({
            "success": False,
            "error": f"op 파라미터 필요. 사용 가능: {sorted(mapping.keys())}"
        }, ensure_ascii=False)
    tool = mapping.get(op)
    if not tool:
        return json.dumps({
            "success": False,
            "error": f"알 수 없는 op: '{op}'. 사용 가능: {sorted(mapping.keys())}"
        }, ensure_ascii=False)
    return _TOOLS[tool](tool_input)


_TOOLS["computer_op"] = _do_op


def execute(tool_input: dict, context) -> str | dict:
    """도구 실행 엔트리포인트 (ToolContext 기반 신규 시그니처).

    Returns:
        str (JSON): 텍스트 전용 결과
        dict: 이미지를 포함한 결과 {"content", "images", "details"}
    """
    tool_name = context.tool_name
    handler = _TOOLS.get(tool_name)
    if not handler:
        return json.dumps({"success": False, "error": f"알 수 없는 도구: {tool_name}"}, ensure_ascii=False)

    try:
        return handler(tool_input)
    except Exception as e:
        error_type = type(e).__name__
        if "FailSafe" in error_type:
            return json.dumps({
                "success": False,
                "error": "긴급 정지! 마우스가 화면 모서리에 도달했습니다. 자동화가 중단되었습니다."
            }, ensure_ascii=False)
        return json.dumps({
            "success": False,
            "error": f"{error_type}: {str(e)}"
        }, ensure_ascii=False)
