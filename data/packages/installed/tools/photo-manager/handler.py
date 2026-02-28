"""
handler.py - Photo Manager 도구 핸들러
AI 에이전트에서 호출되는 도구 실행 핸들러
"""

import os
import sys
import json
import requests
from typing import Dict, Any

# 현재 디렉토리를 경로에 추가
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

import photo_db
import scanner


# API 서버 URL
API_BASE_URL = "http://127.0.0.1:8765"


def _resolve_scan_path(params: Dict[str, Any]) -> str:
    """
    스캔 경로 자동 해석.
    1. params["path"]가 기존 스캔 경로와 일치하면 그대로 사용
    2. 유효한 디렉토리이면 사용
    3. 위 모두 실패 시 사진 수가 가장 많은 스캔 자동 선택
    반환: 스캔 경로 문자열 또는 None
    """
    path = params.get("path")

    result = photo_db.list_scans()
    scans = result.get("scans", []) if result.get("success") else []

    if path:
        expanded = os.path.abspath(os.path.expanduser(path))
        # 스캔된 경로와 정확히 매칭?
        for scan in scans:
            if scan["root_path"] == expanded:
                return expanded
        # 유효한 디렉토리이면 사용
        if os.path.isdir(expanded):
            return expanded

    # 자동 선택: 사진 수가 가장 많은 스캔
    if scans:
        best = max(scans, key=lambda s: s.get("photo_count", 0))
        return best["root_path"]

    return None


