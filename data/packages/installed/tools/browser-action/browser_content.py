"""
browser_content.py - 콘텐츠 추출 및 출력 도구

스크롤, 대기(selector/text/url/network idle), 스크린샷,
텍스트/HTML 추출, 콘솔 로그, 네트워크 로그, PDF 저장,
JavaScript 실행, Dialog 정보, 브라우저 종료.

Version: 4.0.0
"""

import re
import json
import asyncio
import base64
from datetime import datetime

from browser_session import (
    BrowserSession, ensure_active, get_output_dir,
    WAIT_DEFAULT_TIMEOUT, ACTION_TIMEOUT,
)


async def browser_scroll(params: dict) -> dict:
    """페이지 스크롤 (element ref로 특정 요소 내 스크롤 지원)"""
    err = ensure_active()
    if err:
        return err

    page = BrowserSession.get_instance().page
    direction = params.get("direction", "down")
    amount = params.get("amount", 500)
    to_bottom = params.get("to_bottom", False)
    to_top = params.get("to_top", False)
    selector = params.get("selector", "")

    try:
        if selector:
            # 특정 요소 내 스크롤
            script_target = f"document.querySelector('{selector}')"
        else:
            script_target = "window"

        if to_bottom:
            if selector:
                await page.evaluate(f"""() => {{
                    const el = {script_target};
                    if (el) el.scrollTop = el.scrollHeight;
                }}""")
            else:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        elif to_top:
            if selector:
                await page.evaluate(f"""() => {{
                    const el = {script_target};
                    if (el) el.scrollTop = 0;
                }}""")
            else:
                await page.evaluate("window.scrollTo(0, 0)")
        else:
            delta = int(amount) if direction == "down" else -int(amount)
            if selector:
                await page.evaluate(f"""(d) => {{
                    const el = {script_target};
                    if (el) el.scrollTop += d;
                }}""", delta)
            else:
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
    """특정 조건 대기 (selector, text, url, network idle, timeout)"""
    err = ensure_active()
    if err:
        return err

    page = BrowserSession.get_instance().page
    selector = params.get("selector")
    text = params.get("text")
    url_pattern = params.get("url")
    state = params.get("state", "visible")  # visible, hidden, attached, detached
    network_idle = params.get("network_idle", False)
    timeout = params.get("timeout", WAIT_DEFAULT_TIMEOUT)

    try:
        if selector:
            await page.wait_for_selector(selector, state=state, timeout=timeout)
            return {"success": True, "waited_for": f"selector: {selector} (state={state})"}

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

        elif network_idle:
            await page.wait_for_load_state("networkidle", timeout=timeout)
            return {"success": True, "waited_for": "network idle"}

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
            text = await page.locator(selector).first.inner_text(timeout=ACTION_TIMEOUT)
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


async def browser_get_html(params: dict) -> dict:
    """페이지 HTML 소스 추출"""
    err = ensure_active()
    if err:
        return err

    session = BrowserSession.get_instance()
    page = session.page
    selector = params.get("selector")
    outer = params.get("outer", True)
    max_length = params.get("max_length", 50000)

    try:
        if selector:
            locator = page.locator(selector).first
            if outer:
                html = await locator.evaluate("el => el.outerHTML")
            else:
                html = await locator.evaluate("el => el.innerHTML")
        else:
            if outer:
                html = await page.content()
            else:
                html = await page.evaluate("document.body.innerHTML")

        if len(html) > max_length:
            html = html[:max_length] + f"\n\n... (총 {len(html)}자 중 {max_length}자까지 표시)"

        return {
            "success": True,
            "html": html,
            "length": len(html),
            "url": page.url,
        }
    except Exception as e:
        return {"success": False, "error": f"HTML 추출 실패: {str(e)}"}


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


