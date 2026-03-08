"""
browser_snapshot.py - Accessibility Snapshot 도구

CDP(Chrome DevTools Protocol)를 사용하여 페이지의 접근성 트리를 캡처하고
각 요소에 ref를 부여하여 후속 도구에서 사용.

v5.0 변경:
- CDP 전체 작업에 타임아웃 적용 (절대 무한 대기 불가)
- DOM.describeNode 최대 100개로 축소 + 개별 타임아웃
- CDP 실패 시 selector 없이 graceful degradation
- 디버깅용 로깅 추가

Version: 5.0.0
"""

import asyncio

from browser_session import (
    BrowserSession, ensure_active, format_snapshot_text,
)

# 이 값을 넘으면 "복잡한 페이지"로 판정하여 축약 모드로 전환
COMPLEX_PAGE_THRESHOLD = 500

# CDP 관련 타임아웃 (초)
CDP_TOTAL_TIMEOUT = 10       # CDP 전체 작업 최대 시간
CDP_PER_NODE_TIMEOUT = 0.5   # 개별 노드 조회 최대 시간
CDP_MAX_SELECTOR_NODES = 100 # selector 추출 최대 노드 수


async def _extract_selectors_via_cdp(raw_page, ax_nodes):
    """
    CDP를 사용하여 접근성 노드들의 CSS selector를 추출.
    전체 작업에 타임아웃이 적용되며, 실패 시 빈 dict 반환 (graceful degradation).
    """
    selectors = {}

    try:
        cdp = await raw_page.context.new_cdp_session(raw_page)
        try:
            # backendDOMNodeId 수집
            dom_node_ids = []
            for ax_node in ax_nodes:
                backend_id = ax_node.get("backendDOMNodeId")
                if backend_id:
                    dom_node_ids.append(backend_id)

            # 최대 개수 제한
            target_ids = dom_node_ids[:CDP_MAX_SELECTOR_NODES]

            for backend_id in target_ids:
                try:
                    desc = await asyncio.wait_for(
                        cdp.send("DOM.describeNode", {"backendNodeId": backend_id}),
                        timeout=CDP_PER_NODE_TIMEOUT
                    )
                    node = desc.get("node", {})
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
                except asyncio.TimeoutError:
                    continue  # 이 노드는 건너뜀
                except Exception:
                    continue
        finally:
            try:
                await cdp.detach()
            except Exception:
                pass
    except Exception as e:
        print(f"[browser_snapshot] CDP selector 추출 실패 (무시하고 계속): {e}")

    return selectors


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

        # CDP로 접근성 트리 가져오기 (타임아웃 적용)
        ax_nodes = []
        try:
            cdp = await raw_page.context.new_cdp_session(raw_page)
            try:
                result = await asyncio.wait_for(
                    cdp.send("Accessibility.getFullAXTree"),
                    timeout=CDP_TOTAL_TIMEOUT
                )
                ax_nodes = result.get("nodes", [])
            finally:
                try:
                    await cdp.detach()
                except Exception:
                    pass
        except asyncio.TimeoutError:
            print(f"[browser_snapshot] Accessibility.getFullAXTree 타임아웃 ({CDP_TOTAL_TIMEOUT}초)")
            # 폴백: JS로 간이 접근성 트리 생성
            ax_nodes = await _fallback_snapshot_js(page)
        except Exception as e:
            print(f"[browser_snapshot] CDP 접근성 트리 실패: {e}")
            ax_nodes = await _fallback_snapshot_js(page)

        if not ax_nodes:
            return {
                "success": True,
                "snapshot": [],
                "url": page.url,
                "title": await raw_page.title(),
                "message": "페이지에 접근성 요소가 없습니다. browser_get_content 또는 browser_evaluate를 사용하세요."
            }

        # CSS selector 추출 (별도 타임아웃, 실패해도 계속)
        selectors = {}
        try:
            selectors = await asyncio.wait_for(
                _extract_selectors_via_cdp(raw_page, ax_nodes),
                timeout=CDP_TOTAL_TIMEOUT
            )
        except asyncio.TimeoutError:
            print(f"[browser_snapshot] selector 추출 타임아웃 (무시하고 계속)")
        except Exception:
            pass

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


async def _fallback_snapshot_js(page):
    """CDP 실패 시 JavaScript로 간이 접근성 정보를 수집하는 폴백"""
    try:
        nodes = await page.evaluate("""() => {
            const results = [];
            const interactiveSelectors = 'a, button, input, select, textarea, [role="button"], [role="link"], [role="textbox"], [role="searchbox"], [role="combobox"], [role="checkbox"], [role="radio"], [role="tab"], [role="menuitem"]';
            const elements = document.querySelectorAll(interactiveSelectors);

            for (let i = 0; i < Math.min(elements.length, 500); i++) {
                const el = elements[i];
                if (!el.offsetParent && el.tagName !== 'INPUT') continue;  // hidden 제외

                const role = el.getAttribute('role') || el.tagName.toLowerCase();
                const name = el.getAttribute('aria-label')
                    || el.textContent?.trim()?.substring(0, 100)
                    || el.getAttribute('placeholder')
                    || el.getAttribute('title')
                    || '';

                if (!name && role === 'div') continue;

                const node = { role: { value: role }, name: { value: name } };

                // input value
                if (el.value) {
                    node.value = { value: el.value.substring(0, 100) };
                }

                results.push(node);
            }
            return results;
        }""")
        return nodes or []
    except Exception as e:
        print(f"[browser_snapshot] JS 폴백도 실패: {e}")
        return []


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
        # JS 폴백에서 들어올 수 있는 태그명
        "a", "button", "input", "select", "textarea",
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
