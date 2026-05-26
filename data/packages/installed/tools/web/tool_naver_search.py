"""
네이버 검색 API 도구

단일 도구로 네이버의 모든 검색 도메인을 호출합니다. (웹 문서/뉴스/블로그/카페/지식인/책/백과)
같은 NAVER_CLIENT_ID/SECRET 한 쌍으로 모든 엔드포인트가 작동합니다.
한국어 검색에서 DuckDuckGo/Google보다 압도적으로 강합니다.
"""
import os
import sys

# common 유틸리티 사용 (handler.py와 동일한 경로 설정)
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.api_client import api_call
from common.auth_manager import check_api_key
from common.html_utils import clean_html


# 지원하는 검색 도메인 → 네이버 API endpoint
_TYPE_ENDPOINTS = {
    "webkr": "/v1/search/webkr.json",         # 일반 웹 문서
    "news": "/v1/search/news.json",           # 뉴스
    "blog": "/v1/search/blog.json",           # 블로그
    "cafe": "/v1/search/cafearticle.json",    # 카페 글
    "kin": "/v1/search/kin.json",             # 지식인
    "book": "/v1/search/book.json",           # 책
    "encyc": "/v1/search/encyc.json",         # 백과사전
    "doc": "/v1/search/doc.json",             # 전문자료
    "shop": "/v1/search/shop.json",           # 쇼핑
}

# 자연어 별칭 — 사용자/AI가 자주 쓰는 표현을 정식 type으로 정규화
_TYPE_ALIASES = {
    "web": "webkr",
    "웹": "webkr",
    "웹검색": "webkr",
    "웹문서": "webkr",
    "뉴스": "news",
    "블로그": "blog",
    "카페": "cafe",
    "cafearticle": "cafe",
    "지식인": "kin",
    "지식IN": "kin",
    "책": "book",
    "도서": "book",
    "백과": "encyc",
    "백과사전": "encyc",
    "전문자료": "doc",
    "쇼핑": "shop",
}


def _normalize_type(type_: str) -> str:
    """type 파라미터를 정식 키로 정규화"""
    if not type_:
        return "webkr"
    return _TYPE_ALIASES.get(type_, type_)


def _format_item(item: dict, type_: str) -> dict:
    """도메인별 응답 item을 통일된 형식으로 변환"""
    base = {
        "title": clean_html(item.get("title", "")),
        "link": item.get("link", ""),
        "snippet": clean_html(item.get("description", "")),
        "site": "naver",
        "type": type_,
    }

    # 도메인별 추가 메타데이터
    if type_ == "news":
        base["pub_date"] = item.get("pubDate", "")
        base["original_link"] = item.get("originallink", "")
    elif type_ == "blog":
        base["blogger"] = item.get("bloggername", "")
        base["blogger_link"] = item.get("bloggerlink", "")
        base["post_date"] = item.get("postdate", "")
    elif type_ == "cafe":
        base["cafe_name"] = item.get("cafename", "")
        base["cafe_url"] = item.get("cafeurl", "")
    elif type_ == "book":
        base["author"] = item.get("author", "")
        base["publisher"] = item.get("publisher", "")
        base["pub_date"] = item.get("pubdate", "")
        base["isbn"] = item.get("isbn", "")
        base["price"] = item.get("price", "")
        base["image"] = item.get("image", "")
    elif type_ == "encyc":
        base["thumbnail"] = item.get("thumbnail", "")
    elif type_ == "shop":
        base["price"] = item.get("lprice", "")
        base["mall"] = item.get("mallName", "")
        base["image"] = item.get("image", "")
        base["category"] = f"{item.get('category1', '')} > {item.get('category2', '')}"

    return base


def search_naver(
    query: str,
    type: str = "webkr",
    display: int = 5,
    sort: str = "sim",
) -> dict:
    """네이버 검색 API 통합 호출

    Args:
        query: 검색어 (한국어/영어 모두 가능)
        type: 검색 도메인 (webkr/news/blog/cafe/kin/book/encyc/doc/shop). 자연어 별칭("웹"/"뉴스" 등)도 허용
        display: 결과 수 (1~100, 기본 5)
        sort: 정렬 — "sim"(정확도, 기본) 또는 "date"(최신순)

    Returns:
        {
          "success": bool,
          "type": 정규화된 type,
          "total": 전체 결과 수,
          "items": [...],
          "source": "네이버 검색 API"
        }
    """
    if not query:
        return {"success": False, "error": "검색어(query)가 필요합니다."}

    normalized_type = _normalize_type(type)
    endpoint = _TYPE_ENDPOINTS.get(normalized_type)
    if not endpoint:
        return {
            "success": False,
            "error": f"지원하지 않는 type입니다: '{type}'. "
                     f"지원 type: {', '.join(_TYPE_ENDPOINTS.keys())}",
        }

    ok, err = check_api_key("naver")
    if not ok:
        return {"success": False, "error": err}

    # display는 네이버 API 제한(1~100, shop은 1~100, 그 외 1~100) 적용
    display = max(1, min(int(display) if display else 5, 100))

    params = {
        "query": query,
        "display": display,
        "sort": sort if sort in ("sim", "date") else "sim",
    }

    data = api_call("naver", endpoint, params=params)

    if isinstance(data, dict) and "error" in data:
        return {"success": False, "error": data["error"], "type": normalized_type}

    raw_items = data.get("items", []) if isinstance(data, dict) else []
    items = [_format_item(item, normalized_type) for item in raw_items]

    return {
        "success": True,
        "type": normalized_type,
        "total": data.get("total", 0) if isinstance(data, dict) else 0,
        "items": items,
        "source": "네이버 검색 API",
    }
