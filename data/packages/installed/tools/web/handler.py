"""
web 패키지 핸들러
웹 검색, 크롤링, 브라우저 자동화, 뉴스 검색, 신문 생성, 즐겨찾기 사이트 관리 통합
"""

import os
import json
import re
import sys
import difflib
import webbrowser
import importlib.util
from datetime import datetime
from urllib.parse import quote_plus
from pathlib import Path

# common 유틸리티 사용
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.html_utils import clean_html
from common.response_formatter import format_json

try:
    import feedparser
except ImportError:
    feedparser = None

current_dir = Path(__file__).parent

# 출력 디렉토리
OUTPUTS_DIR = 'outputs'


def load_module(module_name):
    """같은 디렉토리의 모듈을 동적으로 로드"""
    module_path = current_dir / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ============== 뉴스 검색 관련 함수 ==============
# clean_html은 common.html_utils에서 임포트


def _text_to_blocks(title, text):
    """비정형 텍스트 → 문서 IR blocks(heading + 문단들). 0-LLM. crawl·pdf 등 공용 패턴.
    빈 줄(\\n\\n)로 문단 분리, 너무 긴 문단은 그대로 둠(렌더가 처리)."""
    blocks = []
    if title:
        blocks.append({"type": "heading", "level": 1, "text": str(title)})
    for para in str(text or "").split("\n\n"):
        para = para.strip()
        if para:
            blocks.append({"type": "paragraph", "text": para})
    return blocks or [{"type": "paragraph", "text": str(text or "")}]


def search_gnews(query: str, count: int = 10, language: str = "ko", region: str = None) -> dict:
    """Google News RSS 검색

    Args:
        language: "ko" (한국어) 또는 "en" (영어) 등
        region: 국가 코드. None이면 language에서 자동 결정 (ko→KR, en→US)
    """
    if feedparser is None:
        return {
            "success": False,
            "error": "feedparser 모듈이 설치되지 않았습니다. pip install feedparser",
            "query": query,
            "results": []
        }

    try:
        count = min(max(1, count), 30)
        encoded_query = quote_plus(query)
        # region 자동 결정
        if region is None:
            region = {"ko": "KR", "en": "US", "ja": "JP", "zh": "CN"}.get(language, "US")
        rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl={language}&gl={region}&ceid={region}:{language}"

        feed = feedparser.parse(rss_url)

        if not feed.entries:
            return {
                "success": False,
                "error": "뉴스를 찾을 수 없습니다",
                "query": query,
                "results": []
            }

        results = []
        for entry in feed.entries[:count]:
            results.append({
                "title": entry.get('title', '제목 없음'),
                "url": entry.get('link', ''),
                "published": entry.get('published', ''),
                "source": entry.get('source', {}).get('title', '출처 없음'),
                "summary": clean_html(entry.get('summary', ''))
            })

        return {
            "success": True,
            "query": query,
            "count": len(results),
            "language": language,
            "results": results,
            # 단일 통화 items(records-관습 카드 shape) — 뉴스 목록 >> 파이프/렌더러.
            "items": [{
                "title": r.get("title", ""),
                "meta": " · ".join(x for x in [r.get("source", ""), r.get("published", "")] if x),
                "summary": r.get("summary", ""),
                "url": r.get("url", ""),
            } for r in results],
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "query": query,
            "results": []
        }


# ============== 사이트 런처 관련 함수 ==============

# 공개 기본 즐겨찾기 — sites.json(개인, .gitignore) 부재 시 첫 화면 시드. 개인정보 없음.
_DEFAULT_SITES = [
    {"name": "Hacker News", "url": "https://news.ycombinator.com/"},
    {"name": "Stratechery", "url": "https://stratechery.com/"},
    {"name": "Aeon", "url": "https://aeon.co/"},
    {"name": "Reddit r/LocalLLaMA", "url": "https://www.reddit.com/r/LocalLLaMA/"},
    {"name": "Lex Fridman (YouTube)", "url": "https://www.youtube.com/@lexfridman"},
    {"name": "GeekNews", "url": "https://news.hada.io/"},
    {"name": "GitHub", "url": "https://github.com/"},
    {"name": "Gemini", "url": "https://gemini.google.com/app"},
]


