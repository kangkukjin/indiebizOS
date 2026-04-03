"""
tool_webcrawl.py - 웹사이트 크롤링 도구
정적 크롤링(requests) 후 콘텐츠가 부족하면 Chrome MCP로 폴백.
"""

import os
import re
import sys
import asyncio
import threading
import importlib.util

# common 유틸리티 사용
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_backend_dir))

import requests
from bs4 import BeautifulSoup

# User-Agent 설정 (차단 방지)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
}

# Chrome MCP 폴백 판단 기준 (이 글자수 미만이면 콘텐츠 부족으로 간주)
_MIN_CONTENT_LENGTH = 200


def _parse_html(html: str, url: str) -> tuple[str, str]:
    """HTML에서 제목과 본문 텍스트를 추출한다."""
    soup = BeautifulSoup(html, 'html.parser')
    title = soup.title.string.strip() if soup.title and soup.title.string else ""

    # 불필요한 요소 제거
    for el in soup(['script', 'style', 'nav', 'footer', 'header', 'aside',
                    'noscript', 'iframe', 'form', 'button', 'svg', 'figure', 'figcaption']):
        el.decompose()

    # 광고/관련기사/댓글 등 노이즈 제거 (class/id 기반)
    noise_patterns = ['comment', 'advert', 'sidebar', 'related', 'recommend',
                      'share', 'social', 'newsletter', 'popup', 'banner', 'cookie']
    for el in list(soup.find_all(True)):
        try:
            classes = ' '.join(el.get('class', []))
            el_id = el.get('id', '')
            combined = (classes + ' ' + el_id).lower()
            if any(p in combined for p in noise_patterns):
                el.decompose()
        except Exception:
            continue

    # 본문 추출: <article> → <main> → <body>
    container = soup.find('article') or soup.find('main') or soup.find('body') or soup
    text = container.get_text(separator='\n')

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    text = '\n'.join(lines)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return title, text


def _truncate(text: str, max_length: int) -> tuple[str, int, bool]:
    """텍스트를 max_length로 자르고 (text, original_length, truncated) 반환."""
    original_length = len(text)
    truncated = original_length > max_length
    if truncated:
        text = text[:max_length] + "\n\n... (내용 생략됨)"
    return text, original_length, truncated


# ─── 1단계: requests 기반 정적 크롤링 ───

def _crawl_static(url: str, max_length: int) -> dict:
    """requests + BeautifulSoup으로 정적 크롤링."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()

        if response.encoding is None or response.encoding == 'ISO-8859-1':
            response.encoding = response.apparent_encoding

        title, text = _parse_html(response.text, url)
        text, original_length, truncated = _truncate(text, max_length)

        return {
            "success": True,
            "url": url,
            "title": title,
            "text": text,
            "length": original_length,
            "truncated": truncated,
            "method": "requests"
        }
    except requests.exceptions.Timeout:
        return {"success": False, "error": "요청 시간 초과 (15초)", "url": url}
    except requests.exceptions.HTTPError as e:
        return {"success": False, "error": f"HTTP 에러: {e.response.status_code}", "url": url}
    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "연결 실패 - URL을 확인하세요", "url": url}
    except Exception as e:
        return {"success": False, "error": str(e), "url": url}


# ─── 2단계: Chrome MCP 폴백 ───

def _get_chrome_driver():
    """browser-action 패키지의 ChromeMCPDriver 싱글톤을 가져온다. 실패 시 None."""
    try:
        chrome_path = os.path.join(
            os.path.dirname(__file__), "..", "browser-action", "browser_chrome.py"
        )
        spec = importlib.util.spec_from_file_location("browser_chrome", chrome_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        driver = mod.ChromeMCPDriver.get_instance()
        if driver.is_connected():
            return driver
    except Exception:
        pass
    return None


async def _crawl_chrome_async(driver, url: str, max_length: int) -> dict:
    """Chrome MCP를 사용하여 실제 브라우저로 페이지 텍스트를 가져온다."""
    try:
        # 페이지 이동
        await driver.call_tool("navigate", {"url": url, "tabId": driver._tab_id})

        # JS 렌더링 대기 (페이지 로드 완료)
        await asyncio.sleep(2)

        # 텍스트 추출
        result = await driver.call_tool("get_page_text", {"tabId": driver._tab_id})
        text = result.get("text", "") if isinstance(result, dict) else str(result)

        if not text or len(text) < _MIN_CONTENT_LENGTH:
            return {"success": False, "error": "Chrome MCP에서도 콘텐츠를 추출하지 못함", "url": url}

        # 제목 추출 시도
        title_result = await driver.call_tool("javascript_tool", {
            "action": "javascript_exec",
            "text": "document.title",
            "tabId": driver._tab_id
        })
        title = ""
        if isinstance(title_result, dict):
            title = title_result.get("text", title_result.get("result", ""))

        # 정리 및 자르기
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        text = '\n'.join(lines)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text, original_length, truncated = _truncate(text, max_length)

        return {
            "success": True,
            "url": url,
            "title": title,
            "text": text,
            "length": original_length,
            "truncated": truncated,
            "method": "chrome_mcp"
        }
    except Exception as e:
        return {"success": False, "error": f"Chrome MCP 크롤링 실패: {e}", "url": url}


def _run_async(coro):
    """기존 system_tools의 async 루프를 재사용하거나, 없으면 새로 실행."""
    try:
        from system_tools import _get_async_loop
        loop = _get_async_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=30)
    except ImportError:
        # system_tools를 임포트할 수 없으면 직접 실행
        return asyncio.run(coro)


# ─── 메인 함수 ───

def crawl_website(url: str, max_length: int = 10000) -> dict:
    """
    웹사이트를 크롤링하여 텍스트 내용을 추출한다.
    1단계: requests (빠름, ~1초)
    2단계: 실패 또는 콘텐츠 부족 시 Chrome MCP로 폴백 (JS 렌더링 지원)
    """
    if not url:
        return {"success": False, "error": "URL이 필요합니다.", "url": ""}

    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    # 1단계: 정적 크롤링
    result = _crawl_static(url, max_length)

    # 콘텐츠가 충분하면 바로 반환
    if result.get("success") and len(result.get("text", "")) >= _MIN_CONTENT_LENGTH:
        return result

    # 2단계: Chrome MCP 폴백
    driver = _get_chrome_driver()
    if driver is None:
        # Chrome MCP 사용 불가 — 원래 결과(또는 에러) 그대로 반환
        return result

    chrome_result = _run_async(_crawl_chrome_async(driver, url, max_length))
    if chrome_result.get("success"):
        return chrome_result

    # Chrome MCP도 실패하면, 원래 결과 중 나은 것을 반환
    if result.get("success"):
        return result
    return chrome_result


def use_tool(tool_input: dict) -> dict:
    """도구 인터페이스"""
    url = tool_input.get('url', '')
    max_length = tool_input.get('max_length', 10000)
    return crawl_website(url, max_length)
