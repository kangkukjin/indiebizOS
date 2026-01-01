"""
안드로이드 관리 도구
Android Management Tool for IndieBiz

ADB(Android Debug Bridge)를 통해 안드로이드 스마트폰을 관리합니다.

기능:
- 기기 연결 상태 확인
- 미디어 동기화 (DCIM → PC)
- 앱 목록 및 정보 조회
- 클립보드 공유 (PC ↔ 폰)
- 시스템 상태 (배터리, 저장공간)
- 화면 캡처
- 파일 전송 (양방향)
- 알림 조회

사전 요구사항:
- ADB 설치 (brew install android-platform-tools 또는 Android SDK)
- 폰에서 USB 디버깅 활성화
- PC와 폰을 USB로 연결하거나 WiFi ADB 설정
"""

import subprocess
import os
import re
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict


def run_adb(args: List[str], device_id: Optional[str] = None, timeout: int = 30) -> dict:
    """ADB 명령 실행"""
    cmd = ["adb"]
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
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"ADB 명령 타임아웃 ({timeout}초)"}
    except FileNotFoundError:
        return {"success": False, "error": "ADB가 설치되어 있지 않습니다. 'brew install android-platform-tools'로 설치하세요."}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============================================================
# 기기 연결 관리
# ============================================================

def list_devices() -> dict:
    """연결된 안드로이드 기기 목록 조회"""
    result = run_adb(["devices", "-l"])

    if not result["success"]:
        return {"success": False, "message": result.get("error", "ADB 실행 실패")}

    devices = []
    lines = result["stdout"].split("\n")

    for line in lines[1:]:  # 첫 줄은 "List of devices attached"
        if not line.strip():
            continue

        parts = line.split()
        if len(parts) >= 2:
            device_id = parts[0]
            status = parts[1]

            # 추가 정보 파싱
            info = {}
            for part in parts[2:]:
                if ":" in part:
                    key, value = part.split(":", 1)
                    info[key] = value

            devices.append({
                "id": device_id,
                "status": status,
                "model": info.get("model", "Unknown"),
                "device": info.get("device", "Unknown"),
                "product": info.get("product", "Unknown")
            })

    return {
        "success": True,
        "devices": devices,
        "count": len(devices),
        "message": f"{len(devices)}개의 기기가 연결되어 있습니다." if devices else "연결된 기기가 없습니다."
    }


def get_device_info(device_id: Optional[str] = None) -> dict:
    """기기 상세 정보 조회"""
    # 기기 선택
    if not device_id:
        devices = list_devices()
        if not devices["devices"]:
            return {"success": False, "message": "연결된 기기가 없습니다."}
        device_id = devices["devices"][0]["id"]

    info = {}

    # 모델명
    result = run_adb(["shell", "getprop", "ro.product.model"], device_id)
    if result["success"]:
        info["model"] = result["stdout"]

    # 제조사
    result = run_adb(["shell", "getprop", "ro.product.manufacturer"], device_id)
    if result["success"]:
        info["manufacturer"] = result["stdout"]

    # 안드로이드 버전
    result = run_adb(["shell", "getprop", "ro.build.version.release"], device_id)
    if result["success"]:
        info["android_version"] = result["stdout"]

    # SDK 버전
    result = run_adb(["shell", "getprop", "ro.build.version.sdk"], device_id)
    if result["success"]:
        info["sdk_version"] = result["stdout"]

    # 시리얼 번호
    result = run_adb(["shell", "getprop", "ro.serialno"], device_id)
    if result["success"]:
        info["serial"] = result["stdout"]

    return {
        "success": True,
        "device_id": device_id,
        "info": info,
        "message": f"{info.get('manufacturer', '')} {info.get('model', '')} (Android {info.get('android_version', '')})"
    }


# ============================================================
# 시스템 상태
# ============================================================

