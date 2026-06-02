"""
ITS 국가교통정보센터 교통 CCTV

전국 고속도로 및 국도의 실시간 CCTV 영상 정보를 조회합니다.

필요 환경변수:
  - ITS_API_KEY: 국가교통정보센터 API 키 (https://www.its.go.kr 에서 발급)
"""

import json
import os
import time
import webbrowser
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict

from common import calculate_distance, success_response, error_response, KOREA_BOUNDS

# API 설정
ITS_API_KEY = os.environ.get("ITS_API_KEY", "")
ITS_API_BASE = "https://openapi.its.go.kr:9443/cctvInfo"

# 전국 CCTV 캐시 (이름 검색 가속화)
_name_search_cache = {"data": [], "timestamp": 0}
_NAME_CACHE_TTL = 120  # 2분


def _call_single_api(rtype: str, min_x: float, max_x: float,
                     min_y: float, max_y: float) -> List[Dict]:
    """단일 도로 유형 + 단일 영역 API 호출 (병렬 실행 단위)"""
    params = {
        "apiKey": ITS_API_KEY,
        "type": rtype,
        "cctvType": "1",
        "minX": str(min_x),
        "maxX": str(max_x),
        "minY": str(min_y),
        "maxY": str(max_y),
        "getType": "json"
    }

    results = []
    try:
        response = requests.get(ITS_API_BASE, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        if "response" in data and "data" in data["response"]:
            cctv_list = data["response"]["data"]
            if cctv_list and isinstance(cctv_list, list):
                for cctv in cctv_list:
                    if isinstance(cctv, dict):
                        cctv["road_type"] = rtype
                        results.append(cctv)
    except requests.exceptions.RequestException as e:
        print(f"[CCTV] API 호출 오류 ({rtype}): {e}")
    except json.JSONDecodeError as e:
        print(f"[CCTV] JSON 파싱 오류 ({rtype}): {e}")

    return results


def _call_cctv_api(min_x: float, max_x: float, min_y: float, max_y: float,
                   road_type: str = "all") -> List[Dict]:
    """CCTV API 호출 (도로 유형별 병렬)"""
    if not ITS_API_KEY:
        raise ValueError("ITS_API_KEY 환경변수가 설정되지 않았습니다.")

    types_to_query = ["ex", "its"] if road_type == "all" else [road_type]

    if len(types_to_query) == 1:
        return _call_single_api(types_to_query[0], min_x, max_x, min_y, max_y)

    # 2개 도로 유형 병렬 호출
    results = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(_call_single_api, rtype, min_x, max_x, min_y, max_y): rtype
            for rtype in types_to_query
        }
        for future in as_completed(futures):
            results.extend(future.result())

    return results


def _call_cctv_api_multi_region(regions: List[Dict], road_type: str = "all") -> List[Dict]:
    """여러 지역을 병렬로 API 호출 (이름 검색용)"""
    if not ITS_API_KEY:
        raise ValueError("ITS_API_KEY 환경변수가 설정되지 않았습니다.")

    types_to_query = ["ex", "its"] if road_type == "all" else [road_type]

    # 모든 (지역 × 도로유형) 조합을 병렬 실행
    tasks = []
    for region in regions:
        for rtype in types_to_query:
            tasks.append((rtype, region["min_x"], region["max_x"],
                          region["min_y"], region["max_y"]))

    results = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_call_single_api, *task) for task in tasks]
        for future in as_completed(futures):
            results.extend(future.result())

    return results


def _format_cctv(cctv: Dict, distance: float = None) -> Dict:
    """CCTV 정보 포맷팅"""
    result = {
        "name": cctv.get("cctvname", "알 수 없음"),
        "url": cctv.get("cctvurl", ""),
        "lat": float(cctv.get("coordy", 0)),
        "lng": float(cctv.get("coordx", 0)),
        "road_type": "고속도로" if cctv.get("road_type") == "ex" else "국도",
        "format": cctv.get("cctvformat", ""),
        "resolution": cctv.get("cctvresolution", ""),
        "source": "its_traffic"
    }
    if distance is not None:
        result["distance_km"] = round(distance, 2)
    return result


def search_cctv(min_x: float, max_x: float, min_y: float, max_y: float,
                road_type: str = "all") -> str:
    """지정한 영역 내의 CCTV 목록 조회"""
    try:
        cctv_list = _call_cctv_api(min_x, max_x, min_y, max_y, road_type)
        if not cctv_list:
            return success_response(count=0, message="해당 영역에 CCTV가 없습니다.", cctvs=[])

        formatted = [_format_cctv(c) for c in cctv_list]
        return success_response(count=len(formatted), cctvs=formatted)
    except Exception as e:
        return error_response(str(e))


