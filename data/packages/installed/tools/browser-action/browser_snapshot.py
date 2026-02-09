"""
browser_snapshot.py - Accessibility Snapshot 도구

CDP(Chrome DevTools Protocol)를 사용하여 페이지의 접근성 트리를 캡처하고
각 요소에 ref를 부여하여 후속 도구에서 사용.

Version: 3.0.0
"""

from browser_session import (
    BrowserSession, ensure_active, format_snapshot_text,
)


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

        elements = []

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

                ref = session.add_ref(element_info)

                elements.append({
                    "ref": ref,
                    **element_info
                })

        session._snapshot_url = page.url

        snapshot_text = format_snapshot_text(elements)

        return {
            "success": True,
            "snapshot": elements,
            "snapshot_text": snapshot_text,
            "element_count": len(elements),
            "url": page.url,
            "title": await raw_page.title()
        }
    except Exception as e:
        return {"success": False, "error": f"스냅샷 캡처 실패: {str(e)}"}


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
