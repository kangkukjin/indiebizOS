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
        return {"success": False, "error": f"{key_error} https://developers.kakao.com 에서 발급받으세요."}

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
        return {"success": False, "error": f"{key_error} https://developers.naver.com 에서 발급받으세요."}

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
    # 제목 칸 규약(F1, 2026-08-16 상상훈련): 계열 간 제목 칸이 name/title 로 갈리면
    # 교차 each/join 이 매번 필드명 실측을 요구한다 — 표준 title 을 병기(native name 보존).
    for r in results["combined"]:
        r.setdefault("title", r.get("name", ""))
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
        return {"success": False, "error": key_error}

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

    return {"success": False, "error": "결과가 없습니다."}


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
        return {"success": False, "error": key_error}

    # 장소명 → 좌표 자동 변환
    origin_info = _geocode_place(origin)
    if not origin_info:
        return {"success": False, "error": f"출발지를 찾을 수 없습니다: {origin}"}

    dest_info = _geocode_place(destination)
    if not dest_info:
        return {"success": False, "error": f"목적지를 찾을 수 없습니다: {destination}"}

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
            return {"success": False, "error": "경로를 찾을 수 없습니다.", "raw": data}

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
        return {"success": False, "error": f"길찾기 실패: {str(e)}"}


_MARKER_LABEL_KEYS = ("name", "title", "label")
_MARKER_PLACE_KEYS = ("place", "query", "address", "location")


def _marker_label(mk: dict, fallback: str = "") -> str:
    for k in _MARKER_LABEL_KEYS:
        if mk.get(k):
            return str(mk[k])
    return fallback


def _marker_place_term(mk: dict) -> str:
    """좌표 없는 마커에서 '무엇을 찾을지'를 뽑는다. 전용 키(place/address 등)가 라벨(name)보다
    우선 — 라벨은 '① 어머니 댁 (황골마을1단지)'처럼 꾸며져 있어 검색어로는 약하다."""
    for k in _MARKER_PLACE_KEYS:
        if mk.get(k):
            return str(mk[k])
    return _marker_label(mk)


def _normalize_markers(markers) -> tuple:
    """마커 정규화. 좌표가 없으면 장소명으로 지오코딩해서 살린다.

    좌표만 받던 옛 계약은 desc 가 광고한 "여러 장소 비교"를 실제로는 못 하게 했다 —
    장소명을 넣으면 조용히 탈락한 뒤 "위치 정보가 필요합니다"라는 엉뚱한 거절이 나갔다
    (2026-08-18 ep1202: 마커 3개를 줬는데 안 준 것처럼 답함).
    반환: (정규화 목록, 지오코딩된 [(라벨, 찾은 이름)], 못 찾은 [라벨])
    """
    norm, geocoded, failed = [], [], []
    for raw in markers or []:
        mk = {"name": raw} if isinstance(raw, str) else raw
        if not isinstance(mk, dict):
            failed.append(str(raw)[:40])
            continue
        label, note = _marker_label(mk), None
        try:
            entry = {"name": label, "lat": float(mk["lat"]), "lng": float(mk["lng"])}
        except (KeyError, TypeError, ValueError):
            term = _marker_place_term(mk)
            hit = _geocode_place(term) if term else None
            if not hit:
                failed.append(label or term or "?")
                continue
            x, y, found = hit          # _geocode_place 는 (경도, 위도, 이름) 순
            entry = {"name": label or found or term, "lat": y, "lng": x}
            geocoded.append((entry["name"], found or term))
            if found and found != entry["name"]:
                note = f"카카오 검색: {found}"   # 무엇으로 해석했는지 지도에서 보이게
        # $items 파이프의 가격·링크를 통과시킨다 (여기서 조용히 사라지던 것).
        # url 은 웹 주소만 — 사진 items 의 로컬 파일 경로는 지도 팝업에서 열리지 않는
        # 죽은 링크가 되므로 싣지 않는다.
        if mk.get("meta"):
            entry["meta"] = str(mk["meta"])
        if str(mk.get("url") or "").startswith(("http://", "https://")):
            entry["url"] = str(mk["url"])
        if note and not entry.get("meta"):
            entry["meta"] = note
        norm.append(entry)
    return norm, geocoded, failed


