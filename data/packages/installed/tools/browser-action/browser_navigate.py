"""
browser_navigate.py - 브라우저 네비게이션 도구

URL 이동, 히스토리 앞/뒤 이동, HTTP 상태코드 반환, 리다이렉트 추적.

Version: 4.0.0
"""

import asyncio
from browser_session import (
    BrowserSession, ensure_active,
    NAVIGATE_TIMEOUT, BLOCKED_URL_SCHEMES,
)


async def browser_navigate(params: dict, project_path: str = ".") -> dict:
    """브라우저를 열고 URL로 이동. HTTP 상태코드와 리다이렉트 체인 추적."""
    url = params.get("url", "")
    headless = params.get("headless", True)
    wait_for = params.get("wait_for", "domcontentloaded")

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

        # 리다이렉트 체인 추적
        redirects = []
        status_code = 0

        def _on_response(response):
            nonlocal status_code
            # 메인 프레임 응답만 추적
            if response.request.is_navigation_request():
                if response.status in (301, 302, 303, 307, 308):
                    redirects.append({
                        "url": response.url,
                        "status": response.status,
                    })
                else:
                    status_code = response.status

        page_raw = session.raw_page
        page_raw.on("response", _on_response)

        try:
            response = await page_raw.goto(url, wait_until=wait_for, timeout=NAVIGATE_TIMEOUT)
            if response:
                status_code = status_code or response.status
        except Exception as goto_err:
            err_msg = str(goto_err).lower()
            if "closed" in err_msg or "disposed" in err_msg or "crashed" in err_msg:
                await session._close_internal()
                page = await session.ensure_browser(headless=headless)
                session.clear_refs()
                page_raw = session.raw_page
                response = await page_raw.goto(url, wait_until=wait_for, timeout=NAVIGATE_TIMEOUT)
                if response:
                    status_code = response.status
            elif "timeout" in err_msg:
                # 타임아웃이지만 페이지가 부분 로드되었을 수 있음
                status_code = -1
            else:
                raise
        finally:
            try:
                page_raw.remove_listener("response", _on_response)
            except Exception:
                pass

        title = await page_raw.title()
        final_url = page_raw.url

        result = {
            "success": True,
            "title": title,
            "url": final_url,
            "status_code": status_code,
            "tab_id": session.active_tab_id,
        }

        if redirects:
            result["redirects"] = redirects

        if status_code == -1:
            result["warning"] = "타임아웃으로 페이지가 완전히 로드되지 않았을 수 있습니다."

        if status_code >= 400:
            result["warning"] = f"HTTP {status_code} 에러가 발생했습니다."

        return result
    except Exception as e:
        err_str = str(e).lower()
        # 에러 분류
        if "net::err_name_not_resolved" in err_str:
            return {"success": False, "error": f"도메인을 찾을 수 없습니다: {url}"}
        elif "net::err_connection_refused" in err_str:
            return {"success": False, "error": f"연결이 거부되었습니다: {url}"}
        elif "net::err_connection_timed_out" in err_str or "timeout" in err_str:
            return {"success": False, "error": f"연결 시간 초과: {url}"}
        elif "net::err_ssl" in err_str or "ssl" in err_str:
            return {"success": False, "error": f"SSL/TLS 인증서 오류: {url}"}
        elif "net::err_too_many_redirects" in err_str:
            return {"success": False, "error": f"리다이렉트가 너무 많습니다: {url}"}
        else:
            return {"success": False, "error": f"페이지 열기 실패: {str(e)}"}


async def browser_navigate_back(params: dict) -> dict:
    """브라우저 히스토리에서 이전 페이지로 이동"""
    err = ensure_active()
    if err:
        return err

    try:
        session = BrowserSession.get_instance()
        page = session.raw_page
        session.clear_refs()

        response = await page.go_back(wait_until="domcontentloaded", timeout=NAVIGATE_TIMEOUT)

        return {
            "success": True,
            "title": await page.title(),
            "url": page.url,
            "status_code": response.status if response else 0,
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
        page = session.raw_page
        session.clear_refs()

        response = await page.go_forward(wait_until="domcontentloaded", timeout=NAVIGATE_TIMEOUT)

        return {
            "success": True,
            "title": await page.title(),
            "url": page.url,
            "status_code": response.status if response else 0,
        }
    except Exception as e:
        return {"success": False, "error": f"앞으로 가기 실패: {str(e)}"}
