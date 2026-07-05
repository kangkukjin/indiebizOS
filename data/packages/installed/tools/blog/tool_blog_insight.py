"""
Blog Insight Tool for IndieBiz
==============================
블로그 글을 수집하고 AI 요약을 저장하여 에이전트가 보고서를 작성할 수 있게 하는 도구

설계 원칙:
- 기초 도구만 제공, AI 에이전트가 조합해서 사용
- 500자 요약은 별도 테이블에 저장
- 보고서 생성은 내부 AI가 처리 (토큰 절약)
"""

import os
import sys
import json
import sqlite3
import requests
import re
import feedparser
from datetime import datetime
from typing import Optional, List, Dict, Any
from bs4 import BeautifulSoup

# common 유틸리티 사용
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

from common.html_utils import clean_html

# 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "blog_insight.db")

# 시스템 AI 설정 경로
BACKEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "..", "..", "backend"))
SYSTEM_AI_CONFIG_PATH = os.path.join(BACKEND_DIR, "data", "system_ai_config.json")

BLOG_URL = "https://irepublic.tistory.com"
RSS_URL = f"{BLOG_URL}/rss"
RSS_SIZE = 50


def markdown_to_html(content: str, title: str, date_str: str, doc_type: str = "report") -> str:
    """마크다운을 HTML로 변환"""
    try:
        import markdown
        html_body = markdown.markdown(content, extensions=['tables', 'fenced_code'])
    except ImportError:
        html_body = f"<pre style='white-space: pre-wrap;'>{content}</pre>"

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;700&display=swap');
        body {{ font-family: 'Noto Sans KR', sans-serif; max-width: 900px; margin: 0 auto; padding: 40px 20px; line-height: 1.8; color: #333; background-color: #f9f9f9; }}
        .content-card {{ background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); }}
        h1 {{ color: #1a2a6c; border-bottom: 3px solid #1a2a6c; padding-bottom: 10px; font-size: 2.5em; }}
        h2 {{ color: #1a2a6c; margin-top: 1.5em; border-left: 5px solid #1a2a6c; padding-left: 15px; }}
        h3 {{ color: #2c3e50; margin-top: 1.2em; }}
        a {{ color: #3498db; text-decoration: none; border-bottom: 1px solid #3498db; }}
        a:hover {{ color: #2980b9; border-bottom-width: 2px; }}
        pre {{ background: #2c3e50; color: #ecf0f1; padding: 15px; border-radius: 8px; overflow-x: auto; }}
        code {{ font-family: 'Courier New', Courier, monospace; background: #f0f0f0; padding: 2px 5px; border-radius: 3px; }}
        blockquote {{ margin: 20px 0; padding: 10px 20px; border-left: 5px solid #ddd; font-style: italic; color: #666; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        .meta {{ color: #7f8c8d; font-size: 0.9em; margin-bottom: 30px; }}
        hr {{ border: 0; border-top: 1px solid #eee; margin: 40px 0; }}
        @media print {{ body {{ background: white; }} .content-card {{ box-shadow: none; padding: 0; }} }}
    </style>
</head>
<body>
    <div class="content-card">
        <h1>{title}</h1>
        <p class="meta">발행일: {date_str} | 출처: {BLOG_URL}</p>
        {html_body}
    </div>
</body>
</html>"""


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


def get_report_ai_client():
    """보고서 생성용 AI 클라이언트 반환"""
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


def get_db() -> sqlite3.Connection:
    """DB 연결 및 테이블 생성"""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

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

    # FTS5 전문 검색 가상 테이블 (BM25 키워드 검색용)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS posts_fts USING fts5(
            title, content,
            content='posts', content_rowid='id'
        )
    """)

    # FTS5 자동 동기화 트리거
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS posts_fts_insert
        AFTER INSERT ON posts BEGIN
            INSERT INTO posts_fts(rowid, title, content)
            VALUES (new.id, new.title, new.content);
        END
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS posts_fts_delete
        AFTER DELETE ON posts BEGIN
            INSERT INTO posts_fts(posts_fts, rowid, title, content)
            VALUES ('delete', old.id, old.title, old.content);
        END
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS posts_fts_update
        AFTER UPDATE ON posts BEGIN
            INSERT INTO posts_fts(posts_fts, rowid, title, content)
            VALUES ('delete', old.id, old.title, old.content);
            INSERT INTO posts_fts(rowid, title, content)
            VALUES (new.id, new.title, new.content);
        END
    """)

    # RAG 검색 인덱스 상태 추적 테이블
    conn.execute("""
        CREATE TABLE IF NOT EXISTS search_index_status (
            post_id TEXT PRIMARY KEY,
            indexed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            embedding_version TEXT DEFAULT 'v1',
            FOREIGN KEY (post_id) REFERENCES posts(post_id)
        )
    """)

    conn.commit()

    # 기존 포스트를 FTS5로 마이그레이션 (최초 1회)
    _migrate_fts5_if_needed(conn)

    return conn


def _migrate_fts5_if_needed(conn: sqlite3.Connection):
    """기존 포스트를 FTS5 인덱스로 마이그레이션 (최초 1회)"""
    try:
        fts_count = conn.execute("SELECT COUNT(*) FROM posts_fts").fetchone()[0]
        posts_count = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        if fts_count >= posts_count:
            return  # 이미 동기화됨
        print(f"[Blog] FTS5 인덱스 마이그레이션 중... ({posts_count}개 포스트)")
        conn.execute("INSERT INTO posts_fts(posts_fts) VALUES('rebuild')")
        conn.commit()
        print(f"[Blog] FTS5 마이그레이션 완료")
    except Exception as e:
        print(f"[Blog] FTS5 마이그레이션 스킵: {e}")


def parse_rss_date(rss_date: str) -> Optional[str]:
    try:
        dt = datetime.strptime(rss_date.strip(), "%a, %d %b %Y %H:%M:%S %z")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return None


# strip_html은 common.html_utils.clean_html로 대체
strip_html = clean_html


def fetch_rss_feed() -> List[Dict[str, Any]]:
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
    try:
        conn = get_db()
        existing = set(row[0] for row in conn.execute("SELECT post_id FROM posts").fetchall())
        rss_posts = fetch_rss_feed()
        
        new_posts = []
        for post in rss_posts:
            if post['post_id'] not in existing:
                pub_date_db = parse_rss_date(post['pub_date'])
                conn.execute("""
                    INSERT OR IGNORE INTO posts (post_id, title, category, pub_date, content, char_count)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (post['post_id'], post['title'], post['category'], pub_date_db, post['content'], len(post['content'])))
                new_posts.append({'post_id': post['post_id'], 'title': post['title'], 'pub_date': pub_date_db})
                # canonical store(vault)에 .md 기록 — A안: vault가 진실 소스
                try:
                    from tool_blog_vault import write_post_md
                    write_post_md({
                        'post_id': post['post_id'], 'title': post['title'],
                        'category': post['category'], 'pub_date': pub_date_db,
                        'content': post['content'],
                    })
                except Exception as e:
                    print(f"[Blog] vault .md 기록 실패({post['post_id']}): {e}")

        conn.commit()
        total = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        conn.close()

        # 새 포스트의 벡터 임베딩 생성 (선택적, 실패해도 무시)
        if new_posts:
            try:
                from tool_blog_rag import BlogHybridSearch
                engine = BlogHybridSearch()
                indexed = engine.index_new_posts()
                if indexed > 0:
                    print(f"[Blog] {indexed}개 새 포스트 RAG 인덱싱 완료")
            except Exception as e:
                print(f"[Blog] RAG 인덱싱 스킵: {e}")

        return {'success': True, 'new_count': len(new_posts), 'new_posts': new_posts, 'total_posts': total}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def blog_get_posts(count: int = 20, offset: int = 0, category: Optional[str] = None, with_summary: bool = False, only_without_summary: bool = False) -> Dict[str, Any]:
    try:
        conn = get_db()
        count = min(count, 100)
        
        if only_without_summary:
            query = "SELECT p.* FROM posts p LEFT JOIN summaries s ON p.post_id = s.post_id WHERE s.post_id IS NULL"
            params = []
        else:
            query = "SELECT p.* " + (", s.summary, s.keywords" if with_summary else "") + " FROM posts p " + ("LEFT JOIN summaries s ON p.post_id = s.post_id" if with_summary else "") + " WHERE 1=1"
            params = []
        
        if category:
            query += " AND p.category = ?"
            params.append(category)
        
        query += " ORDER BY p.pub_date DESC LIMIT ? OFFSET ?"
        params.extend([count, offset])
        
        rows = conn.execute(query, params).fetchall()
        posts = []
        for row in rows:
            post = {'post_id': row['post_id'], 'title': row['title'], 'category': row['category'], 'pub_date': row['pub_date'], 'content_preview': row['content'][:300] + '...'}
            if with_summary and 'summary' in row.keys():
                post['summary'] = row['summary']
                post['keywords'] = row['keywords']
            posts.append(post)
        
        conn.close()
        return {'success': True, 'count': len(posts), 'posts': posts}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def blog_get_post(post_id: str) -> Dict[str, Any]:
    try:
        conn = get_db()
        row = conn.execute("SELECT p.*, s.summary, s.keywords FROM posts p LEFT JOIN summaries s ON p.post_id = s.post_id WHERE p.post_id = ?", (post_id,)).fetchone()
        conn.close()
        if not row: return {'success': False, 'error': f'Post not found: {post_id}'}
        return {'success': True, 'post': {'post_id': row['post_id'], 'title': row['title'], 'category': row['category'], 'pub_date': row['pub_date'], 'content': row['content'], 'summary': row['summary'], 'keywords': row['keywords'], 'link': f"{BLOG_URL}/{row['post_id']}"}}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def blog_get_summaries(count: int = 20, offset: int = 0, category: Optional[str] = None) -> Dict[str, Any]:
    try:
        conn = get_db()
        count = min(count, 100)
        query = "SELECT p.post_id, p.title, p.category, p.pub_date, s.summary, s.keywords FROM summaries s JOIN posts p ON s.post_id = p.post_id WHERE 1=1"
        params = []
        if category: query += " AND p.category = ?"; params.append(category)
        query += " ORDER BY p.pub_date DESC LIMIT ? OFFSET ?"
        params.extend([count, offset])
        rows = conn.execute(query, params).fetchall()
        summaries = [dict(row) for row in rows]
        conn.close()
        return {'success': True, 'count': len(summaries), 'summaries': summaries}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def blog_save_summary(post_id: str, summary: str, keywords: str = "") -> Dict[str, Any]:
    try:
        conn = get_db()
        conn.execute("INSERT OR REPLACE INTO summaries (post_id, summary, keywords) VALUES (?, ?, ?)", (post_id, summary, keywords))
        conn.commit()
        conn.close()
        # canonical store(vault)의 .md 요약/키워드도 갱신 — A안
        try:
            from tool_blog_vault import update_post_summary_md
            update_post_summary_md(post_id, summary, keywords)
        except Exception as e:
            print(f"[Blog] vault 요약 갱신 실패({post_id}): {e}")
        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def blog_search(query: str, count: int = 20, search_in: str = "all") -> Dict[str, Any]:
    try:
        conn = get_db()
        count = min(count, 50)
        where = "p.title LIKE ?" if search_in == "title" else "p.content LIKE ?" if search_in == "content" else "(p.title LIKE ? OR p.content LIKE ?)"
        like_query = f"%{query}%"
        params = [like_query, like_query, count] if search_in == "all" else [like_query, count]
        sql = f"SELECT p.*, s.summary FROM posts p LEFT JOIN summaries s ON p.post_id = s.post_id WHERE {where} ORDER BY p.pub_date DESC LIMIT ?"
        rows = conn.execute(sql, params).fetchall()
        results = [{'post_id': row['post_id'], 'title': row['title'], 'category': row['category'], 'pub_date': row['pub_date'], 'content_preview': row['content'][:200] + '...', 'has_summary': row['summary'] is not None} for row in rows]
        conn.close()
        return {'success': True, 'results': results}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def blog_stats() -> Dict[str, Any]:
    try:
        conn = get_db()
        total_posts = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        total_summaries = conn.execute("SELECT COUNT(*) FROM summaries").fetchone()[0]
        without_summary = conn.execute("SELECT COUNT(*) FROM posts p LEFT JOIN summaries s ON p.post_id = s.post_id WHERE s.post_id IS NULL").fetchone()[0]
        conn.close()
        return {'success': True, 'total_posts': total_posts, 'total_summaries': total_summaries, 'posts_without_summary': without_summary}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def _search_gnews(keyword: str, max_results: int = 5) -> List[Dict]:
    results = []
    try:
        from ddgs import DDGS  # 표준 검색 패키지(구 duckduckgo_search 대체, core 번들)
        for r in DDGS().news(keyword, max_results=max_results):
            results.append({
                "title": r.get('title', ''),
                "snippet": r.get('body') or r.get('excerpt', ''),
                "link": r.get('url') or r.get('href', ''),
                "source": r.get('source', ''),
            })
    except Exception:
        pass
    return results


def _fetch_rss(url: str, limit: int = 5) -> List[Dict]:
    try:
        feed = feedparser.parse(url)
        return [{"title": e.title, "link": e.link, "snippet": strip_html(e.summary)[:200]} for e in feed.entries[:limit]]
    except: return []


def blog_insight_report(count: int = 50, category: Optional[str] = None, project_path: str = ".") -> Dict[str, Any]:
    """블로그 인사이트 통합 보고서 생성 (동기화 포함)"""
    try:
        # 0. 데이터 동기화
        print("🔄 블로그 최신 데이터 동기화 중...")
        blog_check_new_posts()
        
        # 1. 요약 데이터 가져오기
        summaries_result = blog_get_summaries(count=count, category=category)
        summaries = summaries_result.get('summaries', [])
        
        # 요약이 부족하면 미요약 글에 대해 즉석 요약 생성 (최대 5개)
        if len(summaries) < 10:
            print("📝 미요약 글 요약 생성 중...")
            conn = get_db()
            missing = conn.execute("SELECT p.post_id, p.title, p.content FROM posts p LEFT JOIN summaries s ON p.post_id = s.post_id WHERE s.post_id IS NULL ORDER BY p.pub_date DESC LIMIT 5").fetchall()
            if missing:
                client, provider, model = get_report_ai_client()
                for m in missing:
                    prompt = f"다음 블로그 글을 500자 내외로 요약하고 핵심 키워드 3개를 추출해줘. 형식: 요약내용 | 키워드1,키워드2,키워드3\n\n제목: {m['title']}\n내용: {m['content'][:2000]}"
                    try:
                        if provider == "gemini": res = client.models.generate_content(model=model, contents=prompt).text
                        elif provider == "openai": res = client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}]).choices[0].message.content
                        if "|" in res:
                            summ, kws = res.split("|", 1)
                            blog_save_summary(m['post_id'], summ.strip(), kws.strip())
                    except: pass
                # 다시 불러오기
                summaries = blog_get_summaries(count=count, category=category).get('summaries', [])
        
        if not summaries: return {'success': False, 'error': '분석할 데이터가 없습니다.'}

        # 2. AI 분석 및 키워드 추출
        print("🧠 AI 인사이트 분석 중...")
        client, provider, model = get_report_ai_client()
        context = "\n".join([f"- {s['title']} ({s['category']}): {s['summary'][:100]}..." for s in summaries[:20]])
        prompt = f"다음 블로그 요약들을 분석하여 1.최근 관심사 분석, 2.학습 방향 제안(3가지 구체적 영역과 프로젝트), 3.검색할 뉴스 키워드 3개를 마크다운으로 작성해줘.\n\n{context}"
        
        if provider == "gemini": analysis = client.models.generate_content(model=model, contents=prompt).text
        elif provider == "openai": analysis = client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}]).choices[0].message.content
        
        # 뉴스 키워드 파싱 (간단히)
        news_keywords = ["AI", "기술", "비즈니스"]
        for line in analysis.split("\n"):
            if "뉴스 키워드" in line or "키워드:" in line:
                found = re.findall(r'["\']([^"\']+)["\']|`([^`]+)`', line)
                if found: news_keywords = [f[0] or f[1] for f in found]
        
        # 3. 추가 정보 수집
        print("🌐 관련 뉴스 및 자료 수집 중...")
        news_section = "\n## 📰 관련 뉴스\n"
        for kw in news_keywords[:3]:
            for art in _search_gnews(kw, 3):
                news_section += f"- [{art['title']}]({art['link']}) ({art['source']})\n"
        
        # 4. 보고서 조립 및 저장
        report_md = f"# 📊 블로그 인사이트 보고서\n\n{analysis}\n\n{news_section}\n\n---\n*생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
        html_content = markdown_to_html(report_md, "블로그 인사이트 보고서", datetime.now().strftime("%Y-%m-%d"))
        
        out_dir = os.path.join(project_path, "outputs")
        os.makedirs(out_dir, exist_ok=True)
        filename = f"blog_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        filepath = os.path.join(out_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return {'success': True, 'report_path': filepath, 'message': f'보고서 생성 완료: {filepath}'}
    except Exception as e:
        return {'success': False, 'error': str(e)}
