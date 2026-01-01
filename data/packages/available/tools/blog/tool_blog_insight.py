"""
Blog Insight Tool for IndieBiz
==============================
블로그 글을 수집하고 AI 요약을 저장하여 에이전트가 보고서를 작성할 수 있게 하는 도구

설계 원칙:
- 기초 도구만 제공, AI 에이전트가 조합해서 사용
- 500자 요약은 별도 테이블에 저장
- 보고서 생성은 내부 AI가 처리 (토큰 절약)

도구 목록:
1. blog_get_posts - 글 목록 조회 (요약 포함 여부 선택)
2. blog_get_post - 특정 글 전문 조회
3. blog_get_summaries - 요약 목록 조회
4. blog_search - 키워드로 글 검색
5. blog_stats - DB 통계
6. blog_generate_report - AI가 보고서 생성 (내부 처리)
"""

import os
import json
import sqlite3
import requests
import re
from datetime import datetime
from typing import Optional, List, Dict, Any
from bs4 import BeautifulSoup

# 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "blog_insight.db")
SETTINGS_PATH = os.path.join(DATA_DIR, "tool_settings.json")
from tool_utils import markdown_to_html, OUTPUTS_DIR

BLOG_URL = "https://irepublic.tistory.com"
RSS_URL = f"{BLOG_URL}/rss"
RSS_SIZE = 50


def load_tool_settings() -> dict:
    """도구 설정 로드"""
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {
        "blog_insight": {
            "report_ai": {
                "provider": "gemini",
                "model": "gemini-2.0-flash-exp",
                "api_key": ""
            }
        }
    }


def get_report_ai_client():
    """보고서 생성용 AI 클라이언트 반환"""
    settings = load_tool_settings()
    ai_config = settings.get("blog_insight", {}).get("report_ai", {})

    provider = ai_config.get("provider", "gemini")
    model = ai_config.get("model", "gemini-2.0-flash-exp")
    api_key = ai_config.get("api_key", "")

    if provider == "gemini":
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


def get_db() -> sqlite3.Connection:
    """DB 연결 및 테이블 생성"""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # posts 테이블
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id TEXT UNIQUE,
            title TEXT,
            category TEXT,
            pub_date DATETIME,
            content TEXT,
            char_count INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # summaries 테이블 (AI 요약 저장)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id TEXT UNIQUE,
            summary TEXT,
            keywords TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (post_id) REFERENCES posts(post_id)
        )
    """)
    
    conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_post_id ON posts(post_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_pub_date ON posts(pub_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_summaries_post_id ON summaries(post_id)")
    
    conn.commit()
    return conn


def parse_rss_date(rss_date: str) -> Optional[str]:
    """RSS 날짜를 DB 형식으로 변환"""
    try:
        # "Fri, 19 Dec 2025 10:36:06 +0900" 형식
        dt = datetime.strptime(rss_date.strip(), "%a, %d %b %Y %H:%M:%S %z")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return None


def strip_html(html: str) -> str:
    """HTML 태그 제거"""
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text(separator=' ')
    return re.sub(r'\s+', ' ', text).strip()


def fetch_rss_feed() -> List[Dict[str, Any]]:
    """RSS 피드에서 글 목록 가져오기"""
    url = f"{RSS_URL}?size={RSS_SIZE}"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.content, 'xml')
    items = soup.find_all('item')
    
    posts = []
    for item in items:
        link = item.find('link').text if item.find('link') else ""
        post_id_match = re.search(r'/(\d+)$', link)
        post_id = post_id_match.group(1) if post_id_match else link
        
        title = item.find('title').text if item.find('title') else ""
        pub_date = item.find('pubDate').text if item.find('pubDate') else ""
        description = item.find('description').text if item.find('description') else ""
        
        categories = [cat.text for cat in item.find_all('category')]
        category = categories[0] if categories else ""
        
        content_text = strip_html(description)
        
        posts.append({
            'post_id': post_id,
            'title': title,
            'link': link,
            'pub_date': pub_date,
            'category': category,
            'content': content_text
        })
    
    return posts


# =============================================================================
# 도구 함수들
# =============================================================================

def blog_check_new_posts() -> Dict[str, Any]:
    """
    RSS에서 새 글 확인하고 DB에 저장
    
    Returns:
        dict: {
            'success': bool,
            'new_count': int,
            'new_posts': list[{post_id, title, pub_date}],
            'total_posts': int
        }
    """
    try:
        conn = get_db()
        
        # 기존 post_id 목록
        existing = set(row[0] for row in conn.execute("SELECT post_id FROM posts").fetchall())
        
        # RSS 가져오기
        rss_posts = fetch_rss_feed()
        
        new_posts = []
        for post in rss_posts:
            if post['post_id'] not in existing:
                pub_date_db = parse_rss_date(post['pub_date'])
                
                conn.execute("""
                    INSERT OR IGNORE INTO posts (post_id, title, category, pub_date, content, char_count)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    post['post_id'],
                    post['title'],
                    post['category'],
                    pub_date_db,
                    post['content'],
                    len(post['content'])
                ))
                
                new_posts.append({
                    'post_id': post['post_id'],
                    'title': post['title'],
                    'pub_date': pub_date_db
                })
        
        conn.commit()
        
        total = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        conn.close()
        
        return {
            'success': True,
            'new_count': len(new_posts),
            'new_posts': new_posts,
            'total_posts': total
        }
        
    except Exception as e:
        return {'success': False, 'error': str(e)}


