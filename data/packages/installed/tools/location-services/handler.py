import os
import sys
import json
import time
import requests
from datetime import datetime, timedelta
import re

# common 유틸리티 사용
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.api_client import api_call, api_call_raw
from common.auth_manager import check_api_key
from common.response_formatter import error_response

# Amadeus OAuth2 토큰용 (직접 관리 필요)
AMADEUS_API_KEY = os.environ.get("AMADEUS_API_KEY", "")
AMADEUS_API_SECRET = os.environ.get("AMADEUS_API_SECRET", "")
AMADEUS_BASE_URL = "https://test.api.amadeus.com"

def get_amadeus_token():
    auth_url = f"{AMADEUS_BASE_URL}/v1/security/oauth2/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": AMADEUS_API_KEY,
        "client_secret": AMADEUS_API_SECRET
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        response = requests.post(auth_url, data=data, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json().get("access_token")
    except:
        pass
    return None


# ── 좌표/표시 봉투 공통 헬퍼 ──────────────────────────────
# 위치 액션 표준: 출력 좌표는 항상 {lat,lng} float, 지도형 결과는 map_data 봉투.
# sys.modules["common"] 충돌(cctv 패키지가 'common' 이름을 flat 모듈로 덮음) 때문에
# backend/common 공유 대신 패키지 로컬에 둔다. 봉투 스키마 규약은 cctv/프론트와 동일.
def _normalize_coords(lat, lng):
    """좌표를 표준 {lat,lng} float로 정규화. 파싱 실패·(0,0)·범위밖이면 None."""
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


def build_location_map(center: dict, markers: list, zoom: int = 14) -> dict:
    """location_map 봉투. center={lat,lng,name}, markers=[{name,lat,lng}]."""
    return {"type": "location_map", "center": center, "zoom": zoom, "markers": markers}


def build_route_map(origin: dict, destination: dict, path: list, summary: dict) -> dict:
    """route_map 봉투. origin/destination={lat,lng,name}, path=[[lat,lng]]."""
    return {"type": "route_map", "origin": origin, "destination": destination,
            "path": path, "summary": summary}


def search_kakao_restaurants(query: str, x: str = None, y: str = None,
                             radius: int = 5000, size: int = 10, sort: str = "accuracy"):
    """
    카카오 로컬 API로 맛집/음식점 검색 (페이지네이션 — 최대 45건)

    Args:
        query: 검색 키워드 (예: "강남 파스타", "홍대 맛집")
        x: 중심 좌표 경도
        y: 중심 좌표 위도
        radius: 검색 반경 (미터, 최대 20000)
        size: 결과 수 (최대 45 = 15×3페이지)
        sort: 정렬 (accuracy: 정확도순, distance: 거리순)
    """
    key_ok, key_error = check_api_key("kakao")
    if not key_ok:
        return {"error": f"{key_error} https://developers.kakao.com 에서 발급받으세요."}

    size = min(size, 45)
    restaurants = []
    total = 0
    page = 1
    # 페이지 크기는 15 고정 (페이지마다 size가 바뀌면 오프셋이 어긋남) — 마지막에 잘라냄
    while len(restaurants) < size and page <= 3:
        params = {
            "query": query,
            "category_group_code": "FD6",  # 음식점 카테고리
            "size": 15,
            "sort": sort,
            "page": page,
        }
        if x and y:
            params["x"] = x
            params["y"] = y
            params["radius"] = min(radius, 20000)

        data = api_call("kakao", "/v2/local/search/keyword.json", params=params, timeout=10)
        if isinstance(data, dict) and "error" in data:
            if page == 1:
                return data
            break

        total = data.get("meta", {}).get("total_count", total)
        for doc in data.get("documents", []):
            # 카카오: x=경도, y=위도 (문자열) → 표준 {lat,lng} float
            coords = _normalize_coords(doc.get("y"), doc.get("x")) or {"lat": None, "lng": None}
            restaurants.append({
                "name": doc.get("place_name", ""),
                "category": doc.get("category_name", ""),
                "cat": _simple_category(doc.get("category_name", "")),
                "address": doc.get("road_address_name") or doc.get("address_name", ""),
                "phone": doc.get("phone", ""),
                "url": doc.get("place_url", ""),
                "distance": doc.get("distance", ""),
                "lat": coords["lat"],
                "lng": coords["lng"],
            })

        if data.get("meta", {}).get("is_end", True):
            break
        page += 1

    restaurants = restaurants[:size]
    return {
        "total": total,
        "restaurants": restaurants,
        "message": f"'{query}' 검색 결과 {len(restaurants)}개의 맛집을 찾았습니다."
    }


def search_naver_local(query: str, display: int = 5, sort: str = "random"):
    """
    네이버 로컬 검색 API로 맛집/장소 검색

    Args:
        query: 검색 키워드 (예: "강남 파스타", "홍대 맛집")
        display: 결과 수 (최대 5)
        sort: 정렬 (random: 정확도순, comment: 리뷰순)
    """
    key_ok, key_error = check_api_key("naver")
    if not key_ok:
        return {"error": f"{key_error} https://developers.naver.com 에서 발급받으세요."}

    params = {
        "query": query,
        "display": min(display, 5),
        "sort": sort
    }

    data = api_call("naver", "/v1/search/local.json", params=params, timeout=10)
    if isinstance(data, dict) and "error" in data:
        return data

    items = data.get("items", [])

    # HTML 태그 제거 함수
    def clean_html(text):
        return re.sub('<[^<]+?>', '', text) if text else ""

    restaurants = []
    for item in items:
        # 네이버 local: mapx/mapy = WGS84 * 1e7 (예: "1270276000") → 표준 {lat,lng} float
        coords = None
        try:
            coords = _normalize_coords(int(item.get("mapy")) / 1e7, int(item.get("mapx")) / 1e7)
        except (TypeError, ValueError):
            coords = None
        coords = coords or {"lat": None, "lng": None}
        restaurants.append({
            "name": clean_html(item.get("title", "")),
            "category": item.get("category", ""),
            "cat": _simple_category(item.get("category", "")),
            "address": item.get("roadAddress") or item.get("address", ""),
            "phone": item.get("telephone", ""),
            "url": item.get("link", ""),
            "description": clean_html(item.get("description", "")),
            "lat": coords["lat"],
            "lng": coords["lng"],
        })

    return {
        "total": data.get("total", 0),
        "restaurants": restaurants,
        "message": f"[네이버] '{query}' 검색 결과 {len(restaurants)}개를 찾았습니다."
    }


def _norm_name(name: str) -> str:
    """가게명 비교용 정규화 — 괄호(지점 표기)·기호·공백 제거."""
    base = re.sub(r'\([^)]*\)', '', name or '')
    return re.sub(r'[^0-9a-zA-Z가-힣]', '', base).lower()


def _simple_category(category: str) -> str:
    """'음식점 > 양식 > 이탈리안' → '양식'. 앱 필터 칩용 굵은 분류."""
    parts = [p.strip() for p in (category or "").split(">") if p.strip()]
    if len(parts) >= 2 and parts[0] in ("음식점", "카페"):
        return parts[1] if parts[0] == "음식점" else "카페"
    return parts[-1] if parts else "기타"


def _blog_evidence(region: str, name: str):
    """
    네이버 블로그 검색으로 추천 근거 수집 — 언급 수(인기 신호) + 후기 제목(추천 이유).
    가게명이 실제로 등장하는 글의 제목만 reason 재료로 채택 (동음이의 잡음 필터).
    """
    q = f"{region} {name}".strip()
    data = api_call("naver", "/v1/search/blog.json",
                    params={"query": q, "display": 5, "sort": "sim"}, timeout=5)
    if not isinstance(data, dict) or "error" in data:
        return None

    def strip_html(t):
        return re.sub('<[^<]+?>', '', t or '')

    key = _norm_name(name)
    titles = []
    for it in data.get("items", []):
        title = strip_html(it.get("title", ""))
        blob = _norm_name(title + strip_html(it.get("description", "")))
        if key and key in blob:
            titles.append(title)
    return {"blog_count": data.get("total", 0), "blog_titles": titles[:2]}


def _enrich_with_blogs(items: list, region: str, top_n: int = 12):
    """상위 top_n개 가게에 블로그 언급 수·후기 제목을 병렬로 붙임 (in-place)."""
    from concurrent.futures import ThreadPoolExecutor

    def work(r):
        try:
            ev = _blog_evidence(region, r.get("name", ""))
        except Exception:
            return
        if ev:
            r["blog_count"] = ev["blog_count"]
            if ev["blog_titles"]:
                r["reason"] = " / ".join(ev["blog_titles"])[:90]

    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(work, items[:top_n]))