def get_battery_status(device_id: Optional[str] = None) -> dict:
    """배터리 상태 조회"""
    result = run_adb(["shell", "dumpsys", "battery"], device_id)

    if not result["success"]:
        return {"success": False, "message": result.get("error", "배터리 정보 조회 실패")}

    battery = {}
    for line in result["stdout"].split("\n"):
        line = line.strip()
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip().lower().replace(" ", "_")
            value = value.strip()
            battery[key] = value

    level = battery.get("level", "?")
    status_map = {"2": "충전 중", "3": "방전 중", "4": "방전 안 함", "5": "완충"}
    charging = status_map.get(battery.get("status", ""), battery.get("status", "알 수 없음"))

    return {
        "success": True,
        "level": int(level) if level.isdigit() else level,
        "charging": charging,
        "temperature": f"{int(battery.get('temperature', 0)) / 10}°C" if battery.get('temperature', '').isdigit() else None,
        "health": battery.get("health", "Unknown"),
        "raw": battery,
        "message": f"배터리: {level}% ({charging})"
    }


def get_storage_info(device_id: Optional[str] = None) -> dict:
    """저장 공간 정보 조회"""
    result = run_adb(["shell", "df", "-h", "/data"], device_id)

    if not result["success"]:
        return {"success": False, "message": result.get("error", "저장 공간 조회 실패")}

    lines = result["stdout"].split("\n")
    if len(lines) < 2:
        return {"success": False, "message": "저장 공간 정보 파싱 실패"}

    # 헤더와 데이터 파싱
    parts = lines[1].split()
    if len(parts) >= 4:
        storage = {
            "total": parts[1],
            "used": parts[2],
            "available": parts[3],
            "use_percent": parts[4] if len(parts) > 4 else "?"
        }
        return {
            "success": True,
            "storage": storage,
            "message": f"저장 공간: {storage['available']} 사용 가능 ({storage['use_percent']} 사용 중)"
        }

    return {"success": False, "message": "저장 공간 정보 파싱 실패"}


def get_system_status(device_id: Optional[str] = None) -> dict:
    """시스템 전체 상태 조회"""
    battery = get_battery_status(device_id)
    storage = get_storage_info(device_id)
    device = get_device_info(device_id)

    return {
        "success": True,
        "device": device.get("info", {}),
        "battery": {
            "level": battery.get("level"),
            "charging": battery.get("charging"),
            "temperature": battery.get("temperature")
        } if battery.get("success") else None,
        "storage": storage.get("storage") if storage.get("success") else None,
        "message": f"{device.get('message', '')} | {battery.get('message', '')} | {storage.get('message', '')}"
    }


# ============================================================
# 앱 관리
# ============================================================

def list_packages(device_id: Optional[str] = None, third_party_only: bool = True) -> dict:
    """설치된 앱 목록 조회"""
    args = ["shell", "pm", "list", "packages"]
    if third_party_only:
        args.append("-3")  # 서드파티 앱만

    result = run_adb(args, device_id)

    if not result["success"]:
        return {"success": False, "message": result.get("error", "앱 목록 조회 실패")}

    packages = []
    for line in result["stdout"].split("\n"):
        if line.startswith("package:"):
            packages.append(line.replace("package:", ""))

    return {
        "success": True,
        "packages": packages,
        "count": len(packages),
        "message": f"{len(packages)}개의 {'사용자' if third_party_only else '전체'} 앱이 설치되어 있습니다."
    }


def get_app_info(package_name: str, device_id: Optional[str] = None) -> dict:
    """특정 앱의 상세 정보 조회"""
    result = run_adb(["shell", "dumpsys", "package", package_name], device_id, timeout=10)

    if not result["success"]:
        return {"success": False, "message": result.get("error", "앱 정보 조회 실패")}

    info = {"package": package_name}

    # 버전 정보 추출
    version_match = re.search(r"versionName=(\S+)", result["stdout"])
    if version_match:
        info["version"] = version_match.group(1)

    # 설치 시간
    install_match = re.search(r"firstInstallTime=(\d{4}-\d{2}-\d{2})", result["stdout"])
    if install_match:
        info["installed"] = install_match.group(1)

    # 마지막 업데이트
    update_match = re.search(r"lastUpdateTime=(\d{4}-\d{2}-\d{2})", result["stdout"])
    if update_match:
        info["updated"] = update_match.group(1)

    return {
        "success": True,
        "info": info,
        "message": f"{package_name} v{info.get('version', '?')}"
    }


