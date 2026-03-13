"""
UTIC 도시교통정보센터 CCTV

전국 도시 내부 도로 및 주요 지점의 실시간 CCTV 영상 정보를 조회합니다.

데이터 소스 (하이브리드):
  1순위: 실시간 API (http://www.utic.go.kr/map/mapcctv.do) → 16,000+ CCTV
  2순위: 로컬 JSON 캐시 (utic_cctv_list.json) → API 실패 시 폴백

필요 환경변수:
  - UTIC_API_KEY: 도시교통정보센터 인증키

API 호출 조건:
  - Referer 헤더 필수: http://www.utic.go.kr/guide/cctvOpenData.do
  - 키 기반 인증 (등록된 IP 대역에서만 동작)
"""

import json
import os
import re
import time
import urllib.request
from pathlib import Path
from typing import List, Dict, Optional

from common import calculate_distance, success_response, error_response

# 설정
UTIC_API_KEY = os.environ.get("UTIC_API_KEY", "")
UTIC_API_URL = "http://www.utic.go.kr/map/mapcctv.do"
UTIC_STREAM_JSP = "http://www.utic.go.kr/jsp/map/openDataCctvStream.jsp"
CACHE_FILE = Path(__file__).parent / "utic_cctv_list.json"

# API 결과 메모리 캐시 (TTL: 10분)
_api_cache = None
_api_cache_time = 0
_API_CACHE_TTL = 600  # 10분

# 로컬 파일 캐시
_file_cache = None

# m3u8 URL 캐시 — KIND → m3u8 URL 템플릿을 캐싱
_m3u8_cache: Dict[str, Optional[str]] = {}


