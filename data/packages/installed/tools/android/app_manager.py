"""
앱 관리 모듈
앱 목록, 상세 정보, 용량, 사용량 통계, 삭제
"""

import sys
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

_current_dir = Path(__file__).parent
if str(_current_dir) not in sys.path:
    sys.path.insert(0, str(_current_dir))

from adb_core import run_adb


def list_packages(device_id: Optional[str] = None, third_party_only: bool = True) -> dict:
    """설치된 앱 목록 조회"""
    args = ["shell", "pm", "list", "packages"]
    if third_party_only:
        args.append("-3")

    result = run_adb(args, device_id)

    if not result["success"]:
        return result

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


def get_app_sizes(device_id: Optional[str] = None, limit: int = 20) -> dict:
    """앱별 용량 조회 (상위 N개)"""
    packages_result = list_packages(device_id, third_party_only=True)
    if not packages_result["success"]:
        return packages_result

    app_sizes = []
    # 시간 절약을 위해 상위 30개 패키지만 샘플링하여 크기 확인
    for package in packages_result["packages"][:30]:
        # 앱 데이터 경로 크기 확인
        result = run_adb(["shell", "du", "-sh", f"/data/data/{package}"], device_id, timeout=5)
        if result["success"] and result["stdout"]:
            parts = result["stdout"].split()
            if parts:
                size = parts[0]
                app_sizes.append({"package": package, "size": size})

    def parse_size(s):
        s = s.upper()
        if "G" in s: return float(s.replace("G", "")) * 1024
        if "M" in s: return float(s.replace("M", ""))
        if "K" in s: return float(s.replace("K", "")) / 1024
        return 0

    app_sizes.sort(key=lambda x: parse_size(x["size"]), reverse=True)

    return {
        "success": True,
        "apps": app_sizes[:limit],
        "message": f"용량 상위 {min(limit, len(app_sizes))}개 앱 정보"
    }


def get_app_usage_stats(device_id: Optional[str] = None, days: int = 1) -> dict:
    """앱 사용량 통계 조회 (ACTIVITY_RESUMED/PAUSED 이벤트 기반 계산)

    Args:
        days: 조회 기간 (1=24시간, 7=일주일 등). 기본 1일.
    """
    result = run_adb([
        "shell", "dumpsys", "usagestats"
    ], device_id, timeout=60)

    if not result["success"]:
        return result

    # 앱별 사용 시간 계산 (ACTIVITY_RESUMED ~ PAUSED 간격)
    apps = {}
    active_sessions = {}  # 현재 활성 세션 추적

    for line in result["stdout"].split("\n"):
        line = line.strip()

        # ACTIVITY_RESUMED: 앱이 포그라운드로 올라옴
        if "type=ACTIVITY_RESUMED" in line:
            match = re.search(r'time="([^"]+)".*package=(\S+)', line)
            if match:
                time_str, package = match.groups()
                # 패키지명에서 불필요한 부분 제거
                package = package.split()[0]
                try:
                    timestamp = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                    active_sessions[package] = timestamp

                    if package not in apps:
                        apps[package] = {
                            "package": package,
                            "total_time_ms": 0,
                            "session_count": 0,
                            "last_used": None
                        }
                    apps[package]["last_used"] = time_str
                except:
                    pass

        # ACTIVITY_PAUSED 또는 ACTIVITY_STOPPED: 앱이 백그라운드로
        elif "type=ACTIVITY_PAUSED" in line or "type=ACTIVITY_STOPPED" in line:
            match = re.search(r'time="([^"]+)".*package=(\S+)', line)
            if match:
                time_str, package = match.groups()
                package = package.split()[0]
                if package in active_sessions:
                    try:
                        end_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                        start_time = active_sessions[package]
                        duration_ms = int((end_time - start_time).total_seconds() * 1000)

                        if duration_ms > 0 and duration_ms < 3600000 * 12:  # 12시간 이상은 무시 (비정상)
                            apps[package]["total_time_ms"] += duration_ms
                            apps[package]["session_count"] += 1

                        del active_sessions[package]
                    except:
                        pass

    # 사용 시간 포맷팅
    for pkg, data in apps.items():
        ms = data["total_time_ms"]
        hours = ms // 3600000
        minutes = (ms % 3600000) // 60000
        seconds = (ms % 60000) // 1000

        if hours > 0:
            data["total_time_formatted"] = f"{hours}시간 {minutes}분"
        elif minutes > 0:
            data["total_time_formatted"] = f"{minutes}분 {seconds}초"
        else:
            data["total_time_formatted"] = f"{seconds}초"

        data["total_time"] = ms  # 하위 호환성

    # 사용자 앱만 필터링 (시스템 앱 제외)
    user_packages = list_packages(device_id, third_party_only=True)
    if user_packages.get("success"):
        user_pkg_set = set(user_packages.get("packages", []))
        filtered_apps = {k: v for k, v in apps.items() if k in user_pkg_set}
    else:
        filtered_apps = apps

    # 사용 시간 기준 정렬
    sorted_apps = sorted(filtered_apps.values(), key=lambda x: x.get("total_time_ms", 0), reverse=True)

    # 사용 시간이 0인 앱 제외
    sorted_apps = [app for app in sorted_apps if app.get("total_time_ms", 0) > 0]

    return {
        "success": True,
        "apps": sorted_apps[:50],
        "count": len(sorted_apps),
        "period": "최근 24시간",
        "message": f"최근 24시간 동안 {len(sorted_apps)}개 앱 사용"
    }