def get_app_sizes(device_id: Optional[str] = None, limit: int = 20) -> dict:
    """앱별 용량 조회 (상위 N개)"""
    # 서드파티 앱 목록
    packages_result = list_packages(device_id, third_party_only=True)
    if not packages_result["success"]:
        return packages_result

    app_sizes = []
    for package in packages_result["packages"][:50]:  # 최대 50개만 조회 (시간 절약)
        result = run_adb(["shell", "du", "-sh", f"/data/data/{package}"], device_id, timeout=5)
        if result["success"] and result["stdout"]:
            parts = result["stdout"].split()
            if parts:
                size = parts[0]
                app_sizes.append({"package": package, "size": size})

    # 크기순 정렬 (대략적)
    def parse_size(s):
        s = s.upper()
        if "G" in s:
            return float(s.replace("G", "")) * 1024
        elif "M" in s:
            return float(s.replace("M", ""))
        elif "K" in s:
            return float(s.replace("K", "")) / 1024
        return 0

    app_sizes.sort(key=lambda x: parse_size(x["size"]), reverse=True)

    return {
        "success": True,
        "apps": app_sizes[:limit],
        "message": f"용량 상위 {min(limit, len(app_sizes))}개 앱"
    }


# ============================================================
# 미디어 동기화
# ============================================================

def sync_media(device_id: Optional[str] = None,
               source_path: str = "/sdcard/DCIM/Camera",
               dest_path: Optional[str] = None,
               newer_than: Optional[str] = None) -> dict:
    """미디어 파일 동기화 (폰 → PC)"""

    # 기본 저장 경로
    if dest_path is None:
        dest_path = str(Path(__file__).parent / "android_media")

    # 저장 폴더 생성
    Path(dest_path).mkdir(parents=True, exist_ok=True)

    # 먼저 폰의 파일 목록 확인
    result = run_adb(["shell", "ls", "-la", source_path], device_id)
    if not result["success"]:
        return {"success": False, "message": f"소스 경로 접근 실패: {source_path}"}

    # 파일 가져오기
    result = run_adb(["pull", source_path, dest_path], device_id, timeout=300)

    if result["success"]:
        # 가져온 파일 수 확인
        pulled_files = list(Path(dest_path).rglob("*"))
        file_count = len([f for f in pulled_files if f.is_file()])

        return {
            "success": True,
            "source": source_path,
            "destination": dest_path,
            "files_synced": file_count,
            "message": f"{file_count}개 파일을 {dest_path}로 동기화했습니다."
        }
    else:
        return {
            "success": False,
            "message": f"동기화 실패: {result.get('stderr', result.get('error', ''))}"
        }


def list_phone_media(device_id: Optional[str] = None,
                     path: str = "/sdcard/DCIM/Camera",
                     limit: int = 20) -> dict:
    """폰의 미디어 파일 목록 조회"""
    result = run_adb(["shell", "ls", "-lt", path], device_id)

    if not result["success"]:
        return {"success": False, "message": result.get("error", "파일 목록 조회 실패")}

    files = []
    for line in result["stdout"].split("\n")[:limit + 1]:
        parts = line.split()
        if len(parts) >= 8 and not line.startswith("total"):
            filename = parts[-1]
            date_str = f"{parts[5]} {parts[6]} {parts[7]}"
            files.append({
                "name": filename,
                "date": date_str,
                "size": parts[4]
            })

    return {
        "success": True,
        "path": path,
        "files": files[:limit],
        "count": len(files),
        "message": f"{path}에 {len(files)}개 파일"
    }


# ============================================================
# 화면 캡처
# ============================================================