def search_restaurants_combined(query: str, x: str = None, y: str = None,
                                 radius: int = 5000, kakao_size: int = 30,
                                 naver_size: int = 5, naver_sort: str = "comment",
                                 enrich: bool = True):
    """
    카카오 + 네이버 API를 병합하여 맛집 검색
    (중복 가게 병합 + 네이버 블로그 후기로 추천 근거 부착)

    Args:
        query: 검색 키워드
        x, y: 좌표 (카카오용)
        radius: 검색 반경 (카카오용)
        kakao_size: 카카오 결과 수 (최대 45)
        naver_size: 네이버 결과 수 (API 상한 5)
        naver_sort: 네이버 정렬 (random/comment)
        enrich: True면 상위 가게에 블로그 언급 수·후기 제목 부착
    """
    results = {
        "query": query,
        "kakao": {"restaurants": [], "total": 0},
        "naver": {"restaurants": [], "total": 0},
        "combined": [],
        "message": ""
    }

    # 카카오 검색
    kakao_result = search_kakao_restaurants(query, x, y, radius, kakao_size, "accuracy")
    if "error" not in kakao_result:
        results["kakao"] = {
            "restaurants": kakao_result.get("restaurants", []),
            "total": kakao_result.get("total", 0)
        }
        for r in kakao_result.get("restaurants", []):
            r["source"] = "kakao"
            results["combined"].append(r)

    # 네이버 검색 — 같은 가게는 카카오 항목에 병합(설명만 취함), 새 가게만 추가
    naver_result = search_naver_local(query, naver_size, naver_sort)
    if "error" not in naver_result:
        results["naver"] = {
            "restaurants": naver_result.get("restaurants", []),
            "total": naver_result.get("total", 0)
        }
        by_name = {_norm_name(r["name"]): r for r in results["combined"]}
        for r in naver_result.get("restaurants", []):
            k = _norm_name(r.get("name", ""))
            dup = by_name.get(k)
            if dup:
                dup["source"] = "kakao+naver"
                if r.get("description"):
                    dup["description"] = r["description"]
            else:
                r["source"] = "naver"
                results["combined"].append(r)
                if k:
                    by_name[k] = r

    # 추천 근거: 네이버 블로그 검색 — 언급 수(blog_count) + 후기 제목(reason)
    if enrich and results["combined"]:
        region = query.split()[0] if query.split() else ""
        _enrich_with_blogs(results["combined"], region)
        # 블로그 언급 많은 순으로 정렬 (안정 정렬 — 동률은 API 정확도순 유지)
        results["combined"].sort(key=lambda r: -(r.get("blog_count") or 0))

    kakao_count = len(results["kakao"]["restaurants"])
    naver_count = len(results["naver"]["restaurants"])
    results["message"] = (f"'{query}' 검색 결과 {len(results['combined'])}개 "
                          f"(카카오 {kakao_count} + 네이버 {naver_count}, 중복 병합"
                          f"{', 블로그 후기 언급순 정렬' if enrich else ''})")

    # 좌표 계약(#1): 위치 액션 출력 항목은 lat/lng 보장 — 좌표 없는 항목은 드롭.
    results["combined"] = [r for r in results["combined"]
                           if r.get("lat") is not None and r.get("lng") is not None]
    # 표시 봉투(#4): 결과를 지도에 바로 그릴 수 있게 map_data 동봉.
    markers = [{"name": r.get("name", ""), "lat": r["lat"], "lng": r["lng"]}
               for r in results["combined"]]
    if markers:
        results["map_data"] = build_location_map(
            center={"lat": markers[0]["lat"], "lng": markers[0]["lng"], "name": query},
            markers=markers)

    # 단일 통화 — native 맛집 dict(name/category/address/phone/url/distance 등 풍부)를 items로.
    # (옛 records 5칸 변환은 distance/phone 등을 납작하게 버려 손실적이라 은퇴.) map_data는 별도 유지.
    results["items"] = results.pop("combined")
    results["count"] = len(results["items"])
    return results


def reverse_geocode_kakao(x: float, y: float):
    """
    카카오 로컬 API로 좌표를 행정구역 명칭으로 변환

    Args:
        x: 경도 (longitude)
        y: 위도 (latitude)
    """
    key_ok, key_error = check_api_key("kakao")
    if not key_ok:
        return {"error": key_error}

    params = {
        "x": x,
        "y": y
    }

    data = api_call("kakao", "/v2/local/geo/coord2regioncode.json", params=params, timeout=10)
    if isinstance(data, dict) and "error" in data:
        return data

    documents = data.get("documents", [])

    # 행정동(H) 또는 법정동(B) 중 하나 선택 (보통 H가 행정구역 명칭으로 적합)
    for doc in documents:
        if doc.get("region_type") == "H":
            return {
                "address": doc.get("address_name", ""),
                "region_1depth": doc.get("region_1depth_name", ""),
                "region_2depth": doc.get("region_2depth_name", ""),
                "region_3depth": doc.get("region_3depth_name", ""),
                "region_4depth": doc.get("region_4depth_name", "")
            }

    if documents:
        doc = documents[0]
        return {
            "address": doc.get("address_name", ""),
            "region_1depth": doc.get("region_1depth_name", ""),
            "region_2depth": doc.get("region_2depth_name", ""),
            "region_3depth": doc.get("region_3depth_name", ""),
            "region_4depth": doc.get("region_4depth_name", "")
        }

    return {"error": "결과가 없습니다."}


