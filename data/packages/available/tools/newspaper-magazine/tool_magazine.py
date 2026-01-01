"""
tool_magazine.py - 통합 잡지 생성 도구

다양한 정보 소스에서 콘텐츠를 수집하여 잡지 형식으로 조립합니다.

지원 소스:
- Hacker News: 기술 트렌드
- Reddit: 커뮤니티 토론
- Medium: 에세이/사색
- Google Books: 책 추천

특징:
- 하나의 도구로 모든 소스 관리
- newspaper.py와 동일한 구조
- Markdown + HTML 자동 생성
- 스탠다드 도구 (토큰 절약)
"""

import os
import json
import re
import requests
from datetime import datetime
from html import unescape
from tool_utils import markdown_to_html, OUTPUTS_DIR


# 잡지 프리셋 정의
MAGAZINE_PRESETS = {
    "주간": {
        "title": "IndieBiz 주간 매거진",
        "sections": [
            {"source": "hackernews", "count": 5},
            {"source": "reddit", "subreddit": "programming", "count": 3},
            {"source": "medium", "topic": "technology", "count": 3},
            {"source": "books", "topic": "자기계발", "count": 3}
        ]
    },
    
    "여행": {
        "title": "IndieBiz 여행 매거진",
        "sections": [
            {"source": "reddit", "subreddit": "travel", "count": 5},
            {"source": "medium", "topic": "travel", "count": 3},
            {"source": "books", "topic": "여행", "count": 3}
        ]
    },
    
    "기술": {
        "title": "IndieBiz 기술 매거진",
        "sections": [
            {"source": "hackernews", "count": 10},
            {"source": "reddit", "subreddit": "programming", "count": 5},
            {"source": "medium", "topic": "programming", "count": 3}
        ]
    },
    
    "철학": {
        "title": "IndieBiz 인문 매거진",
        "sections": [
            {"source": "reddit", "subreddit": "philosophy", "count": 5},
            {"source": "medium", "topic": "philosophy", "count": 5},
            {"source": "books", "topic": "철학", "count": 3}
        ]
    },
    
    "문화": {
        "title": "IndieBiz 문화 매거진",
        "sections": [
            {"source": "reddit", "subreddit": "books", "count": 4},
            {"source": "medium", "topic": "culture", "count": 3},
            {"source": "books", "topic": "예술", "count": 3}
        ]
    },
    
    "종합": {
        "title": "IndieBiz 종합 매거진",
        "sections": [
            {"source": "hackernews", "count": 5},
            {"source": "reddit", "subreddit": "science", "count": 3},
            {"source": "reddit", "subreddit": "AI", "count": 3},
            {"source": "medium", "topic": "technology", "count": 3},
            {"source": "medium", "topic": "life", "count": 3},
            {"source": "books", "topic": "인공지능", "count": 3},
            {"source": "books", "topic": "뇌과학", "count": 3},
            {"source": "books", "topic": "건축", "count": 3},
        ]
    }
}


def clean_html(text: str) -> str:
    """HTML 태그 완전 제거 및 엔티티 디코딩"""
    if not text:
        return ""
    
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def fetch_hackernews(count: int = 5) -> dict:
    """
    Hacker News 최신 인기 글 가져오기
    
    Args:
        count: 가져올 글 개수
    
    Returns:
        {'success': bool, 'items': list}
    """
    print(f"   🔥 Hacker News Top {count} 가져오는 중...")
    
    try:
        # Top Stories API
        response = requests.get(
            'https://hacker-news.firebaseio.com/v0/topstories.json',
            timeout=10
        )
        
        if response.status_code != 200:
            return {'success': False, 'items': []}
        
        story_ids = response.json()[:count]
        items = []
        
        for story_id in story_ids:
            try:
                item_response = requests.get(
                    f'https://hacker-news.firebaseio.com/v0/item/{story_id}.json',
                    timeout=5
                )
                
                if item_response.status_code == 200:
                    item_data = item_response.json()
                    
                    items.append({
                        'title': item_data.get('title', ''),
                        'url': item_data.get('url', f'https://news.ycombinator.com/item?id={story_id}'),
                        'points': item_data.get('score', 0),
                        'comments': item_data.get('descendants', 0),
                        'author': item_data.get('by', 'unknown'),
                        'time': datetime.fromtimestamp(item_data.get('time', 0)).strftime('%Y-%m-%d %H:%M')
                    })
            except Exception as e:
                print(f"      ⚠️  항목 {story_id} 가져오기 실패: {e}")
                continue
        
        print(f"      ✓ {len(items)}개 가져옴")
        return {'success': True, 'items': items}
    
    except Exception as e:
        print(f"      ❌ Hacker News 에러: {e}")
        return {'success': False, 'items': []}


