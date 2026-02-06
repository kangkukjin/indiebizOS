"""
ADB 핵심 유틸리티
ADB 실행 파일 검색 및 명령 실행
"""

import subprocess
import os
import shutil
from pathlib import Path
from typing import Optional, List


def find_adb() -> Optional[str]:
    """ADB 실행 파일의 경로를 찾습니다."""
    # 0. 환경변수 ANDROID_HOME 또는 ANDROID_SDK_ROOT 확인
    android_home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
    if android_home:
        adb_from_env = os.path.join(android_home, "platform-tools", "adb")
        if os.path.exists(adb_from_env):
            return adb_from_env

    # 1. 시스템 PATH 확인
    adb_path = shutil.which("adb")
    if adb_path:
        return adb_path

    # 2. 흔한 설치 경로 확인 (macOS/Linux)
    home = str(Path.home())
    common_paths = [
        "/usr/local/bin/adb",
        "/opt/homebrew/bin/adb",
        f"{home}/Library/Android/sdk/platform-tools/adb",
        f"{home}/Android/Sdk/platform-tools/adb",
        # Android Studio 기본 설치 경로
        "/Applications/Android Studio.app/Contents/sdk/platform-tools/adb",
        # Homebrew cask로 설치된 경우
        "/usr/local/Caskroom/android-platform-tools/latest/platform-tools/adb",
        "/opt/homebrew/Caskroom/android-platform-tools/latest/platform-tools/adb",
    ]

    # Windows 경로 추가
    if os.name == 'nt':
        common_paths.extend([
            r"C:\Program Files (x86)\Android\android-sdk\platform-tools\adb.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
            os.path.expandvars(r"%USERPROFILE%\AppData\Local\Android\Sdk\platform-tools\adb.exe"),
        ])

    for path in common_paths:
        if os.path.exists(path):
            return path

    # 3. macOS: 모든 사용자의 Library 폴더 검색
    if os.path.exists("/Users"):
        for user_dir in os.listdir("/Users"):
            user_adb = f"/Users/{user_dir}/Library/Android/sdk/platform-tools/adb"
            if os.path.exists(user_adb):
                return user_adb

    return None


def run_adb(args: List[str], device_id: Optional[str] = None, timeout: int = 30) -> dict:
    """ADB 명령 실행 및 상세 에러 캡처"""
    adb_path = find_adb()

    if not adb_path:
        return {
            "success": False,
            "error_type": "PRECONDITION_FAILED",
            "error": "ADB 실행 파일을 찾을 수 없습니다.",
            "message": "ADB가 설치되어 있지 않거나 PATH에 없습니다. 'brew install android-platform-tools'(macOS) 또는 공식 사이트에서 SDK Platform Tools를 설치해 주세요.",
            "checked_paths": ["시스템 PATH", "/usr/local/bin", "/opt/homebrew/bin", "~/Library/Android/sdk/platform-tools"]
        }

    cmd = [adb_path]
    if device_id:
        cmd.extend(["-s", device_id])
    cmd.extend(args)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip()
            # 흔한 에러에 대한 친절한 설명 추가
            friendly_msg = error_msg
            if "device not found" in error_msg.lower():
                friendly_msg = "기기를 찾을 수 없습니다. USB 케이블 연결을 확인하거나, 'android_list_devices'로 연결 상태를 확인하세요."
            elif "unauthorized" in error_msg.lower():
                friendly_msg = "기기에서 USB 디버깅 권한 승인이 필요합니다. 폰 화면에서 '허용'을 눌러주세요."

            return {
                "success": False,
                "error_type": "EXECUTION_ERROR",
                "returncode": result.returncode,
                "stderr": error_msg,
                "message": friendly_msg,
                "command": " ".join(cmd)
            }

        return {
            "success": True,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip()
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error_type": "TIMEOUT",
            "message": f"ADB 명령이 {timeout}초 내에 응답하지 않아 중단되었습니다. 기기 연결 상태를 확인하세요."
        }
    except Exception as e:
        return {
            "success": False,
            "error_type": "SYSTEM_ERROR",
            "error": str(e),
            "message": f"시스템 오류가 발생했습니다: {str(e)}"
        }
