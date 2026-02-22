"""
Kinsight - 블로그 기반 개인 인사이트 도구
==========================================
블로그 최신글과 나의 정보를 AI에게 주고,
오늘날 연결되어야 할 커뮤니티와 읽거나 보아야 할 것을 추천받습니다.
"""

import os
import sys
import json
import sqlite3
from datetime import datetime
from typing import Dict, Any

# common 유틸리티 사용
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

# 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "blog_insight.db")

# 시스템 데이터 경로 (blog 폴더 → tools → installed → packages → data)
INDIEBIZ_DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "..", ".."))
PROFILE_PATH = os.path.join(INDIEBIZ_DATA_DIR, "my_profile.txt")
SYSTEM_AI_CONFIG_PATH = os.path.join(INDIEBIZ_DATA_DIR, "system_ai_config.json")

BLOG_URL = "https://irepublic.tistory.com"


def load_system_ai_config() -> dict:
    """시스템 AI 설정 로드"""
    if os.path.exists(SYSTEM_AI_CONFIG_PATH):
        try:
            with open(SYSTEM_AI_CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {
        "provider": "google",
        "model": "gemini-2.0-flash",
        "apiKey": ""
    }


def load_profile() -> str:
    """나의 정보 로드"""
    if os.path.exists(PROFILE_PATH):
        try:
            with open(PROFILE_PATH, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except:
            pass
    return ""


def get_ai_client():
    """AI 클라이언트 반환"""
    config = load_system_ai_config()
    provider = config.get("provider", "google")
    model = config.get("model", "gemini-2.0-flash")
    api_key = config.get("apiKey") or config.get("api_key", "")

    if provider in ["google", "gemini"]:
        from google import genai
        client = genai.Client(api_key=api_key)
        return client, "gemini", model
    elif provider == "openai":
        import openai
        client = openai.OpenAI(api_key=api_key)
        return client, "openai", model
    elif provider == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        return client, "anthropic", model
    else:
        raise ValueError(f"Unknown provider: {provider}")


def get_latest_posts(count: int = 10, before_date: str = None) -> list:
    """
    블로그 DB에서 최신글 가져오기 (원문 전체)

    Args:
        count: 가져올 글 수
        before_date: 이 날짜 이전의 글만 가져옴 (YYYY-MM-DD 형식)
    """
    if not os.path.exists(DB_PATH):
        return []

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    if before_date:
        rows = conn.execute("""
            SELECT post_id, title, category, pub_date, content
            FROM posts
            WHERE pub_date < ?
            ORDER BY pub_date DESC
            LIMIT ?
        """, (before_date, count)).fetchall()
    else:
        rows = conn.execute("""
            SELECT post_id, title, category, pub_date, content
            FROM posts
            ORDER BY pub_date DESC
            LIMIT ?
        """, (count,)).fetchall()

    conn.close()

    posts = []
    for row in rows:
        posts.append({
            'post_id': row['post_id'],
            'title': row['title'],
            'category': row['category'],
            'pub_date': row['pub_date'],
            'content': row['content'],
            'link': f"{BLOG_URL}/{row['post_id']}"
        })

    return posts


def markdown_to_html(content: str, title: str, date_str: str) -> str:
    """마크다운을 HTML로 변환"""
    try:
        import markdown
        html_body = markdown.markdown(content, extensions=['tables', 'fenced_code', 'nl2br'])
    except ImportError:
        html_body = f"<pre style='white-space: pre-wrap;'>{content}</pre>"

    html_template = """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;700&display=swap');
        body {{
            font-family: 'Noto Sans KR', sans-serif;
            max-width: 900px;
            margin: 0 auto;
            padding: 40px 20px;
            line-height: 1.8;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }}
        .content-card {{
            background: white;
            padding: 50px;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }}
        h1 {{
            color: #4a148c;
            border-bottom: 4px solid #7c4dff;
            padding-bottom: 15px;
            font-size: 2.2em;
            margin-bottom: 10px;
        }}
        h2 {{
            color: #6a1b9a;
            margin-top: 2em;
            border-left: 5px solid #7c4dff;
            padding-left: 15px;
        }}
        h3 {{
            color: #7b1fa2;
            margin-top: 1.5em;
        }}
        a {{
            color: #7c4dff;
            text-decoration: none;
            border-bottom: 2px solid #e1bee7;
            transition: all 0.3s;
        }}
        a:hover {{
            color: #4a148c;
            border-bottom-color: #7c4dff;
        }}
        ul, ol {{
            padding-left: 1.5em;
        }}
        li {{
            margin: 0.5em 0;
        }}
        blockquote {{
            margin: 20px 0;
            padding: 15px 25px;
            border-left: 5px solid #7c4dff;
            background: #f3e5f5;
            border-radius: 0 10px 10px 0;
            font-style: italic;
            color: #4a148c;
        }}
        .meta {{
            color: #9575cd;
            font-size: 0.95em;
            margin-bottom: 30px;
        }}
        .insight-badge {{
            display: inline-block;
            background: linear-gradient(135deg, #7c4dff, #b388ff);
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.85em;
            margin-bottom: 20px;
        }}
        hr {{
            border: 0;
            height: 2px;
            background: linear-gradient(to right, #7c4dff, #b388ff);
            margin: 40px 0;
        }}
        @media print {{
            body {{ background: white; }}
            .content-card {{ box-shadow: none; padding: 0; }}
        }}
    </style>
</head>
<body>
    <div class="content-card">
        <div class="insight-badge">🔮 Kinsight</div>
        <h1>{title}</h1>
        <p class="meta">생성일: {date_str} | 블로그: {blog_url}</p>
        {html_body}
    </div>
</body>
</html>"""
    return html_template.format(title=title, date_str=date_str, html_body=html_body, blog_url=BLOG_URL)


def kinsight(project_path: str = ".", before_date: str = None) -> Dict[str, Any]:
    """기존 kinsight 함수 (하위 호환성 유지)"""
    return kinsight2(project_path=project_path, count=10, before_date=before_date)


def kinsight2(project_path: str = ".", count: int = 10, before_date: str = None) -> Dict[str, Any]:
    """
    Kinsight2: 블로그 기반 개인 인사이트 생성 (글 개수 지정 가능)

    Args:
        project_path: 프로젝트 경로 (outputs 폴더 위치)
        count: 분석할 글 개수 (기본 10)
        before_date: 이 날짜 이전의 글로 분석 (YYYY-MM-DD 형식, 없으면 최신글)
    """
    try:
        # 1. 글 가져오기
        posts = get_latest_posts(count, before_date=before_date)
        if not posts:
            return {'success': False, 'error': '블로그 데이터가 없습니다. blog_check_new_posts를 먼저 실행하세요.'}

        # 2. 나의 정보 로드
        profile = load_profile()

        # 3. AI 프롬프트 구성
        posts_text = ""
        for i, post in enumerate(posts, 1):
            posts_text += f"\n\n--- 글 {i} ---\n"
            posts_text += f"제목: {post['title']}\n"
            posts_text += f"카테고리: {post['category']}\n"
            posts_text += f"날짜: {post['pub_date']}\n"
            posts_text += f"본문:\n{post['content']}\n"

        prompt = f"""당신은 개인의 관심사와 성장을 돕는 인사이트 큐레이터입니다.

## 나의 정보
{profile if profile else "(정보 없음)"}

## 최근 블로그 글 {len(posts)}개 (원문)
{posts_text}

---

위 블로그 글들을 분석하고, 다음 질문에 깊이 있게 답변해 주세요:

**"이런 글을 쓴 사람이 오늘날 연결되어야 할 커뮤니티와 읽거나 보아야 할 것은 무엇인가요?"**

다음 형식으로 답변해 주세요:

## 🔍 글쓴이 분석
(이 사람의 관심사, 사고방식, 추구하는 가치를 간략히 분석)

## 🤝 연결되어야 할 커뮤니티
(온라인/오프라인 커뮤니티 3-5개 구체적 추천, 각각 왜 적합한지 설명)

## 📚 읽어야 할 책/글
(책 3-5권, 블로그/아티클 3-5개 추천, 왜 읽어야 하는지 설명)

## 🎬 봐야 할 콘텐츠
(영상, 강연, 다큐멘터리 등 3-5개 추천)

## 🌱 다음 단계 제안
(이 사람의 성장을 위한 구체적인 다음 행동 2-3가지)

각 추천에는 가능하면 실제 링크나 구체적인 이름을 포함해 주세요.
"""

        # 4. AI 호출
        client, provider, model = get_ai_client()

        if provider == "gemini":
            response = client.models.generate_content(model=model, contents=prompt)
            ai_answer = response.text
        elif provider == "openai":
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}]
            )
            ai_answer = response.choices[0].message.content
        elif provider == "anthropic":
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )
            ai_answer = response.content[0].text
        else:
            return {'success': False, 'error': f'지원하지 않는 AI 제공자: {provider}'}

        # 5. 참고 글 목록 추가
        reference_section = "\n\n---\n\n## 📝 참고한 블로그 글\n\n"
        for i, post in enumerate(posts, 1):
            pub_date = post['pub_date'][:10] if post['pub_date'] else ''
            reference_section += f"{i}. [{post['title']}]({post['link']}) ({pub_date})\n"

        full_content = ai_answer + reference_section

        # 6. HTML 생성 및 저장
        now = datetime.now()
        if before_date:
            title = f"Kinsight2 (글 {len(posts)}개) - {before_date} 이전"
        else:
            title = f"Kinsight2 (글 {len(posts)}개) - {now.strftime('%Y년 %m월 %d일')}"

        html_content = markdown_to_html(full_content, title, now.strftime("%Y-%m-%d %H:%M"))

        out_dir = os.path.join(project_path, "outputs")
        os.makedirs(out_dir, exist_ok=True)

        filename = f"kinsight2_{now.strftime('%Y%m%d_%H%M%S')}.html"
        filepath = os.path.join(out_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return {
            'success': True,
            'report_path': os.path.abspath(filepath),
            'message': f'Kinsight2 보고서 생성 완료 (분석 글: {len(posts)}개)',
            'analyzed_posts': len(posts),
            'has_profile': bool(profile),
            'before_date': before_date
        }

    except Exception as e:
        return {'success': False, 'error': str(e)}
