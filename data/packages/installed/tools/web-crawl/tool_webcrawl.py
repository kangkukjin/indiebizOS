"""
tool_webcrawl.py - 웹사이트 크롤링 도구 (파일 기반)
"""

import requests
from bs4 import BeautifulSoup
import json

# Playwright (선택적)
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


def get_tool_definition():
    return {
        "name": "crawl_website",
        "description": """특정 URL의 웹사이트를 크롤링하여 텍스트 내용을 추출하고 자동 생성된 파일에 저장합니다.

**기능:**
- 정적 사이트: 빠른 크롤링 (1-2초)
- 동적 사이트: 자동 감지 후 Playwright로 크롤링 (3-5초)

**결과:**
- 파일이 자동으로 생성되며 경로는 반환값의 'file' 필드에 포함됩니다

**사용 시기:**
- 사용자가 URL을 제공했을 때
- 특정 웹페이지의 내용을 읽어야 할 때""",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "크롤링할 웹사이트 URL"
                },
                "max_length": {
                    "type": "integer",
                    "description": "최대 텍스트 길이 (기본: 10000자)",
                    "default": 10000
                }
            },
            "required": ["url"]
        }
    }


def crawl_website(url: str, max_length: int = 10000) -> dict:
    """웹사이트 크롤링하고 자동 생성된 파일에 저장"""
    from datetime import datetime
    import re
    
    # 자동 파일명 생성 (URL에서 도메인 추출)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    domain = re.sub(r'https?://(www\.)?', '', url).split('/')[0].replace('.', '_')
    output_file = f"/tmp/crawl_{domain}_{timestamp}.json"
    try:
        # 간단한 요청
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        # HTML 파싱
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 텍스트 추출
        for script in soup(["script", "style"]):
            script.decompose()
        
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        # 길이 제한
        if len(text) > max_length:
            text = text[:max_length] + "\n\n... (내용 생략)"
        
        # 파일 저장
        result = {
            "url": url,
            "text": text,
            "length": len(text)
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        return {
            "success": True,
            "file": output_file,
            "url": url,
            "length": len(text)
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "url": url
        }


def use_tool(tool_input: dict) -> dict:
    url = tool_input.get('url', '')
    max_length = tool_input.get('max_length', 10000)
    
    if not url:
        return {"success": False, "error": "url이 필요합니다"}
    
    return crawl_website(url, max_length)
