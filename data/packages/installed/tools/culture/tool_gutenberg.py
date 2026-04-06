import requests
import logging

logger = logging.getLogger(__name__)

def search_gutenberg(query: str = None, author_year_start: int = None, author_year_end: int = None, topic: str = None, languages: str = 'en'):
    """
    Project Gutenberg에서 도서를 검색합니다 (Gutendex API 사용)
    """
    url = "https://gutendex.com/books"
    params = {}
    if query:
        params['search'] = query
    if author_year_start:
        params['author_year_start'] = author_year_start
    if author_year_end:
        params['author_year_end'] = author_year_end
    if topic:
        params['topic'] = topic
    if languages:
        params['languages'] = languages
        
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for book in data.get('results', [])[:10]:  # 최대 10개 반환
            authors = [a['name'] for a in book.get('authors', [])]
            formats = book.get('formats', {})
            # 텍스트 또는 HTML 다운로드 링크 추출
            text_url = formats.get('text/plain; charset=us-ascii') or formats.get('text/plain; charset=utf-8') or formats.get('text/plain')
            html_url = formats.get('text/html')
            
            results.append({
                'id': book.get('id'),
                'title': book.get('title'),
                'authors': authors,
                'subjects': book.get('subjects', []),
                'languages': book.get('languages', []),
                'text_url': text_url,
                'html_url': html_url,
                'download_count': book.get('download_count', 0)
            })
            
        return {
            "count": data.get('count', 0),
            "results": results,
            "next": data.get('next'),
            "previous": data.get('previous')
        }
    except Exception as e:
        logger.error(f"Gutendex API 호출 오류: {str(e)}")
        return {"error": f"Gutenberg 검색 실패: {str(e)}"}