def fetch_reddit(subreddit: str = 'programming', count: int = 5) -> dict:
    """
    Reddit 인기 포스트 가져오기
    
    Args:
        subreddit: 서브레딧 이름 (예: 'programming', 'travel', 'books')
        count: 가져올 포스트 개수
    
    Returns:
        {'success': bool, 'items': list}
    """
    print(f"   🤖 Reddit r/{subreddit} Top {count} 가져오는 중...")
    
    try:
        # Reddit JSON API (인증 불필요)
        url = f'https://www.reddit.com/r/{subreddit}/hot.json'
        headers = {'User-Agent': 'IndieBiz Magazine Bot 1.0'}
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return {'success': False, 'items': []}
        
        data = response.json()
        posts = data.get('data', {}).get('children', [])
        
        if not posts:
            return {'success': False, 'items': []}
        
        items = []
        for post_data in posts[:count]:
            post = post_data.get('data', {})
            
            # 자체 텍스트 또는 링크
            is_self = post.get('is_self', False)
            post_url = f"https://www.reddit.com{post.get('permalink', '')}" if is_self else post.get('url', '')
            
            # 본문 요약
            selftext = post.get('selftext', '')
            if selftext and len(selftext) > 300:
                selftext = selftext[:300] + '...'
            
            items.append({
                'title': post.get('title', ''),
                'author': post.get('author', 'unknown'),
                'url': post_url,
                'score': post.get('score', 0),
                'num_comments': post.get('num_comments', 0),
                'created': datetime.fromtimestamp(post.get('created_utc', 0)).strftime('%Y-%m-%d'),
                'selftext': selftext,
                'is_self': is_self
            })
        
        print(f"      ✓ {len(items)}개 가져옴")
        return {'success': True, 'items': items}
    
    except Exception as e:
        print(f"      ❌ Reddit 에러: {e}")
        return {'success': False, 'items': []}


def fetch_medium(topic: str = 'philosophy', count: int = 3) -> dict:
    """
    Medium 에세이 가져오기 (RSS 피드)
    
    Args:
        topic: 주제 태그
        count: 가져올 글 개수
    
    Returns:
        {'success': bool, 'items': list}
    """
    print(f"   ✍️  Medium '{topic}' 에세이 가져오는 중...")
    
    try:
        import feedparser
        from urllib.parse import quote
        
        # Medium 태그 RSS (URL 인코딩 적용)
        encoded_topic = quote(topic)
        feed_url = f'https://medium.com/feed/tag/{encoded_topic}'
        
        feed = feedparser.parse(feed_url)
        
        if not feed.entries:
            return {'success': False, 'items': []}
        
        items = []
        for entry in feed.entries[:count]:
            # 요약 추출 (HTML 제거)
            summary = clean_html(entry.get('summary', ''))
            if len(summary) > 300:
                summary = summary[:300] + '...'
            
            items.append({
                'title': entry.get('title', ''),
                'author': entry.get('author', 'Unknown'),
                'url': entry.get('link', ''),
                'published': entry.get('published', ''),
                'summary': summary
            })
        
        print(f"      ✓ {len(items)}개 가져옴")
        return {'success': True, 'items': items}
    
    except ImportError:
        print("      ⚠️  feedparser 설치 필요: pip install feedparser")
        return {'success': False, 'items': []}
    except Exception as e:
        print(f"      ❌ Medium 에러: {e}")
        return {'success': False, 'items': []}


