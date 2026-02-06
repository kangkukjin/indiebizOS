"""
파일 및 화면 유틸리티 모듈
스크린샷, 파일 전송, 클립보드, 알림 조회
"""

import sys
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

_current_dir = Path(__file__).parent
if str(_current_dir) not in sys.path:
    sys.path.insert(0, str(_current_dir))

from adb_core import run_adb


def capture_screen(device_id: Optional[str] = None, save_path: Optional[str] = None) -> dict:
    """폰 화면 캡처"""
    if save_path is None:
        outputs_dir = Path.cwd() / "outputs"
        outputs_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = str(outputs_dir / f"android_screen_{timestamp}.png")

    phone_path = "/sdcard/screenshot_temp.png"

    # 1. 폰에서 촬영
    cap_res = run_adb(["shell", "screencap", "-p", phone_path], device_id)
    if not cap_res["success"]: return cap_res

    # 2. PC로 가져오기
    pull_res = run_adb(["pull", phone_path, save_path], device_id)
    if not pull_res["success"]: return pull_res

    # 3. 폰에서 삭제
    run_adb(["shell", "rm", phone_path], device_id)

    return {
        "success": True,
        "file_path": save_path,
        "message": f"화면 캡처 완료: {save_path}"
    }


def send_to_clipboard(text: str, device_id: Optional[str] = None) -> dict:
    """텍스트 전송 (Clipper 앱 우선, 실패 시 직접 입력)"""
    # 1. Clipper 앱 시도
    escaped = text.replace("'", "'\\''")
    res = run_adb(["shell", "am", "broadcast", "-a", "clipper.set", "-e", "text", f"'{escaped}'"], device_id)

    if res["success"] and "result=0" not in res.get("stdout", ""):
        return {
            "success": True,
            "method": "clipboard",
            "message": "Clipper 앱을 통해 클립보드에 복사했습니다."
        }

    # 2. 직접 입력 시도
    res = run_adb(["shell", "input", "text", text.replace(" ", "%s")], device_id)
    if res["success"]:
        return {
            "success": True,
            "method": "direct_input",
            "message": "클립보드 앱이 없어 활성 입력창에 직접 입력했습니다."
        }

    return res


def push_file(local_path: str, remote_path: str = "/sdcard/Download/", device_id: Optional[str] = None) -> dict:
    """파일 전송"""
    if not os.path.exists(local_path):
        return {"success": False, "message": f"로컬 파일을 찾을 수 없습니다: {local_path}"}

    res = run_adb(["push", local_path, remote_path], device_id, timeout=120)
    if res["success"]:
        return {
            "success": True,
            "local": local_path,
            "remote": remote_path,
            "message": f"파일 전송 완료: {os.path.basename(local_path)} → {remote_path}"
        }
    return res


def pull_file(remote_path: str, local_path: Optional[str] = None, device_id: Optional[str] = None) -> dict:
    """파일 가져오기"""
    if local_path is None:
        local_path = str(Path.cwd() / "outputs" / os.path.basename(remote_path))
        Path(local_path).parent.mkdir(exist_ok=True)

    res = run_adb(["pull", remote_path, local_path], device_id, timeout=120)
    if res["success"]:
        return {
            "success": True,
            "remote": remote_path,
            "local": local_path,
            "message": f"파일 가져오기 완료: {remote_path} → {local_path}"
        }
    return res


def get_notifications(device_id: Optional[str] = None) -> dict:
    """알림 목록 조회"""
    res = run_adb(["shell", "dumpsys", "notification", "--noredact"], device_id, timeout=15)
    if not res["success"]: return res

    notifications = []
    # 간단한 파싱 로직 (패키지명과 제목 추출)
    for line in res["stdout"].split("\n"):
        line = line.strip()
        if "pkg=" in line:
            pkg = re.search(r"pkg=(\S+)", line)
            if pkg: notifications.append({"package": pkg.group(1)})
        elif "android.title=" in line and notifications:
            title = re.search(r"android\.title=(.+?)(?:android\.|$)", line)
            if title: notifications[-1]["title"] = title.group(1).strip()

    return {
        "success": True,
        "notifications": notifications[:15],
        "message": f"{len(notifications)}개의 알림을 감지했습니다."
    }


def open_android_manager_window(device_id: Optional[str] = None, project_id: Optional[str] = None) -> dict:
    """Android Manager 창 열기 요청"""
    import urllib.request
    import urllib.parse

    try:
        url = "http://127.0.0.1:8765/android/open-window"
        params = []
        if device_id:
            params.append(f"device_id={urllib.parse.quote(device_id)}")
        if project_id:
            params.append(f"project_id={urllib.parse.quote(project_id)}")
        if params:
            url += "?" + "&".join(params)

        req = urllib.request.Request(url, method='POST')
        with urllib.request.urlopen(req, timeout=5) as response:
            return {
                "success": True,
                "message": "Android Manager 창을 열었습니다."
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"창 열기 요청 실패: {str(e)}"
        }
