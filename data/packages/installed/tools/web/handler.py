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


def search_gnews(query: str = "", count: int = 10, language: str = "ko", region: str = None, headlines: bool = False) -> dict:
    """Google News RSS 검색

    Args:
        language: "ko" (한국어) 또는 "en" (영어) 등
        region: 국가 코드. None이면 language에서 자동 결정 (ko→KR, en→US)
        headlines: True면 키워드 없이 구글뉴스 톱 헤드라인 피드 — '오늘의 핫토픽' 소스.
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
        # region 자동 결정
        if region is None:
            region = {"ko": "KR", "en": "US", "ja": "JP", "zh": "CN"}.get(language, "US")
        if headlines:
            # 키워드 없는 톱 헤드라인 — 오늘 세상이 크게 다룬 사건. 뒤에 curate로 군집·랭킹.
            rss_url = f"https://news.google.com/rss?hl={language}&gl={region}&ceid={region}:{language}"
        else:
            encoded_query = quote_plus(query)
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
            # query 필드 = 어느 검색어가 낸 항목인지 태그 → group 뷰(by:"{query}")·table:groupby 로 섹션화 가능.
            "items": [{
                "title": r.get("title", ""),
                "meta": " · ".join(x for x in [r.get("source", ""), r.get("published", "")] if x),
                "summary": r.get("summary", ""),
                "url": r.get("url", ""),
                "query": query,
            } for r in results],
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "query": query,
            "results": []
        }


# ============== 신문 섹션 편집 (경량 AI dedup/선별) ==============

def _norm_title(t: str) -> str:
    """제목 정규화 — 매체 접미사·기호·공백 제거해 근접 중복 비교용."""
    t = (t or "").strip()
    t = re.split(r"\s[-|·]\s", t)[0]           # "제목 - 매체명" 꼬리 제거
    return re.sub(r"[^0-9A-Za-z가-힣]+", "", t).lower()


def _heuristic_dedup(items: list, threshold: float = 0.86) -> list:
    """제목 근접 유사도로 노골적 중복 제거(0토큰). 첫 등장만 남김.
    AI 편집 전 pool 축소 + AI 실패 시 폴백 겸용."""
    kept, seen = [], []
    for it in items:
        n = _norm_title(it.get("title", ""))
        if not n:
            kept.append(it)
            continue
        if any(n == s or difflib.SequenceMatcher(None, n, s).ratio() >= threshold for s in seen):
            continue
        seen.append(n)
        kept.append(it)
    return kept


def _curate_section(topic: str, items: list, keep: int) -> list:
    """한 주제 섹션의 기사 pool → 경량 AI가 같은 사건 중복을 하나로 묶어 대표만
    남기고 뉴스가치 순 상위 keep개를 고른다. AI는 '고르기'만(번호 선택) — 제목/URL
    재작성 없음(환각·조작 차단). 실패 시 휴리스틱 dedup 폴백. 절대 빈 목록 반환 안 함."""
    if keep < 1:
        keep = 1
    pool = _heuristic_dedup(items)             # 1차: 값싼 근접중복 제거로 pool 축소
    if len(pool) <= keep:
        return pool[:keep]                     # 이미 충분히 적으면 AI 불필요

    try:                                        # 2차: 경량 AI 의미 dedup + 뉴스가치 정렬
        from consciousness_agent import lightweight_ai_call
        lines = []
        for i, it in enumerate(pool, 1):
            src = (it.get("meta") or "").split(" · ")[0].strip()
            summ = (it.get("summary") or "").strip().replace("\n", " ")[:100]
            line = f"{i}. {it.get('title', '')}"
            if src:
                line += f" [{src}]"
            if summ:
                line += f" — {summ}"
            lines.append(line)
        sys_prompt = (
            "너는 개인 신문의 섹션 편집자다. 한 주제에 대한 기사 목록을 받는다.\n"
            "같은 사건을 다룬 중복 기사는 하나로 묶고, 각 사건에서 가장 정보가 풍부한 기사 하나만 남겨라.\n"
            "그 뒤 주제에 대한 뉴스 가치가 높은 순으로 정렬하라.\n"
            "기사를 새로 쓰거나 제목을 바꾸지 말고, 주어진 번호 중에서만 골라라.\n"
            "출력은 남길 기사 번호의 JSON 배열 하나만. 예: [3, 1, 8]. 다른 말 금지."
        )
        prompt = f"주제: {topic}\n목표 기사 수: {keep}\n\n기사 목록:\n" + "\n".join(lines)
        resp = lightweight_ai_call(prompt, system_prompt=sys_prompt, role="classify")
        if resp:
            m = re.search(r"\[[\d,\s]*\]", resp)
            if m:
                picked, used = [], set()
                for n in json.loads(m.group(0)):
                    if isinstance(n, int) and 1 <= n <= len(pool) and n not in used:
                        used.add(n)
                        picked.append(pool[n - 1])
                    if len(picked) >= keep:
                        break
                if picked:
                    return picked
    except Exception as e:
        print(f"[_curate_section] 경량 AI 편집 실패, 휴리스틱 폴백: {e}", file=sys.stderr)

    return pool[:keep]                          # 폴백: 근접중복 제거된 pool 앞에서 keep개


def _parse_curate(tool_input: dict):
    """curate 파라미터 → 양의 정수 또는 None."""
    v = tool_input.get("curate")
    if v in (None, "", False):
        return None
    try:
        v = int(v)
        return v if v >= 1 else None
    except (TypeError, ValueError):
        return None


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
        # 배치 팬아웃(queries: 리스트/콤마·개행) — 각 검색어를 돌려 query 태그된 항목을 한 목록으로.
        # group 뷰(신문 섹션)·table:groupby 에 바로 먹인다. N-way 팬아웃을 액션 하나로(신문 계기용).
        _queries = tool_input.get("queries")
        if _queries:
            if isinstance(_queries, str):
                _queries = re.split(r"[,\n]", _queries)
            _queries = [str(q).strip() for q in _queries if str(q).strip()]
            if not _queries:
                return format_json({"success": False, "error": "검색어(queries)가 비었습니다."})
            _count = tool_input.get("count", 10)
            _lang = tool_input.get("language", "auto")
            _curate = _parse_curate(tool_input)
            # curate 시 오버페치(약 3배)해 섹션별 dedup 후 빈 자리 자동 채움
            _fetch = min(30, max(_curate * 3, _count)) if _curate else _count

            def _dl(q):
                if _lang != "auto":
                    return _lang
                kc = sum(1 for c in q if '가' <= c <= '힣' or 'ㄱ' <= c <= 'ㆎ')
                return "ko" if kc > len(q) * 0.2 else "en"

            all_items, sections = [], []
            # 오늘의 핫토픽 — headlines:true 면 키워드 없는 톱헤드라인을 맨 앞 섹션으로(원격/폰 신문 파리티)
            if tool_input.get("headlines") in (True, "true", "True", 1, "1"):
                _hl = search_gnews(count=_fetch, language=(_lang if _lang != "auto" else "ko"), headlines=True)
                _hi = [{
                    "title": r.get("title", ""),
                    "meta": " · ".join(x for x in [r.get("source"), r.get("published")] if x),
                    "summary": "" if (r.get("summary") or "") == r.get("title") else (r.get("summary") or ""),
                    "url": r.get("url", ""), "link_label": "기사 보기", "query": "오늘의 핫토픽",
                } for r in (_hl.get("results") or [])]
                if _curate:
                    _hi = _curate_section("오늘의 핫토픽", _hi, _curate)
                all_items.extend(_hi)
                sections.append({"query": "오늘의 핫토픽", "count": len(_hi)})
            for q in _queries:
                res = search_gnews(query=q, count=_fetch, language=_dl(q))
                items = [{
                    "title": r.get("title", ""),
                    "meta": " · ".join(x for x in [r.get("source"), r.get("published")] if x),
                    "summary": "" if (r.get("summary") or "") == r.get("title") else (r.get("summary") or ""),
                    "url": r.get("url", ""), "link_label": "기사 보기", "query": q,
                } for r in (res.get("results") or [])]
                if _curate:
                    items = _curate_section(q, items, _curate)
                all_items.extend(items)
                sections.append({"query": q, "count": len(items)})
            return format_json({"success": True, "queries": _queries, "count": len(all_items),
                                "sections": sections, "items": all_items})

        # 오늘의 핫토픽 — 키워드 없는 톱 헤드라인을 curate가 군집·랭킹(중복 많이 다뤄진=핫)
        if tool_input.get("headlines") in (True, "true", "True", 1, "1"):
            language = tool_input.get("language", "ko")
            if language == "auto":
                language = "ko"
            _curate = _parse_curate(tool_input)
            _fetch = min(30, max(_curate * 3, tool_input.get("count", 12))) if _curate else tool_input.get("count", 12)
            result = search_gnews(count=_fetch, language=language, headlines=True)
            if isinstance(result, dict) and isinstance(result.get("results"), list):
                result["items"] = [{
                    "title": r.get("title", ""),
                    "meta": " · ".join(x for x in [r.get("source"), r.get("published")] if x),
                    "summary": "" if (r.get("summary") or "") == r.get("title") else (r.get("summary") or ""),
                    "url": r.get("url", ""), "link_label": "기사 보기",
                    "query": "오늘의 핫토픽",
                } for r in result["results"]]
                if _curate:
                    result["items"] = _curate_section("오늘의 핫토픽", result["items"], _curate)
                    result["count"] = len(result["items"])
            return format_json(result)

        query = tool_input.get("query", "")
        if not query:
            return format_json({"success": False, "error": "검색어(query 또는 queries)가 필요합니다."})

        # 언어 자동 감지: 명시적 지정이 없으면 쿼리에서 판단
        language = tool_input.get("language", "auto")
        if language == "auto":
            korean_chars = sum(1 for c in query if '\uac00' <= c <= '\ud7a3' or '\u3131' <= c <= '\u318e')
            language = "ko" if korean_chars > len(query) * 0.2 else "en"

        _curate = _parse_curate(tool_input)
        _fetch = min(30, max(_curate * 3, tool_input.get("count", 10))) if _curate else tool_input.get("count", 10)
        result = search_gnews(
            query=query,
            count=_fetch,
            language=language
        )
        if isinstance(result, dict) and isinstance(result.get("results"), list):
            result["items"] = [{  # 단일 통화 items(records-관습 카드 shape)
                "title": r.get("title", ""),
                "meta": " · ".join(x for x in [r.get("source"), r.get("published")] if x),
                "summary": "" if (r.get("summary") or "") == r.get("title") else (r.get("summary") or ""),
                "url": r.get("url", ""), "link_label": "기사 보기",
                "query": query,  # 검색어 태그 → group 뷰/table:groupby 섹션화용
            } for r in result["results"]]
            if _curate:
                result["items"] = _curate_section(query, result["items"], _curate)
                result["count"] = len(result["items"])
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
