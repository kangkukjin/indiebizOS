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
        count = min(max(1, count), 100)  # 검색 RSS는 GET 1회에 ~105개 — 100까지 공짜(같은 요청)
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
    """제목 근접 유사도로 노골적 중복 제거(0토큰). 첫 등장만 남기되, 흡수한 중복 수를
    `sources` 필드에 기록 — 군집 크기('얼마나 널리 다뤄졌나')는 편집장의 hot 신호,
    군집 1('단독 보도')은 surface 후보 신호."""
    kept, seen = [], []                        # seen: (정규화 제목, kept 인덱스)
    for it in items:
        n = _norm_title(it.get("title", ""))
        if not n:
            kept.append(dict(it))
            continue
        hit = None
        for s, ki in seen:
            if n == s or difflib.SequenceMatcher(None, n, s).ratio() >= threshold:
                hit = ki
                break
        if hit is not None:
            kept[hit]["sources"] = kept[hit].get("sources", 1) + 1
            continue
        seen.append((n, len(kept)))
        kept.append(dict(it))
    return kept


_STUDY_HANDLER = None


def _guardian_items(query: str, count: int = 30) -> list:
    """가디언 기사 → 신문 items 통화. **정본 구현=study 패키지 [sense:search_guardian]**
    (능력1·구현1 — web은 importlib로 빌려 쓴다, 고유 모듈명으로 충돌 회피).
    study 미설치·GUARDIAN_API_KEY 부재·무결과 시 [] 반환 — 신문은 gnews만으로 진행."""
    global _STUDY_HANDLER
    try:
        if _STUDY_HANDLER is None:
            import importlib.util
            p = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "study", "handler.py"))
            spec = importlib.util.spec_from_file_location("_study_handler_for_web", p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _STUDY_HANDLER = mod
        res = _STUDY_HANDLER._search_guardian({"query": query, "page_size": min(count, 50)})
        if isinstance(res, dict) and res.get("items"):
            return [{
                "title": r.get("title", ""),
                "meta": " · ".join(x for x in ["The Guardian", r.get("meta", "")] if x),
                "summary": r.get("summary", ""),
                "url": r.get("url", ""), "link_label": "기사 보기",
            } for r in res["items"]]
    except Exception as e:
        print(f"[_guardian_items] 가디언 검색 생략: {e}", file=sys.stderr)
    return []


def _hn_items(query: str = "", count: int = 30, front_page: bool = False) -> list:
    """Hacker News(Algolia API) → 신문 items 통화. 키 불요. points=주목도(편집장 hot 신호).
    front_page=현재 프론트페이지(핫토픽 analog), 아니면 story 키워드 검색. 실패 시 [] (신문 무손상).
    url=외부 기사 우선(없으면 HN 토론), hn_url=HN 토론(댓글)은 항상 보존."""
    import urllib.request as _u, urllib.parse as _p
    try:
        n = min(max(count, 1), 50)
        if front_page:
            url = f"http://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage={n}"
        else:
            url = (f"http://hn.algolia.com/api/v1/search?query={_p.quote(query or '')}"
                   f"&tags=story&hitsPerPage={n}&numericFilters=points>5")
        with _u.urlopen(url, timeout=12) as r:
            hits = json.loads(r.read()).get("hits", [])
    except Exception as e:
        print(f"[_hn_items] HN 검색 생략: {e}", file=sys.stderr)
        return []
    items = []
    for h in hits:
        oid = h.get("objectID", "")
        ext = h.get("url") or ""
        disc = f"https://news.ycombinator.com/item?id={oid}"
        pts, nc = h.get("points") or 0, h.get("num_comments") or 0
        dom = ""
        if ext:
            try:
                dom = _p.urlparse(ext).netloc.replace("www.", "")
            except Exception:
                dom = ""
        items.append({
            "title": h.get("title") or h.get("story_title") or "(제목 없음)",
            "meta": " · ".join(x for x in [f"▲{pts}", f"💬{nc}", dom or "news.ycombinator.com"] if x),
            "summary": "",
            "url": ext or disc,      # 외부 기사 우선, 없으면 HN 토론
            "hn_url": disc,          # HN 토론(댓글) 항상 보존
            "link_label": "기사 보기",
            "points": pts,           # 편집장 hot 신호(gnews 의 ×N매체 대응)
        })
    return items


_PERSPECTIVE_CACHE: dict = {}


def _load_perspective_core() -> str:
    """관점 코어(블로그 12년치의 증류, vault/위키/관점 코어.md) — 편집장의 개인 기준선.
    mtime 캐시. 없으면 빈 문자열 → 뉴스가치-only 폴백(신문은 항상 나옴).
    경로는 PERSPECTIVE_CORE_PATH 환경변수로 재지정 가능(이식성)."""
    global _PERSPECTIVE_CACHE
    path = os.environ.get("PERSPECTIVE_CORE_PATH") or os.path.expanduser(
        "~/Documents/iRepublic-Vault/위키/관점 코어.md")
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return ""
    if _PERSPECTIVE_CACHE.get("path") == path and _PERSPECTIVE_CACHE.get("mtime") == mtime:
        return _PERSPECTIVE_CACHE.get("text", "")
    try:
        text = Path(path).read_text(encoding="utf-8")
        text = re.sub(r"^---[\s\S]*?---\s*", "", text, count=1)   # frontmatter 제거
        _PERSPECTIVE_CACHE = {"path": path, "mtime": mtime, "text": text}
        return text
    except OSError:
        return ""


def _curate_sections_batch(secs: list, keep: int) -> list:
    """여러 섹션을 경량 AI '편집장' **1회 호출**로 선별. secs=[{topic, items}] →
    같은 순서의 [{"picks": 선별(role/why 부착), "rest": 나머지 풀(편집신문 대체 후보)}].

    편성(2026-07-11 관점 큐레이션): keep개를 세 슬롯으로 —
      hot     여러 매체가 다룬 사건(dedup 군집 ×N) = 세상과의 접점 유지
      delta   관점 코어(블로그 증류) 기준 *새 정보* — 입장 위반·확장/열린 질문/구체 단독.
              '이미 믿는 것' 재확인 금지 = 기준선 뺄셈(반버블)
      surface 섹션 지배 프레임과 결이 다른 이질 1건 의무(forager surface — 필터버블 반대힘)
    관점 코어 없으면 뉴스가치+surface 폴백. AI 실패 시 휴리스틱 pool[:keep] — 절대 빈 신문 없음."""
    if keep < 1:
        keep = 1
    pools = [_heuristic_dedup(s.get("items") or []) for s in secs]
    need_ai = [i for i, p in enumerate(pools) if len(p) > keep]

    def _fallback():
        return [{"picks": p[:keep], "rest": p[keep:]} for p in pools]

    if not need_ai:
        return _fallback()

    try:
        from consciousness_agent import lightweight_ai_call
        core = _load_perspective_core()
        blocks = []
        for i in need_ai:
            lines = []
            for j, it in enumerate(pools[i], 1):
                src = (it.get("meta") or "").split(" · ")[0].strip()
                line = f"{j}. {it.get('title', '')}"
                if src:
                    line += f" [{src}]"
                if it.get("sources", 1) > 1:
                    line += f" (×{it['sources']}매체)"      # gnews: 몇 매체가 다뤘나
                elif it.get("points"):
                    line += f" (▲{it['points']})"          # HN: 포인트 = 주목도
                lines.append(line)
            blocks.append(f"[섹션 {i}] 주제: {secs[i].get('topic', '')}\n" + "\n".join(lines))

        persp = ""
        delta_rule = ""
        if core:
            persp = (
                "\n독자의 관점 코어(그의 블로그 12년치의 증류 — 이미 믿는 것, 배격하는 프레임, 열린 질문):\n"
                "<관점>\n" + core + "\n</관점>\n"
            )
            delta_rule = (
                "- delta: 독자의 관점에 *가장 신선한 소수*. 그의 입장을 위반·확장하거나, 열린 질문에 닿거나,\n"
                "  추적 실타래의 실제 진전, 구체적 단독 사례. '이미 믿는 것'(끝난 일반론) 재확인은 금지.\n"
            )
        sys_prompt = (
            "너는 개인 신문의 편집장이다. 여러 섹션의 기사 제목 목록을 한 번에 받는다.\n"
            + persp +
            "★핵심: 역할은 *절대 문턱*이 아니라 *분포(곡선)*다. 섹션의 기사를 서로 비교해 상대적으로 등급을 매겨라 —\n"
            "'많은 기사가 관점에 관련 있다'가 아니라 '이 섹션에서 가장 신선한 게 무엇인가'를 가려라.\n"
            "목표 수(N)를 대략 이렇게 나눠라 (N=7 기준):\n"
            "- hot: 가장 널리 주목받은 중요 사건(여러 매체 ×N, 또는 HN 이면 ▲포인트 높음) 2~3개. **세상과의 접점이라 반드시 남긴다**(0개 금지).\n"
            + delta_rule +
            "  delta 는 2~3개까지만 — 실타래에 속한다고 다 delta 가 아니다. 널리 다뤄졌으면 hot 으로.\n"
            "- surface: 섹션의 지배적 흐름·프레임과 결이 다른 이질 기사 딱 1개(작게 다뤄졌어도). 의무.\n"
            "같은 사건의 중복 기사는 하나만. 기사를 새로 쓰거나 제목을 바꾸지 말고 번호로만 골라라.\n"
            '출력은 JSON 객체 하나만: {"0": [{"n": 3, "r": "hot", "w": "이유"}, ...], "2": [...]} '
            "— 키=섹션 번호, n=기사 번호, r=hot|delta|surface, w=고른 이유(25자 이내). 다른 말 금지."
        )
        prompt = f"섹션당 목표 기사 수: {keep}\n\n" + "\n\n".join(blocks)
        resp = lightweight_ai_call(prompt, system_prompt=sys_prompt, role="classify")
        m = re.search(r"\{[\s\S]*\}", resp or "")
        if not m:
            return _fallback()
        sel = json.loads(m.group(0))
        out = []
        for i, p in enumerate(pools):
            if i not in need_ai:
                out.append({"picks": p[:keep], "rest": p[keep:]})
                continue
            picked, used = [], set()
            for e in (sel.get(str(i)) or []):
                if isinstance(e, dict):
                    n, r, w = e.get("n"), e.get("r"), e.get("w")
                elif isinstance(e, int):            # 번호-만 응답도 수용(강건성)
                    n, r, w = e, None, None
                else:
                    continue
                if isinstance(n, int) and 1 <= n <= len(p) and n not in used:
                    used.add(n)
                    it = dict(p[n - 1])
                    if r in ("hot", "delta", "surface"):
                        it["role"] = r
                    if w:
                        it["why"] = str(w)[:60]
                    picked.append(it)
                if len(picked) >= keep:
                    break
            if not picked:
                out.append({"picks": p[:keep], "rest": p[keep:]})
            else:
                rest = [it for j, it in enumerate(p, 1) if j not in used]
                out.append({"picks": picked, "rest": rest})
        return out
    except Exception as e:
        print(f"[_curate_sections_batch] 경량 AI 편집 실패, 휴리스틱 폴백: {e}", file=sys.stderr)
        return _fallback()


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
            _fetch = 100 if _curate else _count   # 편집장은 넓게 보고 좁게 뽑는다 — GET 1회라 공짜

            def _dl(q):
                if _lang != "auto":
                    return _lang
                kc = sum(1 for c in q if '가' <= c <= '힣' or 'ㄱ' <= c <= 'ㆎ')
                return "ko" if kc > len(q) * 0.2 else "en"

            # RSS 병렬 페치(키워드당 GET 1회) + 경량 AI 일괄 편집(전 섹션 1회 호출) —
            # 직렬 (RSS+AI)×N 루프가 신문 조립을 느리게 하던 것을 해소(2026-07-11).
            def _to_items(res, tag):
                return [{
                    "title": r.get("title", ""),
                    "meta": " · ".join(x for x in [r.get("source"), r.get("published")] if x),
                    "summary": "" if (r.get("summary") or "") == r.get("title") else (r.get("summary") or ""),
                    "url": r.get("url", ""), "link_label": "기사 보기", "query": tag,
                } for r in (res.get("results") or [])]

            _sources = str(tool_input.get("sources") or "gnews,guardian")

            def _fetch_section_items(q):
                lang = _dl(q)
                items = _to_items(search_gnews(query=q, count=_fetch, language=lang), q)
                # 가디언 합류: curate(신문 편성) + 영어 키워드일 때만 — 한국어 질의는 가디언 코퍼스에 없음
                if _curate and "guardian" in _sources and lang == "en":
                    items += [{**g, "query": q} for g in _guardian_items(q, 30)]
                return items

            jobs = []  # (섹션명, items thunk) — 오늘의 핫토픽은 맨 앞 섹션(원격/폰 신문 파리티)
            if tool_input.get("headlines") in (True, "true", "True", 1, "1"):
                jobs.append(("오늘의 핫토픽", lambda: _to_items(search_gnews(
                    count=_fetch, language=(_lang if _lang != "auto" else "ko"), headlines=True), "오늘의 핫토픽")))
            for q in _queries:
                jobs.append((q, (lambda qq: (lambda: _fetch_section_items(qq)))(q)))
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as ex:
                fetched = list(ex.map(lambda j: j[1](), jobs))
            secs = [{"topic": jobs[i][0], "items": fetched[i]} for i in range(len(jobs))]
            curated = _curate_sections_batch(secs, _curate) if _curate else None

            all_items, pool_rest, sections = [], [], []
            for i in range(len(secs)):
                items = curated[i]["picks"] if curated else secs[i]["items"]
                if curated:
                    pool_rest.extend(curated[i]["rest"])
                all_items.extend(items)
                sections.append({"query": jobs[i][0], "count": len(items)})
            resp = {"success": True, "queries": _queries, "count": len(all_items),
                    "sections": sections, "items": all_items}
            if curated:
                resp["pool"] = pool_rest   # 편집장이 안 뽑은 나머지(query 태그로 섹션 구분) — 편집신문 대체 후보
                resp["perspective"] = bool(_load_perspective_core())  # 관점 코어 반영 여부 — silent 폴백을 UI에 노출
            return format_json(resp)

        # 오늘의 핫토픽 — 키워드 없는 톱 헤드라인을 curate가 군집·랭킹(중복 많이 다뤄진=핫)
        if tool_input.get("headlines") in (True, "true", "True", 1, "1"):
            language = tool_input.get("language", "ko")
            if language == "auto":
                language = "ko"
            _curate = _parse_curate(tool_input)
            _fetch = 100 if _curate else tool_input.get("count", 12)   # 헤드라인 피드는 실제 최대 ~34
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
                    cr = _curate_sections_batch([{"topic": "오늘의 핫토픽", "items": result["items"]}], _curate)[0]
                    result["items"], result["pool"] = cr["picks"], cr["rest"]
                    result["count"] = len(result["items"])
                    result["perspective"] = bool(_load_perspective_core())
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
        _fetch = 100 if _curate else tool_input.get("count", 10)   # 편집장은 넓게 보고 좁게 뽑는다
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
                # 가디언 합류(영어 키워드): 정본=study search_guardian, 실패 시 조용히 gnews만
                if "guardian" in str(tool_input.get("sources") or "gnews,guardian") and language == "en":
                    result["items"] += [{**g, "query": query} for g in _guardian_items(query, 30)]
                cr = _curate_sections_batch([{"topic": query, "items": result["items"]}], _curate)[0]
                result["items"], result["pool"] = cr["picks"], cr["rest"]
                result["count"] = len(result["items"])
                result["perspective"] = bool(_load_perspective_core())
        return format_json(result)

    # Hacker News 신문 소스 — gnews 와 형제. 별도 판(HN 전용)용. 편집장·관점 필터 공유.
    elif tool_name == "search_hn":
        _curate = _parse_curate(tool_input)
        _fetch = 100 if _curate else tool_input.get("count", 15)
        _front = tool_input.get("headlines") in (True, "true", "True", 1, "1") or \
                 tool_input.get("front_page") in (True, "true", "True", 1, "1")

        _queries = tool_input.get("queries")
        if _queries:
            if isinstance(_queries, str):
                _queries = re.split(r"[,\n]", _queries)
            _queries = [str(q).strip() for q in _queries if str(q).strip()]
            if not _queries:
                return format_json({"success": False, "error": "검색어(queries)가 비었습니다."})
            jobs = []  # (섹션명, fetch thunk) — front_page 는 맨 앞(핫토픽 analog)
            if _front:
                jobs.append(("HN 프론트페이지", lambda: _hn_items(count=_fetch, front_page=True)))
            for q in _queries:
                jobs.append((q, (lambda qq: (lambda: _hn_items(qq, _fetch)))(q)))
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as ex:
                fetched = list(ex.map(lambda j: j[1](), jobs))
            secs = [{"topic": jobs[i][0],
                     "items": [{**it, "query": jobs[i][0]} for it in fetched[i]]} for i in range(len(jobs))]
            curated = _curate_sections_batch(secs, _curate) if _curate else None
            all_items, pool_rest, sections = [], [], []
            for i in range(len(secs)):
                items = curated[i]["picks"] if curated else secs[i]["items"]
                if curated:
                    pool_rest.extend(curated[i]["rest"])
                all_items.extend(items)
                sections.append({"query": jobs[i][0], "count": len(items)})
            resp = {"success": True, "queries": _queries, "count": len(all_items),
                    "sections": sections, "items": all_items}
            if curated:
                resp["pool"] = pool_rest
                resp["perspective"] = bool(_load_perspective_core())
            return format_json(resp)

        topic = "HN 프론트페이지" if _front else tool_input.get("query", "")
        if not _front and not topic:
            return format_json({"success": False, "error": "검색어(query/queries) 또는 headlines 가 필요합니다."})
        items = [{**it, "query": topic} for it in _hn_items("" if _front else topic, _fetch, front_page=_front)]
        resp = {"success": True, "query": topic, "count": len(items), "items": items}
        if _curate:
            cr = _curate_sections_batch([{"topic": topic, "items": items}], _curate)[0]
            resp["items"], resp["pool"] = cr["picks"], cr["rest"]
            resp["count"] = len(resp["items"])
            resp["perspective"] = bool(_load_perspective_core())
        return format_json(resp)

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
