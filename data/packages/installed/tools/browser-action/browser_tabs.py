"""
browser_tabs.py - 탭 및 iframe 관리 도구

다중 탭 관리, iframe 전환 기능.

Version: 3.0.0
"""

from browser_session import BrowserSession, ensure_active


async def browser_tab_list(params: dict) -> dict:
    """열린 탭 목록 조회"""
    err = ensure_active()
    if err:
        return err

    session = BrowserSession.get_instance()
    tabs = []

    for tab_id in session.tab_ids:
        page = session.get_tab_page(tab_id)
        if page and not page.is_closed():
            try:
                tabs.append({
                    "tab_id": tab_id,
                    "title": await page.title(),
                    "url": page.url,
                    "active": tab_id == session.active_tab_id,
                })
            except Exception:
                tabs.append({
                    "tab_id": tab_id,
                    "title": "(접근 불가)",
                    "url": "",
                    "active": tab_id == session.active_tab_id,
                })

    return {
        "success": True,
        "tabs": tabs,
        "count": len(tabs),
        "active_tab": session.active_tab_id
    }


async def browser_tab_new(params: dict) -> dict:
    """새 탭 열기"""
    err = ensure_active()
    if err:
        return err

    url = params.get("url", "")
    session = BrowserSession.get_instance()

    try:
        tab_id = await session.new_tab(url if url else None)

        page = session.get_tab_page(tab_id)
        title = ""
        final_url = ""
        if page and not page.is_closed():
            try:
                title = await page.title()
                final_url = page.url
            except Exception:
                pass

        return {
            "success": True,
            "tab_id": tab_id,
            "title": title,
            "url": final_url,
            "snapshot_hint": "페이지 구조를 파악하려면 browser_snapshot을 호출하세요."
        }
    except Exception as e:
        return {"success": False, "error": f"새 탭 열기 실패: {str(e)}"}


async def browser_tab_switch(params: dict) -> dict:
    """탭 전환"""
    err = ensure_active()
    if err:
        return err

    tab_id = params.get("tab_id", "")
    if not tab_id:
        return {"success": False, "error": "tab_id가 필요합니다. browser_tab_list로 탭 목록을 확인하세요."}

    session = BrowserSession.get_instance()

    if session.switch_tab(tab_id):
        page = session.page
        title = ""
        url = ""
        if page:
            try:
                title = await session.raw_page.title()
                url = page.url
            except Exception:
                pass

        return {
            "success": True,
            "tab_id": tab_id,
            "title": title,
            "url": url,
            "snapshot_hint": "탭 전환 후 browser_snapshot을 호출하여 새 탭의 구조를 파악하세요."
        }
    else:
        return {
            "success": False,
            "error": f"탭 '{tab_id}'를 찾을 수 없거나 이미 닫혔습니다.",
            "available_tabs": session.tab_ids
        }


async def browser_tab_close(params: dict) -> dict:
    """탭 닫기"""
    err = ensure_active()
    if err:
        return err

    tab_id = params.get("tab_id", "")
    session = BrowserSession.get_instance()

    target = tab_id or session.active_tab_id

    if await session.close_tab(target):
        result = {
            "success": True,
            "closed_tab": target,
        }

        if session.tab_ids:
            result["active_tab"] = session.active_tab_id
            result["remaining_tabs"] = len(session.tab_ids)
        else:
            result["message"] = "모든 탭이 닫혔습니다. 새 탭을 열려면 browser_tab_new 또는 browser_navigate를 사용하세요."

        return result
    else:
        return {
            "success": False,
            "error": f"탭 '{target}'를 찾을 수 없습니다.",
            "available_tabs": session.tab_ids
        }


async def browser_iframe_list(params: dict) -> dict:
    """현재 페이지의 iframe 목록"""
    err = ensure_active()
    if err:
        return err

    session = BrowserSession.get_instance()
    page = session.raw_page

    try:
        frames = page.frames
        iframe_list = []

        for i, frame in enumerate(frames):
            if frame == page.main_frame:
                continue
            iframe_list.append({
                "index": i,
                "name": frame.name or "",
                "url": frame.url or "",
            })

        return {
            "success": True,
            "iframes": iframe_list,
            "count": len(iframe_list),
            "current_frame": "iframe" if session._active_frame else "main",
        }
    except Exception as e:
        return {"success": False, "error": f"iframe 목록 조회 실패: {str(e)}"}


async def browser_iframe_switch(params: dict) -> dict:
    """iframe으로 전환"""
    err = ensure_active()
    if err:
        return err

    name = params.get("name", "")
    index = params.get("index")
    url_pattern = params.get("url", "")

    session = BrowserSession.get_instance()
    page = session.raw_page

    try:
        frames = page.frames
        target_frame = None

        if name:
            for frame in frames:
                if frame.name == name:
                    target_frame = frame
                    break
        elif index is not None:
            if 0 <= index < len(frames):
                target_frame = frames[index]
        elif url_pattern:
            for frame in frames:
                if url_pattern in (frame.url or ""):
                    target_frame = frame
                    break

        if target_frame is None:
            return {
                "success": False,
                "error": "지정한 iframe을 찾을 수 없습니다.",
                "hint": "browser_iframe_list로 사용 가능한 iframe을 확인하세요."
            }

        session.set_active_frame(target_frame)

        return {
            "success": True,
            "switched_to": {
                "name": target_frame.name or "",
                "url": target_frame.url or "",
            },
            "snapshot_hint": "iframe 내부의 구조를 파악하려면 browser_snapshot을 호출하세요."
        }
    except Exception as e:
        return {"success": False, "error": f"iframe 전환 실패: {str(e)}"}


async def browser_iframe_reset(params: dict) -> dict:
    """iframe에서 메인 페이지로 복귀"""
    err = ensure_active()
    if err:
        return err

    session = BrowserSession.get_instance()

    was_in_iframe = session._active_frame is not None
    session.reset_frame()

    return {
        "success": True,
        "message": "메인 페이지로 돌아왔습니다." if was_in_iframe else "이미 메인 페이지입니다.",
        "snapshot_hint": "메인 페이지의 구조를 파악하려면 browser_snapshot을 호출하세요."
    }
