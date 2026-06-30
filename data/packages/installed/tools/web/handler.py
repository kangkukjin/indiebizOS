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


def search_google_news(query: str, count: int = 10, language: str = "ko", region: str = None) -> dict:
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


def _norm_title(t: str) -> str:
    """제목 정규화 — 끝의 ' - 출처' 떼고 소문자·기호 제거(중복 판정용)."""
    t = re.split(r'\s+[-–|]\s+[^-–|]+$', t or "")[0]  # 끝의 " - 출처명" 제거
    return re.sub(r'[^\w가-힣]', '', t.lower())


def _clean_summary(title: str, summary: str) -> str:
    """요약이 제목의 반복(구글뉴스 흔한 'title - source' 잡음)이면 버림 — 정보성 없는 카드 방지."""
    if not summary:
        return ""
    ns, nt = _norm_title(summary), _norm_title(title)
    if not nt:
        return summary.strip()
    # 요약이 제목을 거의 그대로 담고 있으면(앞부분 포함/높은 유사) 중복으로 간주
    if nt in ns or ns in nt or difflib.SequenceMatcher(None, ns, nt).ratio() > 0.75:
        return ""
    return summary.strip()


def _pub_ts(item: dict) -> float:
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(item.get('published', '')).timestamp()
    except Exception:
        return 0.0


def _dedup_rank(items: list, limit: int) -> list:
    """근접 중복 기사 묶고 중요도순 정렬 — 0토큰 결정적 품질 향상.
    중요도 신호 = coverage(같은 사건을 보도한 매체 수) → 많을수록 위. 대표는 그룹 내 최신 기사.
    반환 각 항목에 coverage(int) 부착."""
    groups = []  # {norm, members:[...]}
    for it in items:
        nt = _norm_title(it.get('title', ''))
        if not nt:
            continue
        placed = False
        for g in groups:
            gn = g['norm']
            if nt == gn or nt in gn or gn in nt or difflib.SequenceMatcher(None, nt, gn).ratio() > 0.82:
                g['members'].append(it)
                placed = True
                break
        if not placed:
            groups.append({'norm': nt, 'members': [it]})

    ranked = []
    for g in groups:
        rep = max(g['members'], key=_pub_ts)  # 그룹 대표 = 최신
        rep = dict(rep)
        rep['coverage'] = len(g['members'])
        ranked.append((rep, len(g['members']), _pub_ts(rep)))
    # 중요도(coverage) 우선, 동률이면 최신
    ranked.sort(key=lambda x: (x[1], x[2]), reverse=True)
    return [r[0] for r in ranked[:limit]]


def generate_section(keyword: str, news_count: int = 7, exclude_sources: list = None,
                     language: str = "ko", region: str = None) -> dict:
    """키워드로 뉴스 검색 → 중복 제거 + 중요도순 정렬 + 요약 정리(전부 결정적, 0토큰)."""
    if exclude_sources is None:
        exclude_sources = []

    # 중복 제거 후 news_count개 확보를 위해 넉넉히 수집(over-fetch).
    fetch_count = min(30, max(news_count * 4, 12))
    result = search_google_news(query=keyword, count=fetch_count, language=language, region=region)

    if not result['success'] or not result['results']:
        return {'keyword': keyword, 'items': [], 'news_count': 0, 'success': False}

    excluded_count = 0
    filtered = []
    for item in result['results']:
        if any(ex in item.get('source', '') for ex in exclude_sources):
            excluded_count += 1
        else:
            filtered.append(item)

    if not filtered:
        return {'keyword': keyword, 'items': [], 'news_count': 0, 'success': False}

    items = _dedup_rank(filtered, news_count)  # 중복 묶기 + 중요도순 + 상위 news_count
    for it in items:
        it['summary'] = _clean_summary(it.get('title', ''), it.get('summary', ''))  # 요약 잡음 정리
        # 제목 끝의 ' - 출처' 꼬리 제거(meta에 출처 별도 표시 — 출처와 일치할 때만 안전)
        title, src = it.get('title', ''), it.get('source', '')
        m = re.search(r'\s+[-–|]\s+([^-–|]+)$', title)
        if m and src and (m.group(1).strip() in src or src in m.group(1).strip()):
            it['title'] = title[:m.start()].strip()

    return {
        'keyword': keyword,
        'items': items,  # [{title, url, published, source, summary, coverage}] — 문서 IR 생산용
        'news_count': len(items),
        'raw_count': len(filtered),
        'excluded_count': excluded_count,
        'success': True
    }