def generate_route_map_data(origin_coord: tuple, dest_coord: tuple,
                            path_coords: list, origin_name: str = "출발",
                            dest_name: str = "도착", summary_info: dict = None) -> dict:
    """
    경로 지도 데이터 생성 (프론트엔드 렌더링용)

    Args:
        origin_coord: 출발지 좌표 (경도, 위도)
        dest_coord: 목적지 좌표 (경도, 위도)
        path_coords: 경로 좌표 리스트 [(경도, 위도), ...]
        origin_name: 출발지 이름
        dest_name: 목적지 이름
        summary_info: 요약 정보 (거리, 시간 등)

    Returns:
        지도 렌더링용 데이터 딕셔너리
    """
    # 경로 좌표를 [위도, 경도] 형식으로 변환 (Leaflet 형식)
    path_latlng = [[coord[1], coord[0]] for coord in path_coords]

    # 좌표 샘플링 (최대 50개) + 정밀도 제한 (소수점 5자리 ≈ 1m 정확도)
    if len(path_latlng) > 50:
        step = len(path_latlng) // 50
        path_latlng = path_latlng[::step]
    path_latlng = [[round(c[0], 5), round(c[1], 5)] for c in path_latlng]

    return build_route_map(
        origin={**(_normalize_coords(origin_coord[1], origin_coord[0]) or {"lat": origin_coord[1], "lng": origin_coord[0]}), "name": origin_name},
        destination={**(_normalize_coords(dest_coord[1], dest_coord[0]) or {"lat": dest_coord[1], "lng": dest_coord[0]}), "name": dest_name},
        path=path_latlng,
        summary={
            "distance_km": summary_info.get("distance_km", 0) if summary_info else 0,
            "duration_min": summary_info.get("duration_min", 0) if summary_info else 0,
            "toll": summary_info.get("fare", {}).get("toll", 0) if summary_info else 0,
        })


def _geocode_place(place_str: str) -> tuple:
    """
    장소명 또는 좌표 문자열을 (경도,위도,이름) 튜플로 변환.
    - "127.0,37.5" → (127.0, 37.5, "")
    - "127.0,37.5,name=강남역" → (127.0, 37.5, "강남역")
    - "오송역" → 카카오 키워드 검색 → (경도, 위도, "오송역")
    """
    if not place_str:
        return None

    parts = place_str.split(",")
    # 좌표 형식인지 확인 (첫 두 파트가 숫자)
    try:
        x = float(parts[0].strip())
        y = float(parts[1].strip())
        name = ""
        if len(parts) > 2 and "name=" in parts[2]:
            name = parts[2].strip().replace("name=", "")
        return (x, y, name)
    except (ValueError, IndexError):
        pass

    # 장소명으로 카카오 키워드 검색
    data = api_call("kakao", "/v2/local/search/keyword.json",
                    params={"query": place_str, "size": 1}, timeout=10)
    if isinstance(data, dict) and data.get("documents"):
        place = data["documents"][0]
        return (float(place["x"]), float(place["y"]),
                place.get("place_name", place_str))

    return None


def kakao_navigation(origin: str, destination: str, waypoints: str = None,
                      priority: str = "RECOMMEND", avoid: str = None,
                      alternatives: bool = False, summary: bool = False,
                      generate_map: bool = True) -> dict:
    """
    카카오모빌리티 길찾기 API

    Args:
        origin: 출발지 — 좌표("경도,위도") 또는 장소명("오송역")
        destination: 목적지 — 좌표("경도,위도") 또는 장소명("수원 포레파크원")
        waypoints: 경유지 (최대 5개, "|"로 구분)
        priority: 경로 우선순위 (RECOMMEND: 추천, TIME: 최단시간, DISTANCE: 최단거리)
        avoid: 회피 옵션 (쉼표 구분: toll,motorway,ferries,schoolzone,uturn)
        alternatives: 대안 경로 제공 여부
        summary: 요약 정보만 반환 여부
        generate_map: HTML 지도 생성 여부 (기본: True)

    Returns:
        경로 정보 (거리, 시간, 요금, 지도 데이터)
    """
    key_ok, key_error = check_api_key("kakao")
    if not key_ok:
        return {"error": key_error}

    # 장소명 → 좌표 자동 변환
    origin_info = _geocode_place(origin)
    if not origin_info:
        return {"error": f"출발지를 찾을 수 없습니다: {origin}"}

    dest_info = _geocode_place(destination)
    if not dest_info:
        return {"error": f"목적지를 찾을 수 없습니다: {destination}"}

    origin_coord_str = f"{origin_info[0]},{origin_info[1]}"
    dest_coord_str = f"{dest_info[0]},{dest_info[1]}"

    params = {
        "origin": origin_coord_str,
        "destination": dest_coord_str,
        "priority": priority,
        "alternatives": str(alternatives).lower(),
        "summary": str(summary).lower()
    }

    if waypoints:
        params["waypoints"] = waypoints
    if avoid:
        params["avoid"] = avoid

    data = api_call("kakao", "/v1/directions",
                    params=params, timeout=15,
                    base_url="https://apis-navi.kakaomobility.com",
                    extra_headers={"Content-Type": "application/json"})
    if isinstance(data, dict) and "error" in data:
        return data

    try:
        routes = data.get("routes", [])

        if not routes:
            return {"error": "경로를 찾을 수 없습니다.", "raw": data}

        result = {
            "trans_id": data.get("trans_id"),
            "routes": []
        }

        # 경로 좌표 수집 (지도 생성용)
        all_path_coords = []

        for route in routes:
            route_info = {
                "result_code": route.get("result_code"),
                "result_msg": route.get("result_msg")
            }

            summary_data = route.get("summary", {})
            if summary_data:
                route_info["summary"] = {
                    "origin": summary_data.get("origin", {}),
                    "destination": summary_data.get("destination", {}),
                    "waypoints": summary_data.get("waypoints", []),
                    "distance": summary_data.get("distance"),  # 미터
                    "distance_km": round(summary_data.get("distance", 0) / 1000, 1),
                    "duration": summary_data.get("duration"),  # 초
                    "duration_min": round(summary_data.get("duration", 0) / 60),
                    "fare": summary_data.get("fare", {}),  # 요금 정보
                    "priority": summary_data.get("priority")
                }

            # 구간별: 경로 좌표 수집 + 주요 안내만 추출
            sections = route.get("sections", [])
            if sections:
                key_guides = []
                for section in sections:
                    # 경로 좌표 수집 (roads의 vertexes)
                    roads = section.get("roads", [])
                    for road in roads:
                        vertexes = road.get("vertexes", [])
                        for i in range(0, len(vertexes), 2):
                            if i + 1 < len(vertexes):
                                all_path_coords.append((vertexes[i], vertexes[i+1]))

                    # 주요 안내만 (고속도로 진입/출구, 톨게이트 등)
                    guides = section.get("guides", [])
                    for guide in guides:
                        g_type = guide.get("type", 0)
                        # 주요 타입만: 고속도로(8,9), 톨게이트(6), IC/JC(5), 도착(100,101)
                        if g_type in (5, 6, 8, 9, 100, 101) or guide.get("name"):
                            key_guides.append({
                                "name": guide.get("name", ""),
                                "guidance": guide.get("guidance", ""),
                                "distance": guide.get("distance")
                            })

                if key_guides:
                    route_info["key_guides"] = key_guides[:15]  # 최대 15개

            result["routes"].append(route_info)

        # 간단한 요약 메시지
        if result["routes"] and result["routes"][0].get("summary"):
            s = result["routes"][0]["summary"]
            fare_info = ""
            if s.get("fare"):
                toll = s["fare"].get("toll", 0)
                if toll > 0:
                    fare_info = f", 톨비: {toll:,}원"
            result["message"] = f"총 {s['distance_km']}km, 약 {s['duration_min']}분 소요{fare_info}"

        # 지도 데이터 생성 (프론트엔드 렌더링용)
        if generate_map and all_path_coords and not summary:
            origin_coord = (origin_info[0], origin_info[1])
            dest_coord = (dest_info[0], dest_info[1])

            # 장소명: geocode 결과 > API 응답 > 기본값
            origin_name = origin_info[2] or "출발지"
            dest_name = dest_info[2] or "목적지"
            if result["routes"] and result["routes"][0].get("summary"):
                s = result["routes"][0]["summary"]
                if s.get("origin", {}).get("name"):
                    origin_name = s["origin"]["name"]
                if s.get("destination", {}).get("name"):
                    dest_name = s["destination"]["name"]

            map_data = generate_route_map_data(
                origin_coord=origin_coord,
                dest_coord=dest_coord,
                path_coords=all_path_coords,
                origin_name=origin_name,
                dest_name=dest_name,
                summary_info=result["routes"][0].get("summary")
            )

            result["map_data"] = map_data

        return result

    except Exception as e:
        return {"error": f"길찾기 실패: {str(e)}"}


