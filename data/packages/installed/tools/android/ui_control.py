"""
UI 제어 모듈 (Computer-Use Style)
터치, 스와이프, 키 입력, 텍스트 입력, 화면 정보, UI 트리 덤프, 스크린샷(base64)

ADB의 input 명령을 통해 안드로이드 기기의 화면을 직접 제어합니다.
AI가 스크린샷을 보고 → 분석하고 → 조작하는 computer-use 패턴을 지원합니다.
"""

import sys
import base64
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree

_current_dir = Path(__file__).parent
if str(_current_dir) not in sys.path:
    sys.path.insert(0, str(_current_dir))

from adb_core import run_adb


# ============ 키코드 매핑 ============

KEY_MAP = {
    "HOME": 3,
    "BACK": 4,
    "CALL": 5,
    "END_CALL": 6,
    "VOLUME_UP": 24,
    "VOLUME_DOWN": 25,
    "POWER": 26,
    "CAMERA": 27,
    "ENTER": 66,
    "DELETE": 67,
    "RECENT": 187,
    "TAB": 61,
    "SPACE": 62,
    "MENU": 82,
    "SEARCH": 84,
    "MEDIA_PLAY_PAUSE": 85,
    "MEDIA_NEXT": 87,
    "MEDIA_PREVIOUS": 88,
    "MOVE_HOME": 122,
    "MOVE_END": 123,
}


# ============ 터치/제스처 ============

def tap(x: int, y: int, device_id: Optional[str] = None) -> dict:
    """화면의 지정 좌표를 터치합니다."""
    res = run_adb(["shell", "input", "tap", str(x), str(y)], device_id)
    if not res["success"]:
        return res
    return {
        "success": True,
        "action": "tap",
        "x": x,
        "y": y,
        "message": f"({x}, {y}) 좌표를 터치했습니다."
    }


