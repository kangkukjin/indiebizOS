"""
browser_snapshot.py - Accessibility Snapshot 도구

CDP(Chrome DevTools Protocol)를 사용하여 페이지의 접근성 트리를 캡처하고
각 요소에 ref를 부여하여 후속 도구에서 사용.

v4.0 변경:
- Shadow DOM 지원 (pierceOpenShadowRoots)
- CSS selector 생성 (요소 식별 정확도 향상)
- 복잡한 페이지 축약 모드 개선
- backendDOMNodeId 기반 selector 추출

Version: 4.0.0
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

        raw_page = session.raw_page
        cdp = await raw_page.context.new_cdp_session(raw_page)
        try:
            # Shadow DOM 포함하여 전체 트리 가져오기
            result = await cdp.send("Accessibility.getFullAXTree")
            ax_nodes = result.get("nodes", [])

            # backendDOMNodeId가 있는 노드들의 CSS selector 추출 시도
            selectors = {}
            dom_node_ids = []
            for ax_node in ax_nodes:
                backend_id = ax_node.get("backendDOMNodeId")
                if backend_id:
                    dom_node_ids.append(backend_id)

            # 배치로 CSS selector 추출 (성능 최적화)
            if dom_node_ids:
                try:
                    for backend_id in dom_node_ids[:300]:  # 최대 300개까지만
                        try:
                            desc = await cdp.send("DOM.describeNode", {"backendNodeId": backend_id})
                            node = desc.get("node", {})
                            node_id = node.get("nodeId", 0)
                            if node_id:
                                # DOM.getNodeForLocation 대신 CSS path 직접 생성
                                attrs = node.get("attributes", [])
                                tag = node.get("localName", "")
                                css_id = ""
                                css_class = ""
                                for i in range(0, len(attrs) - 1, 2):
                                    if attrs[i] == "id":
                                        css_id = attrs[i + 1]
                                    elif attrs[i] == "class":
                                        css_class = attrs[i + 1]

                                if css_id:
                                    selectors[backend_id] = f"#{css_id}"
                                elif tag and css_class:
                                    first_class = css_class.split()[0]
                                    selectors[backend_id] = f"{tag}.{first_class}"
                        except Exception:
                            pass
                except Exception:
                    pass
        finally:
            await cdp.detach()

        if not ax_nodes:
            return {
                "success": True,
                "snapshot": [],
                "url": page.url,
                "title": await raw_page.title(),
                "message": "페이지에 접근성 요소가 없습니다."
            }

        elements = _extract_elements(ax_nodes, session, selectors)

        session._snapshot_url = page.url
        page_title = await raw_page.title()

        # 복잡한 페이지 감지
        if len(elements) > COMPLEX_PAGE_THRESHOLD:
            return _build_condensed_result(elements, page.url, page_title, session)

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


def _extract_elements(ax_nodes: list, session, selectors: dict = None) -> list:
    """접근성 노드에서 유효한 요소 추출"""
    if selectors is None:
        selectors = {}

    interactive_roles = {
        "button", "link", "textbox", "searchbox", "combobox",
        "listbox", "option", "checkbox", "radio", "switch",
        "slider", "spinbutton", "tab", "tabpanel", "menuitem",
        "menuitemcheckbox", "menuitemradio", "treeitem",
        "gridcell", "row", "columnheader", "rowheader",
        "progressbar", "scrollbar", "meter",
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
            if props.get("required"):
                element_info["required"] = True
            if props.get("expanded") is not None:
                element_info["expanded"] = props["expanded"]

            # CSS selector 추가 (있으면)
            backend_id = ax_node.get("backendDOMNodeId")
            if backend_id and backend_id in selectors:
                element_info["selector"] = selectors[backend_id]

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
    """복잡한 페이지용 축약 결과 생성"""
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

    condensed = interactive + text_sample

    # _interactive 태그 제거
    for el in condensed:
        el.pop("_interactive", None)
    for el in elements:
        el.pop("_interactive", None)

    snapshot_text = format_snapshot_text(condensed)

    guide = (
        f"복잡한 페이지입니다 (요소 {total}개, 임계값 {COMPLEX_PAGE_THRESHOLD}개 초과).\n"
        f"interactive 요소 {len(interactive)}개 + 텍스트 샘플 {len(text_sample)}개만 표시합니다.\n"
        f"나머지 텍스트 {text_count - len(text_sample)}개는 생략되었습니다.\n\n"
        f"이 페이지에서 특정 데이터를 추출하려면 browser_evaluate를 사용하세요.\n"
        f"예시:\n"
        f'  browser_evaluate(expression="document.querySelector(\'h1\')?.textContent")\n'
        f'  browser_evaluate(expression="[...document.querySelectorAll(\'table tr\')].map(r => r.textContent).join(\'\\n\')")'
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
