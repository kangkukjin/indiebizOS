"""
browser_interact.py - 브라우저 상호작용 도구

ref 기반 클릭, 더블클릭, 우클릭, 텍스트 입력, 옵션 선택,
hover, 드래그, 키 입력, 파일 업로드, 체크박스 토글.

Version: 4.0.0
"""

import asyncio
from browser_session import (
    BrowserSession, ensure_active, check_stale_ref, find_locator, find_by_selector,
    ACTION_TIMEOUT, LOCATOR_TIMEOUT, _identity_locator,
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
        # 반복 행의 동일 이름은 새 snapshot으로도 구분되지 않는다. 임의 nth 선택 금지.
        role, name = element_info.get("role", ""), element_info.get("name", "")
        count = 0
        if role and name:
            try:
                count = await _identity_locator(page, role, name).count()
            except Exception:
                pass
        if count > 1:
            return None, {
                "success": False, "error_code": "REF_AMBIGUOUS",
                "error": f"같은 이름·역할의 요소가 {count}개입니다 (ref={ref}). "
                         "content/evaluate로 행·링크 주소를 확인하고 고유한 selector로 지정하세요.",
                "candidate_count": count,
                "recovery": {"reason": "동명 요소 중복", "use": "selector", "candidate_count": count},
            }
        desc = params.get("element", "")
        return None, {
            "success": False,
            "error": f"요소를 찾을 수 없습니다: {desc} (ref={ref}). "
                     "화면 변경 후에는 browser_snapshot을 다시 호출하고 새 ref를 선택하세요.",
            "error_code": "REF_NOT_RESOLVED",
            "recovery": {"op": "snapshot", "reason": "요소가 사라졌거나 신원을 유일하게 확인할 수 없습니다."},
        }

    return locator, None


def _element_label(session, params):
    """호출자가 설명을 생략해도 snapshot의 대상 이름을 영수증에 남긴다."""
    ref = params.get("ref", "")
    info = session.get_ref(ref) if ref else {}
    name = params.get("element") or (info or {}).get("name") or (info or {}).get("role") or "요소"
    return f"{name} ({ref or params.get('selector', '')})"


async def _visible_drag_point(locator, raw_page):
    """메인 viewport 안에서 실제 대상에 닿는 점. 긴 영역은 보이는 부분만 사용."""
    box = await locator.bounding_box()
    if not box:
        return None
    viewport = await raw_page.evaluate("({width:innerWidth,height:innerHeight})")
    left, top = max(1, box["x"]), max(1, box["y"])
    right = min(viewport["width"] - 1, box["x"] + box["width"])
    bottom = min(viewport["height"] - 1, box["y"] + box["height"])
    if right <= left or bottom <= top:
        return None
    for fx, fy in ((.5, .5), (.5, .15), (.5, .85), (.15, .5), (.85, .5)):
        x, y = left + (right - left) * fx, top + (bottom - top) * fy
        hit = await locator.evaluate("""(el, offset) => {
            const r = el.getBoundingClientRect();
            const hit = el.ownerDocument.elementFromPoint(r.x + offset.x, r.y + offset.y);
            return el.isConnected && (hit === el || el.contains(hit));
        }""", {"x": x - box["x"], "y": y - box["y"]})
        if hit:
            return {"x": x, "y": y}
    return None


async def _guarded_drag(session, source, target):
    """좌표를 확정한 뒤 자동 스크롤 없이 조작하고 실제 시작 대상·스크롤을 감시."""
    raw_page = session.raw_page
    await source.scroll_into_view_if_needed(timeout=ACTION_TIMEOUT)
    if not await _visible_drag_point(target, raw_page):
        await target.scroll_into_view_if_needed(timeout=ACTION_TIMEOUT)
    start = await _visible_drag_point(source, raw_page)
    end = await _visible_drag_point(target, raw_page)
    if not start or not end:
        return {"success": False, "error_code": "DRAG_NOT_IN_VIEW",
                "error": "출발점과 도착점을 한 화면에서 확인할 수 없습니다. 화면 안의 작은 대상이나 칸 제목을 선택하세요."}

    target_handle = await target.element_handle()
    guard = await source.evaluate_handle("""(el, target) => {
        const doc = el.ownerDocument;
        const state = {scrolled:false, wrong_source:false, wrong_target:false, started:false, html5:false,
                       actual_source:null};
        const scrolls = [];
        for (const node of [el,target])
            for (let p=node; p; p=p.parentElement) scrolls.push([p,p.scrollLeft,p.scrollTop]);
        const win = doc.defaultView, x=win.scrollX, y=win.scrollY;
        const changed = () => win.scrollX!==x || win.scrollY!==y ||
            scrolls.some(([p,x,y])=>p.scrollLeft!==x || p.scrollTop!==y);
        const scroll = () => {state.scrolled ||= changed();};
        const check = e => {
            state.scrolled ||= changed();
            if (e.type==='pointerdown' || e.type==='mousedown' || e.type==='dragstart') {
                const valid = e.target===el || el.contains(e.target) ||
                    (e.type==='dragstart' && e.target===el.closest('[draggable="true"]'));
                state.wrong_source ||= !valid;
                state.started ||= valid;
                state.html5 ||= e.type==='dragstart';
                state.actual_source = e.target.getAttribute('aria-label') ||
                    e.target.id || (e.target.textContent || '').trim().slice(0,200);
            }
            if (e.type==='drop') state.wrong_target ||= !(e.target===target || target.contains(e.target));
            if (state.scrolled || state.wrong_source || state.wrong_target || !el.isConnected || !target.isConnected) {
                e.preventDefault(); e.stopImmediatePropagation();
            }
        };
        const types=['pointerdown','mousedown','dragstart','dragover','drop','pointerup'];
        doc.addEventListener('scroll',scroll,true);
        types.forEach(t=>doc.addEventListener(t,check,true));
        return {read:()=>({...state,scrolled:state.scrolled||changed(),
                            detached:!el.isConnected || !target.isConnected}),
                cleanup:()=>{doc.removeEventListener('scroll',scroll,true);
                    types.forEach(t=>doc.removeEventListener(t,check,true));}};
    }""", target_handle)
    await target_handle.dispose()
    pressed = False
    completed = False
    try:
        await raw_page.mouse.move(**start)
        pressed = True
        await raw_page.mouse.down()
        await raw_page.mouse.move(**end, steps=12)
        # HTML5 dragover is dispatched on a second move on all supported Chromium versions.
        await raw_page.mouse.move(**end)
        observed = await guard.evaluate("g=>g.read()")
        if any(observed[k] for k in ("scrolled", "wrong_source", "wrong_target", "detached")) or not observed["started"]:
            return {"success": False, "error_code": "DRAG_TARGET_UNVERIFIED",
                    "error": "드래그 중 스크롤 또는 시작 대상 불일치를 감지했습니다. 상태를 다시 읽고 대상을 선택하세요.",
                    "scrolled_during_drag": observed["scrolled"], "observation": observed}
        await raw_page.mouse.up()
        pressed = False
        completed = True
        observed = await guard.evaluate("g=>g.read()")
        if any(observed[k] for k in ("scrolled", "wrong_source", "wrong_target", "detached")):
            return {"success": False, "error_code": "DRAG_TARGET_UNVERIFIED",
                    "error": "드래그 중 화면이 변경됐습니다. 실제 결과를 다시 확인하세요.",
                    "scrolled_during_drag": observed["scrolled"], "observation": observed}
        return {"success": True, "scrolled_during_drag": False, "observation": observed,
                "verification": "gesture_only", "snapshot_hint": "조작 완료는 저장 성공을 뜻하지 않습니다. 화면과 저장 결과를 다시 읽어 확인하세요."}
    finally:
        try:
            if not completed:
                await raw_page.keyboard.press("Escape")
        finally:
            try:
                if pressed:
                    await raw_page.mouse.up()
            finally:
                try:
                    await guard.evaluate("g=>g.cleanup()")
                finally:
                    await guard.dispose()


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
            "clicked": _element_label(session, params),
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
            "double_clicked": _element_label(session, params),
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
            "right_clicked": _element_label(session, params),
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
            "element": _element_label(session, params),
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

    from browser_session import select_request
    try:
        mode, values = select_request(params)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    session = BrowserSession.get_instance()
    page = session.page

    locator, loc_err = await _resolve_locator(session, page, params, input_mode=True)
    if loc_err:
        return loc_err

    try:
        selected = await locator.select_option(label=values) if mode == "label" else await locator.select_option(values)

        result = {
            "success": True,
            "selected": selected,
            "requested": values,
            "element": _element_label(session, params)
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
            "element": _element_label(session, params)
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

    files = params.get("files")
    if files is None and params.get("path") is not None:  # 단수 path → 배열 래핑(자연어 호환)
        files = params["path"]
    if isinstance(files, str):
        files = [files]
    if not files:
        return {"success": False, "error": "files(또는 path) 파일 경로가 필요합니다."}

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
            "element": _element_label(session, params)
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
            "hovered": _element_label(session, params)
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

        result = await _guarded_drag(session, source_locator, target_locator)
        result.update(
            source={"ref": source_ref, "name": source_info.get("name", ""), "role": source_info.get("role", "")},
            target={"ref": target_ref, "name": target_info.get("name", ""), "role": target_info.get("role", "")},
            dragged=f"{_element_label(session, {'ref': source_ref})} → {_element_label(session, {'ref': target_ref})}",
        )
        return result
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
