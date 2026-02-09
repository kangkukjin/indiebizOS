"""
browser_content.py - 콘텐츠 추출 및 출력 도구

스크롤, 대기, 스크린샷, 텍스트 추출, 콘솔 로그, PDF 저장,
JavaScript 실행, 브라우저 종료.

Version: 3.0.0
"""

import re
import json
import asyncio
from datetime import datetime

from browser_session import (
    BrowserSession, ensure_active, get_output_dir,
    WAIT_DEFAULT_TIMEOUT,
)


async def browser_scroll(params: dict) -> dict:
    """페이지 스크롤"""
    err = ensure_active()
    if err:
        return err

    page = BrowserSession.get_instance().page
    direction = params.get("direction", "down")
    amount = params.get("amount", 500)
    to_bottom = params.get("to_bottom", False)
    to_top = params.get("to_top", False)

    try:
        if to_bottom:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        elif to_top:
            await page.evaluate("window.scrollTo(0, 0)")
        else:
            delta = int(amount) if direction == "down" else -int(amount)
            await page.evaluate("(d) => window.scrollBy(0, d)", delta)

        scroll_info = await page.evaluate('''() => ({
            scrollY: Math.round(window.scrollY),
            scrollHeight: document.body.scrollHeight,
            viewportHeight: window.innerHeight
        })''')

        return {
            "success": True,
            "scroll_position": scroll_info["scrollY"],
            "page_height": scroll_info["scrollHeight"],
            "viewport_height": scroll_info["viewportHeight"]
        }
    except Exception as e:
        return {"success": False, "error": f"스크롤 실패: {str(e)}"}


async def browser_wait_for(params: dict) -> dict:
    """특정 조건 대기"""
    err = ensure_active()
    if err:
        return err

    page = BrowserSession.get_instance().page
    selector = params.get("selector")
    text = params.get("text")
    url_pattern = params.get("url")
    timeout = params.get("timeout", WAIT_DEFAULT_TIMEOUT)

    try:
        if selector:
            await page.wait_for_selector(selector, timeout=timeout)
            return {"success": True, "waited_for": f"selector: {selector}"}

        elif text:
            await page.wait_for_function(
                '(t) => document.body.innerText.includes(t)',
                arg=text,
                timeout=timeout
            )
            return {"success": True, "waited_for": f"text: {text}"}

        elif url_pattern:
            await page.wait_for_url(re.compile(url_pattern), timeout=timeout)
            return {"success": True, "waited_for": f"url: {url_pattern}"}

        else:
            await asyncio.sleep(timeout / 1000)
            return {"success": True, "waited_for": f"{timeout}ms"}

    except Exception as e:
        return {"success": False, "error": f"대기 실패: {str(e)}"}


async def browser_screenshot(params: dict, project_path: str = ".") -> dict:
    """스크린샷 저장"""
    err = ensure_active()
    if err:
        return err

    session = BrowserSession.get_instance()
    page = session.raw_page
    full_page = params.get("full_page", False)
    selector = params.get("selector")

    try:
        out_dir = get_output_dir(project_path, "screenshots")
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"screenshot_{timestamp}.png"
        filepath = out_dir / filename

        if selector:
            element = page.locator(selector).first
            await element.screenshot(path=str(filepath))
        else:
            await page.screenshot(path=str(filepath), full_page=full_page)

        return {
            "success": True,
            "file_path": str(filepath.resolve())
        }
    except Exception as e:
        return {"success": False, "error": f"스크린샷 실패: {str(e)}"}


async def browser_get_content(params: dict) -> dict:
    """페이지 텍스트 추출"""
    err = ensure_active()
    if err:
        return err

    session = BrowserSession.get_instance()
    page = session.page
    selector = params.get("selector")
    max_length = params.get("max_length", 10000)

    try:
        if selector:
            text = await page.locator(selector).first.inner_text(timeout=10000)
        else:
            text = await page.inner_text('body')

        if len(text) > max_length:
            text = text[:max_length] + f"\n\n... (총 {len(text)}자 중 {max_length}자까지 표시)"

        return {
            "success": True,
            "title": await session.raw_page.title(),
            "url": page.url,
            "text": text,
            "length": len(text)
        }
    except Exception as e:
        return {"success": False, "error": f"콘텐츠 추출 실패: {str(e)}"}


async def browser_console_logs(params: dict) -> dict:
    """콘솔 로그 조회"""
    err = ensure_active()
    if err:
        return err

    session = BrowserSession.get_instance()
    log_type = params.get("type", "all")
    search = params.get("search", "")
    limit = params.get("limit", 100)
    clear = params.get("clear", False)

    logs = list(session._console_logs)

    if log_type != "all":
        logs = [l for l in logs if l["type"] == log_type]

    if search:
        logs = [l for l in logs if search.lower() in l["text"].lower()]

    logs = logs[-limit:]

    if clear:
        session._console_logs.clear()

    return {
        "success": True,
        "logs": logs,
        "count": len(logs)
    }


async def browser_save_pdf(params: dict, project_path: str = ".") -> dict:
    """페이지를 PDF로 저장"""
    err = ensure_active()
    if err:
        return err

    page = BrowserSession.get_instance().raw_page
    format_size = params.get("format", "A4")
    landscape = params.get("landscape", False)
    print_background = params.get("print_background", True)

    try:
        out_dir = get_output_dir(project_path, "pdfs")
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"page_{timestamp}.pdf"
        filepath = out_dir / filename

        await page.pdf(
            path=str(filepath),
            format=format_size,
            landscape=landscape,
            print_background=print_background
        )

        return {
            "success": True,
            "file_path": str(filepath.resolve())
        }
    except Exception as e:
        return {"success": False, "error": f"PDF 저장 실패: {str(e)}"}


async def browser_evaluate(params: dict) -> dict:
    """JavaScript 실행"""
    err = ensure_active()
    if err:
        return err

    page = BrowserSession.get_instance().page
    expression = params.get("expression", "")

    if not expression:
        return {"success": False, "error": "expression이 필요합니다."}

    try:
        result = await page.evaluate(expression)

        try:
            json.dumps(result, ensure_ascii=False)
        except (TypeError, ValueError):
            result = str(result)

        return {
            "success": True,
            "result": result
        }
    except Exception as e:
        return {"success": False, "error": f"JavaScript 실행 실패: {str(e)}"}


async def browser_close(params: dict = None) -> dict:
    """브라우저 종료"""
    try:
        session = BrowserSession.get_instance()
        was_active = session.is_active
        await session.close()
        return {
            "success": True,
            "message": "브라우저 종료 완료" if was_active else "브라우저가 이미 종료 상태입니다."
        }
    except Exception as e:
        return {"success": False, "error": f"종료 실패: {str(e)}"}