def capture_screen(device_id: Optional[str] = None,
                   save_path: Optional[str] = None) -> dict:
    """폰 화면 캡처"""
    # 저장 경로 설정
    if save_path is None:
        outputs_dir = Path(__file__).parent / "outputs"
        outputs_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = str(outputs_dir / f"android_screen_{timestamp}.png")

    # 폰에서 스크린샷 촬영
    phone_path = "/sdcard/screenshot_temp.png"
    result = run_adb(["shell", "screencap", "-p", phone_path], device_id)

    if not result["success"]:
        return {"success": False, "message": f"스크린샷 촬영 실패: {result.get('error', '')}"}

    # PC로 가져오기
    result = run_adb(["pull", phone_path, save_path], device_id)

    if not result["success"]:
        return {"success": False, "message": f"스크린샷 전송 실패: {result.get('error', '')}"}

    # 폰에서 임시 파일 삭제
    run_adb(["shell", "rm", phone_path], device_id)

    return {
        "success": True,
        "file_path": save_path,
        "message": f"화면 캡처 완료: {save_path}"
    }


# ============================================================
# 클립보드 공유
# ============================================================

def send_to_clipboard(text: str, device_id: Optional[str] = None) -> dict:
    """PC에서 폰 클립보드로 텍스트 전송"""
    # 특수문자 이스케이프
    escaped = text.replace("'", "'\\''")

    result = run_adb(["shell", "am", "broadcast", "-a", "clipper.set", "-e", "text", f"'{escaped}'"], device_id)

    # Clipper 앱이 없으면 다른 방법 시도
    if not result["success"] or "error" in result.get("stderr", "").lower():
        # input text 방식 (활성 입력 필드에 직접 입력)
        result = run_adb(["shell", "input", "text", escaped.replace(" ", "%s")], device_id)

        if result["success"]:
            return {
                "success": True,
                "method": "input",
                "message": "텍스트를 입력했습니다. (현재 입력 필드에 직접 입력됨)"
            }
        else:
            return {
                "success": False,
                "message": "클립보드 전송 실패. Clipper 앱 설치가 필요할 수 있습니다."
            }

    return {
        "success": True,
        "method": "clipboard",
        "message": f"클립보드에 텍스트를 복사했습니다. ({len(text)}자)"
    }


def get_clipboard(device_id: Optional[str] = None) -> dict:
    """폰 클립보드 내용 가져오기"""
    result = run_adb(["shell", "am", "broadcast", "-a", "clipper.get"], device_id)

    # Clipper 앱 응답 파싱
    if result["success"] and "data=" in result["stdout"]:
        match = re.search(r'data="([^"]*)"', result["stdout"])
        if match:
            return {
                "success": True,
                "text": match.group(1),
                "message": "클립보드 내용을 가져왔습니다."
            }

    return {
        "success": False,
        "message": "클립보드 조회 실패. Clipper 앱 설치가 필요합니다."
    }


# ============================================================
# 파일 전송
# ============================================================

def push_file(local_path: str, remote_path: str = "/sdcard/Download/",
              device_id: Optional[str] = None) -> dict:
    """PC에서 폰으로 파일 전송"""
    if not os.path.exists(local_path):
        return {"success": False, "message": f"파일을 찾을 수 없습니다: {local_path}"}

    result = run_adb(["push", local_path, remote_path], device_id, timeout=120)

    if result["success"]:
        filename = os.path.basename(local_path)
        return {
            "success": True,
            "local": local_path,
            "remote": f"{remote_path}{filename}",
            "message": f"파일 전송 완료: {filename} → {remote_path}"
        }
    else:
        return {
            "success": False,
            "message": f"파일 전송 실패: {result.get('stderr', result.get('error', ''))}"
        }


def pull_file(remote_path: str, local_path: Optional[str] = None,
              device_id: Optional[str] = None) -> dict:
    """폰에서 PC로 파일 가져오기"""
    if local_path is None:
        downloads_dir = Path(__file__).parent / "android_downloads"
        downloads_dir.mkdir(exist_ok=True)
        local_path = str(downloads_dir / os.path.basename(remote_path))

    result = run_adb(["pull", remote_path, local_path], device_id, timeout=120)

    if result["success"]:
        return {
            "success": True,
            "remote": remote_path,
            "local": local_path,
            "message": f"파일 가져오기 완료: {remote_path} → {local_path}"
        }
    else:
        return {
            "success": False,
            "message": f"파일 가져오기 실패: {result.get('stderr', result.get('error', ''))}"
        }


