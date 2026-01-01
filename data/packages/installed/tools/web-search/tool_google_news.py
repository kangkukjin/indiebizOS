"""
tool_google_news.py - Google 뉴스 RSS 검색 도구 (파일 기반)

Google News RSS를 사용하여 최신 뉴스를 검색합니다.
"""

import feedparser
from datetime import datetime
from typing import Dict
import json
from urllib.parse import quote_plus


def get_tool_definition():
    """도구 정의 반환"""
    return {
        "name": "google_news_search",
        "description": """Google News에서 최신 뉴스를 검색하고 결과를 자동 생성된 파일에 저장합니다.

**특징:**
- API 키 불필요
- 실시간 최신 뉴스
- 자동 최신순 정렬

**결과:**
- 파일이 자동으로 생성되며 경로는 반환값의 'file' 필드에 포함됩니다

**사용 시기:**
- 최신 뉴스가 필요할 때
- "오늘", "최근", "최신" 같은 시간 키워드가 있을 때""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "검색할 키워드"
                },
                "count": {
                    "type": "integer",
                    "description": "최대 결과 개수 (기본: 10, 최대: 30)",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 30
                },
                "language": {
                    "type": "string",
                    "description": "언어 코드 (ko=한국어, en=영어)",
                    "default": "ko"
                }
            },
            "required": ["query"]
        }
    }


def search_google_news(query: str, count: int = 10, language: str = "ko") -> Dict:
    """Google News 검색하고 자동 생성된 파일에 저장"""
    from datetime import datetime
    
    # 자동 파일명 생성
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"/tmp/news_{timestamp}.json"
    try:
        count = min(max(1, count), 30)
        
        # RSS URL 생성
        encoded_query = quote_plus(query)
        rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl={language}&gl=KR&ceid=KR:{language}"
        
        # RSS 파싱
        feed = feedparser.parse(rss_url)
        
        if not feed.entries:
            return {
                "success": False,
                "error": "뉴스를 찾을 수 없습니다",
                "query": query
            }
        
        # 결과 정리
        results = []
        for entry in feed.entries[:count]:
            results.append({
                "title": entry.get('title', '제목 없음'),
                "url": entry.get('link', ''),
                "published": entry.get('published', ''),
                "source": entry.get('source', {}).get('title', '출처 없음'),
                "summary": entry.get('summary', '요약 없음')
            })
        
        # 파일 저장
        result_data = {
            "query": query,
            "count": len(results),
            "language": language,
            "results": results
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        
        return {
            "success": True,
            "file": output_file,
            "query": query,
            "count": len(results)
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "query": query
        }


def use_tool(tool_input: dict) -> dict:
    query = tool_input.get('query', '')
    count = tool_input.get('count', 10)
    language = tool_input.get('language', 'ko')
    
    if not query:
        return {"success": False, "error": "query가 필요합니다"}
    
    return search_google_news(query, count, language)
