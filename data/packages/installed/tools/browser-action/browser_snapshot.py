"""
browser_snapshot.py - Accessibility Snapshot 도구

CDP(Chrome DevTools Protocol)를 사용하여 페이지의 접근성 트리를 캡처하고
각 요소에 ref를 부여하여 후속 도구에서 사용.

복잡한 페이지 감지:
  요소 수가 COMPLEX_PAGE_THRESHOLD를 초과하면 전체 스냅샷 대신
  축약 버전(interactive 요소 + 상위 텍스트)을 반환하고,
  browser_evaluate 사용을 안내합니다.

Version: 3.1.0
"""

from browser_session import (
    BrowserSession, ensure_active, format_snapshot_text,
)

# 이 값을 넘으면 "복잡한 페이지"로 판정하여 축약 모드로 전환
COMPLEX_PAGE_THRESHOLD = 500


async def browser_snapshot(params: dict) -> dict:
    """현재 페이지의 Accessibility Snapshot 캡처."""
    err = ensure_active()
    if err:
        return err

    session = BrowserSession.get_instance()
    page = session.page

    try:
        session.clear_refs()

        # CDP를 통해 접근성 트리 가져오기
        # iframe 모드일 때는 raw_page에서 CDP 세션 생성
        raw_page = session.raw_page
        cdp = await raw_page.context.new_cdp_session(raw_page)
        try:
            result = await cdp.send("Accessibility.getFullAXTree")
        finally:
            await cdp.detach()

        ax_nodes = result.get("nodes", [])

        if not ax_nodes:
            return {
                "success": True,
                "snapshot": [],
                "url": page.url,
                "title": await raw_page.title(),
                "message": "페이지에 접근성 요소가 없습니다."
            }

        elements = _extract_elements(ax_nodes, session)

        session._snapshot_url = page.url
        page_title = await raw_page.title()

        # 복잡한 페이지 감지: 요소가 너무 많으면 축약 모드
        if len(elements) > COMPLEX_PAGE_THRESHOLD:
            return _build_condensed_result(elements, page.url, page_title, session)

        # 일반 페이지: 전체 스냅샷 반환
        snapshot_text = format_snapshot_text(elements)

        return {
            "success": True,
            "snapshot": elements,
            "snapshot_text": snapshot_text,
            "element_count": len(elements),
            "url": page.url,
            "title": page_title
        }
    except Exception as e:
        return {"success": False, "error": f"스냅샷 캡처 실패: {str(e)}"}


def _extract_elements(ax_nodes: list, session) -> list:
    """접근성 노드에서 유효한 요소 추출"""
    interactive_roles = {
        "button", "link", "textbox", "searchbox", "combobox",
        "listbox", "option", "checkbox", "radio", "switch",
        "slider", "spinbutton", "tab", "tabpanel", "menuitem",
        "menuitemcheckbox", "menuitemradio", "treeitem",
        "gridcell", "row", "columnheader", "rowheader"
    }

    skip_roles = {
        "none", "generic", "presentation", "rootwebarea",
        "inlinetextbox", "statictext", "linebreak",
    }

    elements = []

    for ax_node in ax_nodes:
        role_obj = ax_node.get("role", {})
        role = role_obj.get("value", "") if isinstance(role_obj, dict) else str(role_obj)

        name_obj = ax_node.get("name", {})
        name = name_obj.get("value", "") if isinstance(name_obj, dict) else str(name_obj)

        value_obj = ax_node.get("value", {})
        value = value_obj.get("value", "") if isinstance(value_obj, dict) else str(value_obj)

        role_lower = role.lower()

        if role_lower in skip_roles:
            continue

        props = {}
        for prop in ax_node.get("properties", []):
            prop_name = prop.get("name", "")
            prop_val = prop.get("value", {})
            if isinstance(prop_val, dict):
                props[prop_name] = prop_val.get("value", "")
            else:
                props[prop_name] = prop_val

        is_interactive = role_lower in interactive_roles
        has_content = bool(name or value)

        if is_interactive or has_content:
            element_info = {
                "role": role_lower,
                "name": name[:100] if name else "",
            }

            if value:
                element_info["value"] = value[:100]
            if props.get("focused"):
                element_info["focused"] = True
            if props.get("disabled"):
                element_info["disabled"] = True
            if "checked" in props:
                element_info["checked"] = props["checked"]
            if props.get("selected"):
                element_info["selected"] = True

            # interactive 여부 태그 (축약 모드에서 필터링용)
            if is_interactive:
                element_info["_interactive"] = True

            ref = session.add_ref(element_info)

            elements.append({
                "ref": ref,
                **element_info
            })

    return elements


def _build_condensed_result(elements: list, url: str, title: str, session) -> dict:
    """복잡한 페이지용 축약 결과 생성

    전략:
    1. interactive 요소(버튼, 링크, 입력 등)는 전부 포함
    2. 텍스트 요소는 처음 100개만 포함 (페이지 구조 파악용)
    3. AI에게 browser_evaluate 사용을 안내
    """
    total = len(elements)

    interactive = []
    text_sample = []
    text_count = 0

    for el in elements:
        if el.get("_interactive"):
            interactive.append(el)
        else:
            text_count += 1
            if len(text_sample) < 100:
                text_sample.append(el)

    # 축약 요소 합치기 (interactive 전부 + 텍스트 샘플)
    condensed = interactive + text_sample

    # _interactive 태그 제거 (AI에게 전달 불필요)
    for el in condensed:
        el.pop("_interactive", None)
    for el in elements:
        el.pop("_interactive", None)

    snapshot_text = format_snapshot_text(condensed)

    guide = (
        f"⚠️ 복잡한 페이지입니다 (요소 {total}개, 임계값 {COMPLEX_PAGE_THRESHOLD}개 초과).\n"
        f"interactive 요소 {len(interactive)}개 + 텍스트 샘플 {len(text_sample)}개만 표시합니다.\n"
        f"나머지 텍스트 {text_count - len(text_sample)}개는 생략되었습니다.\n\n"
        f"💡 이 페이지에서 특정 데이터를 추출하려면 browser_evaluate를 사용하세요.\n"
        f"예시:\n"
        f'  browser_evaluate(expression="document.querySelector(\'h1\')?.textContent")\n'
        f'  browser_evaluate(expression="document.title")\n'
        f'  browser_evaluate(expression="[...document.querySelectorAll(\'table tr\')].map(r => r.textContent).join(\'\\n\')")\n\n'
        f"전체 스냅샷을 다시 시도하지 마세요. browser_evaluate로 필요한 데이터만 직접 추출하는 것이 훨씬 빠르고 정확합니다."
    )

    return {
        "success": True,
        "snapshot": condensed,
        "snapshot_text": snapshot_text,
        "element_count": total,
        "condensed": True,
        "interactive_count": len(interactive),
        "text_sample_count": len(text_sample),
        "text_omitted": text_count - len(text_sample),
        "url": url,
        "title": title,
        "guide": guide
    }


# 하위 호환성
async def browser_get_interactive(params: dict) -> dict:
    """browser_snapshot 별칭 (하위 호환성)"""
    result = await browser_snapshot(params)
    if result.get("success"):
        elements = result.get("snapshot", [])
        return {
            "success": True,
            "elements": [
                {
                    "tag": el.get("role", ""),
                    "type": el.get("role", ""),
                    "text": el.get("name", ""),
                    "selector": f"ref={el.get('ref', '')}",
                    "ref": el.get("ref", ""),
                }
                for el in elements
            ],
            "count": len(elements),
            "url": result.get("url", "")
        }
    return result