def get_app_info(package_name: str, device_id: Optional[str] = None) -> dict:
    """특정 앱의 상세 정보 조회"""
    # 앱 정보 가져오기
    result = run_adb([
        "shell", "dumpsys", "package", package_name
    ], device_id, timeout=15)

    if not result["success"]:
        return result

    info = {
        "package": package_name,
        "version": None,
        "install_time": None,
        "update_time": None,
        "size": None
    }

    for line in result["stdout"].split("\n"):
        line = line.strip()

        if "versionName=" in line:
            match = re.search(r'versionName=(\S+)', line)
            if match:
                info["version"] = match.group(1)

        if "firstInstallTime=" in line:
            match = re.search(r'firstInstallTime=(.+)', line)
            if match:
                info["install_time"] = match.group(1).strip()

        if "lastUpdateTime=" in line:
            match = re.search(r'lastUpdateTime=(.+)', line)
            if match:
                info["update_time"] = match.group(1).strip()

    # 앱 크기 가져오기
    size_result = run_adb(["shell", "du", "-sh", f"/data/data/{package_name}"], device_id, timeout=5)
    if size_result["success"] and size_result["stdout"]:
        parts = size_result["stdout"].split()
        if parts:
            info["size"] = parts[0]

    # 앱 이름 가져오기 (라벨)
    label_result = run_adb([
        "shell", "cmd", "package", "resolve-activity",
        "--brief", f"{package_name}"
    ], device_id, timeout=5)

    return {
        "success": True,
        "info": info,
        "message": f"{package_name} 앱 정보"
    }


def uninstall_app(package_name: str, device_id: Optional[str] = None) -> dict:
    """앱 삭제 (사용자 앱만 가능)"""
    # 시스템 앱인지 확인
    check_result = run_adb([
        "shell", "pm", "list", "packages", "-s"
    ], device_id)

    if check_result["success"]:
        system_packages = check_result["stdout"]
        if f"package:{package_name}" in system_packages:
            return {
                "success": False,
                "message": f"{package_name}은(는) 시스템 앱이라 삭제할 수 없습니다."
            }

    # 앱 삭제 실행
    result = run_adb(["uninstall", package_name], device_id, timeout=30)

    if not result["success"]:
        return result

    if "Success" in result.get("stdout", ""):
        return {
            "success": True,
            "package": package_name,
            "message": f"{package_name} 앱이 삭제되었습니다."
        }
    else:
        return {
            "success": False,
            "package": package_name,
            "message": f"앱 삭제 실패: {result.get('stdout', '')} {result.get('stderr', '')}"
        }


def get_apps_with_details(device_id: Optional[str] = None, limit: int = 50, offset: int = 0) -> dict:
    """앱 목록과 상세 정보 (용량, 사용량) 조회

    Args:
        limit: 조회 개수
        offset: 건너뛸 개수 (페이지네이션용)
    """
    # 사용자 앱 목록
    packages_result = list_packages(device_id, third_party_only=True)
    if not packages_result["success"]:
        return packages_result

    all_packages = packages_result["packages"]
    total_count = len(all_packages)

    # offset과 limit 적용
    target_packages = all_packages[offset:offset + limit]

    # 사용량 정보
    usage_result = get_app_usage_stats(device_id)
    usage_map = {}
    if usage_result.get("success"):
        for app in usage_result.get("apps", []):
            usage_map[app["package"]] = app

    apps = []
    for package in target_packages:
        app_info = {
            "package": package,
            "name": package.split(".")[-1],  # 기본 이름
            "size": None,
            "last_used": None,
            "total_time_formatted": None
        }

        # 크기 조회
        size_result = run_adb(["shell", "du", "-sh", f"/data/data/{package}"], device_id, timeout=3)
        if size_result["success"] and size_result["stdout"]:
            parts = size_result["stdout"].split()
            if parts:
                app_info["size"] = parts[0]

        # 사용량 정보 병합
        if package in usage_map:
            app_info["last_used"] = usage_map[package].get("last_used")
            app_info["total_time_formatted"] = usage_map[package].get("total_time_formatted")

        apps.append(app_info)

    return {
        "success": True,
        "apps": apps,
        "count": len(apps),
        "total": total_count,
        "offset": offset,
        "has_more": offset + len(apps) < total_count,
        "message": f"전체 {total_count}개 중 {offset + 1}~{offset + len(apps)}번째" if apps else f"{total_count}개의 앱 정보"
    }
