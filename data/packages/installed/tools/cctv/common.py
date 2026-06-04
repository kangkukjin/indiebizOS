"""
CCTV 패키지 공통 유틸리티
"""

import json
import math
import os

# HTTP 요청 헤더
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
}

# 대한민국 경계
KOREA_BOUNDS = {
    "min_x": 124.0,
    "max_x": 132.0,
    "min_y": 33.0,
    "max_y": 43.0
}


def calculate_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 간의 거리 계산 (km, Haversine 공식)"""
    R = 6371
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def normalize_coords(lat, lng):
    """좌표를 표준 {lat,lng} float로 정규화. 파싱 실패·(0,0)·범위 밖이면 None.

    위치 액션의 좌표 계약(항상 {lat:float, lng:float})을 강제하는 단일 지점.
    """
    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return None
    if lat == 0 and lng == 0:
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
        return None
    return {"lat": lat, "lng": lng}


def is_hls_playable(url: str) -> bool:
    """URL이 hls.js로 재생 가능한 HLS 스트림인지 판단 (재생가능 판정 단일 소스)."""
    if not url:
        return False
    u = url.lower()
    # UTIC JSP 페이지 → m3u8 추출 전엔 재생 불가
    if 'utic.go.kr' in u and '.jsp' in u:
        return False
    return ('.m3u8' in u or 'ktict.co.kr' in u or 'eseoul.go.kr' in u
            or ':1935/' in u or 'streamlock.net' in u)


def success_response(**kwargs) -> str:
    """성공 응답 JSON"""
    result = {"success": True}
    result.update(kwargs)
    return json.dumps(result, ensure_ascii=False)


def error_response(error: str, **kwargs) -> str:
    """에러 응답 JSON"""
    result = {"success": False, "error": error}
    result.update(kwargs)
    return json.dumps(result, ensure_ascii=False)


def get_output_dir(project_path: str = None) -> str:
    """CCTV 캡처 출력 디렉토리 반환"""
    if project_path and os.path.isdir(project_path):
        output_dir = os.path.join(project_path, "outputs", "cctv_captures")
    else:
        # indiebizOS 기본 outputs 사용 (cctv -> tools -> installed -> packages -> data -> indiebizOS)
        base = os.path.abspath(__file__)
        for _ in range(6):
            base = os.path.dirname(base)
        output_dir = os.path.join(base, "outputs", "cctv_captures")
    os.makedirs(output_dir, exist_ok=True)
    return output_dir
