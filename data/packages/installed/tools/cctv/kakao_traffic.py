"""
카카오맵 CCTV 통합 모듈

카카오맵 API를 통해 전국 교통 CCTV에 접근한다.
- 전국 6,892대 CCTV (서울/경기/부산/대구/인천/광주/대전/울산/세종/제주 등 17개 시도)
- API 키 불필요, IP 제한 없음
- 모든 CCTV가 cctvsec.ktict.co.kr 경유 HLS 스트리밍 제공
- ffmpeg 캡처 및 hls.js 재생 가능

소스:
  mltm(국토교통부/고속도로), utic(경찰청/시내도로), jeju(제주자치경찰단),
  gyeonggi(경기도), cheonan(천안시), kbs, suwon_beltway, icheon, 등
"""

import json
import os
import re
import time
import urllib.request
from typing import Dict, List, Optional, Tuple

# ── 상수 ──────────────────────────────────────────────
KAKAO_CCTV_INFO_URL = "https://map.kakao.com/api/cctvs/"
KAKAO_CCTV_URL_API = "https://map.kakao.com/api/cctvs/url/"
KAKAO_CCTV_LIST_URL = "https://map.kakao.com/traffic/cctvListInBox"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://map.kakao.com/",
}

# ── 캐시 ──────────────────────────────────────────────
_CACHE_DIR = os.path.dirname(os.path.abspath(__file__))
_CACHE_FILE = os.path.join(_CACHE_DIR, "kakao_cctv_list.json")

_cctv_list: Optional[List[Dict]] = None
_hls_cache: Dict[str, Tuple[str, float]] = {}   # key → (url, timestamp)
_HLS_CACHE_TTL = 300  # 5분 (URL에 토큰 포함, 만료될 수 있음)


def _load_cctv_list() -> List[Dict]:
    """로컬 캐시에서 CCTV 목록을 로드한다."""
    global _cctv_list
    if _cctv_list is not None:
        return _cctv_list
    if os.path.exists(_CACHE_FILE):
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            _cctv_list = json.load(f)
        print(f"[카카오] 로컬 캐시 로드: {len(_cctv_list)}대 CCTV")
        return _cctv_list
    _cctv_list = []
    return _cctv_list


def _get_hls_url(key: str) -> Optional[str]:
    """카카오맵 API를 호출해 HLS 스트림 URL을 가져온다."""
    # 캐시 확인
    if key in _hls_cache:
        url, ts = _hls_cache[key]
        if time.time() - ts < _HLS_CACHE_TTL:
            return url

    try:
        api_url = f"{KAKAO_CCTV_URL_API}{key}"
        req = urllib.request.Request(api_url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        live_url = data.get("liveUrl", "") or data.get("vodUrl", "")
        if live_url:
            _hls_cache[key] = (live_url, time.time())
            return live_url
    except Exception as e:
        print(f"[카카오] HLS URL 조회 실패 (key={key}): {e}")
    return None


def _format_cctv(cctv: Dict, distance_km: float = None) -> Dict:
    """CCTV 데이터를 통합 포맷으로 변환한다."""
    key = cctv.get("key", "")
    hls_url = _get_hls_url(key)

    result = {
        "name": cctv.get("name", ""),
        "url": hls_url or "",
        "lat": 0,  # Congnamul 좌표 → WGS84 변환은 별도 처리 필요
        "lon": 0,
        "source": "kakao",
        "source_detail": cctv.get("source", ""),
        "source_name": cctv.get("sourceName", "카카오맵"),
        "region": cctv.get("region", ""),
        "road_name": cctv.get("roadName", ""),
        "kakao_key": key,
        "has_video": bool(hls_url),
        "stream_type": "hls" if hls_url else None,
    }
    if distance_km is not None:
        result["distance_km"] = round(distance_km, 2)
    return result


# ── 공개 API ─────────────────────────────────────────

def get_cctv_by_name(query: str, limit: int = 5) -> str:
    """이름으로 CCTV를 검색한다."""
    cctvs = _load_cctv_list()
    if not cctvs:
        return json.dumps({"success": False, "error": "캐시 데이터 없음"}, ensure_ascii=False)

    query_lower = query.lower().strip()

    # 교통 CCTV 소스 우선 (KBS 등 방송소스 후순위)
    _SOURCE_PRIORITY = {
        "utic": 20, "mltm": 18, "jeju": 18,
        "gyeonggi": 15, "cheonan": 15, "suwon_beltway": 15,
        "icheon": 15, "gyeonggi_south": 15, "gyeongin_3rd": 15,
        "mltm_hwaseong": 15, "kbs": 2,
    }

    results = []
    for c in cctvs:
        name = c.get("name", "").lower()
        road = c.get("roadName", "").lower()
        region = c.get("region", "").lower()
        # 이름, 도로명, 지역명 매칭
        if query_lower in name or query_lower in road or query_lower in region:
            score = _SOURCE_PRIORITY.get(c.get("source", ""), 10)
            if query_lower in name:
                score += 10
                if name.startswith(query_lower):
                    score += 5
            if query_lower in road:
                score += 3
            if query_lower in region:
                score += 1
            # liveFlag 보너스
            if c.get("liveFlag"):
                score += 2
            results.append((score, c))

    results.sort(key=lambda x: -x[0])
    top = results[:limit]
    formatted = [_format_cctv(c) for _, c in top]

    return json.dumps({
        "success": True,
        "count": len(formatted),
        "cctvs": formatted,
    }, ensure_ascii=False)


def get_cctv_by_key(key: str) -> str:
    """카카오맵 key로 CCTV 정보와 스트림 URL을 가져온다."""
    try:
        api_url = f"{KAKAO_CCTV_INFO_URL}{key}"
        req = urllib.request.Request(api_url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        hls_url = _get_hls_url(key)
        return json.dumps({
            "success": True,
            "cctv": {
                "name": data.get("name", ""),
                "url": hls_url or "",
                "region": data.get("region", ""),
                "road_name": data.get("roadName", ""),
                "source": data.get("source", ""),
                "source_name": data.get("sourceName", ""),
                "kakao_key": key,
                "has_video": bool(hls_url),
                "stream_type": "hls" if hls_url else None,
            }
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


def get_cctv_by_region(region: str, limit: int = 10) -> str:
    """지역명으로 CCTV를 검색한다."""
    cctvs = _load_cctv_list()
    matched = [c for c in cctvs if region in c.get("region", "")]
    formatted = [_format_cctv(c) for c in matched[:limit]]
    return json.dumps({
        "success": True,
        "count": len(formatted),
        "total_in_region": len(matched),
        "cctvs": formatted,
    }, ensure_ascii=False)


def get_data_stats() -> str:
    """카카오맵 CCTV 통계를 반환한다."""
    cctvs = _load_cctv_list()
    from collections import Counter
    sources = dict(Counter(c.get("source", "?") for c in cctvs))
    regions = dict(Counter(c.get("region", "?") for c in cctvs))

    return json.dumps({
        "success": True,
        "total_cctv": len(cctvs),
        "data_source": "kakao_map",
        "api_key_required": False,
        "sources": sources,
        "regions": regions,
    }, ensure_ascii=False)