def show_location_map(query: str = None, lat: float = None, lng: float = None,
                       zoom: int = 15, markers: list = None) -> dict:
    """
    특정 위치의 지도를 대화창에 표시

    Args:
        query: 검색할 장소명 (예: '강남역')
        lat: 위도 (직접 지정시)
        lng: 경도 (직접 지정시)
        zoom: 줌 레벨 (기본: 15)
        markers: 추가 마커 목록 [{name, lat, lng}, ...]

    Returns:
        지도 데이터 (map_data 포함)
    """
    center_lat = lat
    center_lng = lng
    center_name = query or "위치"

    # 장소명으로 검색
    if query and (lat is None or lng is None):
        key_ok, key_error = check_api_key("kakao")
        if not key_ok:
            return {"error": key_error}

        data = api_call("kakao", "/v2/local/search/keyword.json",
                        params={"query": query, "size": 1}, timeout=10)
        if isinstance(data, dict) and "error" in data:
            return data

        if data.get("documents"):
            place = data["documents"][0]
            center_lng = float(place["x"])
            center_lat = float(place["y"])
            center_name = place.get("place_name", query)
        else:
            return {"error": f"'{query}' 장소를 찾을 수 없습니다."}

    if center_lat is None or center_lng is None:
        return {"error": "위치 정보가 필요합니다. query 또는 lat/lng를 지정하세요."}

    # 마커 목록 생성
    all_markers = [{"name": center_name, "lat": center_lat, "lng": center_lng}]
    if markers:
        all_markers.extend(markers)

    # 지도 데이터 생성 (표시 봉투 단일 빌더, #4)
    map_data = build_location_map(
        center={"lat": center_lat, "lng": center_lng, "name": center_name},
        markers=all_markers, zoom=zoom)

    return {
        "message": f"'{center_name}' 위치 지도",
        "center": {"lat": center_lat, "lng": center_lng, "name": center_name},
        "map_data": map_data
    }


# ── travel 내부 해소 (도시명→IATA, 상대날짜→절대날짜) ───────────────
# 주요 도시 IATA 도시코드(메트로). 미등록은 Amadeus city-search로 동적 해소.
_IATA_CITY = {
    "서울": "SEL", "seoul": "SEL", "부산": "PUS", "busan": "PUS",
    "제주": "CJU", "jeju": "CJU",
    # 인천/김포 (서울 메트로 SEL 에도 포함되나, 명시 지정 대비)
    "인천": "ICN", "incheon": "ICN", "김포": "GMP", "gimpo": "GMP",
    # 한국 지방공항 — Amadeus city-search 가 한글 키워드를 못 풀어 명시 매핑(미등록 시 "공항 코드 못 찾음")
    "청주": "CJJ", "cheongju": "CJJ", "대구": "TAE", "daegu": "TAE",
    "광주": "KWJ", "gwangju": "KWJ", "여수": "RSU", "yeosu": "RSU",
    "울산": "USN", "ulsan": "USN", "포항": "KPO", "pohang": "KPO",
    "양양": "YNY", "yangyang": "YNY", "무안": "MWX", "muan": "MWX",
    "군산": "KUV", "gunsan": "KUV", "원주": "WJU", "wonju": "WJU",
    "사천": "HIN", "진주": "HIN", "sacheon": "HIN",
    "도쿄": "TYO", "동경": "TYO", "tokyo": "TYO",
    "오사카": "OSA", "osaka": "OSA", "후쿠오카": "FUK", "fukuoka": "FUK",
    "삿포로": "SPK", "sapporo": "SPK", "나고야": "NGO", "nagoya": "NGO",
    "베이징": "BJS", "북경": "BJS", "beijing": "BJS",
    "상하이": "SHA", "상해": "SHA", "shanghai": "SHA",
    "홍콩": "HKG", "hongkong": "HKG",
    "타이베이": "TPE", "대만": "TPE", "타이페이": "TPE", "taipei": "TPE",
    "방콕": "BKK", "bangkok": "BKK", "싱가포르": "SIN", "singapore": "SIN",
    "하노이": "HAN", "hanoi": "HAN", "호치민": "SGN", "hochiminh": "SGN",
    "마닐라": "MNL", "manila": "MNL", "발리": "DPS", "덴파사르": "DPS", "bali": "DPS",
    "다낭": "DAD", "danang": "DAD", "괌": "GUM", "guam": "GUM", "사이판": "SPN", "saipan": "SPN",
    "파리": "PAR", "paris": "PAR", "런던": "LON", "london": "LON",
    "로마": "ROM", "rome": "ROM", "프랑크푸르트": "FRA", "frankfurt": "FRA",
    "뮌헨": "MUC", "munich": "MUC", "바르셀로나": "BCN", "barcelona": "BCN",
    "마드리드": "MAD", "madrid": "MAD", "암스테르담": "AMS", "amsterdam": "AMS",
    "이스탄불": "IST", "istanbul": "IST", "두바이": "DXB", "dubai": "DXB",
    "취리히": "ZRH", "zurich": "ZRH", "빈": "VIE", "vienna": "VIE", "프라하": "PRG", "prague": "PRG",
    "뉴욕": "NYC", "newyork": "NYC", "로스앤젤레스": "LAX", "la": "LAX", "losangeles": "LAX",
    "샌프란시스코": "SFO", "sanfrancisco": "SFO", "시카고": "CHI", "chicago": "CHI",
    "워싱턴": "WAS", "washington": "WAS", "시애틀": "SEA", "seattle": "SEA",
    "라스베이거스": "LAS", "lasvegas": "LAS", "보스턴": "BOS", "boston": "BOS",
    "호놀룰루": "HNL", "하와이": "HNL", "honolulu": "HNL", "hawaii": "HNL",
    "토론토": "YTO", "toronto": "YTO", "밴쿠버": "YVR", "vancouver": "YVR",
    "시드니": "SYD", "sydney": "SYD", "멜버른": "MEL", "melbourne": "MEL",
}

