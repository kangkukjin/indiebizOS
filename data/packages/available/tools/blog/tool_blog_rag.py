"""
블로그 RAG 검색 도구 - 원본 rag5 시스템 이식
하이브리드 검색 (Semantic + TF-IDF) 사용
"""

import sys
import os

# rag5 경로 추가
sys.path.insert(0, '/Users/kangkukjin/Desktop/AI/blog/rag5')


def search_blog(query: str, limit: int = 5) -> dict:
    """
    블로그에서 관련 글 검색 (하이브리드 검색)
    
    Args:
        query: 검색 질문
        limit: 최대 결과 수 (기본 5개)
    
    Returns:
        검색 결과 (제목, 내용, 유사도 점수)
    """
    try:
        from k_thoughts_interface_v2 import KThoughtsSystemV2
        
        print(f"[블로그 RAG] 검색 시작: {query}")
        
        # 시스템 초기화 (캐시 사용으로 빠름)
        system = KThoughtsSystemV2()
        if not system.is_initialized:
            print(f"[블로그 RAG] 시스템 초기화 중... (첫 실행은 시간이 걸립니다)")
            system.initialize()
            print(f"[블로그 RAG] 초기화 완료!")
        
        print(f"[블로그 RAG] 하이브리드 검색 실행 (Semantic + TF-IDF)...")
        results = system.search(query, mode='hybrid', top_k=limit)
        
        if not results:
            return {
                'success': True,
                'results': [],
                'message': f'검색 결과가 없습니다: {query}'
            }
        
        # 결과 포맷팅 (이미 포맷된 결과 사용)
        formatted_results = []
        for result in results:
            formatted_results.append({
                'rank': result.get('rank', 0),
                'title': result.get('title', 'Unknown'),
                'content': result.get('content_preview', ''),
                'similarity': result.get('score', 0),
                'search_type': result.get('search_type', 'hybrid'),
                'post_id': str(result.get('post_id', 'unknown')),
                'date': str(result.get('publish_date', 'unknown')),
                'category': result.get('category', 'unknown'),
                'relevance': result.get('relevance', 'unknown'),
                'key_insight': result.get('key_insight', '')
            })
        
        print(f"[블로그 RAG] {len(formatted_results)}개 결과 발견")
        
        return {
            'success': True,
            'query': query,
            'results': formatted_results,
            'message': f'{len(formatted_results)}개의 관련 글을 찾았습니다. (하이브리드 검색)'
        }
        
    except Exception as e:
        print(f"[블로그 RAG] 오류: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'results': [],
            'message': f'검색 실패: {str(e)}'
        }


def get_post_content(post_id: str) -> dict:
    """
    특정 포스트의 전체 내용 가져오기
    
    Args:
        post_id: 포스트 ID 또는 제목
    
    Returns:
        포스트 전체 내용
    """
    try:
        from k_thoughts_interface_v2 import KThoughtsSystemV2
        
        print(f"[블로그 RAG] 포스트 조회: {post_id}")
        
        system = KThoughtsSystemV2()
        if not system.is_initialized:
            system.initialize()
        
        # post_id로 검색 (post_id는 문자열)
        if post_id.isdigit():
            post = system.posts_df[system.posts_df['post_id'] == post_id]
        else:
            # 제목으로 검색
            post = system.posts_df[system.posts_df['title'].str.contains(post_id, case=False, na=False)]
        
        if post.empty:
            return {
                'success': False,
                'message': f'포스트를 찾을 수 없습니다: {post_id}'
            }
        
        post = post.iloc[0]
        
        return {
            'success': True,
            'title': post['title'],
            'content': post['content'],
            'date': str(post.get('publish_date', 'unknown')),
            'post_id': str(post.get('post_id', 'unknown')),
            'category': post.get('category', 'unknown')
        }
        
    except Exception as e:
        print(f"[블로그 RAG] 오류: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'message': f'실패: {str(e)}'
        }


def search_semantic(query: str, limit: int = 5) -> dict:
    """
    의미 기반 검색만 사용 (Semantic Search)
    
    Args:
        query: 검색 질문
        limit: 최대 결과 수
    
    Returns:
        검색 결과
    """
    try:
        from k_thoughts_interface_v2 import KThoughtsSystemV2
        
        print(f"[블로그 RAG] Semantic 검색: {query}")
        
        system = KThoughtsSystemV2()
        if not system.is_initialized:
            system.initialize()
        
        results = system.search(query, mode='semantic', top_k=limit)
        
        formatted_results = []
        for result in results:
            formatted_results.append({
                'rank': result.get('rank', 0),
                'title': result.get('title', 'Unknown'),
                'content': result.get('content_preview', ''),
                'similarity': result.get('score', 0),
                'search_type': result.get('search_type', 'semantic'),
                'relevance': result.get('relevance', 'unknown')
            })
        
        return {
            'success': True,
            'results': formatted_results,
            'message': f'{len(formatted_results)}개 발견 (Semantic Search)'
        }
        
    except Exception as e:
        return {
            'success': False,
            'results': [],
            'message': f'실패: {str(e)}'
        }


# 도구 정의
BLOG_RAG_TOOLS = [
    {
        "name": "search_blog",
        "description": "**내 개인 티스토리 블로그 'K의 생각'**에서 과거에 작성한 글을 검색합니다. 웹 뉴스 검색이 아닙니다! 내가 쓴 철학, 사회, 기술 관련 글을 찾을 때만 사용하세요. 뉴스나 최신 정보는 web_search를 사용하세요.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "검색할 질문이나 키워드"
                },
                "limit": {
                    "type": "integer",
                    "description": "최대 결과 수 (기본 5개)",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_post_content",
        "description": "특정 블로그 포스트의 전체 내용을 가져옵니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "post_id": {
                    "type": "string",
                    "description": "포스트 ID 또는 제목의 일부"
                }
            },
            "required": ["post_id"]
        }
    },
    {
        "name": "search_semantic",
        "description": "의미 기반 검색만 사용합니다. 키워드가 정확히 일치하지 않아도 의미적으로 유사한 글을 찾습니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "검색할 질문"
                },
                "limit": {
                    "type": "integer",
                    "description": "최대 결과 수 (기본 5개)",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    }
]
