"""
tool_unified_search.py - 종합 검색 도구
DuckDuckGo 웹 검색 + Google News + YouTube + OpenAlex 논문을 한 번에 검색하여 통합 결과 반환
"""

import os
import sys
import importlib.util
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote_plus

_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.response_formatter import format_json

current_dir = Path(__file__).parent


def _search_ddg(query: str, count: int = 5, country: str = "kr-kr") -> dict:
    """DuckDuckGo 웹 검색"""
    try:
        from ddgs import DDGS
        count = min(max(1, count), 10)
        ddgs = DDGS()
        results = ddgs.text(query, region=country, max_results=count, safesearch='moderate')
        formatted = []
        for r in results:
            formatted.append({
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            })
        return {"source": "web", "success": True, "count": len(formatted), "results": formatted}
    except Exception as e:
        return {"source": "web", "success": False, "error": str(e), "results": []}


def _search_news(query: str, count: int = 5, language: str = "ko") -> dict:
    """Google News RSS 검색"""
    try:
        import feedparser
        from common.html_utils import clean_html
    except ImportError:
        return {"source": "news", "success": False, "error": "feedparser 미설치", "results": []}

    try:
        count = min(max(1, count), 20)
        encoded_query = quote_plus(query)
        region = {"ko": "KR", "en": "US", "ja": "JP", "zh": "CN"}.get(language, "US")
        rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl={language}&gl={region}&ceid={region}:{language}"

        feed = feedparser.parse(rss_url)
        if not feed.entries:
            return {"source": "news", "success": True, "count": 0, "results": []}

        formatted = []
        for entry in feed.entries[:count]:
            formatted.append({
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "published": entry.get("published", ""),
                "source_name": entry.get("source", {}).get("title", ""),
                "summary": clean_html(entry.get("summary", "")),
            })
        return {"source": "news", "success": True, "count": len(formatted), "results": formatted}
    except Exception as e:
        return {"source": "news", "success": False, "error": str(e), "results": []}


def _search_youtube(query: str, count: int = 3) -> dict:
    """YouTube 검색"""
    try:
        import yt_dlp
    except ImportError:
        return {"source": "youtube", "success": False, "error": "yt-dlp 미설치", "results": []}

    try:
        count = min(max(1, count), 10)
        search_query = f"ytsearch{count}:{query}"
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'extract_flat': True}) as ydl:
            result = ydl.extract_info(search_query, download=False)
            entries = result.get("entries", [])

        # 채널/플레이리스트 필터링
        entries = [e for e in entries if e.get("id") and not e["id"].startswith("UC") and len(e["id"]) <= 16]

        formatted = []
        for e in entries:
            vid = e.get("id", "")
            duration = e.get("duration")
            if duration:
                mins, secs = divmod(int(duration), 60)
                hours, mins = divmod(mins, 60)
                duration_str = f"{hours}:{mins:02d}:{secs:02d}" if hours else f"{mins}:{secs:02d}"
            else:
                duration_str = ""
            formatted.append({
                "title": e.get("title", ""),
                "channel": e.get("channel", e.get("uploader", "")),
                "duration": duration_str,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "video_id": vid,
            })
        return {"source": "youtube", "success": True, "count": len(formatted), "results": formatted}
    except Exception as e:
        return {"source": "youtube", "success": False, "error": str(e), "results": []}


def _search_papers(query: str, count: int = 3) -> dict:
    """OpenAlex 논문 검색 (완전 무료, API 키 불필요, 쿼터 제한 없음)"""
    try:
        import requests
    except ImportError:
        return {"source": "papers", "success": False, "error": "requests 미설치", "results": []}

    try:
        count = min(max(1, count), 10)
        response = requests.get("https://api.openalex.org/works", params={
            "search": query,
            "per-page": count,
            "sort": "relevance_score:desc",
            "select": "id,title,authorships,publication_year,cited_by_count,doi,open_access,abstract_inverted_index,primary_location",
        }, timeout=15)
        response.raise_for_status()
        data = response.json()

        works = data.get("results", [])
        if not works:
            return {"source": "papers", "success": True, "count": 0, "results": []}

        formatted = []
        for work in works:
            # 저자 (최대 3명)
            authorships = work.get("authorships", [])
            authors = [a.get("author", {}).get("display_name", "") for a in authorships[:3]]
            if len(authorships) > 3:
                authors.append("et al.")

            # 초록 복원 (inverted index → 원문)
            abstract = ""
            inv_idx = work.get("abstract_inverted_index")
            if inv_idx:
                word_positions = []
                for word, positions in inv_idx.items():
                    for pos in positions:
                        word_positions.append((pos, word))
                word_positions.sort()
                abstract = " ".join(w for _, w in word_positions)
                if len(abstract) > 200:
                    abstract = abstract[:200] + "..."

            # DOI URL
            doi = work.get("doi", "")

            # 오픈액세스 PDF
            oa_url = ""
            oa_info = work.get("open_access", {})
            if oa_info:
                oa_url = oa_info.get("oa_url", "") or ""

            # 저널
            primary_loc = work.get("primary_location", {}) or {}
            source = primary_loc.get("source", {}) or {}
            journal = source.get("display_name", "")

            formatted.append({
                "title": work.get("title", ""),
                "authors": ", ".join(authors),
                "year": work.get("publication_year"),
                "citations": work.get("cited_by_count", 0),
                "journal": journal,
                "doi": doi,
                "pdf_url": oa_url,
                "abstract": abstract,
            })
        return {"source": "papers", "success": True, "count": len(formatted), "results": formatted}
    except Exception as e:
        return {"source": "papers", "success": False, "error": str(e), "results": []}