def fetch_google_books(topic: str, count: int = 3) -> dict:
    """
    Google Books 검색
    
    Args:
        topic: 검색 주제
        count: 가져올 책 개수
    
    Returns:
        {'success': bool, 'items': list}
    """
    print(f"   📚 Google Books '{topic}' 검색 중...")
    
    try:
        api_url = 'https://www.googleapis.com/books/v1/volumes'
        
        params = {
            'q': topic,
            'maxResults': count,
            'langRestrict': 'ko',  # 한국어 책
            'orderBy': 'relevance'
        }
        
        response = requests.get(api_url, params=params, timeout=10)
        
        if response.status_code != 200:
            return {'success': False, 'items': []}
        
        data = response.json()
        
        if 'items' not in data:
            return {'success': False, 'items': []}
        
        items = []
        for item in data['items']:
            volume_info = item.get('volumeInfo', {})
            
            # 저자 리스트
            authors = volume_info.get('authors', ['Unknown'])
            author_str = ', '.join(authors)
            
            # 설명
            description = volume_info.get('description', '')
            if description:
                description = clean_html(description)
                if len(description) > 200:
                    description = description[:200] + '...'
            
            items.append({
                'title': volume_info.get('title', ''),
                'authors': author_str,
                'publisher': volume_info.get('publisher', ''),
                'published_date': volume_info.get('publishedDate', ''),
                'description': description,
                'thumbnail': volume_info.get('imageLinks', {}).get('thumbnail', ''),
                'info_link': volume_info.get('infoLink', '')
            })
        
        print(f"      ✓ {len(items)}개 찾음")
        return {'success': True, 'items': items}
    
    except Exception as e:
        print(f"      ❌ Google Books 에러: {e}")
        return {'success': False, 'items': []}


def generate_section_hackernews(count: int = 5) -> dict:
    """Hacker News 섹션 생성"""
    result = fetch_hackernews(count)
    
    if not result['success'] or not result['items']:
        return {
            'success': False,
            'markdown': "## 🔥 Hacker News\n\n데이터를 가져올 수 없습니다.\n\n---\n\n"
        }
    
    section = "## 🔥 Hacker News\n\n"
    
    for i, item in enumerate(result['items'], 1):
        section += f"### {i}. {item['title']}\n\n"
        section += f"**{item['points']} points** | {item['comments']} comments | by {item['author']}\n\n"
        section += f"🔗 [Read More]({item['url']})\n\n"
        section += "---\n\n"
    
    return {'success': True, 'markdown': section, 'count': len(result['items'])}


def generate_section_reddit(subreddit: str, count: int = 5) -> dict:
    """Reddit 섹션 생성"""
    result = fetch_reddit(subreddit, count)
    
    if not result['success'] or not result['items']:
        return {
            'success': False,
            'markdown': f"## 🤖 Reddit: r/{subreddit}\n\n포스트를 가져올 수 없습니다.\n\n---\n\n"
        }
    
    section = f"## 🤖 Reddit: r/{subreddit}\n\n"
    
    for i, item in enumerate(result['items'], 1):
        section += f"### {i}. {item['title']}\n\n"
        section += f"**{item['score']} upvotes** | {item['num_comments']} comments | by u/{item['author']}\n\n"
        
        # 자체 글이면 본문 일부 포함
        if item['selftext']:
            section += f"{item['selftext']}\n\n"
        
        section += f"🔗 [Read More]({item['url']})\n\n"
        section += "---\n\n"
    
    return {'success': True, 'markdown': section, 'count': len(result['items'])}


def generate_section_medium(topic: str, count: int = 3) -> dict:
    """Medium 섹션 생성"""
    result = fetch_medium(topic, count)
    
    if not result['success'] or not result['items']:
        return {
            'success': False,
            'markdown': f"## ✍️ Medium: {topic}\n\n에세이를 가져올 수 없습니다.\n\n---\n\n"
        }
    
    section = f"## ✍️ Medium: {topic}\n\n"
    
    for i, item in enumerate(result['items'], 1):
        section += f"### {i}. {item['title']}\n\n"
        section += f"**by {item['author']}** | {item['published']}\n\n"
        
        if item['summary']:
            section += f"{item['summary']}\n\n"
        
        section += f"🔗 [Read on Medium]({item['url']})\n\n"
        section += "---\n\n"
    
    return {'success': True, 'markdown': section, 'count': len(result['items'])}