def swipe(x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300, device_id: Optional[str] = None) -> dict:
    """화면에서 스와이프 제스처를 수행합니다."""
    res = run_adb(["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms)], device_id)
    if not res["success"]:
        return res
    return {
        "success": True,
        "action": "swipe",
        "from": {"x": x1, "y": y1},
        "to": {"x": x2, "y": y2},
        "duration_ms": duration_ms,
        "message": f"({x1},{y1})에서 ({x2},{y2})로 스와이프했습니다."
    }


def long_press(x: int, y: int, duration_ms: int = 1000, device_id: Optional[str] = None) -> dict:
    """화면의 지정 좌표를 길게 누릅니다."""
    res = run_adb(["shell", "input", "swipe", str(x), str(y), str(x), str(y), str(duration_ms)], device_id)
    if not res["success"]:
        return res
    return {
        "success": True,
        "action": "long_press",
        "x": x,
        "y": y,
        "duration_ms": duration_ms,
        "message": f"({x}, {y}) 좌표를 {duration_ms}ms 동안 길게 눌렀습니다."
    }


# ============ 키 입력 ============

def press_key(keycode: str, device_id: Optional[str] = None) -> dict:
    """하드웨어 키 이벤트를 발생시킵니다."""
    if isinstance(keycode, str) and keycode.upper() in KEY_MAP:
        resolved = str(KEY_MAP[keycode.upper()])
        key_label = keycode.upper()
    else:
        resolved = str(keycode)
        key_label = resolved

    res = run_adb(["shell", "input", "keyevent", resolved], device_id)
    if not res["success"]:
        return res
    return {
        "success": True,
        "action": "key",
        "keycode": resolved,
        "key_name": key_label,
        "message": f"{key_label} 키를 눌렀습니다."
    }


# ============ 텍스트 입력 ============

# IndieBiz IME 관련 상수
_INDIEBIZ_IME = "com.indiebiz.cliphelper/.IndieBizIME"
_SAMSUNG_IME = "com.samsung.android.honeyboard/.service.HoneyBoardService"


def _get_current_ime(device_id: Optional[str] = None) -> str:
    """현재 활성 IME를 조회합니다."""
    res = run_adb(["shell", "settings", "get", "secure", "default_input_method"], device_id)
    if res["success"]:
        return res.get("stdout", "").strip()
    return ""


def _input_text_via_ime(text: str, device_id: Optional[str] = None) -> bool:
    """IndieBiz IME를 통해 텍스트를 직접 입력합니다.

    1. 현재 IME 저장
    2. IndieBiz IME로 전환
    3. broadcast로 commitText() 호출
    4. 원래 IME 복원
    """
    import time

    # 현재 IME 저장
    original_ime = _get_current_ime(device_id)

    # IndieBiz IME로 전환
    run_adb(["shell", "ime", "set", _INDIEBIZ_IME], device_id)
    time.sleep(0.7)  # IME 전환 대기

    # broadcast로 텍스트 입력
    escaped = text.replace("'", "'\\''")
    res = run_adb([
        "shell", "am", "broadcast",
        "-a", "ADB_INPUT_TEXT",
        "--es", "text", f"'{escaped}'",
        "-n", "com.indiebiz.cliphelper/.TextReceiver"
    ], device_id)

    success = res.get("success", False) and "result=1" in res.get("stdout", "")

    time.sleep(0.3)

    # 원래 IME 복원
    restore_ime = original_ime if original_ime else _SAMSUNG_IME
    run_adb(["shell", "ime", "set", restore_ime], device_id)

    return success


def type_text(text: str, device_id: Optional[str] = None) -> dict:
    """텍스트를 입력합니다.

    영문/숫자는 ADB input text로 직접 입력합니다.
    한글 등 비-ASCII는 IndieBiz IME의 commitText()로 직접 주입합니다.
    """
    if not text:
        return {"success": False, "message": "입력할 텍스트가 없습니다."}

    # ASCII-only text: 직접 입력 (가장 빠름, IME 전환 불필요)
    if text.isascii():
        escaped = text.replace(" ", "%s")
        for char in ['&', '<', '>', '|', ';', '(', ')', '$', '`', '\\', '"', "'"]:
            escaped = escaped.replace(char, f"\\{char}")
        res = run_adb(["shell", "input", "text", escaped], device_id)
        if res["success"]:
            return {
                "success": True,
                "action": "type_text",
                "method": "direct_input",
                "text": text,
                "message": f"텍스트를 입력했습니다: {text[:50]}{'...' if len(text) > 50 else ''}"
            }

    # 한글 포함 텍스트: IndieBiz IME로 commitText() 직접 주입
    if _input_text_via_ime(text, device_id):
        return {
            "success": True,
            "action": "type_text",
            "method": "ime_commit",
            "text": text,
            "message": f"텍스트를 입력했습니다: {text[:50]}{'...' if len(text) > 50 else ''}"
        }

    return {
        "success": False,
        "message": "텍스트 입력 실패.",
        "hint": "IndieBiz IME(com.indiebiz.cliphelper)가 설치 및 활성화되어 있는지 확인하세요. adb shell ime enable com.indiebiz.cliphelper/.IndieBizIME"
    }


# ============ 화면 정보 ============

def get_screen_info(device_id: Optional[str] = None) -> dict:
    """화면 해상도 및 밀도 정보를 조회합니다."""
    size_res = run_adb(["shell", "wm", "size"], device_id)
    if not size_res["success"]:
        return size_res

    width, height = 0, 0
    for line in size_res["stdout"].split("\n"):
        if "Override size" in line or "Physical size" in line:
            match = re.search(r"(\d+)x(\d+)", line)
            if match:
                width, height = int(match.group(1)), int(match.group(2))

    density_res = run_adb(["shell", "wm", "density"], device_id)
    density = 0
    if density_res["success"]:
        for line in density_res["stdout"].split("\n"):
            if "Override density" in line or "Physical density" in line:
                match = re.search(r"(\d+)", line)
                if match:
                    density = int(match.group(1))

    return {
        "success": True,
        "width": width,
        "height": height,
        "density": density,
        "message": f"화면 크기: {width}x{height}, 밀도: {density}dpi"
    }


# ============ UI 계층 구조 ============

def get_ui_hierarchy(device_id: Optional[str] = None) -> dict:
    """현재 화면의 UI 계층 구조를 덤프합니다 (uiautomator)."""
    remote_path = "/sdcard/ui_dump.xml"

    dump_res = run_adb(["shell", "uiautomator", "dump", remote_path], device_id, timeout=15)
    if not dump_res["success"]:
        return dump_res

    local_dir = tempfile.gettempdir()
    local_path = os.path.join(local_dir, "ui_dump.xml")
    pull_res = run_adb(["pull", remote_path, local_path], device_id)
    if not pull_res["success"]:
        return pull_res

    run_adb(["shell", "rm", remote_path], device_id)

    try:
        tree = ElementTree.parse(local_path)
        root = tree.getroot()
        elements = []

        for node in root.iter("node"):
            text = node.get("text", "")
            content_desc = node.get("content-desc", "")
            resource_id = node.get("resource-id", "")
            class_name = node.get("class", "")
            bounds = node.get("bounds", "")
            clickable = node.get("clickable", "false")
            enabled = node.get("enabled", "true")

            if not (text or content_desc or resource_id):
                continue

            el = {
                "text": text,
                "content_desc": content_desc,
                "resource_id": resource_id,
                "class": class_name.split(".")[-1] if class_name else "",
                "clickable": clickable == "true",
                "enabled": enabled == "true",
            }

            bounds_match = re.findall(r"\[(\d+),(\d+)\]", bounds)
            if len(bounds_match) == 2:
                x1, y1 = int(bounds_match[0][0]), int(bounds_match[0][1])
                x2, y2 = int(bounds_match[1][0]), int(bounds_match[1][1])
                el["bounds"] = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
                el["center"] = {"x": (x1 + x2) // 2, "y": (y1 + y2) // 2}

            elements.append(el)

        try:
            os.remove(local_path)
        except OSError:
            pass

        return {
            "success": True,
            "elements": elements[:100],
            "total_elements": len(elements),
            "message": f"UI 요소 {len(elements)}개를 감지했습니다 (상위 {min(len(elements), 100)}개 표시)."
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"UI 계층 파싱 실패: {str(e)}"
        }


# ============ 스크린샷 (AI 비전용) ============

def capture_screen_base64(device_id: Optional[str] = None) -> dict:
    """화면을 캡처하여 base64 이미지로 반환합니다 (AI 비전 분석용).

    이 함수의 결과에 포함된 이미지는 AI가 직접 '볼' 수 있으며,
    화면의 내용을 분석하여 다음 행동을 결정할 수 있습니다.
    """
    phone_path = "/sdcard/screenshot_temp_cv.png"

    cap_res = run_adb(["shell", "screencap", "-p", phone_path], device_id)
    if not cap_res["success"]:
        return cap_res

    local_dir = tempfile.gettempdir()
    local_path = os.path.join(local_dir, f"android_cv_{datetime.now().strftime('%H%M%S')}.png")
    pull_res = run_adb(["pull", phone_path, local_path], device_id)
    if not pull_res["success"]:
        return pull_res

    run_adb(["shell", "rm", phone_path], device_id)

    try:
        with open(local_path, "rb") as f:
            img_bytes = f.read()
        img_base64 = base64.b64encode(img_bytes).decode("utf-8")

        try:
            os.remove(local_path)
        except OSError:
            pass

        return {
            "content": "화면 캡처 완료. 아래 이미지를 분석하여 현재 화면 상태를 파악하세요.",
            "images": [
                {
                    "base64": img_base64,
                    "media_type": "image/png"
                }
            ]
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"스크린샷 base64 인코딩 실패: {str(e)}"
        }


# ============ UI 요소 검색 및 터치 ============

def _parse_ui_elements(device_id: Optional[str] = None) -> list:
    """UI hierarchy를 파싱하여 요소 리스트 반환 (내부용)."""
    remote_path = "/sdcard/ui_dump.xml"

    dump_res = run_adb(["shell", "uiautomator", "dump", remote_path], device_id, timeout=15)
    if not dump_res["success"]:
        return []

    local_dir = tempfile.gettempdir()
    local_path = os.path.join(local_dir, "ui_dump_find.xml")
    pull_res = run_adb(["pull", remote_path, local_path], device_id)
    if not pull_res["success"]:
        return []

    run_adb(["shell", "rm", remote_path], device_id)

    try:
        tree = ElementTree.parse(local_path)
        root = tree.getroot()
        elements = []

        for node in root.iter("node"):
            text = node.get("text", "")
            content_desc = node.get("content-desc", "")
            resource_id = node.get("resource-id", "")
            class_name = node.get("class", "")
            bounds = node.get("bounds", "")
            clickable = node.get("clickable", "false")
            enabled = node.get("enabled", "true")

            el = {
                "text": text,
                "content_desc": content_desc,
                "resource_id": resource_id,
                "class": class_name.split(".")[-1] if class_name else "",
                "clickable": clickable == "true",
                "enabled": enabled == "true",
            }

            bounds_match = re.findall(r"\[(\d+),(\d+)\]", bounds)
            if len(bounds_match) == 2:
                x1, y1 = int(bounds_match[0][0]), int(bounds_match[0][1])
                x2, y2 = int(bounds_match[1][0]), int(bounds_match[1][1])
                el["bounds"] = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
                el["center"] = {"x": (x1 + x2) // 2, "y": (y1 + y2) // 2}

            elements.append(el)

        try:
            os.remove(local_path)
        except OSError:
            pass

        return elements

    except Exception:
        return []


def find_element(query: str, device_id: Optional[str] = None) -> dict:
    """화면에서 텍스트, content_desc, resource_id로 UI 요소를 검색합니다.

    부분 일치로 검색하며, 일치하는 모든 요소의 좌표 정보를 반환합니다.
    """
    if not query:
        return {"success": False, "message": "검색어가 필요합니다."}

    elements = _parse_ui_elements(device_id)
    if not elements:
        return {"success": False, "message": "UI 계층을 가져올 수 없습니다."}

    query_lower = query.lower()
    matched = []

    for el in elements:
        text_match = query_lower in el.get("text", "").lower()
        desc_match = query_lower in el.get("content_desc", "").lower()
        rid_match = query_lower in el.get("resource_id", "").lower()

        if text_match or desc_match or rid_match:
            matched.append(el)

    if not matched:
        return {
            "success": False,
            "message": f"'{query}'와 일치하는 UI 요소를 찾지 못했습니다.",
            "hint": "다른 검색어를 시도하거나, android_ui_hierarchy로 전체 요소를 확인하세요."
        }

    return {
        "success": True,
        "query": query,
        "count": len(matched),
        "elements": matched[:20],
        "message": f"'{query}' 검색 결과: {len(matched)}개 요소 발견"
    }


def find_and_tap(query: str, index: int = 0, device_id: Optional[str] = None) -> dict:
    """화면에서 텍스트/설명으로 요소를 찾아 중심을 터치합니다.

    검색 결과 중 index번째 요소의 중심 좌표를 자동으로 터치합니다.
    정확한 좌표를 모를 때 유용합니다.

    Args:
        query: 검색할 텍스트 (text, content_desc, resource_id에서 부분 일치)
        index: 여러 결과 중 몇 번째를 터치할지 (0부터 시작, 기본 0)
    """
    result = find_element(query, device_id)
    if not result.get("success"):
        return result

    elements = result.get("elements", [])
    if index >= len(elements):
        return {
            "success": False,
            "message": f"index {index}는 검색 결과 범위를 벗어납니다 (총 {len(elements)}개)."
        }

    target = elements[index]
    center = target.get("center")
    if not center:
        return {
            "success": False,
            "message": "선택한 요소의 좌표 정보가 없습니다."
        }

    # 터치 수행
    tap_result = tap(center["x"], center["y"], device_id)
    if not tap_result.get("success"):
        return tap_result

    return {
        "success": True,
        "action": "find_and_tap",
        "query": query,
        "tapped_element": {
            "text": target.get("text", ""),
            "content_desc": target.get("content_desc", ""),
            "class": target.get("class", ""),
            "center": center,
        },
        "message": f"'{query}' 요소를 찾아 ({center['x']}, {center['y']})를 터치했습니다."
    }


# ============ 앱 실행 ============

def open_app(package_name: str, device_id: Optional[str] = None) -> dict:
    """앱을 실행합니다."""
    if not package_name:
        return {"success": False, "message": "패키지명이 필요합니다."}

    res = run_adb([
        "shell", "monkey", "-p", package_name,
        "-c", "android.intent.category.LAUNCHER", "1"
    ], device_id)
    if not res["success"]:
        return res
    return {
        "success": True,
        "action": "open_app",
        "package_name": package_name,
        "message": f"{package_name} 앱을 실행했습니다."
    }