def execute(command: str, params: Dict[str, Any], project_path: str = ".") -> Dict[str, Any]:
    """
    도구 명령 실행

    Args:
        command: 실행할 명령어
        params: 명령어 파라미터
        project_path: 프로젝트 경로 (사용하지 않지만 호환성을 위해 받음)

    Returns:
        실행 결과
    """
    try:
        if command == "scan_photos":
            return scan_photos(params)
        elif command == "list_scans":
            return list_scans(params)
        elif command == "get_gallery":
            return get_gallery(params)
        elif command == "find_duplicates":
            return find_duplicates(params)
        elif command == "get_stats":
            return get_stats(params)
        elif command == "get_timeline":
            return get_timeline(params)
        elif command == "open_photo_manager":
            return open_photo_manager(params)
        else:
            return {"success": False, "error": f"알 수 없는 명령어: {command}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def scan_photos(params: Dict[str, Any]) -> Dict[str, Any]:
    """사진/동영상 폴더 스캔"""
    path = params.get("path")
    if not path:
        return {"success": False, "error": "경로를 지정해주세요."}

    path = os.path.expanduser(path)
    path = os.path.abspath(path)

    if not os.path.exists(path):
        return {"success": False, "error": f"경로가 존재하지 않습니다: {path}"}

    if not os.path.isdir(path):
        return {"success": False, "error": f"디렉토리가 아닙니다: {path}"}

    # 스캔 이름 추출
    if path.startswith('/Volumes/'):
        parts = path.split('/')
        if len(parts) == 3:
            scan_name = parts[2]
        elif len(parts) > 3:
            scan_name = f"{parts[2]}/{parts[-1]}"
        else:
            scan_name = 'Unknown'
    else:
        scan_name = os.path.basename(path) or 'LocalDisk'

    # DB 초기화 및 스캔 ID 생성
    photo_db.init_db()
    scan_id = photo_db.get_or_create_scan(scan_name, path)

    # 스캔 실행
    result = scanner.scan_media(path, scan_id)

    if result.get("success"):
        return {
            "success": True,
            "message": f"스캔이 완료되었습니다.",
            "summary": {
                "폴더": scan_name,
                "사진": result.get("photo_count", 0),
                "동영상": result.get("video_count", 0),
                "총 용량": f"{result.get('total_size_mb', 0)} MB",
                "오류": result.get("errors_count", 0)
            }
        }
    else:
        return result


def list_scans(params: Dict[str, Any]) -> Dict[str, Any]:
    """스캔된 폴더 목록"""
    result = photo_db.list_scans()

    if result.get("success") and result.get("scans"):
        scans = result["scans"]
        summary = []
        for scan in scans:
            scan_id = scan["id"]
            db_path = os.path.join(photo_db.SCANS_DIR, f"scan_{scan_id}.db")
            summary.append({
                "id": scan_id,
                "이름": scan["name"],
                "경로": scan["root_path"],
                "DB": db_path,
                "사진": scan["photo_count"],
                "동영상": scan["video_count"],
                "용량": f"{scan['total_size_mb']} MB",
                "마지막 스캔": scan["last_scan"]
            })
        return {
            "success": True,
            "message": f"{len(scans)}개의 스캔된 폴더가 있습니다.",
            "scans": summary,
            "tip": "특정 기간/장소 사진 검색은 Python으로 DB에 직접 SQL 쿼리하세요. "
                   "예: sqlite3.connect(DB경로) → SELECT filename, taken_date, gps_lat, gps_lon FROM media_files WHERE taken_date LIKE '2021-04%'"
        }
    else:
        return {
            "success": True,
            "message": "스캔된 폴더가 없습니다. 먼저 scan_photos 명령으로 폴더를 스캔해주세요."
        }


def get_gallery(params: Dict[str, Any]) -> Dict[str, Any]:
    """갤러리 조회"""
    path = _resolve_scan_path(params)
    if not path:
        return {"success": False, "error": "스캔 데이터가 없습니다. 먼저 scan_photos로 폴더를 스캔하세요."}

    page = params.get("page", 1)
    limit = params.get("limit", 50)
    media_type = params.get("media_type")
    sort_by = params.get("sort_by", "taken_date")

    result = photo_db.get_gallery(path, page, limit, media_type, sort_by)

    if result.get("success"):
        items = result.get("items", [])
        total = result.get("total", 0)

        # 요약 정보
        summary = []
        for item in items[:10]:  # 최대 10개만 표시
            summary.append({
                "파일명": item["filename"],
                "타입": "사진" if item["media_type"] == "photo" else "동영상",
                "크기": f"{item['size_mb']} MB",
                "촬영일": item["taken_date"] or item["mtime"],
                "카메라": item.get("camera") or "-"
            })

        return {
            "success": True,
            "message": f"총 {total}개 중 {page}페이지 ({len(items)}개)",
            "items": summary,
            "pagination": {
                "현재 페이지": page,
                "페이지당 개수": limit,
                "전체 개수": total,
                "전체 페이지": (total + limit - 1) // limit
            }
        }
    else:
        return result


def find_duplicates(params: Dict[str, Any]) -> Dict[str, Any]:
    """중복 파일 찾기"""
    path = params.get("path")
    if not path:
        return {"success": False, "error": "경로를 지정해주세요."}

    path = os.path.expanduser(path)
    path = os.path.abspath(path)

    result = photo_db.get_duplicates(path)

    if result.get("success"):
        groups = result.get("groups", [])

        if not groups:
            return {
                "success": True,
                "message": "중복 파일이 없습니다."
            }

        # 상위 5개 그룹만 요약
        summary = []
        for group in groups[:5]:
            files = [f["filename"] for f in group["files"]]
            summary.append({
                "중복 개수": group["count"],
                "낭비 용량": f"{group['wasted_mb']} MB",
                "파일들": files
            })

        return {
            "success": True,
            "message": f"{result.get('total_groups')}개 그룹에서 {result.get('total_duplicates')}개 중복 파일 발견",
            "summary": {
                "중복 그룹 수": result.get("total_groups"),
                "중복 파일 수": result.get("total_duplicates"),
                "낭비 용량": f"{result.get('total_wasted_mb')} MB"
            },
            "groups": summary,
            "tip": "Photo Manager 창을 열어 중복 파일을 시각적으로 확인할 수 있습니다."
        }
    else:
        return result


def get_stats(params: Dict[str, Any]) -> Dict[str, Any]:
    """통계 조회"""
    path = _resolve_scan_path(params)
    if not path:
        return {"success": False, "error": "스캔 데이터가 없습니다. 먼저 scan_photos로 폴더를 스캔하세요."}

    result = photo_db.get_stats(path)

    if result.get("success"):
        # 확장자 통계 요약
        ext_summary = []
        for ext in result.get("extensions", [])[:5]:
            ext_summary.append(f".{ext['extension']}: {ext['count']}개 ({ext['size_mb']} MB)")

        # 카메라 통계 요약
        cam_summary = []
        for cam in result.get("cameras", [])[:5]:
            cam_summary.append(f"{cam['camera']}: {cam['count']}개")

        return {
            "success": True,
            "message": f"{result.get('name')} 폴더 통계",
            "summary": {
                "사진": result.get("photo_count"),
                "동영상": result.get("video_count"),
                "총 용량": f"{result.get('total_size_mb')} MB",
                "마지막 스캔": result.get("last_scan")
            },
            "확장자별": ext_summary,
            "카메라별": cam_summary if cam_summary else ["카메라 정보 없음"]
        }
    else:
        return result


def get_timeline(params: Dict[str, Any]) -> Dict[str, Any]:
    """타임라인 조회"""
    path = _resolve_scan_path(params)
    if not path:
        return {"success": False, "error": "스캔 데이터가 없습니다. 먼저 scan_photos로 폴더를 스캔하세요."}

    result = photo_db.get_timeline(path)

    if result.get("success"):
        data = result.get("data", [])

        if not data:
            return {
                "success": True,
                "message": "타임라인 데이터가 없습니다."
            }

        # 최근 12개월만 표시
        summary = []
        for item in data[:12]:
            summary.append({
                "월": item.get("month", "알 수 없음"),
                "사진": item.get("photos", 0),
                "동영상": item.get("videos", 0),
                "용량": f"{item.get('size_mb', 0)} MB"
            })

        return {
            "success": True,
            "message": f"최근 {len(summary)}개월 촬영 현황",
            "timeline": summary
        }
    else:
        return result


def open_photo_manager(params: Dict[str, Any]) -> Dict[str, Any]:
    """Photo Manager 창 열기"""
    path = params.get("path")

    try:
        # API를 통해 창 열기 요청
        url = f"{API_BASE_URL}/photo/open-window"
        if path:
            url += f"?path={path}"

        response = requests.post(url, timeout=5)
        data = response.json()

        if data.get("status") == "requested":
            return {
                "success": True,
                "message": "Photo Manager 창 열기 요청을 보냈습니다.",
                "tip": "잠시 후 Photo Manager 창이 열립니다."
            }
        else:
            return {
                "success": False,
                "error": "창 열기 요청 실패"
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"Photo Manager 창을 열 수 없습니다: {str(e)}"
        }


# 직접 실행 시 테스트
if __name__ == "__main__":
    # 테스트 명령
    print("Photo Manager Handler 테스트")
    print("-" * 40)

    # 스캔 목록
    result = execute("list_scans", {})
    print("스캔 목록:", json.dumps(result, ensure_ascii=False, indent=2))
