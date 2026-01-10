import os
import json
import requests
from datetime import datetime
from jinja2 import Template
import feedparser
import re

# API Keys (환경변수에서 로드)
NINJAS_API_KEY = os.environ.get("NINJAS_API_KEY", "")
AMADEUS_API_KEY = os.environ.get("AMADEUS_API_KEY", "")
AMADEUS_API_SECRET = os.environ.get("AMADEUS_API_SECRET", "")
AMADEUS_BASE_URL = "https://test.api.amadeus.com"
KAKAO_REST_API_KEY = os.environ.get("KAKAO_REST_API_KEY", "")
NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")

# 출력 디렉토리 설정
OUTPUTS_DIR = 'outputs'

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

def search_news(keyword, max_results=5):
    from duckduckgo_search import DDGS
    results = []
    try:
        with DDGS() as ddgs:
            # 최신 ddgs 라이브러리 형식 사용 (ddgs.news)
            ddgs_gen = ddgs.news(keyword, region="wt-wt", safesearch="off", timelimit="d", max_results=max_results)
            for r in ddgs_gen:
                results.append({
                    "title": r['title'],
                    "snippet": r['body'],
                    "link": r['url'],
                    "source": r['source']
                })
    except Exception as e:
        print(f"Error searching news for {keyword}: {e}")
    return results

def fetch_rss(url, limit=7):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200: return []
        feed = feedparser.parse(response.text)
        articles = []
        source_title = feed.feed.get('title', 'RSS Source')
        for entry in feed.entries[:limit]:
            content = entry.get('summary', entry.get('description', ''))
            clean_text = re.sub('<[^<]+?>', '', str(content)).replace('&nbsp;', ' ').strip()
            articles.append({
                "title": entry.get('title', 'No Title'),
                "snippet": clean_text[:400] + "...",
                "link": entry.get('link', ''),
                "source": source_title
            })
        return articles
    except: return []


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


DEFAULT_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="utf-8">
    <title>{{ title }}</title>
    <style>
        body { font-family: sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; color: #333; }
        h1 { color: #1a2a6c; border-bottom: 2px solid #1a2a6c; }
        .article { margin-bottom: 30px; }
        .article h3 { margin: 0; }
        .article a { color: #3498db; }
    </style>
</head>
<body>
    <h1>{{ title }}</h1>
    <p>발행일: {{ date }}</p>
    {% for section in sections %}
        <h2>{{ section.keyword }}</h2>
        {% for article in section.articles %}
            <div class="article">
                <h3>{{ article.title }}</h3>
                <p>{{ article.snippet }}</p>
                <a href="{{ article.link }}" target="_blank">기사 보기</a>
            </div>
        {% endfor %}
    {% endfor %}
</body>
</html>
"""

def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    out_dir = os.path.join(project_path, OUTPUTS_DIR)
    os.makedirs(out_dir, exist_ok=True)

    if tool_name == "generate_magazine":
        topic = tool_input.get("topic")
        title = tool_input.get("title", f"{topic} Weekly Magazine")
        articles = search_news(topic, 10)
        sections = [{"keyword": "심층 취재", "articles": articles}]
        
        template = Template(DEFAULT_TEMPLATE)
        html = template.render(title=title, date=datetime.now().strftime("%Y-%m-%d"), sections=sections)
        filename = f"magazine_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        filepath = os.path.join(out_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f: f.write(html)
        return f"잡지 생성 완료: {os.path.abspath(filepath)}"

    elif tool_name == "generate_it_newspaper":
        title = tool_input.get("title", "IT Tech News")
        sections = [
            {"keyword": "Hacker News", "articles": fetch_rss("https://hnrss.org/frontpage", 5)},
            {"keyword": "Reddit AI", "articles": fetch_rss("https://www.reddit.com/r/artificial/.rss", 5)},
            {"keyword": "Ars Technica", "articles": fetch_rss("https://feeds.arstechnica.com/arstechnica/index", 5)},
            {"keyword": "TechCrunch", "articles": fetch_rss("https://techcrunch.com/feed/", 5)}
        ]
        template = Template(DEFAULT_TEMPLATE)
        html = template.render(title=title, date=datetime.now().strftime("%Y-%m-%d"), sections=sections)
        filename = f"it_news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        filepath = os.path.join(out_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f: f.write(html)
        return f"IT 신문 생성 완료: {os.path.abspath(filepath)}"

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

    return f"Unknown tool: {tool_name}"
