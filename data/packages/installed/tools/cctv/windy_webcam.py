"""
Windy Webcams API v3 연동

전세계 실시간 웹캠을 검색합니다.

필요 환경변수:
  - WINDY_API_KEY: Windy API 키 (https://api.windy.com 에서 발급)
"""

import json
import os
import requests
from typing import Optional

from common import calculate_distance, success_response, error_response

WINDY_API_KEY = os.environ.get("WINDY_API_KEY", "")
WINDY_API_BASE = "https://webcams.windy.com/webcams/api/v3/webcams"

# Windy 카테고리 목록
CATEGORIES = [
    "airport", "beach", "building", "city", "coast", "forest",
    "indoor", "lake", "landscape", "meteo", "mountain", "observatory",
    "port", "river", "sportArea", "square", "traffic", "village"
]


def _call_windy_api(params: dict) -> dict:
    """Windy Webcams API 호출"""
    if not WINDY_API_KEY:
        raise ValueError("WINDY_API_KEY 환경변수가 설정되지 않았습니다. https://api.windy.com 에서 발급받으세요.")

    headers = {
        "x-windy-api-key": WINDY_API_KEY,
        "Accept": "application/json"
    }

    # 기본 include 파라미터
    if "include" not in params:
        params["include"] = "categories,images,location,player,urls"

    try:
        response = requests.get(WINDY_API_BASE, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        if response.status_code == 401:
            raise ValueError("WINDY_API_KEY가 유효하지 않습니다.")
        elif response.status_code == 429:
            raise ValueError("Windy API 요청 한도 초과. 잠시 후 다시 시도하세요.")
        raise ValueError(f"Windy API 오류: {response.status_code}")
    except requests.exceptions.Timeout:
        raise ValueError("Windy API 응답 시간 초과 (15초)")
    except requests.exceptions.ConnectionError:
        raise ValueError("Windy API 네트워크 연결 실패")


def _format_webcam(webcam: dict, ref_lat: float = None, ref_lon: float = None) -> dict:
    """웹캠 정보 포맷팅"""
    location = webcam.get("location", {})
    images = webcam.get("images", {})
    player = webcam.get("player", {})
    urls = webcam.get("urls", {})
    categories = webcam.get("categories", [])

    lat = location.get("latitude", 0)
    lon = location.get("longitude", 0)

    result = {
        "id": str(webcam.get("webcamId", "")),
        "title": webcam.get("title", "알 수 없음"),
        "status": webcam.get("status", ""),
        "lat": lat,
        "lon": lon,
        "city": location.get("city", ""),
        "region": location.get("region", ""),
        "country": location.get("country", ""),
        "category": [c.get("id", "") if isinstance(c, dict) else c for c in categories] if categories else [],
        "image_url": "",
        "player_url": "",
        "detail_url": "",
        "last_updated": webcam.get("lastUpdatedOn", ""),
        "source": "windy_webcams"
    }

    # 이미지 URL 추출
    if images:
        current = images.get("current", {})
        if isinstance(current, dict):
            result["image_url"] = current.get("preview", "") or current.get("thumbnail", "")
        elif isinstance(current, str):
            result["image_url"] = current

    # 플레이어 URL 추출
    if player:
        live = player.get("live", {})
        if isinstance(live, dict):
            result["player_url"] = live.get("embed", "") or live.get("available", "")
        day = player.get("day", {})
        if isinstance(day, dict) and not result["player_url"]:
            result["player_url"] = day.get("embed", "")

    # 상세 URL
    if urls:
        result["detail_url"] = urls.get("detail", "")

    # 거리 계산
    if ref_lat is not None and ref_lon is not None and lat and lon:
        result["distance_km"] = round(calculate_distance(ref_lat, ref_lon, lat, lon), 2)

    return result


def search_webcam(lat: float = None, lon: float = None, radius_km: float = 50,
                  category: str = None, country: str = None, limit: int = 10) -> str:
    """전세계 웹캠 검색"""
    try:
        params = {
            "limit": min(limit, 50)
        }

        # 위치 기반 검색
        if lat is not None and lon is not None:
            params["nearby"] = f"{lat},{lon},{min(radius_km, 250)}"

        # 카테고리 필터
        if category:
            cats = [c.strip() for c in category.split(",") if c.strip() in CATEGORIES]
            if cats:
                params["categories"] = ",".join(cats)

        # 국가 필터
        if country:
            params["countries"] = country.upper()

        data = _call_windy_api(params)
        webcams = data.get("webcams", [])

        formatted = [_format_webcam(w, lat, lon) for w in webcams]
        # active만 필터
        formatted = [w for w in formatted if w.get("status") == "active" or not w.get("status")]

        # 거리순 정렬 (위치 검색인 경우)
        if lat is not None and lon is not None:
            formatted.sort(key=lambda x: x.get("distance_km", 9999))

        return success_response(
            source="windy_webcams",
            count=len(formatted),
            total=data.get("total", len(formatted)),
            webcams=formatted
        )
    except Exception as e:
        return error_response(str(e))


def get_nearby_webcam(lat: float, lon: float, radius_km: float = 50, count: int = 3) -> str:
    """특정 좌표에서 가장 가까운 웹캠 찾기"""
    try:
        params = {
            "nearby": f"{lat},{lon},{min(radius_km, 250)}",
            "limit": min(count, 50)
        }

        data = _call_windy_api(params)
        webcams = data.get("webcams", [])

        formatted = [_format_webcam(w, lat, lon) for w in webcams]
        formatted = [w for w in formatted if w.get("status") == "active" or not w.get("status")]
        formatted.sort(key=lambda x: x.get("distance_km", 9999))
        formatted = formatted[:count]

        return success_response(
            source="windy_webcams",
            count=len(formatted),
            search_location={"lat": lat, "lon": lon},
            webcams=formatted
        )
    except Exception as e:
        return error_response(str(e))


if __name__ == "__main__":
    print("Windy Webcams 모듈")
    if WINDY_API_KEY:
        print(f"API 키: {WINDY_API_KEY[:8]}...")
        print("\n[테스트] 서울 근처 웹캠 검색...")
        result = search_webcam(lat=37.5665, lon=126.9780, radius_km=50, limit=3)
        print(result[:500])
    else:
        print("WINDY_API_KEY 환경변수가 설정되지 않았습니다.")