def blog_get_posts(
    count: int = 20,
    offset: int = 0,
    category: Optional[str] = None,
    with_summary: bool = False,
    only_without_summary: bool = False
) -> Dict[str, Any]:
    """
    글 목록 조회
    
    Args:
        count: 가져올 글 수 (최대 100)
        offset: 시작 위치
        category: 카테고리 필터
        with_summary: 요약 포함 여부
        only_without_summary: 요약이 없는 글만
    
    Returns:
        dict: {
            'success': bool,
            'posts': list[{post_id, title, category, pub_date, content_preview, summary?}]
        }
    """
    try:
        conn = get_db()
        count = min(count, 100)
        
        if only_without_summary:
            query = """
                SELECT p.post_id, p.title, p.category, p.pub_date, p.content
                FROM posts p
                LEFT JOIN summaries s ON p.post_id = s.post_id
                WHERE s.post_id IS NULL
            """
            params = []
        else:
            query = """
                SELECT p.post_id, p.title, p.category, p.pub_date, p.content
            """
            if with_summary:
                query += ", s.summary, s.keywords"
            query += """
                FROM posts p
            """
            if with_summary:
                query += " LEFT JOIN summaries s ON p.post_id = s.post_id"
            query += " WHERE 1=1"
            params = []
        
        if category:
            query += " AND p.category = ?"
            params.append(category)
        
        query += " ORDER BY p.pub_date DESC LIMIT ? OFFSET ?"
        params.extend([count, offset])
        
        rows = conn.execute(query, params).fetchall()
        
        posts = []
        for row in rows:
            post = {
                'post_id': row['post_id'],
                'title': row['title'],
                'category': row['category'],
                'pub_date': row['pub_date'],
                'content_preview': row['content'][:300] + '...' if len(row['content']) > 300 else row['content']
            }
            if with_summary and 'summary' in row.keys():
                post['summary'] = row['summary']
                post['keywords'] = row['keywords']
            posts.append(post)
        
        conn.close()
        return {'success': True, 'count': len(posts), 'posts': posts}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}


def blog_get_post(post_id: str) -> Dict[str, Any]:
    """
    특정 글 전문 조회
    
    Args:
        post_id: 포스트 ID
    
    Returns:
        dict: {
            'success': bool,
            'post': {post_id, title, category, pub_date, content, summary?, keywords?}
        }
    """
    try:
        conn = get_db()
        
        row = conn.execute("""
            SELECT p.*, s.summary, s.keywords
            FROM posts p
            LEFT JOIN summaries s ON p.post_id = s.post_id
            WHERE p.post_id = ?
        """, (post_id,)).fetchone()
        
        conn.close()
        
        if not row:
            return {'success': False, 'error': f'Post not found: {post_id}'}
        
        post = {
            'post_id': row['post_id'],
            'title': row['title'],
            'category': row['category'],
            'pub_date': row['pub_date'],
            'content': row['content'],
            'char_count': row['char_count'],
            'link': f"{BLOG_URL}/{row['post_id']}"
        }
        
        if row['summary']:
            post['summary'] = row['summary']
            post['keywords'] = row['keywords']
        
        return {'success': True, 'post': post}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}


def blog_get_summaries(
    count: int = 20,
    offset: int = 0,
    category: Optional[str] = None
) -> Dict[str, Any]:
    """
    요약 목록 조회 (보고서 작성용)
    
    Args:
        count: 가져올 개수 (최대 100)
        offset: 시작 위치
        category: 카테고리 필터
    
    Returns:
        dict: {
            'success': bool,
            'summaries': list[{post_id, title, category, pub_date, summary, keywords}]
        }
    """
    try:
        conn = get_db()
        count = min(count, 100)
        
        query = """
            SELECT p.post_id, p.title, p.category, p.pub_date, s.summary, s.keywords
            FROM summaries s
            JOIN posts p ON s.post_id = p.post_id
            WHERE 1=1
        """
        params = []
        
        if category:
            query += " AND p.category = ?"
            params.append(category)
        
        query += " ORDER BY p.pub_date DESC LIMIT ? OFFSET ?"
        params.extend([count, offset])
        
        rows = conn.execute(query, params).fetchall()
        
        summaries = [{
            'post_id': row['post_id'],
            'title': row['title'],
            'category': row['category'],
            'pub_date': row['pub_date'],
            'summary': row['summary'],
            'keywords': row['keywords']
        } for row in rows]
        
        conn.close()
        return {'success': True, 'count': len(summaries), 'summaries': summaries}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}