def _fetch_from_api() -> Optional[List[Dict]]:
    """UTIC 실시간 API에서 전체 CCTV 목록 조회"""
    global _api_cache, _api_cache_time

    now = time.time()
    if _api_cache is not None and (now - _api_cache_time) < _API_CACHE_TTL:
        return _api_cache

    if not UTIC_API_KEY:
        return None

    try:
        url = f"{UTIC_API_URL}?key={UTIC_API_KEY}"
        req = urllib.request.Request(url, headers={
            "Referer": "http://www.utic.go.kr/guide/cctvOpenData.do",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if isinstance(data, list) and len(data) > 0:
            _api_cache = data
            _api_cache_time = now
            print(f"[UTIC] 실시간 API 로드 성공: {len(data)}대 CCTV")
            return data
        else:
            print(f"[UTIC] API 응답이 비어있음")
            return None

    except Exception as e:
        print(f"[UTIC] API 호출 실패 (폴백 사용): {e}")
        return None


def _load_file_cache() -> List[Dict]:
    """로컬 JSON 캐시 파일 로드 (폴백)"""
    global _file_cache
    if _file_cache is not None:
        return _file_cache

    if not CACHE_FILE.exists():
        return []

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            _file_cache = json.load(f)
        print(f"[UTIC] 로컬 캐시 로드: {len(_file_cache)}대 CCTV")
        return _file_cache
    except Exception as e:
        print(f"[UTIC] 캐시 파일 로드 오류: {e}")
        return []


def _load_data() -> List[Dict]:
    """CCTV 데이터 로드 (하이브리드: API 우선, 캐시 폴백)"""
    api_data = _fetch_from_api()
    if api_data:
        return api_data
    return _load_file_cache()


def _extract_m3u8_from_jsp(cctv: Dict) -> Optional[str]:
    """JSP 페이지를 호출해 실제 m3u8 스트림 URL을 추출한다.

    결과는 _m3u8_cache에 KIND 단위로 캐싱된다.
    캐시 키는 KIND이며, 같은 도시의 CCTV는 동일한 URL 패턴을 공유한다.
    """
    kind = cctv.get("KIND", "")

    # 캐시 히트
    if kind in _m3u8_cache:
        cached = _m3u8_cache[kind]
        if cached is None:
            return None
        # 캐시된 URL은 샘플 CCTV의 것이므로, 현재 CCTV의 파라미터로 치환이 필요할 수 있다.
        # 하지만 각 CCTV마다 고유 URL이므로 캐시는 "이 KIND가 m3u8을 지원하는지" 여부만 판단용으로 사용.
        # 실제 URL은 매번 JSP에서 추출해야 한다. → 아래로 진행

    try:
        import urllib.parse
        params = {
            "key": UTIC_API_KEY,
            "cctvid": cctv.get("CCTVID", ""),
            "cctvName": cctv.get("CCTVNAME", ""),
            "kind": kind,
            "cctvip": cctv.get("CCTVIP", ""),
            "cctvch": str(cctv.get("CH", "")),
            "id": cctv.get("ID", ""),
            "cctvpasswd": cctv.get("PASSWD", ""),
            "cctvport": cctv.get("PORT", ""),
        }
        jsp_url = f"{UTIC_STREAM_JSP}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(jsp_url, headers={
            "Referer": "http://www.utic.go.kr/guide/cctvOpenData.do",
            "User-Agent": "Mozilla/5.0",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # m3u8 URL 추출 (211.236.72.94 주석 URL 제외)
        m3u8_urls = re.findall(r"(https?://[^'\"<>\s]+\.m3u8[^'\"<>\s]*)", html)
        m3u8_urls = [u for u in m3u8_urls if "211.236.72.94" not in u]

        if m3u8_urls:
            result = m3u8_urls[0]
            _m3u8_cache[kind] = result  # KIND가 m3u8 지원함을 기록
            return result
        else:
            _m3u8_cache[kind] = None  # KIND가 m3u8 미지원
            return None

    except Exception as e:
        print(f"[UTIC] m3u8 추출 실패 ({kind}): {e}")
        return None


def _build_stream_url(cctv: Dict) -> str:
    """CCTV 스트리밍 URL 생성.

    m3u8 직접 URL이 있으면 그것을, 없으면 JSP URL을 반환한다.
    """
    # 먼저 m3u8 직접 추출 시도
    m3u8_url = _extract_m3u8_from_jsp(cctv)
    if m3u8_url:
        return m3u8_url

    # m3u8 없으면 JSP URL 반환 (폴백)
    import urllib.parse
    params = {
        "key": UTIC_API_KEY,
        "cctvid": cctv.get("CCTVID", ""),
        "cctvName": cctv.get("CCTVNAME", ""),
        "kind": cctv.get("KIND", ""),
        "cctvip": cctv.get("CCTVIP", ""),
        "cctvch": str(cctv.get("CH", "")),
        "id": cctv.get("ID", ""),
        "cctvpasswd": cctv.get("PASSWD", ""),
        "cctvport": cctv.get("PORT", ""),
    }
    return f"{UTIC_STREAM_JSP}?{urllib.parse.urlencode(params)}"


def _format_cctv(cctv: Dict, distance: float = None) -> Dict:
    """CCTV 정보 포맷팅"""
    result = {
        "name": cctv.get("CCTVNAME", "알 수 없음"),
        "url": _build_stream_url(cctv),
        "lat": float(cctv.get("YCOORD", 0)),
        "lng": float(cctv.get("XCOORD", 0)),
        "road_type": "도시도로",
        "center": cctv.get("CENTERNAME", ""),
        "kind": cctv.get("KIND", ""),
        "source": "utic_traffic",
        "stream_id": cctv.get("STRMID", cctv.get("CCTVID", "")),
        "has_video": cctv.get("MOVIE", "N") == "Y",
    }
    if distance is not None:
        result["distance_km"] = round(distance, 2)
    return result


def search_cctv(min_x: float, max_x: float, min_y: float, max_y: float,
                limit: int = 50) -> str:
    """지정한 영역 내의 CCTV 목록 조회"""
    try:
        data = _load_data()
        results = []
        for c in data:
            x = float(c.get("XCOORD", 0))
            y = float(c.get("YCOORD", 0))
            if min_x <= x <= max_x and min_y <= y <= max_y:
                results.append(_format_cctv(c))
                if len(results) >= limit:
                    break

        if not results:
            return success_response(
                count=0,
                message="해당 영역에 UTIC CCTV가 없습니다.",
                cctvs=[]
            )

        return success_response(
            count=len(results),
            total_available=len(data),
            cctvs=results
        )
    except Exception as e:
        return error_response(str(e))


def get_nearby_cctv(lat: float, lng: float, radius: float = 5.0,
                    count: int = 10) -> str:
    """특정 좌표에서 가장 가까운 CCTV 찾기"""
    try:
        data = _load_data()
        results = []

        for c in data:
            c_lat = float(c.get("YCOORD", 0))
            c_lng = float(c.get("XCOORD", 0))
            dist = calculate_distance(lat, lng, c_lat, c_lng)
            if dist <= radius:
                results.append((dist, c))

        results.sort(key=lambda x: x[0])
        top_cctvs = results[:count]
        formatted = [_format_cctv(c, dist) for dist, c in top_cctvs]

        return success_response(
            count=len(formatted),
            search_location={"lat": lat, "lng": lng},
            radius_km=radius,
            total_available=len(data),
            cctvs=formatted
        )
    except Exception as e:
        return error_response(str(e))


def get_cctv_by_name(keyword: str, limit: int = 10) -> str:
    """CCTV 이름으로 검색"""
    try:
        data = _load_data()
        keyword_lower = keyword.lower()

        matched = []
        for c in data:
            name = c.get("CCTVNAME", "").lower()
            center = c.get("CENTERNAME", "").lower()
            if keyword_lower in name or keyword_lower in center:
                matched.append(c)

        if not matched:
            return success_response(
                count=0,
                message=f"'{keyword}'를 포함하는 UTIC CCTV를 찾을 수 없습니다.",
                cctvs=[]
            )

        matched = matched[:limit]
        formatted = [_format_cctv(c) for c in matched]
        return success_response(
            count=len(formatted),
            keyword=keyword,
            total_available=len(data),
            cctvs=formatted
        )
    except Exception as e:
        return error_response(str(e))


def refresh_cache() -> str:
    """API에서 최신 데이터를 가져와 로컬 캐시 갱신"""
    global _api_cache, _api_cache_time, _file_cache

    _api_cache = None
    _api_cache_time = 0

    api_data = _fetch_from_api()
    if not api_data:
        return error_response("API 호출 실패. UTIC_API_KEY와 네트워크를 확인하세요.")

    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(api_data, f, ensure_ascii=False, indent=2)
        _file_cache = api_data
        return success_response(
            message=f"캐시 갱신 완료: {len(api_data)}대 CCTV",
            count=len(api_data)
        )
    except Exception as e:
        return error_response(f"캐시 파일 저장 실패: {e}")


def get_data_stats() -> str:
    """현재 데이터 소스 상태 정보"""
    data = _load_data()
    is_api = _api_cache is not None and (time.time() - _api_cache_time) < _API_CACHE_TTL

    centers = {}
    for c in data:
        center = c.get("CENTERNAME", "기타")
        centers[center] = centers.get(center, 0) + 1

    top_centers = sorted(centers.items(), key=lambda x: -x[1])[:10]

    return success_response(
        total_cctv=len(data),
        data_source="실시간 API" if is_api else "로컬 캐시",
        api_key_configured=bool(UTIC_API_KEY),
        cache_ttl_seconds=_API_CACHE_TTL,
        top_centers=[{"name": n, "count": c} for n, c in top_centers]
    )
