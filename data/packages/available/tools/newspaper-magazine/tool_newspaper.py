"""
tool_newspaper.py - 신문 자동 생성 도구 (Google News 버전)

키워드를 입력받아 각 키워드별로 Google News 검색을 실행하고
결과를 신문 형식으로 조립합니다.

특징:
- AI 사용 안 함 (토큰 소비 0)
- 실제 뉴스만 (가짜 없음)
- Google News RSS 기반
- Python으로 조립

스탠다드 도구: OutputRouter를 통해 라우팅
"""

import os
import json
import re
from html import unescape
from datetime import datetime
from tool_google_news import search_google_news
from tool_utils import markdown_to_html, OUTPUTS_DIR


def clean_html(text: str) -> str:
    """HTML 태그 완전 제거 및 엔티티 디코딩"""
    if not text:
        return ""
    
    # HTML 태그 제거
    text = re.sub(r'<[^>]+>', '', text)
    
    # HTML 엔티티 디코딩
    text = unescape(text)
    
    # 여러 공백을 하나로
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def generate_section(keyword: str, news_count: int = 7, exclude_sources: list = None) -> dict:
    """
    키워드로 Google News 검색하여 섹션 생성
    
    Args:
        keyword: 검색 키워드
        news_count: 뉴스 개수 (기본 7개)
        exclude_sources: 제외할 언론사 목록 (예: ['조선일보', '매일경제'])
    
    Returns:
        {
            'keyword': str,
            'markdown': str,
            'news_count': int,
            'success': bool
        }
    """
    print(f"   📰 '{keyword}' 섹션 생성 중...")
    
    if exclude_sources is None:
        exclude_sources = []
    
    # Google News 검색 (더 많이 가져와서 필터링 후 충분한 수 확보)
    fetch_count = news_count * 3 if exclude_sources else news_count
    result = search_google_news(query=keyword, count=fetch_count, language='ko')
    
    # 결과 파일 읽기
    if result['success']:
        with open(result['file'], 'r', encoding='utf-8') as f:
            data = json.load(f)
            result['results'] = data.get('results', [])
    else:
        result['results'] = []
    
    if not result['success'] or not result['results']:
        print(f"      ⚠️  뉴스 없음")
        return {
            'keyword': keyword,
            'markdown': f"## {keyword}\n\n뉴스를 찾을 수 없습니다.\n\n---\n\n",
            'news_count': 0,
            'success': False
        }
    
    # 제외할 언론사 필터링
    filtered_results = []
    excluded_count = 0
    
    for item in result['results']:
        source = item.get('source', '')
        
        # 제외 목록에 있는지 확인 (부분 매칭)
        is_excluded = False
        for exclude in exclude_sources:
            if exclude in source:
                is_excluded = True
                excluded_count += 1
                break
        
        if not is_excluded:
            filtered_results.append(item)
            
            # 필요한 수만큼 모았으면 중단
            if len(filtered_results) >= news_count:
                break
    
    if excluded_count > 0:
        print(f"      🚫 제외됨: {excluded_count}개 ({', '.join(exclude_sources)})")
    
    if not filtered_results:
        print(f"      ⚠️  필터링 후 뉴스 없음")
        return {
            'keyword': keyword,
            'markdown': f"## {keyword}\n\n필터링 후 뉴스를 찾을 수 없습니다.\n\n---\n\n",
            'news_count': 0,
            'success': False
        }
    
    # Markdown 섹션 생성
    section = f"## 📰 {keyword}\n\n"
    
    for i, item in enumerate(filtered_results, 1):
        section += f"### {i}. {item['title']}\n\n"
        section += f"**출처**: {item['source']} | **발행**: {item['published']}\n\n"
        
        # 요약이 있고 제목과 다르면 추가
        if item.get('summary'):
            summary = clean_html(item['summary'])
            if summary and summary != item['title']:
                section += f"{summary}\n\n"
        
        section += f"🔗 [기사 보기]({item['url']})\n\n"
        section += "---\n\n"
    
    print(f"      ✓ {len(filtered_results)}개 뉴스")
    
    return {
        'keyword': keyword,
        'markdown': section,
        'news_count': len(filtered_results),
        'excluded_count': excluded_count,
        'success': True
    }


