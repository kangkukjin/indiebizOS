import os
import json
import requests
from datetime import datetime
from jinja2 import Template
import feedparser
import re

# API Keys
NINJAS_API_KEY = "***REMOVED***"
AMADEUS_API_KEY = "***REMOVED***"
AMADEUS_API_SECRET = "***REMOVED***"
AMADEUS_BASE_URL = "https://test.api.amadeus.com"

# 출력 디렉토리 설정
OUTPUTS_DIR = 'outputs'

def get_amadeus_token():
    auth_url = f"{AMADEUS_BASE_URL}/v1/security/oauth2/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": AMADEUS_API_KEY,
        "client_secret": AMADEUS_API_SECRET
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        response = requests.post(auth_url, data=data, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json().get("access_token")
    except:
        pass
    return None

def search_news(keyword, max_results=5):
    from duckduckgo_search import DDGS
    results = []
    try:
        with DDGS() as ddgs:
            # 최신 ddgs 라이브러리 형식 사용 (ddgs.news)
            ddgs_gen = ddgs.news(keyword, region="wt-wt", safesearch="off", timelimit="d", max_results=max_results)
            for r in ddgs_gen:
                results.append({
                    "title": r['title'],
                    "snippet": r['body'],
                    "link": r['url'],
                    "source": r['source']
                })
    except Exception as e:
        print(f"Error searching news for {keyword}: {e}")
    return results

def fetch_rss(url, limit=7):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200: return []
        feed = feedparser.parse(response.text)
        articles = []
        source_title = feed.feed.get('title', 'RSS Source')
        for entry in feed.entries[:limit]:
            content = entry.get('summary', entry.get('description', ''))
            clean_text = re.sub('<[^<]+?>', '', str(content)).replace('&nbsp;', ' ').strip()
            articles.append({
                "title": entry.get('title', 'No Title'),
                "snippet": clean_text[:400] + "...",
                "link": entry.get('link', ''),
                "source": source_title
            })
        return articles
    except: return []

DEFAULT_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="utf-8">
    <title>{{ title }}</title>
    <style>
        body { font-family: sans-serif; line-height: 1.6; max-width: 800px; margin: 0 auto; padding: 20px; color: #333; }
        h1 { color: #1a2a6c; border-bottom: 2px solid #1a2a6c; }
        .article { margin-bottom: 30px; }
        .article h3 { margin: 0; }
        .article a { color: #3498db; }
    </style>
</head>
<body>
    <h1>{{ title }}</h1>
    <p>발행일: {{ date }}</p>
    {% for section in sections %}
        <h2>{{ section.keyword }}</h2>
        {% for article in section.articles %}
            <div class="article">
                <h3>{{ article.title }}</h3>
                <p>{{ article.snippet }}</p>
                <a href="{{ article.link }}" target="_blank">기사 보기</a>
            </div>
        {% endfor %}
    {% endfor %}
</body>
</html>
"""

def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    out_dir = os.path.join(project_path, OUTPUTS_DIR)
    os.makedirs(out_dir, exist_ok=True)

    if tool_name == "generate_magazine":
        topic = tool_input.get("topic")
        title = tool_input.get("title", f"{topic} Weekly Magazine")
        articles = search_news(topic, 10)
        sections = [{"keyword": "심층 취재", "articles": articles}]
        
        template = Template(DEFAULT_TEMPLATE)
        html = template.render(title=title, date=datetime.now().strftime("%Y-%m-%d"), sections=sections)
        filename = f"magazine_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        filepath = os.path.join(out_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f: f.write(html)
        return f"잡지 생성 완료: {os.path.abspath(filepath)}"

    elif tool_name == "generate_it_newspaper":
        title = tool_input.get("title", "IT Tech News")
        sections = [
            {"keyword": "Hacker News", "articles": fetch_rss("https://hnrss.org/frontpage", 5)},
            {"keyword": "Reddit AI", "articles": fetch_rss("https://www.reddit.com/r/artificial/.rss", 5)},
            {"keyword": "Ars Technica", "articles": fetch_rss("https://feeds.arstechnica.com/arstechnica/index", 5)},
            {"keyword": "TechCrunch", "articles": fetch_rss("https://techcrunch.com/feed/", 5)}
        ]
        template = Template(DEFAULT_TEMPLATE)
        html = template.render(title=title, date=datetime.now().strftime("%Y-%m-%d"), sections=sections)
        filename = f"it_news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        filepath = os.path.join(out_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f: f.write(html)
        return f"IT 신문 생성 완료: {os.path.abspath(filepath)}"

    return f"Unknown tool: {tool_name}"
