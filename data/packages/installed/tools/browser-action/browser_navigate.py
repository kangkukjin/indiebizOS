"""
browser_navigate.py - 브라우저 네비게이션 도구

URL 이동, 히스토리 앞/뒤 이동 기능.

Version: 3.0.0
"""

from browser_session import (
    BrowserSession, ensure_active,
    NAVIGATE_TIMEOUT, BLOCKED_URL_SCHEMES,
)


async def browser_navigate(params: dict, project_path: str = ".") -> dict:
    """브라우저를 열고 URL로 이동"""
    url = params.get("url", "")
    headless = params.get("headless", True)
    wait_for = params.get("wait_for", "load")

    if not url:
        return {"success": False, "error": "URL이 필요합니다."}

    url_lower = url.lower().strip()
    for scheme in BLOCKED_URL_SCHEMES:
        if url_lower.startswith(scheme):
            return {"success": False, "error": f"보안상 허용되지 않는 URL 스킴입니다: {scheme}"}

    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    try:
        session = BrowserSession.get_instance()
        page = await session.ensure_browser(headless=headless)

        session.clear_refs()

        try:
            await page.goto(url, wait_until=wait_for, timeout=NAVIGATE_TIMEOUT)
        except Exception as goto_err:
            err_msg = str(goto_err).lower()
            if "closed" in err_msg or "disposed" in err_msg or "crashed" in err_msg:
                # 자동종료 타이밍 충돌 — 세션 초기화 후 재시도
                await session._close_internal()
                page = await session.ensure_browser(headless=headless)
                session.clear_refs()
                await page.goto(url, wait_until=wait_for, timeout=NAVIGATE_TIMEOUT)
            else:
                raise

        title = await page.title()

        return {
            "success": True,
            "title": title,
            "url": page.url,
            "tab_id": session.active_tab_id,
            "snapshot_hint": "페이지 구조를 파악하려면 browser_snapshot을 호출하세요."
        }
    except Exception as e:
        return {"success": False, "error": f"페이지 열기 실패: {str(e)}"}


async def browser_navigate_back(params: dict) -> dict:
    """브라우저 히스토리에서 이전 페이지로 이동"""
    err = ensure_active()
    if err:
        return err

    try:
        session = BrowserSession.get_instance()
        page = session.page
        session.clear_refs()

        await page.go_back(wait_until="load", timeout=NAVIGATE_TIMEOUT)

        return {
            "success": True,
            "title": await page.title(),
            "url": page.url
        }
    except Exception as e:
        return {"success": False, "error": f"뒤로 가기 실패: {str(e)}"}


async def browser_navigate_forward(params: dict) -> dict:
    """브라우저 히스토리에서 다음 페이지로 이동"""
    err = ensure_active()
    if err:
        return err

    try:
        session = BrowserSession.get_instance()
        page = session.page
        session.clear_refs()

        await page.go_forward(wait_until="load", timeout=NAVIGATE_TIMEOUT)

        return {
            "success": True,
            "title": await page.title(),
            "url": page.url
        }
    except Exception as e:
        return {"success": False, "error": f"앞으로 가기 실패: {str(e)}"}


# 하위 호환성
async def browser_open(params: dict, project_path: str = ".") -> dict:
    """browser_navigate 별칭 (하위 호환성)"""
    return await browser_navigate(params, project_path)