def blog_save_summary(post_id: str, summary: str, keywords: str = "") -> Dict[str, Any]:
    """
    AI가 생성한 요약 저장
    
    Args:
        post_id: 포스트 ID
        summary: 요약 텍스트 (500자 권장)
        keywords: 키워드 (쉼표 구분)
    
    Returns:
        dict: {'success': bool}
    """
    try:
        conn = get_db()
        
        # 해당 포스트 존재 확인
        exists = conn.execute("SELECT 1 FROM posts WHERE post_id = ?", (post_id,)).fetchone()
        if not exists:
            conn.close()
            return {'success': False, 'error': f'Post not found: {post_id}'}
        
        conn.execute("""
            INSERT OR REPLACE INTO summaries (post_id, summary, keywords)
            VALUES (?, ?, ?)
        """, (post_id, summary, keywords))
        
        conn.commit()
        conn.close()
        
        return {'success': True, 'post_id': post_id, 'summary_length': len(summary)}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}


def blog_search(
    query: str,
    count: int = 20,
    search_in: str = "all"  # "title", "content", "all"
) -> Dict[str, Any]:
    """
    키워드로 글 검색
    
    Args:
        query: 검색어
        count: 결과 개수 (최대 50)
        search_in: 검색 범위 (title, content, all)
    
    Returns:
        dict: {
            'success': bool,
            'results': list[{post_id, title, category, pub_date, content_preview}]
        }
    """
    try:
        conn = get_db()
        count = min(count, 50)
        
        if search_in == "title":
            where = "p.title LIKE ?"
        elif search_in == "content":
            where = "p.content LIKE ?"
        else:
            where = "(p.title LIKE ? OR p.content LIKE ?)"
        
        like_query = f"%{query}%"
        
        if search_in == "all":
            params = [like_query, like_query, count]
        else:
            params = [like_query, count]
        
        sql = f"""
            SELECT p.post_id, p.title, p.category, p.pub_date, p.content, s.summary
            FROM posts p
            LEFT JOIN summaries s ON p.post_id = s.post_id
            WHERE {where}
            ORDER BY p.pub_date DESC
            LIMIT ?
        """
        
        rows = conn.execute(sql, params).fetchall()
        
        results = [{
            'post_id': row['post_id'],
            'title': row['title'],
            'category': row['category'],
            'pub_date': row['pub_date'],
            'content_preview': row['content'][:200] + '...' if len(row['content']) > 200 else row['content'],
            'has_summary': row['summary'] is not None
        } for row in rows]
        
        conn.close()
        return {'success': True, 'query': query, 'count': len(results), 'results': results}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}


def blog_stats() -> Dict[str, Any]:
    """
    DB 통계
    
    Returns:
        dict: {
            'total_posts': int,
            'total_summaries': int,
            'posts_without_summary': int,
            'categories': list[{name, count}],
            'date_range': {min, max}
        }
    """
    try:
        conn = get_db()
        
        total_posts = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        total_summaries = conn.execute("SELECT COUNT(*) FROM summaries").fetchone()[0]
        
        without_summary = conn.execute("""
            SELECT COUNT(*) FROM posts p
            LEFT JOIN summaries s ON p.post_id = s.post_id
            WHERE s.post_id IS NULL
        """).fetchone()[0]
        
        categories = conn.execute("""
            SELECT category, COUNT(*) as count
            FROM posts
            WHERE category != ''
            GROUP BY category
            ORDER BY count DESC
        """).fetchall()
        
        date_range = conn.execute("""
            SELECT MIN(pub_date) as min_date, MAX(pub_date) as max_date
            FROM posts
            WHERE pub_date IS NOT NULL
        """).fetchone()
        
        conn.close()
        
        return {
            'success': True,
            'total_posts': total_posts,
            'total_summaries': total_summaries,
            'posts_without_summary': without_summary,
            'summary_coverage': f"{(total_summaries/total_posts*100):.1f}%" if total_posts > 0 else "0%",
            'categories': [{'name': c['category'], 'count': c['count']} for c in categories],
            'date_range': {
                'min': date_range['min_date'],
                'max': date_range['max_date']
            }
        }
        
    except Exception as e:
        return {'success': False, 'error': str(e)}