# ============================================================
# 알림 조회
# ============================================================

def get_notifications(device_id: Optional[str] = None) -> dict:
    """현재 알림 목록 조회"""
    result = run_adb(["shell", "dumpsys", "notification", "--noredact"], device_id, timeout=15)

    if not result["success"]:
        return {"success": False, "message": result.get("error", "알림 조회 실패")}

    notifications = []
    current_notification = {}

    for line in result["stdout"].split("\n"):
        line = line.strip()

        if "pkg=" in line:
            if current_notification:
                notifications.append(current_notification)
            pkg_match = re.search(r"pkg=(\S+)", line)
            current_notification = {
                "package": pkg_match.group(1) if pkg_match else "unknown"
            }
        elif "android.title=" in line:
            title_match = re.search(r"android\.title=(.+?)(?:android\.|$)", line)
            if title_match:
                current_notification["title"] = title_match.group(1).strip()
        elif "android.text=" in line:
            text_match = re.search(r"android\.text=(.+?)(?:android\.|$)", line)
            if text_match:
                current_notification["text"] = text_match.group(1).strip()

    if current_notification:
        notifications.append(current_notification)

    # 중복 제거 및 필터링
    seen = set()
    unique_notifications = []
    for n in notifications:
        key = (n.get("package"), n.get("title", ""), n.get("text", ""))
        if key not in seen and n.get("title"):
            seen.add(key)
            unique_notifications.append(n)

    return {
        "success": True,
        "notifications": unique_notifications[:20],  # 최대 20개
        "count": len(unique_notifications),
        "message": f"{len(unique_notifications)}개의 알림이 있습니다."
    }


# ============================================================
# 도구 정의
# ============================================================

ANDROID_TOOLS = [
    {
        "name": "android_list_devices",
        "description": "연결된 안드로이드 기기 목록을 조회합니다. USB 또는 WiFi ADB로 연결된 기기를 확인합니다.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "android_device_info",
        "description": "안드로이드 기기의 상세 정보(모델, 제조사, Android 버전 등)를 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "특정 기기 ID (생략 시 첫 번째 기기)"
                }
            },
            "required": []
        }
    },
    {
        "name": "android_system_status",
        "description": "안드로이드 기기의 시스템 상태(배터리, 저장공간)를 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "특정 기기 ID (생략 시 첫 번째 기기)"
                }
            },
            "required": []
        }
    },
    {
        "name": "android_list_apps",
        "description": "설치된 앱 목록을 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "특정 기기 ID"
                },
                "third_party_only": {
                    "type": "boolean",
                    "description": "사용자 설치 앱만 표시 (기본값: true)",
                    "default": True
                }
            },
            "required": []
        }
    },
    {
        "name": "android_app_sizes",
        "description": "앱별 용량을 조회하여 큰 앱을 찾습니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "특정 기기 ID"
                },
                "limit": {
                    "type": "integer",
                    "description": "표시할 앱 수 (기본값: 20)",
                    "default": 20
                }
            },
            "required": []
        }
    },
    {
        "name": "android_sync_media",
        "description": "폰의 카메라 사진/동영상을 PC로 동기화합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "특정 기기 ID"
                },
                "source_path": {
                    "type": "string",
                    "description": "폰의 미디어 경로 (기본값: /sdcard/DCIM/Camera)",
                    "default": "/sdcard/DCIM/Camera"
                },
                "dest_path": {
                    "type": "string",
                    "description": "PC 저장 경로 (생략 시 자동 생성)"
                }
            },
            "required": []
        }
    },
    {
        "name": "android_list_media",
        "description": "폰의 미디어 파일 목록을 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "특정 기기 ID"
                },
                "path": {
                    "type": "string",
                    "description": "조회할 경로 (기본값: /sdcard/DCIM/Camera)",
                    "default": "/sdcard/DCIM/Camera"
                },
                "limit": {
                    "type": "integer",
                    "description": "표시할 파일 수 (기본값: 20)",
                    "default": 20
                }
            },
            "required": []
        }
    },
    {
        "name": "android_capture_screen",
        "description": "폰 화면을 캡처합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "특정 기기 ID"
                }
            },
            "required": []
        }
    },
    {
        "name": "android_send_text",
        "description": "PC에서 폰으로 텍스트를 전송합니다 (클립보드 또는 직접 입력).",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "전송할 텍스트"
                },
                "device_id": {
                    "type": "string",
                    "description": "특정 기기 ID"
                }
            },
            "required": ["text"]
        }
    },
    {
        "name": "android_push_file",
        "description": "PC에서 폰으로 파일을 전송합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "local_path": {
                    "type": "string",
                    "description": "PC의 파일 경로"
                },
                "remote_path": {
                    "type": "string",
                    "description": "폰의 저장 경로 (기본값: /sdcard/Download/)",
                    "default": "/sdcard/Download/"
                },
                "device_id": {
                    "type": "string",
                    "description": "특정 기기 ID"
                }
            },
            "required": ["local_path"]
        }
    },
    {
        "name": "android_pull_file",
        "description": "폰에서 PC로 파일을 가져옵니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "remote_path": {
                    "type": "string",
                    "description": "폰의 파일 경로"
                },
                "local_path": {
                    "type": "string",
                    "description": "PC 저장 경로 (생략 시 자동 생성)"
                },
                "device_id": {
                    "type": "string",
                    "description": "특정 기기 ID"
                }
            },
            "required": ["remote_path"]
        }
    },
    {
        "name": "android_notifications",
        "description": "폰의 현재 알림 목록을 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "특정 기기 ID"
                }
            },
            "required": []
        }
    }
]