# 소스별 검색 함수 매핑
_SEARCH_FUNCS = {
    "web": _search_ddg,
    "news": _search_news,
    "youtube": _search_youtube,
    "papers": _search_papers,
}

# 소스별 기본 결과 수
_DEFAULT_COUNTS = {
    "web": 5,
    "news": 5,
    "youtube": 3,
    "papers": 3,
}

ALL_SOURCES = list(_SEARCH_FUNCS.keys())


def unified_search(query: str, sources: list = None, web_count: int = None,
                   news_count: int = None, youtube_count: int = None,
                   papers_count: int = None, language: str = "ko") -> str:
    """종합 검색 - DuckDuckGo + Google News + YouTube + OpenAlex 논문을 병렬로 검색

    Args:
        query: 검색 키워드
        sources: 검색할 소스 목록 (기본: ["web", "news", "youtube", "papers"] 전부)
        web_count: 웹 검색 결과 수 (기본 5)
        news_count: 뉴스 결과 수 (기본 5)
        youtube_count: 유튜브 결과 수 (기본 3)
        papers_count: 논문 결과 수 (기본 3)
        language: 뉴스 검색 언어 (기본 "ko")

    Returns:
        JSON 문자열 - 소스별 결과 통합
    """
    if not query:
        return format_json({"success": False, "error": "query가 필요합니다"})

    if sources is None:
        sources = ALL_SOURCES
    # 문자열이면 리스트로
    if isinstance(sources, str):
        sources = [s.strip() for s in sources.split(",")]
    # 유효한 소스만 필터
    sources = [s for s in sources if s in _SEARCH_FUNCS]
    if not sources:
        return format_json({"success": False, "error": f"유효한 소스가 없습니다. 사용 가능: {ALL_SOURCES}"})

    # 소스별 count 설정
    counts = {
        "web": web_count or _DEFAULT_COUNTS["web"],
        "news": news_count or _DEFAULT_COUNTS["news"],
        "youtube": youtube_count or _DEFAULT_COUNTS["youtube"],
        "papers": papers_count or _DEFAULT_COUNTS["papers"],
    }

    # 병렬 실행
    search_results = {}
    with ThreadPoolExecutor(max_workers=len(sources)) as executor:
        futures = {}
        for src in sources:
            func = _SEARCH_FUNCS[src]
            if src == "web":
                futures[executor.submit(func, query, counts["web"])] = src
            elif src == "news":
                futures[executor.submit(func, query, counts["news"], language)] = src
            elif src == "youtube":
                futures[executor.submit(func, query, counts["youtube"])] = src
            elif src == "papers":
                futures[executor.submit(func, query, counts["papers"])] = src

        for future in as_completed(futures):
            src = futures[future]
            try:
                search_results[src] = future.result()
            except Exception as e:
                search_results[src] = {"source": src, "success": False, "error": str(e), "results": []}

    # 총 결과 수
    total = sum(r.get("count", 0) for r in search_results.values() if r.get("success"))

    return format_json({
        "success": True,
        "query": query,
        "sources": sources,
        "total_results": total,
        "web": search_results.get("web"),
        "news": search_results.get("news"),
        "youtube": search_results.get("youtube"),
        "papers": search_results.get("papers"),
        "_note": "검색 결과는 제목과 요약(snippet)만 포함합니다. 상세 내용이 필요하면: 웹/뉴스 → [sense:crawl]{url: \"...\"}, 유튜브 → [sense:video_transcript]{url: \"...\"}, 논문 → DOI/PDF URL로 [sense:crawl] 사용."
    })


def use_tool(tool_input: dict) -> str:
    """도구 실행 인터페이스"""
    return unified_search(
        query=tool_input.get("query", ""),
        sources=tool_input.get("sources"),
        web_count=tool_input.get("web_count"),
        news_count=tool_input.get("news_count"),
        youtube_count=tool_input.get("youtube_count"),
        papers_count=tool_input.get("papers_count"),
        language=tool_input.get("language", "ko"),
    )