async def browser_network_logs(params: dict) -> dict:
    """네트워크 요청 로그 조회/제어"""
    err = ensure_active()
    if err:
        return err

    session = BrowserSession.get_instance()
    action = params.get("action", "get")  # start, stop, get, clear

    if action == "start":
        session.start_network_capture()
        return {"success": True, "message": "네트워크 캡처 시작"}

    elif action == "stop":
        session.stop_network_capture()
        return {"success": True, "message": "네트워크 캡처 중지"}

    elif action == "clear":
        session._network_logs.clear()
        return {"success": True, "message": "네트워크 로그 초기화"}

    else:  # get
        url_filter = params.get("url_filter", "")
        limit = params.get("limit", 50)
        logs = session.get_network_logs(url_pattern=url_filter, limit=limit)

        return {
            "success": True,
            "logs": logs,
            "count": len(logs),
            "capturing": session._capture_network,
        }


async def browser_dialog_info(params: dict) -> dict:
    """마지막으로 감지된 Dialog(alert/confirm/prompt) 정보 조회"""
    err = ensure_active()
    if err:
        return err

    session = BrowserSession.get_instance()
    dialog = session._last_dialog

    if dialog:
        return {
            "success": True,
            "dialog": dialog,
        }
    else:
        return {
            "success": True,
            "dialog": None,
            "message": "감지된 dialog가 없습니다."
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
    """JavaScript 실행 (타임아웃 지원)"""
    err = ensure_active()
    if err:
        return err

    page = BrowserSession.get_instance().page
    expression = params.get("expression", "")
    timeout = params.get("timeout", ACTION_TIMEOUT)

    if not expression:
        return {"success": False, "error": "expression이 필요합니다."}

    try:
        # asyncio.wait_for로 타임아웃 적용
        result = await asyncio.wait_for(
            page.evaluate(expression),
            timeout=timeout / 1000
        )

        try:
            json.dumps(result, ensure_ascii=False)
        except (TypeError, ValueError):
            result = str(result)

        return {
            "success": True,
            "result": result
        }
    except asyncio.TimeoutError:
        return {"success": False, "error": f"JavaScript 실행 시간 초과 ({timeout}ms)"}
    except Exception as e:
        return {"success": False, "error": f"JavaScript 실행 실패: {str(e)}"}


async def browser_resize(params: dict) -> dict:
    """브라우저 뷰포트 크기 변경"""
    err = ensure_active()
    if err:
        return err

    width = params.get("width", 1280)
    height = params.get("height", 720)

    if width < 320 or width > 3840 or height < 240 or height > 2160:
        return {"success": False, "error": f"유효하지 않은 크기: {width}x{height} (320-3840 x 240-2160)"}

    session = BrowserSession.get_instance()
    page = session.raw_page

    try:
        await page.set_viewport_size({"width": width, "height": height})
        return {
            "success": True,
            "viewport": {"width": width, "height": height}
        }
    except Exception as e:
        return {"success": False, "error": f"뷰포트 변경 실패: {str(e)}"}


async def browser_vision(params: dict, project_path: str = ".") -> dict:
    """페이지 스크린샷을 base64로 반환 (멀티모달 AI가 직접 인식).

    accessibility snapshot으로 잡히지 않는 요소(canvas, 커스텀 UI, 영상 프레임 등)를
    시각적으로 파악할 때 사용. 파일도 동시 저장.
    """
    err = ensure_active()
    if err:
        return err

    session = BrowserSession.get_instance()
    page = session.raw_page
    full_page = params.get("full_page", False)
    selector = params.get("selector")
    quality = params.get("quality", 80)  # JPEG 품질 (토큰 절약)

    try:
        # PNG로 스크린샷 바이트 생성
        if selector:
            element = page.locator(selector).first
            img_bytes = await element.screenshot(type="jpeg", quality=quality)
        else:
            img_bytes = await page.screenshot(
                full_page=full_page,
                type="jpeg",
                quality=quality,
            )

        # base64 인코딩
        img_b64 = base64.b64encode(img_bytes).decode("ascii")

        # 파일도 저장
        out_dir = get_output_dir(project_path, "screenshots")
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filepath = out_dir / f"vision_{timestamp}.jpg"
        with open(filepath, "wb") as f:
            f.write(img_bytes)

        return {
            "success": True,
            "image_base64": img_b64,
            "mime_type": "image/jpeg",
            "file_path": str(filepath.resolve()),
            "size_bytes": len(img_bytes),
            "url": page.url,
            "title": await page.title(),
        }
    except Exception as e:
        return {"success": False, "error": f"Vision 캡처 실패: {str(e)}"}


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