_WEEKDAYS = {
    "월요일": 0, "화요일": 1, "수요일": 2, "목요일": 3, "금요일": 4, "토요일": 5, "일요일": 6,
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
}


def _amadeus_city_lookup(keyword: str):
    """미등록 도시명 → Amadeus city-search로 IATA 코드 동적 해소 (best-effort)."""
    try:
        token = get_amadeus_token()
        if not token:
            return None
        url = f"{AMADEUS_BASE_URL}/v1/reference-data/locations"
        data = api_call_raw(url, headers={"Authorization": f"Bearer {token}"},
                            params={"keyword": keyword, "subType": "CITY"}, timeout=15)
        if isinstance(data, str):
            data = json.loads(data)
        if isinstance(data, dict):
            for item in data.get("data", []):
                code = item.get("iataCode")
                if code:
                    return code
    except Exception:
        pass
    return None


def _resolve_iata(name: str):
    """도시명 → IATA 코드. 이미 3자 코드면 통과, 미등록은 API로 해소."""
    if not name:
        return None
    key = "".join(str(name).lower().split())
    if key in _IATA_CITY:
        return _IATA_CITY[key]
    s = str(name).strip()
    if s.isalpha() and len(s) == 3 and s.isascii():  # 이미 IATA 코드
        return s.upper()
    return _amadeus_city_lookup(name)


def _resolve_travel_date(s):
    """상대/자연어 날짜 → YYYY-MM-DD. 못 풀면 원본 통과(Amadeus가 검증)."""
    if not s:
        return s
    s = str(s).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):  # 이미 ISO
        return s
    today = datetime.now()
    low = s.lower()
    for k, v in {"오늘": 0, "today": 0, "내일": 1, "tomorrow": 1, "모레": 2, "글피": 3}.items():
        if k in low:
            return (today + timedelta(days=v)).strftime("%Y-%m-%d")
    m = re.search(r"(\d+)\s*일\s*(후|뒤)", s)
    if m:
        return (today + timedelta(days=int(m.group(1)))).strftime("%Y-%m-%d")
    base_week = 14 if "다다음주" in s else (7 if ("다음주" in s or "담주" in s) else 0)
    wd = next((v for k, v in _WEEKDAYS.items() if k in low), None)
    if wd is not None:
        ref = today + timedelta(days=base_week)
        delta = (wd - ref.weekday()) % 7
        return (ref + timedelta(days=delta)).strftime("%Y-%m-%d")
    if base_week:
        return (today + timedelta(days=base_week)).strftime("%Y-%m-%d")
    m = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", s)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        for year in (today.year, today.year + 1):
            try:
                cand = datetime(year, month, day)
                if cand.date() >= today.date():
                    return cand.strftime("%Y-%m-%d")
            except ValueError:
                break
    return s


# ── op 디스패처 (2026-06-04 travel 자연어 인터페이스화) ──────────────
_OP_DISPATCHERS = {
    "amadeus_travel_search": {"flight": None, "hotel": None},
}
_OP_DEFAULTS = {"amadeus_travel_search": "flight"}


def _amadeus_short_dt(iso: str) -> str:
    """'2026-07-03T08:30:00' → '07-03 08:30' (빈/짧은 입력은 '')."""
    if not iso or len(iso) < 16:
        return ""
    return iso[5:16].replace("T", " ")


def _amadeus_fmt_dur(iso_dur: str) -> str:
    """ISO8601 기간 'PT2H30M' → '2시간 30분'."""
    if not iso_dur or not iso_dur.startswith("PT"):
        return ""
    h = re.search(r"(\d+)H", iso_dur)
    m = re.search(r"(\d+)M", iso_dur)
    parts = []
    if h:
        parts.append(f"{h.group(1)}시간")
    if m:
        parts.append(f"{m.group(1)}분")
    return " ".join(parts)


