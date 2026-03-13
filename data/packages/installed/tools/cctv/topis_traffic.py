"""
TOPIS 서울교통정보시스템 CCTV

서울시 도로 교통 CCTV 실시간 HLS 스트림을 제공합니다.
API 키 불필요, IP 제한 없음.

API:
  - 목록: https://topis.seoul.go.kr/map/cctv/selectCctvList.do
  - 상세(HLS URL): https://topis.seoul.go.kr/map/selectCctvInfo.do
"""

import json
import time
import urllib.request
from typing import List, Dict, Optional

from common import calculate_distance, success_response, error_response

TOPIS_LIST_URL = "https://topis.seoul.go.kr/map/cctv/selectCctvList.do"
TOPIS_INFO_URL = "https://topis.seoul.go.kr/map/selectCctvInfo.do"
TOPIS_REFERER = "https://topis.seoul.go.kr/map/openCctvMap.do"

# 전체 CCTV 목록 캐시 (TTL: 30분)
_list_cache: Optional[List[Dict]] = None
_list_cache_time = 0
_LIST_CACHE_TTL = 1800

# HLS URL 캐시 — camId → hlsUrl
_hls_cache: Dict[str, str] = {}


def _headers() -> dict:
    return {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Referer": TOPIS_REFERER,
        "Content-Type": "application/x-www-form-urlencoded",
    }


def _fetch_list(keyword: str = "") -> List[Dict]:
    """TOPIS CCTV 목록 조회"""
    global _list_cache, _list_cache_time

    # 전체 목록 캐시 (키워드 없을 때만)
    if not keyword:
        now = time.time()
        if _list_cache is not None and (now - _list_cache_time) < _LIST_CACHE_TTL:
            return _list_cache

    try:
        body = f"cctvName={urllib.request.quote(keyword)}".encode("utf-8")
        req = urllib.request.Request(TOPIS_LIST_URL, data=body, headers=_headers())
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        rows = data.get("rows", [])

        if not keyword and rows:
            _list_cache = rows
            _list_cache_time = time.time()
            print(f"[TOPIS] 목록 로드: {len(rows)}대 CCTV")

        return rows

    except Exception as e:
        print(f"[TOPIS] 목록 조회 실패: {e}")
        return []


def _get_hls_url(cam_id: str) -> Optional[str]:
    """camId로 HLS 스트림 URL 조회"""
    if cam_id in _hls_cache:
        return _hls_cache[cam_id]

    try:
        body = f"camId={cam_id}&cctvSourceCd=HP".encode("utf-8")
        req = urllib.request.Request(TOPIS_INFO_URL, data=body, headers=_headers())
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        rows = data.get("rows", [])
        if rows:
            hls_url = rows[0].get("hlsUrl", "") or rows[0].get("hlsUrlOri", "")
            if hls_url:
                _hls_cache[cam_id] = hls_url
                return hls_url

    except Exception as e:
        print(f"[TOPIS] HLS URL 조회 실패 (camId={cam_id}): {e}")

    return None


def _format_cctv(cam: Dict, distance: float = None) -> Dict:
    """CCTV 정보 포맷팅 (HLS URL 포함)"""
    cam_id = cam.get("camId", "")
    hls_url = _get_hls_url(cam_id)

    result = {
        "name": cam.get("camName", "알 수 없음"),
        "url": hls_url or "",
        "lat": float(cam.get("lat", 0)),
        "lng": float(cam.get("lng", 0)),
        "road_type": "서울시내",
        "center": "TOPIS 서울교통정보시스템",
        "source": "topis",
        "cam_id": cam_id,
        "has_video": bool(hls_url),
    }
    if distance is not None:
        result["distance_km"] = round(distance, 2)
    return result


def get_cctv_by_name(keyword: str, limit: int = 10) -> str:
    """CCTV 이름으로 검색"""
    try:
        rows = _fetch_list(keyword)

        if not rows:
            return success_response(
                count=0,
                message=f"'{keyword}'에 해당하는 서울 CCTV를 찾을 수 없습니다.",
                cctvs=[]
            )

        formatted = [_format_cctv(r) for r in rows[:limit]]
        # HLS URL 없는 것 제거
        formatted = [c for c in formatted if c.get("url")]

        return success_response(
            count=len(formatted),
            keyword=keyword,
            cctvs=formatted
        )
    except Exception as e:
        return error_response(str(e))


def get_nearby_cctv(lat: float, lng: float, radius: float = 5.0,
                    count: int = 10) -> str:
    """좌표 기준 가까운 서울 CCTV"""
    try:
        all_cams = _fetch_list("")  # 전체 목록

        results = []
        for cam in all_cams:
            c_lat = float(cam.get("lat", 0))
            c_lng = float(cam.get("lng", 0))
            dist = calculate_distance(lat, lng, c_lat, c_lng)
            if dist <= radius:
                results.append((dist, cam))

        results.sort(key=lambda x: x[0])
        top = results[:count]
        formatted = [_format_cctv(c, dist) for dist, c in top]
        formatted = [c for c in formatted if c.get("url")]

        return success_response(
            count=len(formatted),
            search_location={"lat": lat, "lng": lng},
            radius_km=radius,
            cctvs=formatted
        )
    except Exception as e:
        return error_response(str(e))


def get_data_stats() -> str:
    """TOPIS 데이터 통계"""
    all_cams = _fetch_list("")
    return success_response(
        total_cctv=len(all_cams),
        data_source="TOPIS 서울교통정보시스템",
        api_key_required=False,
    )