def generate_section_books(topic: str, count: int = 3) -> dict:
    """Google Books 섹션 생성"""
    result = fetch_google_books(topic, count)
    
    if not result['success'] or not result['items']:
        return {
            'success': False,
            'markdown': f"## 📚 Books: {topic}\n\n책을 찾을 수 없습니다.\n\n---\n\n"
        }
    
    section = f"## 📚 Books: {topic}\n\n"
    
    for i, item in enumerate(result['items'], 1):
        section += f"### {i}. {item['title']}\n\n"
        section += f"**저자**: {item['authors']}"
        
        if item['publisher']:
            section += f" | **출판**: {item['publisher']}"
        
        if item['published_date']:
            section += f" | **발행**: {item['published_date']}"
        
        section += "\n\n"
        
        if item['description']:
            section += f"{item['description']}\n\n"
        
        section += f"🔗 [More Info]({item['info_link']})\n\n"
        section += "---\n\n"
    
    return {'success': True, 'markdown': section, 'count': len(result['items'])}


def assemble_magazine(title: str, date_str: str, sections: list) -> str:
    """
    섹션들을 조립하여 완성된 잡지 생성
    """
    # 목차 생성
    toc_items = []
    for section in sections:
        if section.get('success') and section.get('count', 0) > 0:
            name = section.get('name', 'Unknown')
            count = section.get('count', 0)
            toc_items.append(f"- {name} ({count}개)")
    
    toc = "\n".join(toc_items) if toc_items else "- (내용 없음)"
    
    # 섹션 내용 결합
    content = "\n\n".join([s['markdown'] for s in sections if s.get('success')])
    
    # 통계
    total_items = sum(s.get('count', 0) for s in sections if s.get('success'))
    
    # 최종 잡지
    magazine = f"""# {title}

**발행일**: {date_str}  
**발행처**: IndieBiz Magazine System  
**총 항목**: {total_items}개

---

## 📑 목차

{toc}

---

{content}

---

## 📊 제작 정보

- **생성 시각**: {datetime.now().strftime('%Y년 %m월 %d일 %H시 %M분')}
- **섹션 수**: {len([s for s in sections if s.get('success')])}개
- **총 항목**: {total_items}개
- **AI 사용**: 없음 (토큰 소비 0)
"""
    
    return magazine


def generate_magazine(preset: str = None, sections: list = None, title: str = None) -> dict:
    """
    통합 잡지 생성
    
    Args:
        preset: 프리셋 이름 ('주간', '여행', '기술', '철학', '문화', '종합')
        sections: 수동 섹션 설정 (preset 대신 사용)
        title: 잡지 제목 (선택사항)
    
    Returns:
        생성 결과
    """
    
    # 프리셋 처리
    if preset:
        if preset not in MAGAZINE_PRESETS:
            return {
                'success': False,
                'message': f"잡지 생성 실패: 알 수 없는 프리셋 '{preset}'. 사용 가능: {', '.join(MAGAZINE_PRESETS.keys())}",
                'next_action': '이 오류 결과를 요청자에게 call_agent로 전달하세요.'
            }
        
        preset_data = MAGAZINE_PRESETS[preset]
        sections_config = preset_data['sections'].copy()
        magazine_title = title if title else preset_data['title']
        
        print(f"📌 프리셋 사용: {preset}")
    
    elif sections:
        # 수동 설정
        sections_config = sections
        magazine_title = title if title else 'IndieBiz Magazine'
    
    else:
        return {
            'success': False,
            'message': '잡지 생성 실패: preset 또는 sections 중 하나는 필수입니다.',
            'next_action': '이 오류 결과를 요청자에게 call_agent로 전달하세요.'
        }
    
    # 날짜
    today = datetime.now()
    date_str = today.strftime('%Y년 %m월 %d일')
    date_filename = today.strftime('%Y%m%d')
    
    print(f"\n📚 잡지 제작 시작: {magazine_title} ({date_str})")
    print(f"📋 섹션 수: {len(sections_config)}개\n")
    
    # 각 섹션 생성
    sections = []
    
    for i, section_config in enumerate(sections_config, 1):
        source = section_config.get('source')
        print(f"[{i}/{len(sections_config)}]", end=" ")
        
        if source == 'hackernews':
            count = section_config.get('count', 5)
            section = generate_section_hackernews(count)
            section['name'] = 'Hacker News'
            
        elif source == 'reddit':
            subreddit = section_config.get('subreddit', 'programming')
            count = section_config.get('count', 5)
            section = generate_section_reddit(subreddit, count)
            section['name'] = f'Reddit: r/{subreddit}'
            
        elif source == 'medium':
            topic = section_config.get('topic', 'philosophy')
            count = section_config.get('count', 3)
            section = generate_section_medium(topic, count)
            section['name'] = f'Medium: {topic}'
            
        elif source == 'books':
            topic = section_config.get('topic', '여행')
            count = section_config.get('count', 3)
            section = generate_section_books(topic, count)
            section['name'] = f'Books: {topic}'
        
        else:
            print(f"⚠️  알 수 없는 소스: {source}")
            continue
        
        sections.append(section)
    
    print(f"\n✅ 모든 섹션 생성 완료!\n")
    
    # 잡지 조립
    print("📝 잡지 조립 중...")
    final_magazine = assemble_magazine(magazine_title, date_str, sections)

    # HTML 변환 및 저장
    print("🌐 HTML 변환 중...")
    os.makedirs(OUTPUTS_DIR, exist_ok=True)

    html_content = markdown_to_html(final_magazine, magazine_title, date_str, doc_type="magazine")
    html_filename = f"잡지_{date_filename}.html"
    html_filepath = os.path.join(OUTPUTS_DIR, html_filename)

    with open(html_filepath, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"💾 HTML 저장: {html_filename}\n")
    
    # 통계
    total_items = sum(s.get('count', 0) for s in sections if s.get('success'))
    
    return {
        'success': True,
        'message': f'잡지 생성 완료. 파일: {html_filepath}',
        'next_action': '이 결과를 요청자에게 call_agent로 전달하세요.'
    }