def launch_sites(action: str = "open_ui", name: str = None, url: str = None, project_path: str = ".") -> str:
    """자주 가는 사이트 런처 및 관리"""
    sites_path = current_dir / "sites.json"

    # sites.json = 런타임 사용자 상태(개인 북마크, .gitignore — 개인 목록은 추적 밖).
    # 파일이 없으면 공개 기본값(_DEFAULT_SITES)으로 시작하고, 쓰기(add/remove)는 항상
    # sites.json 으로 영속한다 → 개인 즐겨찾기가 저장소로 새지 않는다.
    try:
        if sites_path.exists():
            with open(sites_path, "r", encoding="utf-8") as f:
                sites = json.load(f)
        else:
            sites = [dict(s) for s in _DEFAULT_SITES]
    except Exception as e:
        return f"사이트 목록을 읽는 중 오류 발생: {str(e)}"

    if action == "list":
        # 구조화 반환 — 앱 계기(즐겨찾기)가 items[] 를 직접 렌더. message 는 에이전트/사람용.
        # 단일 통화: native 사이트 dict(name/url)를 그대로 items로.
        if not sites:
            return {"success": True, "items": [], "count": 0, "message": "등록된 사이트가 없습니다."}
        list_str = "\n".join([f"- {s['name']}: {s['url']}" for s in sites])
        return {"success": True, "items": sites, "count": len(sites),
                "message": f"현재 등록된 사이트 목록입니다:\n{list_str}"}

    elif action == "add":
        if not name or not url:
            return "사이트 이름(name)과 URL(url)이 필요합니다."
        sites.append({"name": name, "url": url})
        try:
            with open(sites_path, "w", encoding="utf-8") as f:
                json.dump(sites, f, ensure_ascii=False, indent=2)
            return f"사이트가 추가되었습니다: {name} ({url})"
        except Exception as e:
            return f"저장 중 오류 발생: {str(e)}"

    elif action == "remove":
        if not name:
            return "삭제할 사이트 이름(name)이 필요합니다."
        new_sites = [s for s in sites if s["name"] != name]
        if len(new_sites) == len(sites):
            return f"'{name}' 이름의 사이트를 찾을 수 없습니다."
        try:
            with open(sites_path, "w", encoding="utf-8") as f:
                json.dump(new_sites, f, ensure_ascii=False, indent=2)
            return f"사이트가 삭제되었습니다: {name}"
        except Exception as e:
            return f"저장 중 오류 발생: {str(e)}"

    elif action == "open_ui":
        if not sites:
            return "등록된 사이트가 없습니다. 먼저 사이트를 추가해 주세요."

        buttons_html = ""
        for site in sites:
            buttons_html += f"""
            <a href="{site['url']}" class="site-card" target="_blank">
                <div class="site-name">{site['name']}</div>
                <div class="site-url">{site['url']}</div>
            </a>"""

        html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>IndieBiz Launchpad</title>
    <style>
        body {{
            font-family: -apple-system, sans-serif;
            background-color: #f8f9fa;
            padding: 40px 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }}
        h1 {{ color: #3d5a80; margin-bottom: 30px; }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 20px;
            width: 100%;
            max-width: 1000px;
        }}
        .site-card {{
            background: white;
            border-radius: 12px;
            padding: 20px;
            text-decoration: none;
            color: inherit;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
            transition: all 0.2s ease;
            border: 1px solid rgba(0,0,0,0.05);
        }}
        .site-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 8px 15px rgba(0,0,0,0.1);
            border-color: #3d5a80;
        }}
        .site-name {{ font-size: 1.25rem; font-weight: 600; color: #3d5a80; margin-bottom: 8px; }}
        .site-url {{ font-size: 0.85rem; color: #6c757d; }}
    </style>
</head>
<body>
    <h1>IndieBiz Launchpad</h1>
    <div class="grid">{buttons_html}</div>
</body>
</html>"""

        out_dir = os.path.join(project_path, OUTPUTS_DIR)
        os.makedirs(out_dir, exist_ok=True)
        ui_path = os.path.join(out_dir, "launchpad.html")

        with open(ui_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        webbrowser.open(f"file://{os.path.abspath(ui_path)}")
        return f"런치패드 UI를 생성하고 브라우저에서 열었습니다: {os.path.abspath(ui_path)}"

    return "알 수 없는 작업입니다."


# ============== 메인 핸들러 ==============

def execute(tool_input: dict, context):
    """IndieBiz OS에서 도구를 호출할 때 실행되는 메인 핸들러 (ToolContext 기반 신규 시그니처)."""
    tool_name = context.tool_name
    project_path = context.project_path

    # DuckDuckGo 웹 검색
    if tool_name == "ddgs_search":
        tool_ddgs = load_module("tool_ddgs_search")
        query = tool_input.get("query")
        count = tool_input.get("count", 5)
        country = tool_input.get("country", "kr-kr")
        return tool_ddgs.search_web(query, count, country)

    # 웹페이지 크롤링
    elif tool_name == "crawl_website":
        url = tool_input.get("url")
        max_length = tool_input.get("max_length", 10000)

        if not url:
            return format_json({"success": False, "error": "URL이 제공되지 않았습니다."})

        try:
            tool_webcrawl = load_module("tool_webcrawl")
            result = tool_webcrawl.crawl_website(url, max_length)
            # 단일 통화 items = 문서 IR(type+text 항목) — 크롤한 페이지 텍스트를 문단 블록으로. crawl(url) >> document{pdf}.
            if isinstance(result, dict) and result.get("success") and result.get("text"):
                result["items"] = _text_to_blocks(result.get("title"), result.get("text"))
            return format_json(result)
        except Exception as e:
            return format_json({"success": False, "error": str(e)})

    # Google News 검색
    elif tool_name == "search_gnews":
        query = tool_input.get("query", "")
        if not query:
            return format_json({"success": False, "error": "검색어(query)가 필요합니다."})

        # 언어 자동 감지: 명시적 지정이 없으면 쿼리에서 판단
        language = tool_input.get("language", "auto")
        if language == "auto":
            korean_chars = sum(1 for c in query if '\uac00' <= c <= '\ud7a3' or '\u3131' <= c <= '\u318e')
            language = "ko" if korean_chars > len(query) * 0.2 else "en"

        result = search_gnews(
            query=query,
            count=tool_input.get("count", 10),
            language=language
        )
        if isinstance(result, dict) and isinstance(result.get("results"), list):
            result["items"] = [{  # 단일 통화 items(records-관습 카드 shape)
                "title": r.get("title", ""),
                "meta": " · ".join(x for x in [r.get("source"), r.get("published")] if x),
                "summary": "" if (r.get("summary") or "") == r.get("title") else (r.get("summary") or ""),
                "url": r.get("url", ""), "link_label": "기사 보기",
            } for r in result["results"]]
        return format_json(result)

    # 사이트 런처
    elif tool_name == "launch_sites":
        action = tool_input.get("action", "open_ui")
        name = tool_input.get("name")
        url = tool_input.get("url")
        return launch_sites(action, name, url, project_path)

    else:
        return format_json({
            "success": False,
            "error": f"Unknown tool: {tool_name}"
        })
