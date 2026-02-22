"""
naver_map.py - 네이버 지역검색 API
===================================
네이버 검색 API를 사용하여 가게/상점 기본 정보를 검색.
location-services 패키지의 search_naver_local() 패턴 참고.
"""

import os
import re
import logging
import requests
from typing import Dict, Any

logger = logging.getLogger(__name__)

NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")


def clean_html(text: str) -> str:
    """HTML 태그 제거"""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&#39;', "'")
    return text.strip()


def search_local(query: str, display: int = 5) -> Dict[str, Any]:
    """
    네이버 지역검색 API로 가게 정보 검색.

    Args:
        query: 검색 키워드 (예: "오송 미용실")
        display: 결과 수 (최대 5)

    Returns:
        {"success": bool, "results": [...], "query": str, "site": "naver_map"}
    """
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return {
            "success": False,
            "error": "네이버 API 키가 설정되지 않았습니다. "
                     "NAVER_CLIENT_ID, NAVER_CLIENT_SECRET 환경변수를 확인하세요.",
            "site": "naver_map"
        }

    url = "https://openapi.naver.com/v1/search/local.json"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    params = {
        "query": query,
        "display": min(display, 5),
        "sort": "random"
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code != 200:
            return {
                "success": False,
                "error": f"네이버 API 오류 (HTTP {response.status_code})",
                "site": "naver_map"
            }

        data = response.json()
        items = data.get("items", [])

        results = []
        for item in items:
            results.append({
                "name": clean_html(item.get("title", "")),
                "category": item.get("category", ""),
                "address": item.get("roadAddress") or item.get("address", ""),
                "phone": item.get("telephone", ""),
                "link": item.get("link", ""),
                "description": clean_html(item.get("description", "")),
                "source": "naver_map"
            })

        return {
            "success": True,
            "query": query,
            "site": "naver_map",
            "count": len(results),
            "results": results
        }

    except requests.exceptions.Timeout:
        return {"success": False, "error": "네이버 API 타임아웃", "site": "naver_map"}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "네이버 API 연결 실패", "site": "naver_map"}
    except Exception as e:
        logger.error(f"[LocalInfo] 네이버 지도 검색 실패: {e}")
        return {"success": False, "error": str(e), "site": "naver_map"}
