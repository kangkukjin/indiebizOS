"""
기기 정보 및 시스템 상태 모듈
기기 목록, 상세 정보, 배터리, 저장소, 권한 관리
"""

import sys
from pathlib import Path
from typing import Optional

_current_dir = Path(__file__).parent
if str(_current_dir) not in sys.path:
    sys.path.insert(0, str(_current_dir))

from adb_core import run_adb


def list_devices() -> dict:
    """연결된 안드로이드 기기 목록 조회"""
    result = run_adb(["devices", "-l"])

    if not result["success"]:
        return result

    devices = []
    lines = result["stdout"].split("\n")

    for line in lines[1:]:
        if not line.strip():
            continue

        parts = line.split()
        if len(parts) >= 2:
            device_id = parts[0]
            status = parts[1]

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
        "message": f"{len(devices)}개의 기기가 연결되어 있습니다." if devices else "연결된 기기가 없습니다. USB 디버깅이 켜져 있는지 확인하세요."
    }


def get_device_info(device_id: Optional[str] = None) -> dict:
    """기기 상세 정보 조회"""
    if not device_id:
        devices = list_devices()
        if not devices.get("success") or not devices.get("devices"):
            return {"success": False, "message": "연결된 기기가 없습니다."}
        device_id = devices["devices"][0]["id"]

    info = {}

    # 여러 속성을 한 번에 가져오기 위한 헬퍼
    props = {
        "model": "ro.product.model",
        "manufacturer": "ro.product.manufacturer",
        "android_version": "ro.build.version.release",
        "sdk_version": "ro.build.version.sdk",
        "serial": "ro.serialno"
    }

    for key, prop in props.items():
        res = run_adb(["shell", "getprop", prop], device_id)
        if res["success"]:
            info[key] = res["stdout"]

    return {
        "success": True,
        "device_id": device_id,
        "info": info,
        "message": f"{info.get('manufacturer', '')} {info.get('model', '')} (Android {info.get('android_version', '')})"
    }


def get_battery_status(device_id: Optional[str] = None) -> dict:
    """배터리 상태 조회"""
    result = run_adb(["shell", "dumpsys", "battery"], device_id)

    if not result["success"]:
        return result

    battery = {}
    for line in result["stdout"].split("\n"):
        line = line.strip()
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip().lower().replace(" ", "_")
            value = value.strip()
            battery[key] = value

    level = battery.get("level", "?")
    status_map = {"1": "알 수 없음", "2": "충전 중", "3": "방전 중", "4": "방전 안 함", "5": "완충"}
    charging = status_map.get(battery.get("status", ""), "알 수 없음")

    return {
        "success": True,
        "level": int(level) if level.isdigit() else level,
        "charging": charging,
        "temperature": f"{int(battery.get('temperature', 0)) / 10}°C" if battery.get('temperature', '').isdigit() else None,
        "health": battery.get("health", "Unknown"),
        "message": f"배터리: {level}% ({charging})"
    }


def get_storage_info(device_id: Optional[str] = None) -> dict:
    """저장 공간 정보 조회"""
    result = run_adb(["shell", "df", "-h", "/data"], device_id)

    if not result["success"]:
        return result

    lines = result["stdout"].split("\n")
    if len(lines) < 2:
        return {"success": False, "message": "저장 공간 정보 파싱 실패 (출력 부족)"}

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

    return {"success": False, "message": "저장 공간 정보 파싱 실패 (포맷 불일치)"}


def get_system_status(device_id: Optional[str] = None) -> dict:
    """시스템 전체 상태 조회"""
    battery = get_battery_status(device_id)
    storage = get_storage_info(device_id)
    device = get_device_info(device_id)

    return {
        "success": True,
        "device_id": device_id,
        "device": device.get("info", {}),
        "battery": battery if battery.get("success") else None,
        "storage": storage.get("storage") if storage.get("success") else None,
        "message": f"{device.get('message', '')} | {battery.get('message', '')} | {storage.get('message', '')}"
    }


def grant_adb_permissions(device_id: Optional[str] = None) -> dict:
    """ADB shell에 SMS, 통화기록, 연락처 읽기/쓰기 권한 부여

    Android 10 이상에서는 ADB를 통한 content provider 접근이 제한됩니다.
    이 함수는 appops를 사용하여 shell에 필요한 권한을 부여합니다.

    주의: 폰을 재시작하면 권한이 초기화될 수 있습니다.
    """
    permissions = [
        # 읽기 권한
        ("READ_SMS", "SMS 읽기"),
        ("READ_CALL_LOG", "통화 기록 읽기"),
        ("READ_CONTACTS", "연락처 읽기"),
        # 쓰기 권한 (삭제/편집용)
        ("WRITE_SMS", "SMS 쓰기/삭제"),
        ("WRITE_CALL_LOG", "통화 기록 쓰기/삭제"),
        ("WRITE_CONTACTS", "연락처 쓰기/삭제"),
    ]

    results = []
    all_success = True

    for perm, desc in permissions:
        result = run_adb([
            "shell", "appops", "set", "com.android.shell", perm, "allow"
        ], device_id, timeout=10)

        if result["success"]:
            results.append({"permission": perm, "description": desc, "status": "granted"})
        else:
            results.append({"permission": perm, "description": desc, "status": "failed", "error": result.get("message", "")})
            all_success = False

    return {
        "success": all_success,
        "permissions": results,
        "message": "모든 권한이 부여되었습니다. 이제 SMS, 통화기록, 연락처를 읽고 삭제할 수 있습니다." if all_success else "일부 권한 부여에 실패했습니다.",
        "note": "폰을 재시작하면 권한이 초기화될 수 있으므로 다시 실행해야 합니다."
    }


def check_adb_permissions(device_id: Optional[str] = None) -> dict:
    """현재 ADB shell 권한 상태 확인 (읽기/쓰기 모두)"""
    permissions = [
        # 읽기 권한
        ("READ_SMS", "SMS 읽기"),
        ("READ_CALL_LOG", "통화 기록 읽기"),
        ("READ_CONTACTS", "연락처 읽기"),
        # 쓰기 권한
        ("WRITE_SMS", "SMS 쓰기/삭제"),
        ("WRITE_CALL_LOG", "통화 기록 쓰기/삭제"),
        ("WRITE_CONTACTS", "연락처 쓰기/삭제"),
    ]

    results = []
    for perm, desc in permissions:
        result = run_adb([
            "shell", "appops", "get", "com.android.shell", perm
        ], device_id, timeout=10)

        if result["success"]:
            stdout = result.get("stdout", "")
            is_allowed = "allow" in stdout.lower()
            results.append({
                "permission": perm,
                "description": desc,
                "allowed": is_allowed,
                "raw": stdout.strip()
            })
        else:
            results.append({
                "permission": perm,
                "description": desc,
                "allowed": False,
                "error": result.get("message", "")
            })

    all_allowed = all(r.get("allowed", False) for r in results)
    read_allowed = all(r.get("allowed", False) for r in results if r["permission"].startswith("READ_"))
    write_allowed = all(r.get("allowed", False) for r in results if r["permission"].startswith("WRITE_"))

    return {
        "success": True,
        "permissions": results,
        "all_granted": all_allowed,
        "read_granted": read_allowed,
        "write_granted": write_allowed,
        "message": "모든 읽기/쓰기 권한이 허용되어 있습니다." if all_allowed else
                   f"읽기: {'✅' if read_allowed else '❌'}, 쓰기: {'✅' if write_allowed else '❌'}. 'android_grant_permissions'를 실행하세요."
    }
