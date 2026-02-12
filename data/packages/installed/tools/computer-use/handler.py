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


def _do_click(tool_input):
    """computer_click: 마우스 클릭"""
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
    """computer_type: 텍스트 입력 (한글 지원)"""
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


# ── 라우팅 테이블 ──

_TOOLS = {
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


def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str | dict:
    """도구 실행 엔트리포인트

    Returns:
        str (JSON): 텍스트 전용 결과
        dict: 이미지를 포함한 결과 {"content", "images", "details"}
    """
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