def generate_latest_post_insight(ai_client_func) -> str:
    """
    가장 최근 글을 읽고 심층 분석 + 추천 자료 생성
    
    Args:
        ai_client_func: AI 클라이언트 생성 함수
    
    Returns:
        str: 최근 글 심층 분석 마크다운
    """
    try:
        conn = get_db()
        
        # 가장 최근 글 전문 가져오기
        row = conn.execute("""
            SELECT p.post_id, p.title, p.category, p.pub_date, p.content, s.summary, s.keywords
            FROM posts p
            LEFT JOIN summaries s ON p.post_id = s.post_id
            ORDER BY p.pub_date DESC
            LIMIT 1
        """).fetchone()
        
        conn.close()
        
        if not row:
            return ""
        
        post_title = row['title']
        post_date = row['pub_date']
        post_category = row['category'] or '미분류'
        post_content = row['content']
        post_keywords = row['keywords'] or ''
        post_link = f"{BLOG_URL}/{row['post_id']}"
        
        # AI에게 심층 분석 요청
        analysis_prompt = f"""다음은 블로그의 가장 최근 글입니다. 이 글을 읽고 분석해주세요.

## 요청사항

### 1. 이 글에서 더 생각해볼 점 (3가지)
- 글쓴이가 던진 질문이나 주장 중 더 깊이 탐구할 만한 것
- 글에서 암묵적으로 가정하고 있는 것들
- 다른 관점에서 바라볼 수 있는 지점

### 2. 관련해서 읽어볼 자료 (3가지)
- 이 글의 주제와 연결되는 책, 아티클, 영상 등
- 각 자료가 왜 이 글과 연결되는지 간단히 설명
- 가능하면 구체적인 제목과 저자 포함

### 3. 다음 글로 쓸만한 주제 (2가지)
- 이 글의 연장선에서 다룰 수 있는 주제
- 독자가 궁금해할 만한 후속 내용

톤: 친근하고 대화하듯, 구체적으로
분량: 800~1200자

=== 최근 글 ===
제목: {post_title}
날짜: {post_date}
카테고리: {post_category}
키워드: {post_keywords}

{post_content}
"""
        
        try:
            ai_result = ai_client_func()
            
            if ai_result[1] == "gemini":
                client, _, model_name = ai_result
                response = client.models.generate_content(
                    model=model_name,
                    contents=analysis_prompt
                )
                insight_content = response.text
            elif ai_result[1] == "openai":
                client, _, model_name = ai_result
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": analysis_prompt}]
                )
                insight_content = response.choices[0].message.content
            elif ai_result[1] == "anthropic":
                client, _, model_name = ai_result
                response = client.messages.create(
                    model=model_name,
                    max_tokens=2048,
                    messages=[{"role": "user", "content": analysis_prompt}]
                )
                insight_content = response.content[0].text
        
        except Exception as ai_err:
            insight_content = f"(AI 분석 실패: {str(ai_err)})"
        
        return f"""# 📝 가장 최근 글 심층 분석

## [{post_title}]({post_link})

**작성일**: {post_date} | **카테고리**: {post_category}

{insight_content}

---
"""
    
    except Exception as e:
        return f"(최근 글 분석 실패: {str(e)})"


def generate_monthly_summary(summaries: List[Dict]) -> str:
    """
    최근 3개월간 월별 관심사 흐름을 생성
    
    Args:
        summaries: 요약 데이터 리스트
    
    Returns:
        str: 월별 흐름 마크다운
    """
    from collections import Counter, defaultdict
    
    # 월별로 그룹화
    monthly = defaultdict(list)
    for s in summaries:
        if s.get('pub_date'):
            month = s['pub_date'][:7]  # "2025-12-22 06:23:12" -> "2025-12"
            monthly[month].append(s)
    
    # 최근 3개월만 선택
    sorted_months = sorted(monthly.keys(), reverse=True)[:3]
    
    if not sorted_months:
        return ""
    
    # 월 이름 매핑
    month_names = {
        '01': '1월', '02': '2월', '03': '3월', '04': '4월',
        '05': '5월', '06': '6월', '07': '7월', '08': '8월',
        '09': '9월', '10': '10월', '11': '11월', '12': '12월'
    }
    
    # 월별 테마 설명 생성
    monthly_sections = []
    
    for month in sorted_months:
        posts = monthly[month]
        year, mon = month.split('-')
        month_label = f"{year}년 {month_names[mon]}"
        
        # 키워드 집계
        all_keywords = []
        for p in posts:
            if p.get('keywords'):
                all_keywords.extend([k.strip() for k in p['keywords'].split(',')])
        
        top_kw = Counter(all_keywords).most_common(5)
        kw_str = ", ".join([k for k, _ in top_kw])
        
        # 카테고리별 글 수
        categories = Counter([p.get('category', '기타') for p in posts])
        main_category = categories.most_common(1)[0][0] if categories else "기타"
        
        # 글 목록 (최대 5개)
        post_list = "\n".join([f"  - {p['title']}" for p in posts[:5]])
        if len(posts) > 5:
            post_list += f"\n  - ...외 {len(posts) - 5}편"
        
        section = f"""### {month_label} ({len(posts)}편)

**핵심 키워드**: {kw_str}
**주요 카테고리**: {main_category}

{post_list}
"""
        monthly_sections.append(section)
    
    # 흐름 요약
    flow_summary = ""
    if len(sorted_months) >= 2:
        oldest = sorted_months[-1]
        newest = sorted_months[0]
        oldest_kw = [k.strip() for p in monthly[oldest] for k in (p.get('keywords') or '').split(',') if k.strip()]
        newest_kw = [k.strip() for p in monthly[newest] for k in (p.get('keywords') or '').split(',') if k.strip()]
        
        oldest_top = Counter(oldest_kw).most_common(2)
        newest_top = Counter(newest_kw).most_common(2)
        
        oldest_str = ", ".join([k for k, _ in oldest_top]) if oldest_top else "다양한 주제"
        newest_str = ", ".join([k for k, _ in newest_top]) if newest_top else "다양한 주제"
        
        flow_summary = f"""
### 📈 관심사 변화

**{oldest[:7]}**: {oldest_str}
→ **{newest[:7]}**: {newest_str}
"""
    
    return f"""# 📅 월별 관심사 흐름

최근 3개월간 블로그 글의 흐름입니다.

{"".join(monthly_sections)}
{flow_summary}
---
"""


