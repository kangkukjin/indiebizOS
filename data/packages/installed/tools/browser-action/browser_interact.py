"""
browser_interact.py - 브라우저 상호작용 도구

ref 기반 클릭, 텍스트 입력, 옵션 선택, hover, 드래그, 키 입력.

Version: 3.0.0
"""

from browser_session import (
    BrowserSession, ensure_active, check_stale_ref, find_locator,
    ACTION_TIMEOUT, LOCATOR_TIMEOUT,
)


async def browser_click(params: dict) -> dict:
    """ref 기반으로 요소 클릭"""
    err = ensure_active()
    if err:
        return err

    element_desc = params.get("element", "")
    ref = params.get("ref", "")

    if not ref:
        return {"success": False, "error": "ref가 필요합니다. browser_snapshot을 먼저 호출하세요."}

    session = BrowserSession.get_instance()
    page = session.page

    stale_err = check_stale_ref(session, ref)
    if stale_err:
        return stale_err
    element_info = session.get_ref(ref)

    try:
        locator = await find_locator(page, element_info)
        if locator is None:
            return {"success": False, "error": f"요소를 찾을 수 없습니다: {element_desc} (ref={ref})"}

        await locator.click(timeout=ACTION_TIMEOUT)

        try:
            await page.wait_for_load_state("load", timeout=LOCATOR_TIMEOUT)
        except Exception:
            pass

        result = {
            "success": True,
            "clicked": f"{element_desc} ({ref})",
            "url": page.url,
            "title": await session.raw_page.title()
        }
        if element_info.get("_stale_warning"):
            result["warning"] = element_info.pop("_stale_warning")
        return result
    except Exception as e:
        return {"success": False, "error": f"클릭 실패: {str(e)}"}


async def browser_type(params: dict) -> dict:
    """ref 기반으로 입력 필드에 텍스트 입력"""
    err = ensure_active()
    if err:
        return err

    element_desc = params.get("element", "")
    ref = params.get("ref", "")
    text = params.get("text", "")
    submit = params.get("submit", False)
    clear = params.get("clear", True)

    if not ref:
        return {"success": False, "error": "ref가 필요합니다. browser_snapshot을 먼저 호출하세요."}
    if not text and not submit:
        return {"success": False, "error": "text가 필요합니다."}

    session = BrowserSession.get_instance()
    page = session.page

    stale_err = check_stale_ref(session, ref)
    if stale_err:
        return stale_err
    element_info = session.get_ref(ref)

    typable_roles = {"textbox", "searchbox", "combobox", "spinbutton", "textarea"}
    ref_role = element_info.get("role", "")
    if ref_role and ref_role not in typable_roles:
        return {
            "success": False,
            "error": f"ref '{ref}'는 입력 가능한 요소가 아닙니다 (role={ref_role}, name='{element_info.get('name', '')}'). "
                     f"textbox, searchbox 등의 입력 필드 ref를 사용하세요."
        }

    try:
        locator = await find_locator(page, element_info, input_mode=True)
        if locator is None:
            return {"success": False, "error": f"입력 필드를 찾을 수 없습니다: {element_desc} (ref={ref})"}

        if clear:
            await locator.clear()

        await locator.fill(text)

        if submit:
            await locator.press("Enter")
            try:
                await page.wait_for_load_state("load", timeout=LOCATOR_TIMEOUT)
            except Exception:
                pass

        result = {
            "success": True,
            "typed": text,
            "element": f"{element_desc} ({ref})",
            "submitted": submit,
            "url": page.url
        }
        if element_info.get("_stale_warning"):
            result["warning"] = element_info.pop("_stale_warning")
        return result
    except Exception as e:
        return {"success": False, "error": f"입력 실패: {str(e)}"}


async def browser_select_option(params: dict) -> dict:
    """드롭다운에서 옵션 선택"""
    err = ensure_active()
    if err:
        return err

    element_desc = params.get("element", "")
    ref = params.get("ref", "")
    values = params.get("values", [])

    if not ref:
        return {"success": False, "error": "ref가 필요합니다."}
    if not values:
        return {"success": False, "error": "values가 필요합니다."}

    session = BrowserSession.get_instance()
    page = session.page

    stale_err = check_stale_ref(session, ref)
    if stale_err:
        return stale_err
    element_info = session.get_ref(ref)

    try:
        locator = await find_locator(page, element_info, input_mode=True)
        if locator is None:
            return {"success": False, "error": f"select 요소를 찾을 수 없습니다: {element_desc} (ref={ref})"}

        await locator.select_option(values)

        result = {
            "success": True,
            "selected": values,
            "element": f"{element_desc} ({ref})"
        }
        if element_info.get("_stale_warning"):
            result["warning"] = element_info.pop("_stale_warning")
        return result
    except Exception as e:
        return {"success": False, "error": f"옵션 선택 실패: {str(e)}"}


async def browser_hover(params: dict) -> dict:
    """요소 위에 마우스 올리기"""
    err = ensure_active()
    if err:
        return err

    element_desc = params.get("element", "")
    ref = params.get("ref", "")

    if not ref:
        return {"success": False, "error": "ref가 필요합니다."}

    session = BrowserSession.get_instance()
    page = session.page

    stale_err = check_stale_ref(session, ref)
    if stale_err:
        return stale_err
    element_info = session.get_ref(ref)

    try:
        locator = await find_locator(page, element_info)
        if locator is None:
            return {"success": False, "error": f"요소를 찾을 수 없습니다: {element_desc} (ref={ref})"}

        await locator.hover(timeout=ACTION_TIMEOUT)

        result = {
            "success": True,
            "hovered": f"{element_desc} ({ref})"
        }
        if element_info.get("_stale_warning"):
            result["warning"] = element_info.pop("_stale_warning")
        return result
    except Exception as e:
        return {"success": False, "error": f"hover 실패: {str(e)}"}


async def browser_drag(params: dict) -> dict:
    """요소 드래그"""
    err = ensure_active()
    if err:
        return err

    source_desc = params.get("source_element", "")
    source_ref = params.get("source_ref", "")
    target_desc = params.get("target_element", "")
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
            return {"success": False, "error": f"소스 요소를 찾을 수 없습니다: {source_desc} (ref={source_ref})"}

        target_locator = await find_locator(page, target_info)
        if not target_locator:
            return {"success": False, "error": f"타겟 요소를 찾을 수 없습니다: {target_desc} (ref={target_ref})"}

        await source_locator.drag_to(target_locator)

        result = {
            "success": True,
            "dragged": f"{source_desc} → {target_desc}"
        }
        if source_info.get("_stale_warning"):
            result["warning"] = source_info.pop("_stale_warning")
        return result
    except Exception as e:
        return {"success": False, "error": f"드래그 실패: {str(e)}"}


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

        return {
            "success": True,
            "pressed": key
        }
    except Exception as e:
        return {"success": False, "error": f"키 입력 실패: {str(e)}"}