def show_location_map(query: str = None, lat: float = None, lng: float = None,
                       zoom: int = 15, markers: list = None, title: str = None) -> dict:
    """
    특정 위치의 지도를 대화창에 표시

    Args:
        query: 장소명 (예: '강남역'). markers 가 있으면 좌표로 풀지 않고 제목으로만 쓴다.
        lat: 위도 (직접 지정시)
        lng: 경도 (직접 지정시)
        zoom: 줌 레벨 (기본: 15)
        markers: 마커 목록. [{name, lat, lng}] 또는 장소명 문자열/이름만 있는 dict (자동 좌표 변환)
        title: 지도 제목. 절대 좌표로 풀지 않는다 ('광교 코스'처럼 장소가 아닌 이름표용)

    Returns:
        지도 데이터 (map_data 포함)
    """
    norm_markers, geocoded, failed = _normalize_markers(markers)

    center_lat, center_lng = lat, lng
    center_name = title or query or "위치"

    # query 지오코딩 — 마커가 이미 지도를 세우면 query 는 좌표로 풀지 않는다.
    # 카카오 키워드 검색은 임계값이 없어 어떤 문자열에도 뭔가를 돌려준다. 그래서 코스
    # 이름표 '광교 코스'가 상점 'COS 갤러리아광교점'으로 풀려 중심·대표 핀을 차지했다
    # (ep1202). 이름표는 title, 보여줄 곳은 markers 로 간다.
    if query and not norm_markers and (center_lat is None or center_lng is None):
        key_ok, key_error = check_api_key("kakao")
        if not key_ok:
            return {"success": False, "error": key_error}

        data = api_call("kakao", "/v2/local/search/keyword.json",
                        params={"query": query, "size": 1}, timeout=10)
        if isinstance(data, dict) and "error" in data:
            return data

        if data.get("documents"):
            place = data["documents"][0]
            center_lng = float(place["x"])
            center_lat = float(place["y"])
            center_name = title or place.get("place_name", query)
        else:
            return {"success": False, "error": f"'{query}' 장소를 찾을 수 없습니다."}

    # 마커만으로도 지도가 서게 — 중심 미지정이면 첫 마커를 중심으로 (2026-08-16 G1-③:
    # 파이프 하류 `{markers: "$items"}` 호출의 자기 계약 완결).
    center_from_markers = False
    if (center_lat is None or center_lng is None) and norm_markers:
        center_lat = norm_markers[0]["lat"]
        center_lng = norm_markers[0]["lng"]
        # 이름표 우선순위: title > query(좌표로 풀지 않고 제목으로만) > 첫 마커 이름
        center_name = title or query or norm_markers[0]["name"] or center_name
        center_from_markers = True

    if center_lat is None or center_lng is None:
        # 왜 못 세웠는지 말한다 — 준 것을 안 준 것처럼 답하지 않는다.
        if failed:
            return {"success": False, "error":
                    f"마커 {len(failed)}개가 좌표 없이 들어왔고 장소명으로도 찾지 못했습니다: "
                    f"{', '.join(failed[:5])}. 마커는 {{name, lat, lng}} 또는 실재하는 장소명이어야 합니다."}
        return {"success": False,
                "error": "위치 정보가 필요합니다. query 또는 lat/lng 또는 markers 를 지정하세요."}

    # 마커 목록 생성 (중심이 마커에서 나왔으면 같은 점을 이중 표기하지 않는다)
    all_markers = [] if center_from_markers else [{"name": center_name, "lat": center_lat, "lng": center_lng}]
    all_markers.extend(norm_markers)

    # 지도 데이터 생성 (표시 봉투 단일 빌더, #4)
    map_data = build_location_map(
        center={"lat": center_lat, "lng": center_lng, "name": center_name},
        markers=all_markers, zoom=zoom)

    msg = f"'{center_name}' 위치 지도"
    if geocoded:
        shown = ", ".join(f"{lab}→{found}" for lab, found in geocoded[:3])
        msg += f" (장소명 {len(geocoded)}개 좌표 변환: {shown}{'…' if len(geocoded) > 3 else ''})"
    if failed:
        msg += f" (좌표·장소를 못 찾은 {len(failed)}개는 싣지 못함: {', '.join(failed[:3])})"
    result = {
        "message": msg,
        "center": {"lat": center_lat, "lng": center_lng, "name": center_name},
        "map_data": map_data
    }
    if failed:
        result["unresolved"] = failed
    return result


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
    이어진다(이전 '수원 success=False'의 실제 원인). 일시 장애에 한 번 재시도해 견고화.
    호출은 common.geocode 단일 소스 (감사 ⑥) — 전세계(countrycodes=None)·ko 라벨."""
    from common.geocode import nominatim_search
    hit = nominatim_search(city, countrycodes=None, accept_language="ko",
                           timeout=8, retries=1, user_agent="indiebizOS/1.0 (weather)")
    return (hit["lat"], hit["lng"]) if hit else None


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
            return {"success": False, "error": f"'{city}' 도시를 찾을 수 없습니다."}
        lat, lon = coords
        resolved_city = city
    else:
        return {"success": False, "error": "city(도시명) 또는 lat/lon(좌표)이 필요합니다."}

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
            return {"success": False, "error": f"Open-Meteo API 오류: HTTP {resp.status_code}"}

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
        return {"success": False, "error": "날씨 API 타임아웃"}
    except Exception as e:
        return {"success": False, "error": f"날씨 조회 실패: {str(e)}"}


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
            return json.dumps({"success": False, "error": "검색 키워드(query)가 필요합니다."}, ensure_ascii=False)

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

        # origin 기본값 = 이 몸의 선언 위치 (2026-08-16 상상훈련 F5 — "강남역까지"라는
        # 의도는 출발지=지금 여기를 함의하는데 기본값이 없어 {to: ...} 단독 호출이
        # 항상 실패했고, 코퍼스가 그 형태를 가르치고 있었다).
        if destination and not origin:
            try:
                _bl_path = os.path.join(os.environ.get("INDIEBIZ_BASE", os.getcwd()), "data", "body_location.json")
                if not os.path.exists(_bl_path):
                    from runtime_utils import get_base_path
                    _bl_path = os.path.join(str(get_base_path()), "data", "body_location.json")
                with open(_bl_path, encoding="utf-8") as _f:
                    _bl = json.load(_f)
                if _bl.get("lng") is not None and _bl.get("lat") is not None:
                    origin = f"{_bl['lng']},{_bl['lat']}"  # '경도,위도' 형식
            except Exception:
                pass

        # 없는 것만 정확히 짚는다 — "둘 다 필요합니다"는 destination 만 준 호출에 거짓말이었다.
        if not origin and not destination:
            return json.dumps({"success": False, "error": "출발지(origin)와 목적지(destination 또는 to)가 필요합니다. 장소명 또는 '경도,위도' 형식."}, ensure_ascii=False)
        if not destination:
            return json.dumps({"success": False, "error": "목적지(destination 또는 to)가 필요합니다. 장소명 또는 '경도,위도' 형식."}, ensure_ascii=False)
        if not origin:
            return json.dumps({"success": False, "error": "출발지(origin)가 필요합니다 — 이 몸의 선언 위치(data/body_location.json)도 없어 기본값을 만들 수 없었습니다."}, ensure_ascii=False)

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
            markers=tool_input.get("markers"),
            title=tool_input.get("title")
        )
        return json.dumps(result, ensure_ascii=False, indent=2)

    elif tool_name == "reverse_geocode":
        lat = tool_input.get("lat")
        lon = tool_input.get("lon") or tool_input.get("lng")
        if lat is None or lon is None:
            return json.dumps({"success": False, "error": "lat(위도)과 lon(경도)이 필요합니다."}, ensure_ascii=False)
        # 카카오 API는 x=경도, y=위도
        result = reverse_geocode_kakao(x=float(lon), y=float(lat))
        return json.dumps(result, ensure_ascii=False, indent=2)

    return error_response(f"Unknown tool: {tool_name}")