# generate_magazine_standard 제거됨 - 단순 파일 저장만 수행


# AI에게 제공할 도구 정의
MAGAZINE_TOOLS = [
    {
        "name": "generate_magazine",
        "description": """다양한 소스에서 정보를 수집하여 잡지를 생성합니다.

프리셋:
- "주간": 기술 트렌드 + Reddit 토론 + 에세이 + 책
- "여행": Reddit 여행 + 에세이 + 책
- "기술": IT 뉴스 + Reddit 프로그래밍 + 에세이
- "철학": Reddit 철학 + 철학 에세이 + 책
- "문화": Reddit 책 토론 + 문화 에세이 + 예술 책
- "종합": 기술 + Reddit 과학 + 에세이 + 책

특징:
- 프리셋으로 간단하게 사용
- Markdown + HTML 자동 생성
- AI 사용 안 함 (토큰 0)

사용 예시:
1. 간단: generate_magazine(preset="주간")
2. 수동: generate_magazine(sections=[{"source": "hackernews", "count": 5}])""",
        "input_schema": {
            "type": "object",
            "properties": {
                "preset": {
                    "type": "string",
                    "enum": ["주간", "여행", "기술", "철학", "문화", "종합"],
                    "description": "잡지 프리셋 (간단 사용)"
                },
                "sections": {
                    "type": "array",
                    "description": "수동 설정: 섹션 리스트 (preset 대신 사용)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {
                                "type": "string",
                                "enum": ["hackernews", "reddit", "medium", "books"],
                                "description": "정보 소스"
                            },
                            "count": {
                                "type": "integer",
                                "description": "가져올 항목 수"
                            },
                            "subreddit": {
                                "type": "string",
                                "description": "서브레딧 이름 (reddit 소스 사용 시)"
                            },
                            "topic": {
                                "type": "string",
                                "description": "주제 (medium, books)"
                            }
                        },
                        "required": ["source"]
                    }
                },
                "title": {
                    "type": "string",
                    "description": "잡지 제목 (선택사항)"
                }
            },
            "required": []
        }
    }
]


if __name__ == "__main__":
    # 프리셋 테스트
    print("=== 잡지 생성 테스트 (프리셋) ===\n")
    
    result = generate_magazine(preset="주간")
    print(f"\n결과: {result['message']}")
