"""
tool_ddgs_search.py - 웹 검색 도구 (파일 기반)
AI 에이전트가 웹에서 정보를 검색할 수 있음 (무료 DuckDuckGo 사용)
"""

from ddgs import DDGS
from typing import Dict
import json


def get_tool_definition():
    """도구 정의 반환 (AI가 사용할 수 있도록)"""
    return {
        "name": "ddgs_search",
        "description": """DuckDuckGo 검색 엔진으로 키워드 검색을 수행하고 결과를 자동 생성된 파일에 저장합니다.

**사용 시기:**
- URL을 모를 때 키워드로 찾기 (예: "한국 주식 시장 동향")
- 최신 뉴스나 정보 검색 (예: "AI 최신 뉴스")
- 여러 출처에서 정보 수집

**결과:**
- 파일이 자동으로 생성되며 경로는 반환값의 'file' 필드에 포함됩니다

**사용하지 말아야 할 때:**
- 특정 URL의 내용을 읽어야 할 때 → crawl_website 사용
- 이미 URL을 알고 있을 때 → crawl_website 사용""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "검색할 키워드 또는 질문 (예: '한국 주식 시장 동향', 'AI 최신 뉴스')"
                },
                "count": {
                    "type": "integer",
                    "description": "최대 결과 개수 (기본값: 5, 최대: 10)",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 10
                },
                "country": {
                    "type": "string",
                    "description": "검색 지역 코드 (kr-kr=한국, us-en=미국, jp-jp=일본 등, 기본값: kr-kr)",
                    "default": "kr-kr"
                }
            },
            "required": ["query"]
        }
    }


def search_web(query: str, count: int = 5, country: str = "kr-kr") -> Dict:
    """
    DuckDuckGo로 웹 검색하고 자동 생성된 파일에 저장
    
    Args:
        query: 검색 키워드
        count: 최대 결과 수 (1-10)
        country: 검색 지역
    
    Returns:
        {
            "success": bool,
            "file": str,  # 자동 생성된 파일 경로
            "query": str,
            "count": int,
            "error": str  # 실패 시
        }
    """
    import os
    from datetime import datetime
    
    # 자동 파일명 생성
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"/tmp/search_{timestamp}.json"
    try:
        # 최대 결과 수 제한 (Rate limit 방지)
        count = min(max(1, count), 10)
        
        # DuckDuckGo 검색
        ddgs = DDGS()
        results = ddgs.text(
            query,
            region=country,
            max_results=count,
            safesearch='moderate'
        )
        
        # 결과 정리
        formatted_results = []
        for r in results:
            formatted_results.append({
                "title": r.get("title", "제목 없음"),
                "url": r.get("href", ""),
                "snippet": r.get("body", "설명 없음")
            })
        
        # 파일로 저장
        result_data = {
            "query": query,
            "count": len(formatted_results),
            "results": formatted_results
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        
        return {
            "success": True,
            "file": output_file,
            "query": query,
            "count": len(formatted_results)
        }
        
    except Exception as e:
        return {
            "success": False,
            "file": "",
            "query": query,
            "count": 0,
            "error": f"검색 실패: {str(e)}"
        }


def use_tool(tool_input: dict) -> dict:
    """도구 실행"""
    query = tool_input.get('query', '')
    count = tool_input.get('count', 5)
    country = tool_input.get('country', 'kr-kr')
    
    if not query:
        return {
            "success": False,
            "error": "query 파라미터가 필요합니다"
        }
    
    return search_web(query, count, country)