def amadeus_travel_search(tool_input: dict) -> dict:
    """[sense:travel]{op} — 자연어 평면 인터페이스. 도시명→IATA·상대날짜 내부 해소.

    op=flight: from(기본 서울)→to(필수), date(기본 +7일).
    op=hotel:  city(필수).
    op=poi:    city 또는 lat/lng.
    endpoint+params 직접 지정 시 Amadeus 원본 호출(파워유저 탈출구).
    """
    # 파워유저 탈출구: endpoint+params 직접 지정 (후방호환)
    endpoint = tool_input.get("endpoint")
    if endpoint:
        return _amadeus_call(endpoint, tool_input.get("params", {}))

    op = (tool_input.get("op") or _OP_DEFAULTS["amadeus_travel_search"]).strip()
    notes = []

    if op == "flight":
        to_city = tool_input.get("to") or tool_input.get("destination")
        if not to_city:
            return {"error": '항공권은 도착 도시(to)가 필요합니다. 예: [sense:travel]{op: "flight", to: "도쿄"}'}
        has_from = bool(tool_input.get("from") or tool_input.get("origin"))
        from_city = tool_input.get("from") or tool_input.get("origin") or "서울"
        origin_code = _resolve_iata(from_city)
        dest_code = _resolve_iata(to_city)
        if not origin_code or not dest_code:
            bad = from_city if not origin_code else to_city
            return {"error": f"도시 '{bad}'의 공항 코드를 찾지 못했습니다. IATA 코드(예 ICN)로 지정하거나 endpoint+params로 직접 호출하세요."}
        if not has_from:
            notes.append(f"출발지 미지정 — 서울({origin_code}) 기준")
        date_in = tool_input.get("date")
        if date_in:
            dep_date = _resolve_travel_date(date_in)
        else:
            dep_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
            notes.append(f"날짜 미지정 — {dep_date}(약 1주 후) 기준")
        params = {
            "originLocationCode": origin_code,
            "destinationLocationCode": dest_code,
            "departureDate": dep_date,
            "adults": int(tool_input.get("adults", 1)),
        }
        ret = tool_input.get("return_date") or tool_input.get("return")
        if ret:
            params["returnDate"] = _resolve_travel_date(ret)
        result = _amadeus_call("flight-offers", params)

    elif op == "hotel":
        city = tool_input.get("city") or tool_input.get("to") or tool_input.get("query")
        if not city:
            return {"error": '호텔은 도시(city)가 필요합니다. 예: [sense:travel]{op: "hotel", city: "파리"}'}
        code = _resolve_iata(city)
        if not code:
            return {"error": f"도시 '{city}'의 코드를 찾지 못했습니다."}
        result = _amadeus_call("hotel-list", {"cityCode": code})

    else:
        # poi(points-of-interest)는 2026 Amadeus가 영구 폐기(HTTP 410 GONE) — 어휘에서 제거됨.
        return {"error": f"알 수 없는 op '{op}'. 사용 가능: flight/hotel (또는 endpoint+params 직접 지정)"}

    if isinstance(result, dict) and notes and "error" not in result:
        result["notes"] = notes

    # 레코드 통화(비파괴) — 세 op 모두 records[{title,meta,summary,url}] 부착.
    # 앱은 records, >> 파이프(filter/sort/chart)도 records. message=사람용 요약.
    # (compress 폐지: 깨끗한 records+message가 있으면 LLM 압축은 records를 문자열로 파괴할 뿐.)
    if isinstance(result, dict) and "error" not in result:
        items = result.get("results")
        recs = []
        if op == "flight" and isinstance(items, list):
            for off in items:
                if not isinstance(off, dict):
                    continue
                price = off.get("price", {}) or {}
                price_str = (f"{price.get('total')} {price.get('currency', '')}".strip()
                             if isinstance(price, dict) and price.get("total") else "")
                itins = off.get("itineraries", []) or []
                legs = []
                for it in itins:
                    segs = it.get("segments", []) or []
                    if not segs:
                        continue
                    dep = segs[0].get("departure", {}).get("iataCode", "")
                    arr = segs[-1].get("arrival", {}).get("iataCode", "")
                    if dep and arr:
                        legs.append(f"{dep}→{arr}")
                meta_parts = []
                if price_str:
                    meta_parts.append(price_str)
                first = itins[0] if itins else {}
                fsegs = first.get("segments", []) or []
                if fsegs:
                    stops = len(fsegs) - 1
                    meta_parts.append("직항" if stops == 0 else f"{stops}회 경유")
                    dep_at = _amadeus_short_dt(fsegs[0].get("departure", {}).get("at", ""))
                    if dep_at:
                        meta_parts.append(dep_at)
                dur = _amadeus_fmt_dur(first.get("duration", ""))
                if dur:
                    meta_parts.append(dur)
                carriers = off.get("validatingAirlineCodes", []) or []
                if carriers:
                    meta_parts.append("/".join(carriers))
                recs.append({
                    "title": " / ".join(legs) if legs else "항공편",
                    "meta": " · ".join(m for m in meta_parts if m),
                    "summary": "",
                    "url": "",
                })
        elif op == "hotel" and isinstance(items, list):
            for h in items:
                if not isinstance(h, dict):
                    continue
                addr = h.get("address", {})
                addr_str = ", ".join(addr.get("lines", [])) if isinstance(addr, dict) else ""
                dist = h.get("distance", {})
                dist_str = (f"{dist.get('value')}{dist.get('unit', '')}"
                            if isinstance(dist, dict) and dist.get("value") is not None else "")
                recs.append({
                    "title": h.get("name", ""),
                    "meta": " · ".join(x for x in [h.get("iataCode"), addr_str, dist_str] if x),
                    "summary": h.get("hotelId", ""),
                    "url": "",
                })
        result["items"] = recs
        result.pop("results", None)  # 원시 중첩 amadeus 페이로드는 records+message로 대체
        # 사람용 요약(message) — compress 없이도 에이전트가 읽을 깨끗한 텍스트.
        _labels = {"flight": "항공권", "hotel": "호텔"}
        lines = [f"{_labels.get(op, op)} 검색 결과 {len(recs)}건"]
        for i, r in enumerate(recs[:15], 1):
            seg = f"[{i}] {r['title']}"
            if r.get("meta"):
                seg += f" — {r['meta']}"
            if r.get("summary"):
                seg += f"\n    {r['summary']}"
            lines.append(seg)
        result["message"] = "\n".join(lines)
    return result


def _amadeus_call(endpoint: str, params: dict) -> dict:
    """Amadeus API 저수준 호출 (endpoint+params → 결과). 내부용."""
    key_ok, key_error = check_api_key("amadeus")
    if not key_ok:
        return {"error": f"{key_error} https://developers.amadeus.com 에서 발급받으세요."}

    # 토큰 획득
    token = get_amadeus_token()
    if not token:
        return {"error": "Amadeus API 인증 실패. API 키를 확인하세요."}

    # 엔드포인트별 URL 매핑
    endpoint_urls = {
        "flight-offers": f"{AMADEUS_BASE_URL}/v2/shopping/flight-offers",
        "hotel-list": f"{AMADEUS_BASE_URL}/v1/reference-data/locations/hotels/by-city",
        "points-of-interest": f"{AMADEUS_BASE_URL}/v1/reference-data/locations/pois",
        "airport-routes": f"{AMADEUS_BASE_URL}/v1/airport/direct-destinations",
        "city-search": f"{AMADEUS_BASE_URL}/v1/reference-data/locations"
    }

    url = endpoint_urls.get(endpoint)
    if not url:
        available = ", ".join(endpoint_urls.keys())
        return {"error": f"지원하지 않는 엔드포인트: {endpoint}. 사용 가능: {available}"}

    data = api_call_raw(url, headers={"Authorization": f"Bearer {token}"},
                        params=params, timeout=20)

    # api_call_raw returns parsed JSON or error dict
    if isinstance(data, dict) and "error" in data:
        return data

    # data가 문자열이면 JSON 파싱 시도
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return {"error": f"Amadeus API 응답 파싱 실패: {data[:500]}"}

    results = data.get("data", [])

    return {
        "endpoint": endpoint,
        "count": len(results) if isinstance(results, list) else 1,
        "results": results[:20] if isinstance(results, list) else results,  # 최대 20개
        "meta": data.get("meta", {})
    }


# ============== 날씨 (Open-Meteo, 무료/키불필요) ==============

