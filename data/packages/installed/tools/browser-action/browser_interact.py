"""
browser_interact.py - 브라우저 상호작용 도구

ref 기반 클릭, 더블클릭, 우클릭, 텍스트 입력, 옵션 선택,
hover, 드래그, 키 입력, 파일 업로드, 체크박스 토글.

Version: 4.0.0
"""

import asyncio
from browser_session import (
    BrowserSession, ensure_active, check_stale_ref, find_locator, find_by_selector,
    ACTION_TIMEOUT, LOCATOR_TIMEOUT,
)


# ─── 내부 유틸리티 ───

async def _resolve_locator(session, page, params: dict, input_mode: bool = False):
    """ref 또는 selector로 locator를 찾는 공통 로직.

    Returns: (locator, error_dict)
    """
    ref = params.get("ref", "")
    selector = params.get("selector", "")

    # selector 직접 지정 시 ref 불필요
    if selector:
        locator = await find_by_selector(page, selector)
        if locator is None:
            return None, {"success": False, "error": f"selector로 요소를 찾을 수 없습니다: {selector}"}
        return locator, None

    if not ref:
        return None, {"success": False, "error": "ref 또는 selector가 필요합니다. browser_snapshot을 먼저 호출하세요."}

    stale_err = check_stale_ref(session, ref)
    if stale_err:
        return None, stale_err

    element_info = session.get_ref(ref)
    locator = await find_locator(page, element_info, input_mode=input_mode)
    if locator is None:
        desc = params.get("element", "")
        return None, {"success": False, "error": f"요소를 찾을 수 없습니다: {desc} (ref={ref})"}

    return locator, None


def _stale_warning(session, ref: str, result: dict):
    """ref의 stale warning이 있으면 result에 추가"""
    if ref:
        element_info = session.get_ref(ref)
        if element_info and element_info.get("_stale_warning"):
            result["warning"] = element_info.pop("_stale_warning")


async def _wait_navigation(page, timeout=LOCATOR_TIMEOUT):
    """클릭 후 네비게이션 대기 (실패해도 무시)"""
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=timeout)
    except Exception:
        pass


# ─── 클릭 계열 ───

async def browser_click(params: dict) -> dict:
    """ref 또는 selector 기반으로 요소 클릭"""
    err = ensure_active()
    if err:
        return err

    session = BrowserSession.get_instance()
    page = session.page

    locator, loc_err = await _resolve_locator(session, page, params)
    if loc_err:
        return loc_err

    try:
        await locator.click(timeout=ACTION_TIMEOUT)
        await _wait_navigation(page)

        result = {
            "success": True,
            "clicked": f"{params.get('element', '')} ({params.get('ref', params.get('selector', ''))})",
            "url": page.url,
            "title": await session.raw_page.title()
        }
        _stale_warning(session, params.get("ref", ""), result)
        return result
    except Exception as e:
        return {"success": False, "error": f"클릭 실패: {str(e)}"}


async def browser_dblclick(params: dict) -> dict:
    """요소 더블클릭"""
    err = ensure_active()
    if err:
        return err

    session = BrowserSession.get_instance()
    page = session.page

    locator, loc_err = await _resolve_locator(session, page, params)
    if loc_err:
        return loc_err

    try:
        await locator.dblclick(timeout=ACTION_TIMEOUT)

        result = {
            "success": True,
            "double_clicked": f"{params.get('element', '')} ({params.get('ref', params.get('selector', ''))})",
            "url": page.url,
        }
        _stale_warning(session, params.get("ref", ""), result)
        return result
    except Exception as e:
        return {"success": False, "error": f"더블클릭 실패: {str(e)}"}


async def browser_rightclick(params: dict) -> dict:
    """요소 우클릭 (컨텍스트 메뉴)"""
    err = ensure_active()
    if err:
        return err

    session = BrowserSession.get_instance()
    page = session.page

    locator, loc_err = await _resolve_locator(session, page, params)
    if loc_err:
        return loc_err

    try:
        await locator.click(button="right", timeout=ACTION_TIMEOUT)

        result = {
            "success": True,
            "right_clicked": f"{params.get('element', '')} ({params.get('ref', params.get('selector', ''))})",
        }
        _stale_warning(session, params.get("ref", ""), result)
        return result
    except Exception as e:
        return {"success": False, "error": f"우클릭 실패: {str(e)}"}


# ─── 입력 계열 ───

async def browser_type(params: dict) -> dict:
    """ref 기반으로 입력 필드에 텍스트 입력"""
    err = ensure_active()
    if err:
        return err

    text = params.get("text", "")
    submit = params.get("submit", False)
    clear = params.get("clear", True)

    if not text and not submit:
        return {"success": False, "error": "text가 필요합니다."}

    session = BrowserSession.get_instance()
    page = session.page
    ref = params.get("ref", "")

    # role 검증 (ref가 있을 때만)
    if ref:
        element_info = session.get_ref(ref)
        if element_info:
            typable_roles = {"textbox", "searchbox", "combobox", "spinbutton", "textarea"}
            ref_role = element_info.get("role", "")
            if ref_role and ref_role not in typable_roles:
                return {
                    "success": False,
                    "error": f"ref '{ref}'는 입력 가능한 요소가 아닙니다 (role={ref_role}). "
                             f"textbox, searchbox 등의 입력 필드 ref를 사용하세요."
                }

    locator, loc_err = await _resolve_locator(session, page, params, input_mode=True)
    if loc_err:
        return loc_err

    try:
        if clear:
            await locator.clear()

        await locator.fill(text)

        if submit:
            await locator.press("Enter")
            await _wait_navigation(page)

        result = {
            "success": True,
            "typed": text,
            "element": f"{params.get('element', '')} ({params.get('ref', params.get('selector', ''))})",
            "submitted": submit,
            "url": page.url
        }
        _stale_warning(session, ref, result)
        return result
    except Exception as e:
        return {"success": False, "error": f"입력 실패: {str(e)}"}