def _search_guardian_for_newspaper(query: str, count: int = 7, language: str = "en") -> dict:
    """Guardian API로 기사를 검색하여 generate_section과 동일한 형태로 반환"""
    import requests
    import html as html_mod

    api_key = os.getenv("GUARDIAN_API_KEY")
    if not api_key:
        return {'keyword': query, 'items': [], 'news_count': 0, 'success': False}

    try:
        response = requests.get("https://content.guardianapis.com/search", params={
            "q": query, "api-key": api_key, "page-size": count,
            "show-fields": "trailText,headline,shortUrl"
        }, timeout=15)
        response.raise_for_status()
        results_list = response.json().get("response", {}).get("results", [])

        if not results_list:
            return {'keyword': query, 'items': [], 'news_count': 0, 'success': False}

        items = []
        for article in results_list:
            fields = article.get("fields", {})
            headline = fields.get("headline", article.get("webTitle", "No title"))
            trail_text = re.sub('<[^<]+?>', '', fields.get("trailText", ""))
            trail_text = html_mod.unescape(trail_text).strip()
            url = article.get("webUrl", "")
            date = article.get("webPublicationDate", "")[:10]
            section_name = article.get("sectionName", "")

            items.append({'title': headline, 'url': url, 'published': date,
                          'source': f"The Guardian ({section_name})", 'summary': trail_text})

        return {'keyword': query, 'items': items,
                'news_count': len(results_list), 'success': True}

    except Exception as e:
        return {'keyword': query, 'items': [], 'news_count': 0, 'success': False}


def generate_newspaper(keywords: list, title: str = "IndieBiz Daily",
                       exclude_sources: list = None, project_path: str = ".",
                       language: str = None, source: str = "google") -> dict:
    """뉴스 소스별 신문 자동 생성

    Args:
        keywords: 검색 키워드 목록
        title: 신문 제목
        source: 뉴스 소스 - "google" (기본), "guardian"
        language: "ko", "en" 등. None이면 소스에 따라 자동 결정
    """
    if not keywords:
        return {'success': False, 'error': '키워드가 필요합니다.'}

    if exclude_sources is None:
        exclude_sources = []

    # language 자동 결정: 지정 안 하면 소스에 따라
    if language is None:
        language = "en" if source == "guardian" else "ko"

    # region 자동 결정
    region = {"ko": "KR", "en": "US", "ja": "JP", "zh": "CN"}.get(language, "US")

    today = datetime.now()
    date_str = today.strftime('%B %d, %Y') if language != "ko" else today.strftime('%Y년 %m월 %d일')

    sections = []
    for keyword in keywords:
        if source == "guardian":
            section = _search_guardian_for_newspaper(keyword, count=7, language=language)
        else:
            section = generate_section(keyword, news_count=7, exclude_sources=exclude_sources,
                                       language=language, region=region)
        sections.append(section)

    total_news = sum(s.get('news_count', 0) for s in sections)
    src_label = "The Guardian" if source == "guardian" else "Google News RSS"

    # 키워드별 섹션을 공유 문서 IR(heading + cards 블록)로 — 결정적 매핑(LLM 미개입, 기사·링크 무손실).
    blocks = []
    # 목차(섹션 점프 — 키워드 多일 때 내비게이션). list 항목 링크 + heading 앵커.
    toc_label = "목차" if language == "ko" else "Contents"
    toc_items = [{"text": f"{s['keyword']} ({s.get('news_count', 0)}{'개' if language == 'ko' else ''})",
                  "url": f"#{s['keyword']}"}
                 for s in sections if s.get('success') and s.get('news_count', 0) > 0]
    if len(toc_items) > 1:
        blocks.append({"type": "heading", "level": 3, "text": toc_label})
        blocks.append({"type": "list", "items": toc_items})
        blocks.append({"type": "divider"})
    for section in sections:
        blocks.append({"type": "heading", "level": 2, "text": section['keyword'],
                       "anchor": section['keyword']})
        items = section.get('items') or []
        if section.get('success') and items:
            cards = []
            for it in items:
                meta_bits = [b for b in [it.get('source'), it.get('published')] if b]
                cov = it.get('coverage') or 1
                if cov > 1:  # 중요도 신호 — 여러 매체가 보도한 사건
                    meta_bits.append(f"{cov}개 매체 보도" if language == "ko" else f"{cov} sources")
                cards.append({
                    "title": it.get('title', ''),
                    "meta": " | ".join(meta_bits),
                    "summary": it.get('summary') or '',  # 이미 generate_section에서 잡음 정리됨
                    "url": it.get('url', ''),
                    "link_label": "기사 보기" if language == "ko" else "Read Article",
                })
            blocks.append({"type": "cards", "columns": 2, "items": cards})
        else:
            blocks.append({"type": "paragraph",
                           "text": "뉴스를 찾을 수 없습니다." if language == "ko" else "No news found."})

    meta_line = (f"발행일: {date_str} | 발행처: IndieBiz AI | 출처: {src_label} | 총 {total_news}개"
                 if language == "ko"
                 else f"Date: {date_str} | Publisher: IndieBiz AI | Source: {src_label} | {total_news} articles")

    # 문서 IR 반환 — `>> [engines:document]{theme:newspaper}`로 html/pdf/docx 등 렌더.
    return {
        'success': True,
        'message': f'신문 IR 생성 완료 ({len(sections)}섹션 · {total_news}개 기사). >> document로 렌더.',
        'title': title,
        'meta': meta_line,
        'theme': 'newspaper',
        'blocks': blocks,
        'block_count': len(blocks),
        'sections': len(sections),
        'total_news': total_news
    }