# 주요 도시 좌표 캐시
_CITY_COORDS = {
    "seoul": (37.5665, 126.9780), "서울": (37.5665, 126.9780),
    "suwon": (37.2636, 127.0286), "수원": (37.2636, 127.0286),
    "incheon": (37.4563, 126.7052), "인천": (37.4563, 126.7052),
    "busan": (35.1796, 129.0756), "부산": (35.1796, 129.0756),
    "daegu": (35.8714, 128.6014), "대구": (35.8714, 128.6014),
    "daejeon": (36.3504, 127.3845), "대전": (36.3504, 127.3845),
    "gwangju": (35.1595, 126.8526), "광주": (35.1595, 126.8526),
    "ulsan": (35.5384, 129.3114), "울산": (35.5384, 129.3114),
    "jeju": (33.4996, 126.5312), "제주": (33.4996, 126.5312),
    "sejong": (36.4800, 127.2890), "세종": (36.4800, 127.2890),
    "tokyo": (35.6762, 139.6503), "도쿄": (35.6762, 139.6503),
    "osaka": (34.6937, 135.5023), "오사카": (34.6937, 135.5023),
    "new york": (40.7128, -74.0060), "뉴욕": (40.7128, -74.0060),
    "london": (51.5074, -0.1278), "런던": (51.5074, -0.1278),
    "paris": (48.8566, 2.3522), "파리": (48.8566, 2.3522),
    "beijing": (39.9042, 116.4074), "베이징": (39.9042, 116.4074),
    "shanghai": (31.2304, 121.4737), "상하이": (31.2304, 121.4737),
    "singapore": (1.3521, 103.8198), "싱가포르": (1.3521, 103.8198),
    "bangkok": (13.7563, 100.5018), "방콕": (13.7563, 100.5018),
    "sydney": (-33.8688, 151.2093), "시드니": (-33.8688, 151.2093),
}

_WMO_CODES = {
    0: "맑음", 1: "대체로 맑음", 2: "구름 조금", 3: "흐림",
    45: "안개", 48: "상고대 안개",
    51: "가벼운 이슬비", 53: "이슬비", 55: "짙은 이슬비",
    61: "약한 비", 63: "비", 65: "강한 비",
    71: "약한 눈", 73: "눈", 75: "강한 눈", 77: "싸락눈",
    80: "약한 소나기", 81: "소나기", 82: "강한 소나기",
    85: "약한 눈소나기", 86: "강한 눈소나기",
    95: "뇌우", 96: "우박 뇌우", 99: "강한 우박 뇌우",
}


def _geocode_openmeteo(city: str) -> tuple:
    """Open-Meteo geocoding (무키). 영어/로마자 도시명에 강함 — 한글은 빈 결과를 준다."""
    try:
        resp = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "ko"},
            timeout=5
        )
        if resp.ok:
            results = resp.json().get("results", [])
            if results:
                r = results[0]
                return (r["latitude"], r["longitude"])
    except Exception:
        pass
    return None


def _geocode_kakao(city: str) -> tuple:
    """카카오 주소(행정구역) 검색 → (lat, lon). 한국 도시/구/동에 정확. 업소 오매칭 없음(주소 전용)."""
    key_ok, _ = check_api_key("kakao")
    if not key_ok:
        return None
    data = api_call("kakao", "/v2/local/search/address.json",
                    params={"query": city, "size": 1}, timeout=10)
    if isinstance(data, dict) and data.get("documents"):
        d = data["documents"][0]
        try:
            return (float(d["y"]), float(d["x"]))  # 카카오: x=경도, y=위도
        except (KeyError, ValueError, TypeError):
            pass
    return None


def _geocode_nominatim(city: str) -> tuple:
    """OpenStreetMap Nominatim (무키). 전세계 폴백 — 한글 외국 도시까지 처리.

    한글 도시의 주 해소기라 일시 장애(rate-limit/타임아웃)가 곧 날씨 조회 전체 실패로
    이어진다(이전 '수원 success=False'의 실제 원인). 일시 장애에 한 번 재시도해 견고화."""
    for attempt in range(2):
        try:
            resp = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": city, "format": "json", "limit": 1, "accept-language": "ko"},
                headers={"User-Agent": "indiebizOS/1.0 (weather)"},
                timeout=8
            )
            if resp.ok:
                arr = resp.json()
                if arr:
                    return (float(arr[0]["lat"]), float(arr[0]["lon"]))
                return None  # 정상 응답인데 결과 없음 — 재시도 무의미
        except Exception:
            if attempt == 0:
                time.sleep(0.6)  # 일시 장애 — 짧은 백오프 후 1회 재시도
    return None


def _has_hangul(s: str) -> bool:
    return any('가' <= c <= '힣' for c in s)


def _resolve_city_coords(city: str) -> tuple:
    """도시명 → (lat, lon). 정적표에 없으면 외부 지오코더로 내부 해소(호출자가 좌표를 떠넘길 필요 없음).

    한글 도시는 Open-Meteo가 동음 외국/타지역 지명으로 오매칭하므로(예 '전주'→압록강변
    40.4N, '수원'→전남 영광 부근 35.36N) 한글이면 Nominatim(accept-language=ko)·Kakao만
    쓰고 Open-Meteo는 폴백에서 뺀다 — *틀린 위치의 날씨를 조용히 반환하는 것(침묵 오답)이
    "못 찾음" 에러보다 나쁘다.* 둘 다 실패하면 차라리 명시적으로 실패한다.
    영문/로마자는 날씨 전용 Open-Meteo가 정확·빠르므로 먼저 쓴다.
    """
    key = city.lower().strip()
    if key in _CITY_COORDS:
        return _CITY_COORDS[key]

    if _has_hangul(city):
        resolvers = (_geocode_nominatim, _geocode_kakao)
    else:
        resolvers = (_geocode_openmeteo, _geocode_nominatim)

    for resolver in resolvers:
        coords = resolver(city)
        if coords:
            _CITY_COORDS[key] = coords  # 런타임 캐시
            return coords
    return None


def get_weather_openmeteo(city: str = None, lat: float = None, lon: float = None,
                          days: int = 3) -> dict:
    """Open-Meteo로 날씨 조회 (무료, API 키 불필요)"""
    # 좌표 결정
    if lat is not None and lon is not None:
        resolved_city = f"{lat},{lon}"
    elif city:
        coords = _resolve_city_coords(city)
        if not coords:
            return {"error": f"'{city}' 도시를 찾을 수 없습니다."}
        lat, lon = coords
        resolved_city = city
    else:
        return {"error": "city(도시명) 또는 lat/lon(좌표)이 필요합니다."}

    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
                "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_sum,sunrise,sunset",
                "timezone": "auto",
                "forecast_days": min(days, 7),
            },
            timeout=10
        )
        if not resp.ok:
            return {"error": f"Open-Meteo API 오류: HTTP {resp.status_code}"}

        data = resp.json()
        current = data.get("current", {})
        daily = data.get("daily", {})

        result = {
            "city": resolved_city,
            "current": {
                "temp": current.get("temperature_2m"),
                "feels_like": current.get("apparent_temperature"),
                "humidity": current.get("relative_humidity_2m"),
                "wind_speed": current.get("wind_speed_10m"),
                "condition": _WMO_CODES.get(current.get("weather_code", -1), "알 수 없음"),
            },
            "items": []
        }

        # 일별 예보 = 단일 통화 items (풍부 dict: date/max_temp/min_temp/condition/precipitation_mm)
        # chart/spreadsheet 소비자는 items에서 수치 칸을 직접 찾음(table 봉투 불필요).
        times = daily.get("time", [])
        for i, date in enumerate(times):
            result["items"].append({
                "date": date,
                "max_temp": daily["temperature_2m_max"][i],
                "min_temp": daily["temperature_2m_min"][i],
                "condition": _WMO_CODES.get(daily["weather_code"][i], "알 수 없음"),
                "precipitation_mm": daily["precipitation_sum"][i],
            })

        return result

    except requests.Timeout:
        return {"error": "날씨 API 타임아웃"}
    except Exception as e:
        return {"error": f"날씨 조회 실패: {str(e)}"}


