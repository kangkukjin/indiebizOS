"""
CCTV 교통정보 도구 - ITS 국가교통정보센터 API

전국 고속도로 및 국도의 실시간 CCTV 영상 정보를 조회합니다.

필요 환경변수:
  - ITS_API_KEY: 국가교통정보센터 API 키 (https://www.its.go.kr 에서 발급)
"""

import json
import os
import math
import requests
from typing import List, Dict, Any, Optional

# API 설정
ITS_API_KEY = os.environ.get("ITS_API_KEY", "")
ITS_API_BASE = "https://openapi.its.go.kr:9443/cctvInfo"

# 전국 범위 (대한민국)
KOREA_BOUNDS = {
    "min_x": 124.0,  # 최서단 경도
    "max_x": 132.0,  # 최동단 경도
    "min_y": 33.0,   # 최남단 위도
    "max_y": 43.0    # 최북단 위도
}


def _call_cctv_api(min_x: float, max_x: float, min_y: float, max_y: float,
                   road_type: str = "all") -> List[Dict]:
    """CCTV API 호출"""
    if not ITS_API_KEY:
        raise ValueError("ITS_API_KEY 환경변수가 설정되지 않았습니다.")

    results = []

    # 도로 유형에 따라 API 호출
    types_to_query = []
    if road_type == "all":
        types_to_query = ["ex", "its"]
    else:
        types_to_query = [road_type]

    for rtype in types_to_query:
        params = {
            "apiKey": ITS_API_KEY,
            "type": rtype,
            "cctvType": "1",  # 1: 실시간 스트리밍
            "minX": str(min_x),
            "maxX": str(max_x),
            "minY": str(min_y),
            "maxY": str(max_y),
            "getType": "json"
        }

        try:
            response = requests.get(ITS_API_BASE, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if "response" in data and "data" in data["response"]:
                cctv_list = data["response"]["data"]
                if cctv_list:
                    for cctv in cctv_list:
                        cctv["road_type"] = rtype
                    results.extend(cctv_list)
        except requests.exceptions.RequestException as e:
            print(f"[CCTV] API 호출 오류 ({rtype}): {e}")
        except json.JSONDecodeError as e:
            print(f"[CCTV] JSON 파싱 오류 ({rtype}): {e}")

    return results


def _calculate_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """두 좌표 간의 거리 계산 (km, Haversine 공식)"""
    R = 6371  # 지구 반지름 (km)

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)

    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    return R * c


def _format_cctv(cctv: Dict, distance: float = None) -> Dict:
    """CCTV 정보 포맷팅"""
    result = {
        "name": cctv.get("cctvname", "알 수 없음"),
        "url": cctv.get("cctvurl", ""),
        "lat": float(cctv.get("coordy", 0)),
        "lng": float(cctv.get("coordx", 0)),
        "road_type": "고속도로" if cctv.get("road_type") == "ex" else "국도",
        "format": cctv.get("cctvformat", ""),
        "resolution": cctv.get("cctvresolution", "")
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
            return json.dumps({
                "success": True,
                "count": 0,
                "message": "해당 영역에 CCTV가 없습니다.",
                "cctvs": []
            }, ensure_ascii=False)

        formatted = [_format_cctv(c) for c in cctv_list]

        return json.dumps({
            "success": True,
            "count": len(formatted),
            "cctvs": formatted
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e)
        }, ensure_ascii=False)


def get_nearby_cctv(lat: float, lng: float, radius: float = 0.1,
                    count: int = 1, road_type: str = "all") -> str:
    """특정 좌표에서 가장 가까운 CCTV 찾기"""
    try:
        # 검색 영역 설정
        min_x = lng - radius
        max_x = lng + radius
        min_y = lat - radius
        max_y = lat + radius

        cctv_list = _call_cctv_api(min_x, max_x, min_y, max_y, road_type)

        if not cctv_list:
            # 반경을 넓혀서 다시 검색
            expanded_radius = radius * 2
            min_x = lng - expanded_radius
            max_x = lng + expanded_radius
            min_y = lat - expanded_radius
            max_y = lat + expanded_radius
            cctv_list = _call_cctv_api(min_x, max_x, min_y, max_y, road_type)

        if not cctv_list:
            return json.dumps({
                "success": True,
                "count": 0,
                "message": f"반경 {radius*111:.1f}km 내에 CCTV가 없습니다.",
                "cctvs": []
            }, ensure_ascii=False)

        # 거리 계산 및 정렬
        for cctv in cctv_list:
            cctv_lat = float(cctv.get("coordy", 0))
            cctv_lng = float(cctv.get("coordx", 0))
            cctv["_distance"] = _calculate_distance(lat, lng, cctv_lat, cctv_lng)

        cctv_list.sort(key=lambda x: x["_distance"])

        # 상위 N개 반환
        top_cctvs = cctv_list[:count]
        formatted = [_format_cctv(c, c["_distance"]) for c in top_cctvs]

        return json.dumps({
            "success": True,
            "count": len(formatted),
            "search_location": {"lat": lat, "lng": lng},
            "cctvs": formatted
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e)
        }, ensure_ascii=False)