async def browser_select_option(params: dict) -> dict:
    """드롭다운에서 옵션 선택"""
    err = ensure_active()
    if err:
        return err

    values = params.get("values", [])
    if not values:
        return {"success": False, "error": "values가 필요합니다."}

    session = BrowserSession.get_instance()
    page = session.page

    locator, loc_err = await _resolve_locator(session, page, params, input_mode=True)
    if loc_err:
        return loc_err

    try:
        await locator.select_option(values)

        result = {
            "success": True,
            "selected": values,
            "element": f"{params.get('element', '')} ({params.get('ref', params.get('selector', ''))})"
        }
        _stale_warning(session, params.get("ref", ""), result)
        return result
    except Exception as e:
        return {"success": False, "error": f"옵션 선택 실패: {str(e)}"}


async def browser_check(params: dict) -> dict:
    """체크박스/라디오 토글"""
    err = ensure_active()
    if err:
        return err

    checked = params.get("checked", True)

    session = BrowserSession.get_instance()
    page = session.page

    locator, loc_err = await _resolve_locator(session, page, params)
    if loc_err:
        return loc_err

    try:
        if checked:
            await locator.check(timeout=ACTION_TIMEOUT)
        else:
            await locator.uncheck(timeout=ACTION_TIMEOUT)

        result = {
            "success": True,
            "checked": checked,
            "element": f"{params.get('element', '')} ({params.get('ref', params.get('selector', ''))})"
        }
        _stale_warning(session, params.get("ref", ""), result)
        return result
    except Exception as e:
        return {"success": False, "error": f"체크 실패: {str(e)}"}


# ─── 파일 업로드 ───

async def browser_upload_file(params: dict) -> dict:
    """파일 input에 파일 업로드"""
    err = ensure_active()
    if err:
        return err

    files = params.get("files", [])
    if not files:
        return {"success": False, "error": "files(파일 경로 배열)가 필요합니다."}

    session = BrowserSession.get_instance()
    page = session.page

    locator, loc_err = await _resolve_locator(session, page, params)
    if loc_err:
        return loc_err

    try:
        await locator.set_input_files(files)

        return {
            "success": True,
            "uploaded": files,
            "element": f"{params.get('element', '')} ({params.get('ref', params.get('selector', ''))})"
        }
    except Exception as e:
        return {"success": False, "error": f"파일 업로드 실패: {str(e)}"}


# ─── hover / drag ───

async def browser_hover(params: dict) -> dict:
    """요소 위에 마우스 올리기"""
    err = ensure_active()
    if err:
        return err

    session = BrowserSession.get_instance()
    page = session.page

    locator, loc_err = await _resolve_locator(session, page, params)
    if loc_err:
        return loc_err

    try:
        await locator.hover(timeout=ACTION_TIMEOUT)

        result = {
            "success": True,
            "hovered": f"{params.get('element', '')} ({params.get('ref', params.get('selector', ''))})"
        }
        _stale_warning(session, params.get("ref", ""), result)
        return result
    except Exception as e:
        return {"success": False, "error": f"hover 실패: {str(e)}"}


async def browser_drag(params: dict) -> dict:
    """요소 드래그"""
    err = ensure_active()
    if err:
        return err

    source_ref = params.get("source_ref", "")
    target_ref = params.get("target_ref", "")

    if not source_ref or not target_ref:
        return {"success": False, "error": "source_ref와 target_ref가 필요합니다."}

    session = BrowserSession.get_instance()
    page = session.page

    for r in (source_ref, target_ref):
        stale_err = check_stale_ref(session, r)
        if stale_err:
            return stale_err

    source_info = session.get_ref(source_ref)
    target_info = session.get_ref(target_ref)

    try:
        source_locator = await find_locator(page, source_info)
        if not source_locator:
            return {"success": False, "error": f"소스 요소를 찾을 수 없습니다 (ref={source_ref})"}

        target_locator = await find_locator(page, target_info)
        if not target_locator:
            return {"success": False, "error": f"타겟 요소를 찾을 수 없습니다 (ref={target_ref})"}

        await source_locator.drag_to(target_locator)

        return {
            "success": True,
            "dragged": f"{params.get('source_element', '')} → {params.get('target_element', '')}"
        }
    except Exception as e:
        return {"success": False, "error": f"드래그 실패: {str(e)}"}


# ─── 키보드 ───

async def browser_press_key(params: dict) -> dict:
    """키보드 키 누르기"""
    err = ensure_active()
    if err:
        return err

    key = params.get("key", "")
    if not key:
        return {"success": False, "error": "key가 필요합니다."}

    session = BrowserSession.get_instance()
    page = session.page

    try:
        await page.keyboard.press(key)
        return {"success": True, "pressed": key}
    except Exception as e:
        return {"success": False, "error": f"키 입력 실패: {str(e)}"}