def execute(tool_input: dict, context) -> str:
    """ToolContext 기반 신규 시그니처."""
    tool_name = context.tool_name
    if tool_name == "get_weather":
        result = get_weather_openmeteo(
            # location/place 별칭 수용 — 약한 모델이 city 대신 흔히 쓰는 이름(침묵 실패 방지).
            # 코드베이스 관용(from/origin·lon/lng)과 동일.
            city=tool_input.get("city") or tool_input.get("location") or tool_input.get("place"),
            lat=tool_input.get("lat"),
            lon=tool_input.get("lon") or tool_input.get("lng"),
            days=tool_input.get("days", 3)
        )
        return json.dumps(result, ensure_ascii=False, indent=2)

    elif tool_name == "amadeus_travel_search":
        result = amadeus_travel_search(tool_input)
        return json.dumps(result, ensure_ascii=False, indent=2)

    elif tool_name == "search_stay":
        # 국내 숙박·단기임대 (여기어때/삼삼엠투/TourAPI) — 소스별 로직은 tool_stay.py
        import importlib.util as _ilu
        _stay_path = os.path.join(os.path.dirname(__file__), "tool_stay.py")
        _spec = _ilu.spec_from_file_location("tool_stay", _stay_path)
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        result = _mod.search_stay(tool_input)
        return json.dumps(result, ensure_ascii=False, indent=2)

    elif tool_name == "search_restaurants":
        query = tool_input.get("query", "")
        if not query:
            return json.dumps({"error": "검색 키워드(query)가 필요합니다."}, ensure_ascii=False)

        # 쿼리 전처리: 장문 자연어 → 짧은 API 검색어
        # "전주 맛집 분위기 좋고 정갈한 곳" → "전주 맛집"
        if len(query) > 15:
            # 수식어/형용사 제거, 장소명 + 핵심 키워드만 추출
            food_keywords = ["맛집", "식당", "음식점", "카페", "레스토랑", "밥집", "술집",
                             "한식", "중식", "일식", "양식", "분식", "치킨", "피자", "파스타",
                             "고기", "삼겹살", "회", "초밥", "국밥", "냉면", "칼국수", "떡볶이"]
            words = query.split()
            essential = []
            for w in words:
                # 장소명 (첫 1-2 단어) 또는 음식 키워드만 유지
                if len(essential) < 2 or any(kw in w for kw in food_keywords):
                    essential.append(w)
            simplified = " ".join(essential[:4])  # 최대 4단어
            if simplified != query:
                query = simplified

        # 카카오 + 네이버 병합 검색 (+블로그 후기 추천 근거)
        try:
            limit = int(tool_input.get("limit") or 30)
        except (TypeError, ValueError):
            limit = 30
        enrich = tool_input.get("enrich")
        enrich = True if enrich is None else str(enrich).lower() not in ("false", "0", "no")
        result = search_restaurants_combined(
            query=query,
            x=tool_input.get("x"),
            y=tool_input.get("y"),
            radius=tool_input.get("radius", 5000),
            kakao_size=limit,
            enrich=enrich
        )
        return json.dumps(result, ensure_ascii=False, indent=2)

    elif tool_name == "kakao_navigation":
        origin = tool_input.get("from") or tool_input.get("origin", "")  # from/to 우선(자연어), origin/destination 별칭
        destination = tool_input.get("to") or tool_input.get("destination", "")

        # 자연어 파싱: "A에서 B까지" 형식을 origin/destination으로 분리
        if destination and not origin:
            route_match = re.search(r'(.+?)에서\s+(.+?)(?:까지|으로|로|$)', destination)
            if route_match:
                origin = route_match.group(1).strip()
                destination = route_match.group(2).strip()

        if not origin or not destination:
            return json.dumps({"error": "출발지(origin)와 목적지(destination)가 필요합니다. 장소명 또는 '경도,위도' 형식."}, ensure_ascii=False)

        result = kakao_navigation(
            origin=origin,
            destination=destination,
            waypoints=tool_input.get("waypoints"),
            priority=tool_input.get("priority", "RECOMMEND"),
            avoid=tool_input.get("avoid"),
            alternatives=tool_input.get("alternatives", False),
            summary=tool_input.get("summary", False),
            generate_map=tool_input.get("generate_map", True)
        )

        # 응답 압축: map_data를 최상위로, 불필요한 route raw 데이터 제거
        if isinstance(result, dict) and "error" not in result:
            compact = {"message": result.get("message", "길찾기 완료")}
            # 요약 정보
            if result.get("routes") and result["routes"][0].get("summary"):
                s = result["routes"][0]["summary"]
                compact["summary"] = {
                    "distance_km": s.get("distance_km", 0),
                    "duration_min": s.get("duration_min", 0),
                    "toll": s.get("fare", {}).get("toll", 0)
                }
            # 주요 안내 (최대 10개)
            if result.get("routes") and result["routes"][0].get("key_guides"):
                compact["key_guides"] = result["routes"][0]["key_guides"][:10]
            # 지도 데이터 (프론트엔드 렌더링용) — 반드시 포함
            if result.get("map_data"):
                compact["map_data"] = result["map_data"]
            return json.dumps(compact, ensure_ascii=False, indent=2)

        return json.dumps(result, ensure_ascii=False, indent=2)

    elif tool_name == "show_location_map":
        result = show_location_map(
            query=tool_input.get("query"),
            lat=tool_input.get("lat"),
            lng=tool_input.get("lng"),
            zoom=tool_input.get("zoom", 15),
            markers=tool_input.get("markers")
        )
        return json.dumps(result, ensure_ascii=False, indent=2)

    elif tool_name == "reverse_geocode":
        lat = tool_input.get("lat")
        lon = tool_input.get("lon") or tool_input.get("lng")
        if lat is None or lon is None:
            return json.dumps({"error": "lat(위도)과 lon(경도)이 필요합니다."}, ensure_ascii=False)
        # 카카오 API는 x=경도, y=위도
        result = reverse_geocode_kakao(x=float(lon), y=float(lat))
        return json.dumps(result, ensure_ascii=False, indent=2)

    return f"Unknown tool: {tool_name}"