def use_tool(tool_name: str, tool_input: dict) -> dict:
    """도구 실행"""
    device_id = tool_input.get("device_id")

    if tool_name == "android_list_devices":
        return list_devices()

    elif tool_name == "android_device_info":
        return get_device_info(device_id)

    elif tool_name == "android_system_status":
        return get_system_status(device_id)

    elif tool_name == "android_list_apps":
        return list_packages(device_id, tool_input.get("third_party_only", True))

    elif tool_name == "android_app_sizes":
        return get_app_sizes(device_id, tool_input.get("limit", 20))

    elif tool_name == "android_sync_media":
        return sync_media(
            device_id,
            tool_input.get("source_path", "/sdcard/DCIM/Camera"),
            tool_input.get("dest_path")
        )

    elif tool_name == "android_list_media":
        return list_phone_media(
            device_id,
            tool_input.get("path", "/sdcard/DCIM/Camera"),
            tool_input.get("limit", 20)
        )

    elif tool_name == "android_capture_screen":
        return capture_screen(device_id)

    elif tool_name == "android_send_text":
        return send_to_clipboard(tool_input.get("text", ""), device_id)

    elif tool_name == "android_push_file":
        return push_file(
            tool_input.get("local_path", ""),
            tool_input.get("remote_path", "/sdcard/Download/"),
            device_id
        )

    elif tool_name == "android_pull_file":
        return pull_file(
            tool_input.get("remote_path", ""),
            tool_input.get("local_path"),
            device_id
        )

    elif tool_name == "android_notifications":
        return get_notifications(device_id)

    else:
        return {"success": False, "message": f"알 수 없는 도구: {tool_name}"}


# ============================================================
# 테스트
# ============================================================

if __name__ == "__main__":
    print("=== 안드로이드 도구 테스트 ===\n")

    # ADB 확인
    result = subprocess.run(["which", "adb"], capture_output=True, text=True)
    if result.returncode != 0:
        print("❌ ADB가 설치되어 있지 않습니다.")
        print("   설치: brew install android-platform-tools")
        exit(1)

    print(f"✓ ADB 경로: {result.stdout.strip()}\n")

    # 기기 목록
    print("📱 연결된 기기:")
    devices = list_devices()
    print(json.dumps(devices, indent=2, ensure_ascii=False))

    if devices.get("devices"):
        print("\n📊 시스템 상태:")
        status = get_system_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))

        print("\n📦 설치된 앱 (상위 10개):")
        apps = list_packages(third_party_only=True)
        if apps.get("packages"):
            for pkg in apps["packages"][:10]:
                print(f"  - {pkg}")
