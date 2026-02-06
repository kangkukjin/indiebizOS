"""
web 패키지 핸들러
웹 검색, 크롤링, 브라우저 자동화, 뉴스 검색, 신문 생성, 즐겨찾기 사이트 관리 통합
"""

import os
import json
import re
import sys
import webbrowser
import importlib.util
from html import unescape
from datetime import datetime
from urllib.parse import quote_plus
from pathlib import Path

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

def clean_html(text: str) -> str:
    """HTML 태그 제거 및 엔티티 디코딩"""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def search_google_news(query: str, count: int = 10, language: str = "ko") -> dict:
    """Google News RSS 검색"""
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
        rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl={language}&gl=KR&ceid=KR:{language}"

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
            "results": results
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "query": query,
            "results": []
        }


def generate_section(keyword: str, news_count: int = 7, exclude_sources: list = None) -> dict:
    """키워드로 뉴스 검색하여 섹션 생성"""
    if exclude_sources is None:
        exclude_sources = []

    fetch_count = news_count * 3 if exclude_sources else news_count
    result = search_google_news(query=keyword, count=fetch_count, language='ko')

    if not result['success'] or not result['results']:
        return {
            'keyword': keyword,
            'markdown': f"## {keyword}\n\n뉴스를 찾을 수 없습니다.\n\n---\n\n",
            'news_count': 0,
            'success': False
        }

    filtered_results = []
    excluded_count = 0

    for item in result['results']:
        source = item.get('source', '')
        is_excluded = any(ex in source for ex in exclude_sources)

        if is_excluded:
            excluded_count += 1
        else:
            filtered_results.append(item)
            if len(filtered_results) >= news_count:
                break

    if not filtered_results:
        return {
            'keyword': keyword,
            'markdown': f"## {keyword}\n\n필터링 후 뉴스를 찾을 수 없습니다.\n\n---\n\n",
            'news_count': 0,
            'success': False
        }

    section = f"## {keyword}\n\n"
    section += "[GRID_START]\n\n"

    for i, item in enumerate(filtered_results, 1):
        section += "[CARD_START]\n\n"
        section += f"### {i}. {item['title']}\n\n"
        section += f"**출처**: {item['source']} | **발행**: {item['published']}\n\n"

        if item.get('summary') and item['summary'] != item['title']:
            section += f"{item['summary']}\n\n"

        section += f"[기사 보기]({item['url']})\n\n"
        section += "[CARD_END]\n\n"

    section += "[GRID_END]\n\n"

    return {
        'keyword': keyword,
        'markdown': section,
        'news_count': len(filtered_results),
        'excluded_count': excluded_count,
        'success': True
    }