def get_nearby_cctv(lat: float, lng: float, radius: float = 0.1,
                    count: int = 1, road_type: str = "all") -> str:
    """특정 좌표에서 가장 가까운 CCTV 찾기"""
    try:
        min_x, max_x = lng - radius, lng + radius
        min_y, max_y = lat - radius, lat + radius

        cctv_list = _call_cctv_api(min_x, max_x, min_y, max_y, road_type)

        if not cctv_list:
            expanded = radius * 2
            cctv_list = _call_cctv_api(lng - expanded, lng + expanded,
                                       lat - expanded, lat + expanded, road_type)

        if not cctv_list:
            return success_response(count=0,
                                    message=f"반경 {radius * 111:.1f}km 내에 CCTV가 없습니다.",
                                    cctvs=[])

        for cctv in cctv_list:
            cctv_lat = float(cctv.get("coordy", 0))
            cctv_lng = float(cctv.get("coordx", 0))
            cctv["_distance"] = calculate_distance(lat, lng, cctv_lat, cctv_lng)

        cctv_list.sort(key=lambda x: x["_distance"])
        top_cctvs = cctv_list[:count]
        formatted = [_format_cctv(c, c["_distance"]) for c in top_cctvs]

        return success_response(count=len(formatted),
                                search_location={"lat": lat, "lng": lng},
                                cctvs=formatted)
    except Exception as e:
        return error_response(str(e))


def get_cctv_by_name(keyword: str, road_type: str = "all", limit: int = 10) -> str:
    """CCTV 이름으로 검색 (병렬 + 캐싱)"""
    global _name_search_cache

    try:
        now = time.time()

        # 캐시 유효하면 사용 (2분 TTL)
        if _name_search_cache["data"] and (now - _name_search_cache["timestamp"]) < _NAME_CACHE_TTL:
            all_cctvs = _name_search_cache["data"]
        else:
            # 4개 지역 × 도로유형 병렬 호출
            regions = [
                {"min_x": 126.0, "max_x": 129.5, "min_y": 37.0, "max_y": 38.5},
                {"min_x": 126.0, "max_x": 128.0, "min_y": 35.5, "max_y": 37.0},
                {"min_x": 128.0, "max_x": 130.0, "min_y": 35.5, "max_y": 37.0},
                {"min_x": 126.0, "max_x": 130.0, "min_y": 34.0, "max_y": 35.5},
            ]
            all_cctvs = _call_cctv_api_multi_region(regions, road_type)

            # 캐시 업데이트
            _name_search_cache["data"] = all_cctvs
            _name_search_cache["timestamp"] = now

        # 키워드 필터링
        keyword_lower = keyword.lower()
        matched = [c for c in all_cctvs if keyword_lower in c.get("cctvname", "").lower()]

        if not matched:
            return success_response(count=0,
                                    message=f"'{keyword}'를 포함하는 CCTV를 찾을 수 없습니다.",
                                    cctvs=[])

        matched = matched[:limit]
        formatted = [_format_cctv(c) for c in matched]
        return success_response(count=len(formatted), keyword=keyword, cctvs=formatted)
    except Exception as e:
        return error_response(str(e))


def open_cctv(url: str = None, name: str = None, lat: float = None, lng: float = None) -> str:
    """CCTV 영상을 브라우저에서 열기"""
    try:
        if url:
            webbrowser.open(url)
            return success_response(message="CCTV 영상을 브라우저에서 열었습니다.", url=url)

        if name:
            result = json.loads(get_cctv_by_name(name, limit=1))
            if result.get("cctvs"):
                cctv = result["cctvs"][0]
                webbrowser.open(cctv["url"])
                return success_response(message=f"'{cctv['name']}' CCTV 영상을 열었습니다.",
                                        url=cctv["url"], cctv=cctv)
            else:
                return error_response(f"'{name}' CCTV를 찾을 수 없습니다.")

        if lat is not None and lng is not None:
            result = json.loads(get_nearby_cctv(lat, lng, count=1))
            if result.get("cctvs"):
                cctv = result["cctvs"][0]
                webbrowser.open(cctv["url"])
                return success_response(
                    message=f"'{cctv['name']}' CCTV 영상을 열었습니다. (거리: {cctv.get('distance_km', '?')}km)",
                    url=cctv["url"], cctv=cctv)
            else:
                return error_response("근처에 CCTV를 찾을 수 없습니다.")

        return error_response("url, name, 또는 lat/lng 중 하나를 지정해야 합니다.")
    except Exception as e:
        return error_response(str(e))
