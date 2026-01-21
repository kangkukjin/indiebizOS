import os
import json
import requests
from datetime import datetime
import re

# API Keys (환경변수에서 로드)
NINJAS_API_KEY = os.environ.get("NINJAS_API_KEY", "")
AMADEUS_API_KEY = os.environ.get("AMADEUS_API_KEY", "")
AMADEUS_API_SECRET = os.environ.get("AMADEUS_API_SECRET", "")
AMADEUS_BASE_URL = "https://test.api.amadeus.com"
KAKAO_REST_API_KEY = os.environ.get("KAKAO_REST_API_KEY", "")
NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")

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


def search_kakao_restaurants(query: str, x: str = None, y: str = None,
                             radius: int = 5000, size: int = 10, sort: str = "accuracy"):
    """
    카카오 로컬 API로 맛집/음식점 검색

    Args:
        query: 검색 키워드 (예: "강남 파스타", "홍대 맛집")
        x: 중심 좌표 경도
        y: 중심 좌표 위도
        radius: 검색 반경 (미터, 최대 20000)
        size: 결과 수 (최대 15)
        sort: 정렬 (accuracy: 정확도순, distance: 거리순)
    """
    if not KAKAO_REST_API_KEY:
        return {"error": "KAKAO_REST_API_KEY 환경변수가 설정되지 않았습니다. https://developers.kakao.com 에서 발급받으세요."}

    url = "https://dapi.kakao.com/v2/local/search/keyword.json"
    headers = {
        "Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"
    }
    params = {
        "query": query,
        "category_group_code": "FD6",  # 음식점 카테고리
        "size": min(size, 15),
        "sort": sort
    }

    if x and y:
        params["x"] = x
        params["y"] = y
        params["radius"] = min(radius, 20000)

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code != 200:
            return {"error": f"카카오 API 오류: {response.status_code} - {response.text}"}

        data = response.json()
        documents = data.get("documents", [])

        restaurants = []
        for doc in documents:
            restaurants.append({
                "name": doc.get("place_name", ""),
                "category": doc.get("category_name", ""),
                "address": doc.get("road_address_name") or doc.get("address_name", ""),
                "phone": doc.get("phone", ""),
                "url": doc.get("place_url", ""),
                "distance": doc.get("distance", ""),
                "x": doc.get("x", ""),
                "y": doc.get("y", "")
            })

        return {
            "total": data.get("meta", {}).get("total_count", 0),
            "restaurants": restaurants,
            "message": f"'{query}' 검색 결과 {len(restaurants)}개의 맛집을 찾았습니다."
        }

    except requests.exceptions.Timeout:
        return {"error": "카카오 API 요청 시간 초과"}
    except Exception as e:
        return {"error": f"맛집 검색 실패: {str(e)}"}