def blog_insight_report(
    count: int = 50,
    category: Optional[str] = None
) -> Dict[str, Any]:
    """
    블로그 인사이트 통합 보고서 생성
    
    포함 내용:
    1. 블로그 내용 분석 (간단히)
    2. 학습 방향 제안
    3. 월별 관심사 흐름 (최근 3개월)
    4. 블로그 키워드 기반 뉴스 (Google News)
    5. 블로그 키워드 기반 자료 (Hacker News, Medium, Books)
    
    Args:
        count: 분석할 글 수 (최대 100)
        category: 카테고리 필터
    
    Returns:
        dict: {
            'success': bool,
            'report_path': str,
            'message': str
        }
    """
    from tool_newspaper import generate_section as generate_news_section
    from tool_magazine import (
        generate_section_hackernews,
        generate_section_medium,
        generate_section_books
    )
    from collections import Counter
    
    try:
        print("\n" + "="*60)
        print("📊 블로그 인사이트 보고서 생성 시작")
        print("="*60 + "\n")
        
        # 1. 요약 데이터 가져오기
        print("[1/5] 블로그 요약 데이터 수집 중...")
        summaries_result = blog_get_summaries(count=min(count, 100), category=category)
        if not summaries_result.get('success'):
            return {'success': False, 'error': '요약 데이터를 가져올 수 없습니다.'}
        
        summaries = summaries_result.get('summaries', [])
        if not summaries:
            return {'success': False, 'error': '분석할 요약이 없습니다.'}
        
        print(f"      ✓ {len(summaries)}개 요약 수집 완료\n")
        
        # 2. AI로 블로그 관심 주제 추출
        print("[2/5] 블로그 관심 주제 추출 중...")
        summaries_text = ""
        for s in summaries[:30]:
            summaries_text += f"""
---
제목: {s['title']}
카테고리: {s['category']}
키워드: {s['keywords']}
요약: {s['summary']}
"""
        
        # AI에게 관심 주제 추출 요청
        topic_prompt = f"""다음은 한 블로그의 최근 글들 요약입니다.

이런 글들을 쓴 사람이 관심있어할 뉴스 주제 5가지는?

구체적이고 검색 가능한 주제로 답해주세요.
예시: "AI 에이전트" (O), "인공지능" (X, 너무 넓음)

출력 형식 (JSON만, 설명 없이):
["주제1", "주제2", "주제3", "주제4", "주제5"]

=== 블로그 요약 ===
{summaries_text}
"""
        
        try:
            ai_result = get_report_ai_client()
            
            if ai_result[1] == "gemini":
                client, _, model_name = ai_result
                response = client.models.generate_content(
                    model=model_name,
                    contents=topic_prompt
                )
                topics_json = response.text.strip()
            elif ai_result[1] == "openai":
                client, _, model_name = ai_result
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": topic_prompt}]
                )
                topics_json = response.choices[0].message.content.strip()
            elif ai_result[1] == "anthropic":
                client, _, model_name = ai_result
                response = client.messages.create(
                    model=model_name,
                    max_tokens=1024,
                    messages=[{"role": "user", "content": topic_prompt}]
                )
                topics_json = response.content[0].text.strip()
            
            # JSON 파싱
            import re as regex
            json_match = regex.search(r'\[.*?\]', topics_json, regex.DOTALL)
            if json_match:
                news_keywords = json.loads(json_match.group())
                top_keywords = news_keywords  # 호환성 유지
            else:
                # 파싱 실패시 빈도수 기반 폴백
                all_keywords = []
                for s in summaries:
                    if s.get('keywords'):
                        keywords = [k.strip() for k in s['keywords'].split(',')]
                        all_keywords.extend(keywords)
                keyword_counts = Counter(all_keywords)
                top_keywords = [kw for kw, _ in keyword_counts.most_common(10)]
                news_keywords = top_keywords[:5]
                
        except Exception as e:
            # AI 실패시 빈도수 기반 폴백
            print(f"      ⚠️ AI 추출 실패, 빈도수 방식 사용: {e}")
            all_keywords = []
            for s in summaries:
                if s.get('keywords'):
                    keywords = [k.strip() for k in s['keywords'].split(',')]
                    all_keywords.extend(keywords)
            keyword_counts = Counter(all_keywords)
            top_keywords = [kw for kw, _ in keyword_counts.most_common(10)]
            news_keywords = top_keywords[:5]
        
        print(f"      ✓ 관심 주제: {', '.join(news_keywords)}\n")
        
        # 3. AI로 분석 + 학습 방향 생성
        print("[3/5] AI 분석 중...")
        # summaries_text에 날짜 정보 추가 (2단계에서 생성한 것 재사용)
        summaries_text_with_date = ""
        for s in summaries[:30]:
            summaries_text_with_date += f"""
---
제목: {s['title']}
날짜: {s['pub_date']}
카테고리: {s['category']}
키워드: {s['keywords']}
요약: {s['summary']}
"""
        
        analysis_prompt = f"""다음은 블로그 글쓴이가 최근 작성한 글들의 요약입니다.

이 글들을 분석하여 다음 두 가지를 작성해주세요:

## 1. 블로그 내용 분석 (간략히)
- 주요 관심 주제 3~5개
- 글쓴이의 핵심 문제의식
- 최근 글의 흐름

## 2. 학습 방향 제안
- 현재 관심사와 연결되는 새로운 학습 영역 3~5개
- 각 영역별로:
  - 왜 이 영역이 필요한지 (1~2문장)
  - **바로 시도해볼 수 있는 작은 프로젝트** 1개 (구체적으로)
  - 핵심 추천 자료 1개만 (가장 좋은 책 또는 강의 하나)

분량: 1500~2000자
톤: 구체적이고 실용적인 조언
중요: 추천 자료는 각 영역당 1개만! 여러 개 나열하지 말 것.

=== 블로그 요약 데이터 ===
{summaries_text_with_date}
"""
        
        try:
            ai_result = get_report_ai_client()
            
            if ai_result[1] == "gemini":
                client, _, model_name = ai_result
                response = client.models.generate_content(
                    model=model_name,
                    contents=analysis_prompt
                )
                analysis_content = response.text
            elif ai_result[1] == "openai":
                client, _, model_name = ai_result
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": analysis_prompt}]
                )
                analysis_content = response.choices[0].message.content
            elif ai_result[1] == "anthropic":
                client, _, model_name = ai_result
                response = client.messages.create(
                    model=model_name,
                    max_tokens=4096,
                    messages=[{"role": "user", "content": analysis_prompt}]
                )
                analysis_content = response.content[0].text
                
            print("      ✓ AI 분석 완료\n")
                
        except Exception as ai_err:
            analysis_content = f"(AI 분석 실패: {str(ai_err)})"
            print(f"      ⚠️ AI 분석 실패: {ai_err}\n")
        
        # 4. 키워드 기반 뉴스 섹션 생성
        print("[4/5] 키워드 기반 뉴스 수집 중...")
        news_sections = ""
        for keyword in news_keywords[:3]:  # 상위 3개 키워드만
            section = generate_news_section(keyword, news_count=3)
            if section.get('success'):
                news_sections += section['markdown']
        print("      ✓ 뉴스 수집 완료\n")
        
        # 5. 키워드 기반 자료 섹션 생성
        print("[5/5] 관련 자료 수집 중...")
        resource_sections = ""
        
        # Hacker News
        hn_section = generate_section_hackernews(count=5)
        if hn_section.get('success'):
            resource_sections += hn_section['markdown']
        
        # Medium (상위 2개 키워드)
        for keyword in news_keywords[:2]:
            medium_section = generate_section_medium(topic=keyword, count=2)
            if medium_section.get('success'):
                resource_sections += medium_section['markdown']
        
        # Books (상위 2개 키워드)
        for keyword in news_keywords[:2]:
            books_section = generate_section_books(topic=keyword, count=2)
            if books_section.get('success'):
                resource_sections += books_section['markdown']
        
        # 6. 맞춤형 뉴스 섹션 생성 (나의 개인정보 기반)
        print("[6/6] 맞춤형 뉴스 수집 중...")
        personalized_section = ""
        
        profile_path = os.path.join(BASE_DIR, "data", "my_profile.txt")
        if os.path.exists(profile_path):
            try:
                with open(profile_path, 'r', encoding='utf-8') as f:
                    profile_content = f.read().strip()
                
                if profile_content:
                    # AI로 개인정보에서 오늘 관심있을 주제 추출
                    keyword_prompt = f"""다음은 한 사람의 개인정보입니다.

이런 사람이 오늘 아침에 뉴스에서 확인하고 싶을 주제 5가지는?

- 투자 종목 관련 (주가, 실적, 전망)
- 가족이 있는 지역/분야 관련
- 거주 지역 소식
- 일상 관심사 (취미, 라이프스타일)

주의: 직업/전문 분야(물리학, AI 등)는 제외 (블로그 키워드로 이미 커버됨)

출력 형식 (JSON만, 설명 없이):
["주제1", "주제2", "주제3", "주제4", "주제5"]

=== 개인정보 ===
{profile_content}
"""
                    
                    try:
                        ai_result = get_report_ai_client()
                        
                        if ai_result[1] == "gemini":
                            client, _, model_name = ai_result
                            response = client.models.generate_content(
                                model=model_name,
                                contents=keyword_prompt
                            )
                            keywords_json = response.text.strip()
                        elif ai_result[1] == "openai":
                            client, _, model_name = ai_result
                            response = client.chat.completions.create(
                                model=model_name,
                                messages=[{"role": "user", "content": keyword_prompt}]
                            )
                            keywords_json = response.choices[0].message.content.strip()
                        elif ai_result[1] == "anthropic":
                            client, _, model_name = ai_result
                            response = client.messages.create(
                                model=model_name,
                                max_tokens=1024,
                                messages=[{"role": "user", "content": keyword_prompt}]
                            )
                            keywords_json = response.content[0].text.strip()
                        
                        # JSON 파싱
                        import re as regex
                        json_match = regex.search(r'\[.*?\]', keywords_json, regex.DOTALL)
                        if json_match:
                            personal_keywords = json.loads(json_match.group())
                            print(f"      ✓ 맞춤형 키워드: {', '.join(personal_keywords)}")
                            
                            # 맞춤형 뉴스 수집
                            personal_news_sections = ""
                            for keyword in personal_keywords[:8]:  # 상위 8개 키워드 (2배)
                                section = generate_news_section(keyword, news_count=6)  # 키워드당 6개 (2배)
                                if section.get('success'):
                                    personal_news_sections += section['markdown']
                            
                            # 맞춤형 자료 수집
                            personal_resource_sections = ""
                            
                            # Medium (상위 4개 키워드, 키워드당 4개)
                            for keyword in personal_keywords[:4]:
                                medium_section = generate_section_medium(topic=keyword, count=4)
                                if medium_section.get('success'):
                                    personal_resource_sections += medium_section['markdown']
                            
                            # Books (상위 4개 키워드, 키워드당 4개)
                            for keyword in personal_keywords[:4]:
                                books_section = generate_section_books(topic=keyword, count=4)
                                if books_section.get('success'):
                                    personal_resource_sections += books_section['markdown']
                            
                            personalized_section = f"""
---

# 🎯 나를 위한 맞춤형 뉴스

**나의 개인정보**에서 추출한 키워드: `{', '.join(personal_keywords)}`

{personal_news_sections}

## 📚 맞춤형 자료

{personal_resource_sections}
"""
                            print("      ✓ 맞춤형 뉴스 수집 완료\n")
                        else:
                            print("      ⚠️ 키워드 추출 실패 (JSON 파싱 오류)\n")
                            
                    except Exception as ai_err:
                        import traceback
                        print(f"      ⚠️ AI 키워드 추출 실패: {ai_err}")
                        print(f"      상세 에러: {traceback.format_exc()}\n")
                else:
                    print("      ⚠️ 개인정보 파일이 비어있습니다\n")
                    
            except Exception as profile_err:
                print(f"      ⚠️ 개인정보 파일 읽기 실패: {profile_err}\n")
        else:
            print("      ⚠️ 개인정보 파일이 없습니다 (data/my_profile.txt)\n")
        
        # 7. 최근 글 심층 분석
        print("📝 최근 글 심층 분석 중...")
        latest_post_insight = generate_latest_post_insight(get_report_ai_client)
        print("      ✓ 최근 글 분석 완료\n")
        
        # 8. 월별 관심사 흐름 생성
        print("📅 월별 관심사 흐름 생성 중...")
        monthly_summary = generate_monthly_summary(summaries)
        print("      ✓ 월별 흐름 생성 완료\n")
        
        # 9. 보고서 조립
        print("📝 보고서 조립 중...")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        today_str = datetime.now().strftime("%Y년 %m월 %d일")
        
        report_content = f"""# 블로그 인사이트 보고서

**분석 대상**: {BLOG_URL}
**분석 글 수**: {len(summaries)}개
**생성 일시**: {today_str}
**추출 키워드**: {', '.join(news_keywords)}

---

{latest_post_insight}

{analysis_content}

---

{monthly_summary}

# 📰 관련 뉴스

키워드 `{', '.join(news_keywords[:3])}`로 검색한 최신 뉴스입니다.

{news_sections}

---

# 📚 관련 자료

키워드와 관련된 해외 자료들입니다.

{resource_sections}
{personalized_section}

---

## 📊 보고서 정보

- **분석 글 수**: {len(summaries)}개
- **추출 키워드**: {', '.join(top_keywords)}
- **뉴스 키워드**: {', '.join(news_keywords[:3])}
- **생성 시각**: {datetime.now().strftime('%Y년 %m월 %d일 %H시 %M분')}
"""
        
        # HTML 변환 및 저장
        print("🌐 HTML 변환 중...")
        os.makedirs(OUTPUTS_DIR, exist_ok=True)

        html_content = markdown_to_html(report_content, "블로그 인사이트 보고서", today_str, doc_type="report")
        html_filename = f"blog_insight_report_{timestamp}.html"
        html_filepath = os.path.join(OUTPUTS_DIR, html_filename)

        with open(html_filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"💾 HTML 저장: {html_filename}")
        print("\n" + "="*60)
        print("✅ 블로그 인사이트 보고서 생성 완료!")
        print("="*60 + "\n")

        return {
            'success': True,
            'report_path': html_filepath,
            'analyzed_count': len(summaries),
            'keywords': news_keywords,
            'message': f'인사이트 보고서가 생성되었습니다: {html_filepath}'
        }
        
    except Exception as e:
        return {'success': False, 'error': str(e)}


