"""
tool_ddgs_search.py - 웹 검색 도구
AI 에이전트가 웹에서 정보를 검색할 수 있음 (무료 DuckDuckGo 사용)
검색 결과를 직접 반환합니다 (파일 저장 없음).
"""

from ddgs import DDGS
import json


def search_web(query: str, count: int = 5, country: str = "kr-kr") -> str:
    """
    DuckDuckGo로 웹 검색하고 결과를 직접 반환

    Args:
        query: 검색 키워드
        count: 최대 결과 수 (1-10)
        country: 검색 지역

    Returns:
        JSON 문자열 (results 포함)
    """
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

        return json.dumps({
            "success": True,
            "query": query,
            "count": len(formatted_results),
            "results": formatted_results
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({
            "success": False,
            "query": query,
            "error": f"검색 실패: {str(e)}"
        }, ensure_ascii=False)


def use_tool(tool_input: dict) -> str:
    """도구 실행"""
    query = tool_input.get('query', '')
    count = tool_input.get('count', 5)
    country = tool_input.get('country', 'kr-kr')

    if not query:
        return json.dumps({
            "success": False,
            "error": "query 파라미터가 필요합니다"
        }, ensure_ascii=False)

    return search_web(query, count, country)