def search_naver_local(query: str, display: int = 5, sort: str = "random"):
    """
    네이버 로컬 검색 API로 맛집/장소 검색

    Args:
        query: 검색 키워드 (예: "강남 파스타", "홍대 맛집")
        display: 결과 수 (최대 5)
        sort: 정렬 (random: 정확도순, comment: 리뷰순)
    """
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return {"error": "네이버 API 키가 설정되지 않았습니다. https://developers.naver.com 에서 발급받으세요."}

    url = "https://openapi.naver.com/v1/search/local.json"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    params = {
        "query": query,
        "display": min(display, 5),
        "sort": sort
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code != 200:
            return {"error": f"네이버 API 오류: {response.status_code} - {response.text}"}

        data = response.json()
        items = data.get("items", [])

        # HTML 태그 제거 함수
        def clean_html(text):
            return re.sub('<[^<]+?>', '', text) if text else ""

        restaurants = []
        for item in items:
            restaurants.append({
                "name": clean_html(item.get("title", "")),
                "category": item.get("category", ""),
                "address": item.get("roadAddress") or item.get("address", ""),
                "phone": item.get("telephone", ""),
                "url": item.get("link", ""),
                "description": clean_html(item.get("description", "")),
                "mapx": item.get("mapx", ""),
                "mapy": item.get("mapy", "")
            })

        return {
            "total": data.get("total", 0),
            "restaurants": restaurants,
            "message": f"[네이버] '{query}' 검색 결과 {len(restaurants)}개를 찾았습니다."
        }

    except requests.exceptions.Timeout:
        return {"error": "네이버 API 요청 시간 초과"}
    except Exception as e:
        return {"error": f"네이버 검색 실패: {str(e)}"}


def search_restaurants_combined(query: str, x: str = None, y: str = None,
                                 radius: int = 5000, kakao_size: int = 10,
                                 naver_size: int = 5, naver_sort: str = "comment"):
    """
    카카오 + 네이버 API를 병합하여 맛집 검색

    Args:
        query: 검색 키워드
        x, y: 좌표 (카카오용)
        radius: 검색 반경 (카카오용)
        kakao_size: 카카오 결과 수
        naver_size: 네이버 결과 수
        naver_sort: 네이버 정렬 (random/comment)
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

    # 네이버 검색
    naver_result = search_naver_local(query, naver_size, naver_sort)
    if "error" not in naver_result:
        results["naver"] = {
            "restaurants": naver_result.get("restaurants", []),
            "total": naver_result.get("total", 0)
        }
        for r in naver_result.get("restaurants", []):
            r["source"] = "naver"
            results["combined"].append(r)

    kakao_count = len(results["kakao"]["restaurants"])
    naver_count = len(results["naver"]["restaurants"])
    results["message"] = f"'{query}' 검색 결과: 카카오 {kakao_count}개 + 네이버 {naver_count}개 = 총 {kakao_count + naver_count}개"

    return results


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

    # 좌표 샘플링 (너무 많으면 성능 저하, 최대 200개)
    if len(path_latlng) > 200:
        step = len(path_latlng) // 200
        path_latlng = path_latlng[::step]

    return {
        "type": "route_map",
        "origin": {
            "lat": origin_coord[1],
            "lng": origin_coord[0],
            "name": origin_name
        },
        "destination": {
            "lat": dest_coord[1],
            "lng": dest_coord[0],
            "name": dest_name
        },
        "path": path_latlng,
        "summary": {
            "distance_km": summary_info.get("distance_km", 0) if summary_info else 0,
            "duration_min": summary_info.get("duration_min", 0) if summary_info else 0,
            "toll": summary_info.get("fare", {}).get("toll", 0) if summary_info else 0
        }
    }


def kakao_navigation(origin: str, destination: str, waypoints: str = None,
                      priority: str = "RECOMMEND", avoid: str = None,
                      alternatives: bool = False, summary: bool = False,
                      generate_map: bool = True, project_path: str = ".") -> dict:
    """
    카카오모빌리티 길찾기 API

    Args:
        origin: 출발지 좌표 "경도,위도" 또는 "경도,위도,name=장소명"
        destination: 목적지 좌표 "경도,위도" 또는 "경도,위도,name=장소명"
        waypoints: 경유지 (최대 5개, "|"로 구분) "경도1,위도1|경도2,위도2"
        priority: 경로 우선순위 (RECOMMEND: 추천, TIME: 최단시간, DISTANCE: 최단거리)
        avoid: 회피 옵션 (쉼표 구분: toll,motorway,ferries,schoolzone,uturn)
        alternatives: 대안 경로 제공 여부
        summary: 요약 정보만 반환 여부
        generate_map: HTML 지도 생성 여부 (기본: True)
        project_path: 출력 경로

    Returns:
        경로 정보 (거리, 시간, 요금, 구간별 안내, 지도 파일 경로)
    """
    if not KAKAO_REST_API_KEY:
        return {"error": "KAKAO_REST_API_KEY 환경변수가 설정되지 않았습니다."}

    url = "https://apis-navi.kakaomobility.com/v1/directions"
    headers = {
        "Authorization": f"KakaoAK {KAKAO_REST_API_KEY}",
        "Content-Type": "application/json"
    }

    params = {
        "origin": origin,
        "destination": destination,
        "priority": priority,
        "alternatives": str(alternatives).lower(),
        "summary": str(summary).lower()
    }

    if waypoints:
        params["waypoints"] = waypoints
    if avoid:
        params["avoid"] = avoid

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)

        if response.status_code != 200:
            return {"error": f"카카오 네비 API 오류: {response.status_code} - {response.text}"}

        data = response.json()
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

            # 구간별 상세 정보 (summary=False일 때)
            sections = route.get("sections", [])
            if sections:
                route_info["sections"] = []
                for section in sections:
                    section_info = {
                        "distance": section.get("distance"),
                        "duration": section.get("duration"),
                        "guides": []
                    }

                    # 턴바이턴 안내
                    guides = section.get("guides", [])
                    for guide in guides:
                        section_info["guides"].append({
                            "name": guide.get("name"),
                            "guidance": guide.get("guidance"),
                            "type": guide.get("type"),
                            "distance": guide.get("distance")
                        })

                    route_info["sections"].append(section_info)

                    # 경로 좌표 수집 (roads의 vertexes)
                    roads = section.get("roads", [])
                    for road in roads:
                        vertexes = road.get("vertexes", [])
                        # vertexes는 [경도1, 위도1, 경도2, 위도2, ...] 형태
                        for i in range(0, len(vertexes), 2):
                            if i + 1 < len(vertexes):
                                all_path_coords.append((vertexes[i], vertexes[i+1]))

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
            # 출발지/목적지 좌표 파싱
            origin_parts = origin.split(",")
            dest_parts = destination.split(",")

            origin_coord = (float(origin_parts[0]), float(origin_parts[1]))
            dest_coord = (float(dest_parts[0]), float(dest_parts[1]))

            # 장소명 추출
            origin_name = "출발지"
            dest_name = "목적지"
            if len(origin_parts) > 2 and "name=" in origin_parts[2]:
                origin_name = origin_parts[2].replace("name=", "")
            if len(dest_parts) > 2 and "name=" in dest_parts[2]:
                dest_name = dest_parts[2].replace("name=", "")

            # 요약 정보에서 이름 가져오기
            if result["routes"] and result["routes"][0].get("summary"):
                s = result["routes"][0]["summary"]
                if s.get("origin", {}).get("name"):
                    origin_name = s["origin"]["name"]
                if s.get("destination", {}).get("name"):
                    dest_name = s["destination"]["name"]

            # 지도 데이터 생성
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

    except requests.exceptions.Timeout:
        return {"error": "카카오 네비 API 요청 시간 초과"}
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
        if not KAKAO_REST_API_KEY:
            return {"error": "KAKAO_REST_API_KEY 환경변수가 설정되지 않았습니다."}

        try:
            url = "https://dapi.kakao.com/v2/local/search/keyword.json"
            headers = {"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"}
            params = {"query": query, "size": 1}

            response = requests.get(url, headers=headers, params=params, timeout=10)
            data = response.json()

            if data.get("documents"):
                place = data["documents"][0]
                center_lng = float(place["x"])
                center_lat = float(place["y"])
                center_name = place.get("place_name", query)
            else:
                return {"error": f"'{query}' 장소를 찾을 수 없습니다."}

        except Exception as e:
            return {"error": f"장소 검색 실패: {str(e)}"}

    if center_lat is None or center_lng is None:
        return {"error": "위치 정보가 필요합니다. query 또는 lat/lng를 지정하세요."}

    # 마커 목록 생성
    all_markers = [{"name": center_name, "lat": center_lat, "lng": center_lng}]
    if markers:
        all_markers.extend(markers)

    # 지도 데이터 생성
    map_data = {
        "type": "location_map",
        "center": {
            "lat": center_lat,
            "lng": center_lng,
            "name": center_name
        },
        "zoom": zoom,
        "markers": all_markers
    }

    return {
        "message": f"'{center_name}' 위치 지도",
        "center": {"lat": center_lat, "lng": center_lng, "name": center_name},
        "map_data": map_data
    }


def get_api_ninjas_data(endpoint: str, params: dict = None) -> dict:
    """
    API Ninjas를 통해 다양한 지식 정보 조회

    Args:
        endpoint: API 엔드포인트 (quotes, facts, weather, dictionary, trivia 등)
        params: 필터링 매개변수

    지원 엔드포인트 예시:
        - quotes: 명언 (category: happiness, love, etc.)
        - facts: 흥미로운 사실
        - weather: 날씨 (city 필수)
        - dictionary: 사전 정의 (word 필수)
        - trivia: 퀴즈 (category: artliterature, science, etc.)
        - jokes: 농담
        - riddles: 수수께끼
        - historicalevents: 역사적 사건 (day, month, year)
    """
    if not NINJAS_API_KEY:
        return {"error": "NINJAS_API_KEY 환경변수가 설정되지 않았습니다. https://api-ninjas.com 에서 발급받으세요."}

    base_url = "https://api.api-ninjas.com/v1"
    url = f"{base_url}/{endpoint}"

    headers = {
        "X-Api-Key": NINJAS_API_KEY
    }

    try:
        response = requests.get(url, headers=headers, params=params or {}, timeout=15)

        if response.status_code == 401:
            return {"error": "API Ninjas 인증 실패. API 키를 확인하세요."}
        elif response.status_code == 400:
            return {"error": f"잘못된 요청: {response.text}"}
        elif response.status_code != 200:
            return {"error": f"API Ninjas 오류: {response.status_code} - {response.text}"}

        data = response.json()

        # 결과가 리스트인 경우 (대부분의 엔드포인트)
        if isinstance(data, list):
            return {
                "endpoint": endpoint,
                "count": len(data),
                "results": data
            }
        else:
            return {
                "endpoint": endpoint,
                "result": data
            }

    except requests.exceptions.Timeout:
        return {"error": "API Ninjas 요청 시간 초과"}
    except Exception as e:
        return {"error": f"API Ninjas 조회 실패: {str(e)}"}


def search_public_apis(title: str = None, category: str = None) -> dict:
    """
    Public APIs 라이브러리에서 API 검색

    Args:
        title: API 이름으로 검색
        category: 카테고리로 검색 (예: Weather, Finance, Games 등)

    Note: api.publicapis.org 서비스가 중단되어 현재 제한적으로 동작합니다.
    """
    # 내장 API 목록 (자주 사용되는 무료 API들)
    builtin_apis = [
        {"API": "Open-Meteo", "Description": "Free weather API with hourly forecasts", "Auth": "", "HTTPS": True, "Cors": "yes", "Category": "Weather", "Link": "https://open-meteo.com/"},
        {"API": "OpenWeatherMap", "Description": "Weather data and forecasts", "Auth": "apiKey", "HTTPS": True, "Cors": "unknown", "Category": "Weather", "Link": "https://openweathermap.org/api"},
        {"API": "CoinGecko", "Description": "Cryptocurrency data API", "Auth": "", "HTTPS": True, "Cors": "yes", "Category": "Cryptocurrency", "Link": "https://www.coingecko.com/en/api"},
        {"API": "ExchangeRate-API", "Description": "Free currency exchange rates", "Auth": "", "HTTPS": True, "Cors": "yes", "Category": "Currency", "Link": "https://www.exchangerate-api.com/"},
        {"API": "REST Countries", "Description": "Country information", "Auth": "", "HTTPS": True, "Cors": "unknown", "Category": "Geography", "Link": "https://restcountries.com/"},
        {"API": "JSONPlaceholder", "Description": "Fake data for testing and prototyping", "Auth": "", "HTTPS": True, "Cors": "unknown", "Category": "Development", "Link": "https://jsonplaceholder.typicode.com/"},
        {"API": "Random User", "Description": "Random user data generator", "Auth": "", "HTTPS": True, "Cors": "unknown", "Category": "Development", "Link": "https://randomuser.me/"},
        {"API": "PokéAPI", "Description": "Pokemon data API", "Auth": "", "HTTPS": True, "Cors": "yes", "Category": "Games", "Link": "https://pokeapi.co/"},
        {"API": "OMDB", "Description": "Movie database", "Auth": "apiKey", "HTTPS": True, "Cors": "unknown", "Category": "Movies", "Link": "http://www.omdbapi.com/"},
        {"API": "NewsAPI", "Description": "News articles from various sources", "Auth": "apiKey", "HTTPS": True, "Cors": "unknown", "Category": "News", "Link": "https://newsapi.org/"},
        {"API": "NASA", "Description": "NASA data including imagery", "Auth": "", "HTTPS": True, "Cors": "unknown", "Category": "Science", "Link": "https://api.nasa.gov/"},
        {"API": "Wikipedia", "Description": "Wikipedia content API", "Auth": "", "HTTPS": True, "Cors": "unknown", "Category": "Reference", "Link": "https://www.mediawiki.org/wiki/API:Main_page"},
        {"API": "Dog API", "Description": "Random dog images", "Auth": "", "HTTPS": True, "Cors": "yes", "Category": "Animals", "Link": "https://dog.ceo/dog-api/"},
        {"API": "Cat Facts", "Description": "Random cat facts", "Auth": "", "HTTPS": True, "Cors": "unknown", "Category": "Animals", "Link": "https://catfact.ninja/"},
        {"API": "JokeAPI", "Description": "Programming and misc jokes", "Auth": "", "HTTPS": True, "Cors": "yes", "Category": "Entertainment", "Link": "https://jokeapi.dev/"},
        {"API": "Quotable", "Description": "Random quotes API", "Auth": "", "HTTPS": True, "Cors": "unknown", "Category": "Quotes", "Link": "https://quotable.io/"},
        {"API": "IP-API", "Description": "IP geolocation", "Auth": "", "HTTPS": False, "Cors": "unknown", "Category": "Network", "Link": "http://ip-api.com/"},
        {"API": "GitHub", "Description": "GitHub repository and user data", "Auth": "OAuth", "HTTPS": True, "Cors": "yes", "Category": "Development", "Link": "https://docs.github.com/en/rest"},
        {"API": "Unsplash", "Description": "Free high-resolution photos", "Auth": "OAuth", "HTTPS": True, "Cors": "unknown", "Category": "Photography", "Link": "https://unsplash.com/developers"},
        {"API": "Spotify", "Description": "Music streaming data", "Auth": "OAuth", "HTTPS": True, "Cors": "unknown", "Category": "Music", "Link": "https://developer.spotify.com/documentation/web-api/"}
    ]

    # 필터링
    filtered = []
    for api in builtin_apis:
        # 카테고리 필터
        if category and api.get("Category", "").lower() != category.lower():
            continue
        # 이름 필터
        if title and title.lower() not in api.get("API", "").lower():
            continue
        filtered.append({
            "name": api.get("API", ""),
            "description": api.get("Description", ""),
            "auth": api.get("Auth", ""),
            "https": api.get("HTTPS", False),
            "cors": api.get("Cors", ""),
            "category": api.get("Category", ""),
            "link": api.get("Link", "")
        })

    # 카테고리 목록 (검색어 없을 때)
    if not title and not category:
        categories = sorted(list(set(api.get("Category", "") for api in builtin_apis)))
        return {
            "type": "categories",
            "count": len(categories),
            "categories": categories,
            "message": "카테고리 목록입니다. category 매개변수로 특정 카테고리의 API를 검색하세요. (내장 목록, 전체 목록은 https://github.com/public-apis/public-apis 참조)"
        }

    return {
        "query": title or category,
        "count": len(filtered),
        "apis": filtered,
        "note": "내장 API 목록입니다. 더 많은 API는 https://github.com/public-apis/public-apis 참조"
    }


def amadeus_travel_search(endpoint: str, params: dict) -> dict:
    """
    Amadeus API를 통한 여행 정보 검색

    Args:
        endpoint: API 엔드포인트
            - flight-offers: 항공권 검색 (originLocationCode, destinationLocationCode, departureDate, adults 필수)
            - hotel-list: 호텔 목록 (cityCode 필수)
            - points-of-interest: 관광지 (latitude, longitude 필수)
        params: 검색 매개변수

    예시:
        항공권: endpoint="flight-offers", params={"originLocationCode": "ICN", "destinationLocationCode": "NRT", "departureDate": "2024-03-01", "adults": 1}
        호텔: endpoint="hotel-list", params={"cityCode": "PAR"}
        관광지: endpoint="points-of-interest", params={"latitude": 48.8566, "longitude": 2.3522}
    """
    if not AMADEUS_API_KEY or not AMADEUS_API_SECRET:
        return {"error": "AMADEUS_API_KEY/AMADEUS_API_SECRET 환경변수가 설정되지 않았습니다. https://developers.amadeus.com 에서 발급받으세요."}

    # 토큰 획득
    token = get_amadeus_token()
    if not token:
        return {"error": "Amadeus API 인증 실패. API 키를 확인하세요."}

    headers = {
        "Authorization": f"Bearer {token}"
    }

    try:
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

        response = requests.get(url, headers=headers, params=params, timeout=20)

        if response.status_code == 401:
            return {"error": "Amadeus API 인증 만료. 다시 시도하세요."}
        elif response.status_code == 400:
            error_detail = response.json().get("errors", [{}])[0].get("detail", response.text)
            return {"error": f"잘못된 요청: {error_detail}"}
        elif response.status_code != 200:
            return {"error": f"Amadeus API 오류: {response.status_code} - {response.text[:500]}"}

        data = response.json()
        results = data.get("data", [])

        return {
            "endpoint": endpoint,
            "count": len(results) if isinstance(results, list) else 1,
            "results": results[:20] if isinstance(results, list) else results,  # 최대 20개
            "meta": data.get("meta", {})
        }

    except requests.exceptions.Timeout:
        return {"error": "Amadeus API 요청 시간 초과"}
    except Exception as e:
        return {"error": f"Amadeus 여행 검색 실패: {str(e)}"}


def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    if tool_name == "get_api_ninjas_data":
        endpoint = tool_input.get("endpoint", "")
        if not endpoint:
            return json.dumps({"error": "endpoint 매개변수가 필요합니다."}, ensure_ascii=False)
        result = get_api_ninjas_data(endpoint, tool_input.get("params"))
        return json.dumps(result, ensure_ascii=False, indent=2)

    elif tool_name == "search_public_apis":
        result = search_public_apis(
            title=tool_input.get("title"),
            category=tool_input.get("category")
        )
        return json.dumps(result, ensure_ascii=False, indent=2)

    elif tool_name == "amadeus_travel_search":
        endpoint = tool_input.get("endpoint", "")
        params = tool_input.get("params", {})
        if not endpoint:
            return json.dumps({"error": "endpoint 매개변수가 필요합니다."}, ensure_ascii=False)
        result = amadeus_travel_search(endpoint, params)
        return json.dumps(result, ensure_ascii=False, indent=2)

    elif tool_name == "search_restaurants":
        query = tool_input.get("query", "")
        if not query:
            return json.dumps({"error": "검색 키워드(query)가 필요합니다."}, ensure_ascii=False)

        # 카카오 + 네이버 병합 검색
        result = search_restaurants_combined(
            query=query,
            x=tool_input.get("x"),
            y=tool_input.get("y"),
            radius=tool_input.get("radius", 5000)
        )
        return json.dumps(result, ensure_ascii=False, indent=2)

    elif tool_name == "kakao_navigation":
        origin = tool_input.get("origin", "")
        destination = tool_input.get("destination", "")
        if not origin or not destination:
            return json.dumps({"error": "출발지(origin)와 목적지(destination) 좌표가 필요합니다."}, ensure_ascii=False)

        result = kakao_navigation(
            origin=origin,
            destination=destination,
            waypoints=tool_input.get("waypoints"),
            priority=tool_input.get("priority", "RECOMMEND"),
            avoid=tool_input.get("avoid"),
            alternatives=tool_input.get("alternatives", False),
            summary=tool_input.get("summary", False),
            generate_map=tool_input.get("generate_map", True),
            project_path=project_path
        )
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

    return f"Unknown tool: {tool_name}"