def assemble_newspaper(title: str, date_str: str, sections: list) -> str:
    """
    섹션들을 조립하여 완성된 신문 생성
    
    Args:
        title: 신문 제목
        date_str: 발행일
        sections: 섹션 리스트
    
    Returns:
        완성된 Markdown 신문
    """
    # 목차 생성
    toc_items = []
    for section in sections:
        if section['success'] and section['news_count'] > 0:
            keyword = section['keyword']
            count = section['news_count']
            toc_items.append(f"- [{keyword}](#{keyword}) ({count}개)")
    
    toc = "\n".join(toc_items)
    
    # 섹션 내용 결합
    content = "\n\n".join([s['markdown'] for s in sections])
    
    # 통계
    total_news = sum(s['news_count'] for s in sections)
    
    # 최종 신문
    newspaper = f"""# {title}

**발행일**: {date_str}  
**발행처**: IndieBiz AI 신문 시스템  
**총 뉴스**: {total_news}개

---

## 📑 목차

{toc}

---

{content}

---

## 📊 제작 정보

- **생성 시각**: {datetime.now().strftime('%Y년 %m월 %d일 %H시 %M분')}
- **섹션 수**: {len(sections)}개
- **총 뉴스**: {total_news}개
- **출처**: Google News RSS
- **AI 사용**: 없음 (토큰 소비 0)
- **방식**: 키워드별 Google News 검색 → Python 조립
"""

    return newspaper


def generate_newspaper(keywords: list, title: str = "IndieBiz Daily", exclude_sources: list = None) -> dict:
    """
    Google News 기반 신문 자동 생성 (AI 사용 안 함)
    
    Args:
        keywords: 섹션 키워드 리스트 (예: ["한국", "AI", "경제"])
        title: 신문 제목 (기본값: "IndieBiz Daily")
        exclude_sources: 제외할 언론사 목록 (예: ["조선일보", "매일경제"])
    
    Returns:
        생성 결과
    """
    
    # 키워드 검증
    if not keywords:
        return {
            'success': False,
            'message': '신문 생성 실패: 키워드가 필요합니다.',
            'next_action': '이 오류 결과를 요청자에게 call_agent로 전달하세요.'
        }
    
    if exclude_sources is None:
        exclude_sources = []
    
    # 1. 현재 날짜
    today = datetime.now()
    date_str = today.strftime('%Y년 %m월 %d일')
    date_filename = today.strftime('%Y%m%d')
    
    print(f"\n📰 신문 제작 시작: {title} ({date_str})")
    print(f"📋 섹션 수: {len(keywords)}개")
    print(f"🔖 키워드: {', '.join(keywords)}")
    print(f"🔍 출처: Google News RSS")
    if exclude_sources:
        print(f"🚫 제외: {', '.join(exclude_sources)}")
    print()
    
    # 2. 각 키워드별로 섹션 생성 (Google News 검색)
    sections = []
    total_excluded = 0
    
    for i, keyword in enumerate(keywords, 1):
        print(f"[{i}/{len(keywords)}]", end=" ")
        section = generate_section(keyword, news_count=7, exclude_sources=exclude_sources)
        sections.append(section)
        total_excluded += section.get('excluded_count', 0)
    
    print(f"\n✅ 모든 섹션 생성 완료!")
    if total_excluded > 0:
        print(f"🚫 총 {total_excluded}개 기사 제외됨\n")
    
    # 3. 신문 조립 (Python)
    print("📝 신문 조립 중...")
    final_newspaper = assemble_newspaper(title, date_str, sections)

    # 4. HTML 변환 및 저장
    print("🌐 HTML 변환 중...")
    os.makedirs(OUTPUTS_DIR, exist_ok=True)

    html_content = markdown_to_html(final_newspaper, title, date_str, doc_type="newspaper")
    html_filename = f"신문_{date_filename}_{len(keywords)}면.html"
    html_filepath = os.path.join(OUTPUTS_DIR, html_filename)

    with open(html_filepath, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"💾 HTML 저장: {html_filename}\n")
    
    # 6. 통계
    total_news = sum(s['news_count'] for s in sections)
    
    # 7. 결과 반환
    return {
        'success': True,
        'message': f'신문 생성 완료. 파일: {html_filepath}',
        'next_action': '이 결과를 요청자에게 call_agent로 전달하세요.'
    }



NEWSPAPER_TOOLS = [
    {
        "name": "generate_newspaper",
        "description": "Google News 기반 신문을 자동으로 생성합니다. keywords 배열을 받아 각 키워드별로 Google News를 검색하고 신문 형식으로 조립합니다. 결과는 outputs/ 디렉토리에 HTML 파일로 저장됩니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "신문 섹션 키워드 리스트"
                },
                "title": {
                    "type": "string",
                    "description": "신문 제목 (기본: IndieBiz Daily)"
                },
                "exclude_sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "제외할 언론사 목록"
                }
            },
            "required": ["keywords"]
        }
    }
]


if __name__ == "__main__":
    print("=== 신문 생성 테스트 ===\n")
    result = generate_newspaper(["한국", "AI"], "테스트 신문")
    print(f"\n결과: {result['message']}")
