"""
tool_webcrawl.py - 웹사이트 크롤링 도구
정적 웹페이지의 텍스트 내용을 추출합니다.
"""

import requests
from bs4 import BeautifulSoup

# User-Agent 설정 (차단 방지)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
}


def crawl_website(url: str, max_length: int = 10000) -> dict:
    """
    웹사이트를 크롤링하여 텍스트 내용을 추출합니다.

    Args:
        url: 크롤링할 URL
        max_length: 최대 텍스트 길이 (기본 10000자)

    Returns:
        dict: {success, url, title, text, length} 또는 {success, error, url}
    """
    if not url:
        return {"success": False, "error": "URL이 필요합니다.", "url": ""}

    # URL 형식 검증
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    try:
        # HTTP 요청
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()

        # 인코딩 처리
        if response.encoding is None or response.encoding == 'ISO-8859-1':
            response.encoding = response.apparent_encoding

        # HTML 파싱
        soup = BeautifulSoup(response.text, 'html.parser')

        # 페이지 제목 추출
        title = soup.title.string.strip() if soup.title and soup.title.string else ""

        # 불필요한 요소 제거
        for element in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'noscript']):
            element.decompose()

        # 텍스트 추출 및 정리
        text = soup.get_text(separator='\n')
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        text = '\n'.join(lines)

        # 연속 공백 정리
        import re
        text = re.sub(r'\n{3,}', '\n\n', text)

        # 길이 제한
        original_length = len(text)
        if len(text) > max_length:
            text = text[:max_length] + "\n\n... (내용 생략됨)"

        return {
            "success": True,
            "url": url,
            "title": title,
            "text": text,
            "length": original_length,
            "truncated": original_length > max_length
        }

    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "요청 시간 초과 (15초)",
            "url": url
        }
    except requests.exceptions.HTTPError as e:
        return {
            "success": False,
            "error": f"HTTP 에러: {e.response.status_code}",
            "url": url
        }
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "error": "연결 실패 - URL을 확인하세요",
            "url": url
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "url": url
        }


def use_tool(tool_input: dict) -> dict:
    """도구 인터페이스"""
    url = tool_input.get('url', '')
    max_length = tool_input.get('max_length', 10000)
    return crawl_website(url, max_length)