def markdown_to_html(markdown_content: str, title: str, date_str: str) -> str:
    """Markdown을 HTML로 변환"""
    html_body = markdown_content

    html_body = html_body.replace("[GRID_START]", '<div class="grid">')
    html_body = html_body.replace("[GRID_END]", '</div>')
    html_body = html_body.replace("[CARD_START]", '<div class="card">')
    html_body = html_body.replace("[CARD_END]", '</div>')

    html_body = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html_body, flags=re.MULTILINE)
    html_body = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html_body, flags=re.MULTILINE)
    html_body = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html_body, flags=re.MULTILINE)
    html_body = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html_body)
    html_body = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2" target="_blank">\1</a>', html_body)
    html_body = re.sub(r'^---$', r'<hr>', html_body, flags=re.MULTILINE)

    lines = html_body.split('\n')
    processed_lines = []
    grid_depth = 0

    for line in lines:
        if '<div class="grid">' in line or '<div class="card">' in line:
            grid_depth += 1

        if not line.strip():
            if grid_depth == 0:
                processed_lines.append('<div class="spacer"></div>')
        elif line.startswith('<div') or line.startswith('</div') or line.startswith('<h') or line.startswith('<hr'):
            processed_lines.append(line)
        else:
            processed_lines.append(f'<p>{line}</p>')

        if '</div>' in line and grid_depth > 0:
            grid_depth -= 1

    html_body = '\n'.join(processed_lines)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Noto Sans KR', -apple-system, BlinkMacSystemFont, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f0f2f5;
            padding: 30px 10px;
        }}
        .container {{
            max-width: 1100px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        }}
        h1 {{
            color: #1a1a2e;
            font-size: 2.5em;
            margin-bottom: 15px;
            border-bottom: 4px solid #1a1a2e;
            padding-bottom: 15px;
            text-align: center;
        }}
        h2 {{
            color: #1a1a2e;
            font-size: 1.8em;
            margin: 40px 0 20px;
            padding-bottom: 8px;
            border-bottom: 2px solid #eee;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 25px;
            margin-bottom: 30px;
        }}
        @media (max-width: 800px) {{
            .grid {{ grid-template-columns: 1fr; }}
            .container {{ padding: 20px; }}
        }}
        .card {{
            background: #fff;
            border: 1px solid #e1e4e8;
            padding: 20px;
            border-radius: 10px;
            display: flex;
            flex-direction: column;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .card:hover {{
            transform: translateY(-3px);
            box-shadow: 0 6px 15px rgba(0,0,0,0.1);
            border-color: #3d5a80;
        }}
        h3 {{
            color: #22223b;
            font-size: 1.15em;
            margin-bottom: 12px;
            line-height: 1.4;
        }}
        p {{ margin: 8px 0; font-size: 0.95em; color: #444; }}
        .spacer {{ height: 10px; }}
        strong {{ color: #555; font-size: 0.9em; }}
        a {{
            display: inline-block;
            margin-top: auto;
            color: #3d5a80;
            text-decoration: none;
            font-weight: bold;
            font-size: 0.9em;
            padding: 5px 0;
        }}
        a:hover {{ text-decoration: underline; }}
        hr {{
            border: none;
            border-top: 1px solid #eee;
            margin: 30px 0;
        }}
        .meta {{
            text-align: center;
            color: #666;
            font-size: 0.95em;
            margin-bottom: 30px;
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
        }}
        .footer {{
            margin-top: 50px;
            padding-top: 25px;
            border-top: 1px solid #eee;
            color: #999;
            font-size: 0.85em;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>
        <div class="meta">
            <strong>발행일:</strong> {date_str} |
            <strong>발행처:</strong> IndieBiz AI |
            <strong>출처:</strong> Google News RSS
        </div>
        {html_body}
        <div class="footer">
            <p>생성 시각: {datetime.now().strftime('%Y년 %m월 %d일 %H시 %M분')}</p>
            <p>AI 사용: 없음 (토큰 소비 0)</p>
        </div>
    </div>
</body>
</html>"""


def generate_newspaper(keywords: list, title: str = "IndieBiz Daily",
                       exclude_sources: list = None, project_path: str = ".") -> dict:
    """Google News 기반 신문 자동 생성"""
    if not keywords:
        return {'success': False, 'error': '키워드가 필요합니다.'}

    if exclude_sources is None:
        exclude_sources = []

    today = datetime.now()
    date_str = today.strftime('%Y년 %m월 %d일')
    date_filename = today.strftime('%Y%m%d_%H%M%S')

    sections = []
    for keyword in keywords:
        section = generate_section(keyword, news_count=7, exclude_sources=exclude_sources)
        sections.append(section)

    toc_items = []
    for section in sections:
        if section['success'] and section['news_count'] > 0:
            toc_items.append(f"- [{section['keyword']}](#{section['keyword']}) ({section['news_count']}개)")

    toc = "\n".join(toc_items)
    content = "\n\n".join([s['markdown'] for s in sections])
    total_news = sum(s['news_count'] for s in sections)

    newspaper_md = f"""# {title}

**발행일**: {date_str}
**발행처**: IndieBiz AI
**총 뉴스**: {total_news}개

---

## 목차

{toc}

---

{content}
"""

    out_dir = os.path.join(project_path, OUTPUTS_DIR)
    os.makedirs(out_dir, exist_ok=True)

    html_content = markdown_to_html(newspaper_md, title, date_str)
    filename = f"newspaper_{date_filename}.html"
    filepath = os.path.join(out_dir, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html_content)

    return {
        'success': True,
        'message': f'신문 생성 완료: {os.path.abspath(filepath)}',
        'file': os.path.abspath(filepath),
        'title': title,
        'sections': len(sections),
        'total_news': total_news
    }


# ============== 사이트 런처 관련 함수 ==============

def launch_sites(action: str = "open_all", name: str = None, url: str = None, project_path: str = ".") -> str:
    """자주 가는 사이트 런처 및 관리"""
    sites_path = current_dir / "sites.json"

    try:
        if sites_path.exists():
            with open(sites_path, "r", encoding="utf-8") as f:
                sites = json.load(f)
        else:
            sites = []
    except Exception as e:
        return f"사이트 목록을 읽는 중 오류 발생: {str(e)}"

    if action == "open_all":
        opened = []
        for site in sites:
            webbrowser.open(site["url"])
            opened.append(site["name"])
        return f"다음 사이트들을 브라우저에서 열었습니다: {', '.join(opened)}"

    elif action == "list":
        if not sites:
            return "등록된 사이트가 없습니다."
        list_str = "\n".join([f"- {s['name']}: {s['url']}" for s in sites])
        return f"현재 등록된 사이트 목록입니다:\n{list_str}"

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

def execute(tool_name: str, params: dict, project_path: str = None):
    """IndieBiz OS에서 도구를 호출할 때 실행되는 메인 핸들러"""

    # DuckDuckGo 웹 검색
    if tool_name == "ddgs_search":
        tool_ddgs = load_module("tool_ddgs_search")
        query = params.get("query")
        count = params.get("count", 5)
        country = params.get("country", "kr-kr")
        return tool_ddgs.search_web(query, count, country)

    # 웹페이지 크롤링
    elif tool_name == "crawl_website":
        url = params.get("url")
        max_length = params.get("max_length", 10000)

        if not url:
            return json.dumps({"success": False, "error": "URL이 제공되지 않았습니다."}, ensure_ascii=False)

        try:
            tool_webcrawl = load_module("tool_webcrawl")
            result = tool_webcrawl.crawl_website(url, max_length)
            return json.dumps(result, ensure_ascii=False, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    # Google News 검색
    elif tool_name == "google_news_search":
        query = params.get("query", "")
        if not query:
            return json.dumps({"success": False, "error": "검색어(query)가 필요합니다."}, ensure_ascii=False)

        result = search_google_news(
            query=query,
            count=params.get("count", 10),
            language=params.get("language", "ko")
        )
        return json.dumps(result, ensure_ascii=False, indent=2)

    # 신문 생성
    elif tool_name == "generate_newspaper":
        keywords = params.get("keywords", [])
        if not keywords:
            return json.dumps({"success": False, "error": "키워드(keywords)가 필요합니다."}, ensure_ascii=False)

        result = generate_newspaper(
            keywords=keywords,
            title=params.get("title", "IndieBiz Daily"),
            exclude_sources=params.get("exclude_sources", []),
            project_path=project_path or "."
        )
        return json.dumps(result, ensure_ascii=False, indent=2)

    # 사이트 런처
    elif tool_name == "launch_sites":
        action = params.get("action", "open_all")
        name = params.get("name")
        url = params.get("url")
        return launch_sites(action, name, url, project_path or ".")

    else:
        return json.dumps({
            "success": False,
            "error": f"Unknown tool: {tool_name}"
        }, ensure_ascii=False)