# =============================================================================
# IndieBiz 도구 정의 (tools.py에서 사용)
# 에이전트가 사용할 도구만 (blog_check_new_posts, blog_save_summary는 프로그램 스케줄러가 처리)
# =============================================================================

BLOG_INSIGHT_TOOLS = [
    {
        "name": "blog_get_posts",
        "description": "블로그 글 목록을 조회합니다. 요약 포함 여부, 요약 없는 글만 필터링 등 옵션 제공.",
        "parameters": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "가져올 글 수 (기본 20, 최대 100)"},
                "offset": {"type": "integer", "description": "시작 위치"},
                "category": {"type": "string", "description": "카테고리 필터"},
                "with_summary": {"type": "boolean", "description": "요약 포함 여부"},
                "only_without_summary": {"type": "boolean", "description": "요약 없는 글만 조회"}
            },
            "required": []
        },
        "function": blog_get_posts
    },
    {
        "name": "blog_get_post",
        "description": "특정 블로그 글의 전체 내용을 조회합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "post_id": {"type": "string", "description": "포스트 ID"}
            },
            "required": ["post_id"]
        },
        "function": blog_get_post
    },
    {
        "name": "blog_get_summaries",
        "description": "저장된 요약 목록을 조회합니다. 보고서 작성시 활용.",
        "parameters": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "가져올 개수 (기본 20, 최대 100)"},
                "offset": {"type": "integer", "description": "시작 위치"},
                "category": {"type": "string", "description": "카테고리 필터"}
            },
            "required": []
        },
        "function": blog_get_summaries
    },
    {
        "name": "blog_search",
        "description": "키워드로 블로그 글을 검색합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "검색어"},
                "count": {"type": "integer", "description": "결과 개수 (기본 20, 최대 50)"},
                "search_in": {"type": "string", "enum": ["title", "content", "all"], "description": "검색 범위"}
            },
            "required": ["query"]
        },
        "function": blog_search
    },
    {
        "name": "blog_stats",
        "description": "블로그 DB 통계를 조회합니다. 전체 글 수, 요약 수, 카테고리별 분포 등.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        },
        "function": blog_stats
    },
    {
        "name": "blog_insight_report",
        "description": "블로그 인사이트 통합 보고서를 생성합니다. 블로그 분석 + 학습 방향 제안 + 키워드 기반 신문 + 키워드 기반 잡지가 포함된 종합 보고서입니다.",
        "uses_ai": True,
        "ai_config_key": "blog_insight",
        "parameters": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "분석할 글 수 (기본 50, 최대 100)"},
                "category": {"type": "string", "description": "카테고리 필터 (선택)"}
            },
            "required": []
        },
        "function": blog_insight_report
    }
]


# 테스트용
if __name__ == "__main__":
    print("=== Blog Insight Tool Test ===\n")
    
    # 새 글 확인
    print("1. Checking new posts...")
    result = blog_check_new_posts()
    print(f"   New: {result.get('new_count', 0)}, Total: {result.get('total_posts', 0)}")
    
    # 통계
    print("\n2. Stats...")
    stats = blog_stats()
    print(f"   Posts: {stats.get('total_posts')}")
    print(f"   Summaries: {stats.get('total_summaries')}")
    print(f"   Without summary: {stats.get('posts_without_summary')}")
    
    # 글 목록
    print("\n3. Recent posts...")
    posts = blog_get_posts(count=3)
    for p in posts.get('posts', []):
        print(f"   - {p['title'][:40]}...")
    
    print("\nDone!")