def get_cctv_by_name(keyword: str, road_type: str = "all", limit: int = 10) -> str:
    """CCTV 이름으로 검색"""
    try:
        # 전국 범위로 검색 (여러 영역으로 나눠서)
        all_cctvs = []

        # 대한민국을 4개 영역으로 나눔
        regions = [
            # 서울/경기/강원 북부
            {"min_x": 126.0, "max_x": 129.5, "min_y": 37.0, "max_y": 38.5},
            # 충청/전라 북부
            {"min_x": 126.0, "max_x": 128.0, "min_y": 35.5, "max_y": 37.0},
            # 경상 북부
            {"min_x": 128.0, "max_x": 130.0, "min_y": 35.5, "max_y": 37.0},
            # 남부 (전라/경상 남부)
            {"min_x": 126.0, "max_x": 130.0, "min_y": 34.0, "max_y": 35.5},
        ]

        for region in regions:
            cctvs = _call_cctv_api(
                region["min_x"], region["max_x"],
                region["min_y"], region["max_y"],
                road_type
            )
            all_cctvs.extend(cctvs)

        # 키워드로 필터링
        keyword_lower = keyword.lower()
        matched = [
            c for c in all_cctvs
            if keyword_lower in c.get("cctvname", "").lower()
        ]

        if not matched:
            return json.dumps({
                "success": True,
                "count": 0,
                "message": f"'{keyword}'를 포함하는 CCTV를 찾을 수 없습니다.",
                "cctvs": []
            }, ensure_ascii=False)

        # 결과 제한
        matched = matched[:limit]
        formatted = [_format_cctv(c) for c in matched]

        return json.dumps({
            "success": True,
            "count": len(formatted),
            "keyword": keyword,
            "cctvs": formatted
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e)
        }, ensure_ascii=False)


def execute(tool_name: str, tool_input: dict, project_path: str = None) -> str:
    """
    도구 실행 진입점

    Args:
        tool_name: 실행할 도구 이름
        tool_input: 도구 입력 파라미터
        project_path: 프로젝트 경로 (컨텍스트)

    Returns:
        JSON 형식의 결과 문자열
    """
    print(f"[CCTV] 도구 실행: {tool_name}")
    print(f"[CCTV] 입력: {tool_input}")

    try:
        if tool_name == "search_cctv":
            return search_cctv(
                min_x=tool_input.get("min_x"),
                max_x=tool_input.get("max_x"),
                min_y=tool_input.get("min_y"),
                max_y=tool_input.get("max_y"),
                road_type=tool_input.get("road_type", "all")
            )

        elif tool_name == "get_nearby_cctv":
            return get_nearby_cctv(
                lat=tool_input.get("lat"),
                lng=tool_input.get("lng"),
                radius=tool_input.get("radius", 0.1),
                count=tool_input.get("count", 1),
                road_type=tool_input.get("road_type", "all")
            )

        elif tool_name == "get_cctv_by_name":
            return get_cctv_by_name(
                keyword=tool_input.get("keyword"),
                road_type=tool_input.get("road_type", "all"),
                limit=tool_input.get("limit", 10)
            )

        else:
            return json.dumps({
                "success": False,
                "error": f"알 수 없는 도구: {tool_name}"
            }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
            "tool": tool_name
        }, ensure_ascii=False)


# 도구 목록
TOOLS = ["search_cctv", "get_nearby_cctv", "get_cctv_by_name"]


if __name__ == "__main__":
    # 테스트
    print("CCTV 도구 패키지")
    print(f"도구 목록: {TOOLS}")
    print()

    # API 키 확인
    if ITS_API_KEY:
        print(f"API 키: {ITS_API_KEY[:8]}...")

        # 테스트: 서울 지역 CCTV 검색
        print("\n[테스트] 서울 지역 CCTV 검색...")
        result = search_cctv(126.8, 127.2, 37.4, 37.7, "ex")
        print(result[:500] + "..." if len(result) > 500 else result)
    else:
        print("ITS_API_KEY 환경변수가 설정되지 않았습니다.")
        print("backend/.env 파일에 다음을 추가하세요:")
        print("ITS_API_KEY=your_api_key")