# ============== 사이트 런처 관련 함수 ==============

def launch_sites(action: str = "open_ui", name: str = None, url: str = None, project_path: str = ".") -> str:
    """자주 가는 사이트 런처 및 관리"""
    sites_path = current_dir / "sites.json"

    # sites.json = 런타임 사용자 상태(개인 북마크, .gitignore). 없으면 sites.example.json 시드를
    # 읽는다(첫 설치 기본값). 쓰기(add/remove)는 항상 sites.json 으로 → 개인 목록은 추적 밖.
    try:
        read_path = sites_path if sites_path.exists() else (current_dir / "sites.example.json")
        if read_path.exists():
            with open(read_path, "r", encoding="utf-8") as f:
                sites = json.load(f)
        else:
            sites = []
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
    elif tool_name == "google_news_search":
        query = tool_input.get("query", "")
        if not query:
            return format_json({"success": False, "error": "검색어(query)가 필요합니다."})

        # 언어 자동 감지: 명시적 지정이 없으면 쿼리에서 판단
        language = tool_input.get("language", "auto")
        if language == "auto":
            korean_chars = sum(1 for c in query if '\uac00' <= c <= '\ud7a3' or '\u3131' <= c <= '\u318e')
            language = "ko" if korean_chars > len(query) * 0.2 else "en"

        result = search_google_news(
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

    # 네이버 검색 (웹/뉴스/블로그/카페/지식인/책/백과/전문자료/쇼핑 통합)
    elif tool_name == "naver_search":
        tool_naver = load_module("tool_naver_search")
        result = tool_naver.search_naver(
            query=tool_input.get("query", ""),
            type=tool_input.get("type", "webkr"),
            display=tool_input.get("display", 5),
            sort=tool_input.get("sort", "sim"),
        )
        return format_json(result)

    # 종합 검색
    elif tool_name == "unified_search":
        tool_unified = load_module("tool_unified_search")
        return tool_unified.use_tool(tool_input)

    # 신문 생성
    elif tool_name == "generate_newspaper":
        keywords = tool_input.get("keywords", [])
        # 문자열이면 쉼표 구분 리스트로 변환 (IBL target → keywords 매핑 시 문자열로 전달됨)
        if isinstance(keywords, str):
            keywords = [k.strip() for k in keywords.split(",") if k.strip()]
        if not keywords:
            return format_json({"success": False, "error": "키워드(keywords)가 필요합니다."})

        language = tool_input.get("language", None)
        source = tool_input.get("source", "google")
        result = generate_newspaper(
            keywords=keywords,
            title=tool_input.get("title", "IndieBiz Daily"),
            exclude_sources=tool_input.get("exclude_sources", []),
            project_path=project_path,
            language=language,
            source=source
        )
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
