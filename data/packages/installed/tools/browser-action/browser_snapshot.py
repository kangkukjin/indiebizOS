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
import json
import uuid

from browser_session import (
    BrowserSession, ensure_active,
)

# 스냅샷 구조화 배열의 직렬화 상한(요소 '개수'가 아니라 '크기'로 묶는다).
# IBL 엔진이 step 결과를 문자열로 escape(~1.6×)하고 final_result로 복제(2×)하므로,
# 최종 페이로드 ≈ raw × ~3.2. 이를 감안해 raw를 작게 잡아 MCP 토큰 한도 안쪽에
# '여유 있게' 들어오도록 보수적으로 설정 → 페이지 크기 무관하게 재튜닝 불필요.
MAX_RESULT_CHARS = 7000

# CDP 관련 타임아웃 (초)
CDP_TOTAL_TIMEOUT = 10       # CDP 전체 작업 최대 시간
CDP_PER_NODE_TIMEOUT = 0.5   # 개별 노드 조회 최대 시간
CDP_MAX_SELECTOR_NODES = 100 # selector 추출 최대 노드 수


async def _extract_selectors_via_cdp(raw_page, ax_nodes, cdp=None):
    """
    CDP를 사용하여 접근성 노드들의 CSS selector를 추출.
    전체 작업에 타임아웃이 적용되며, 실패 시 빈 dict 반환 (graceful degradation).
    """
    selectors = {}
    owned = cdp is None

    try:
        if owned:
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
                if owned:
                    await cdp.detach()
            except Exception:
                pass
    except Exception as e:
        print(f"[browser_snapshot] CDP selector 추출 실패 (무시하고 계속): {e}")

    return selectors


async def _frame_cdp(raw_page, frame):
    """OOPIF는 자신의 target, 같은 프로세스의 frame은 페이지 target을 쓴다."""
    if frame is not raw_page:
        try:
            return await raw_page.context.new_cdp_session(frame), True
        except Exception:
            pass
    return await raw_page.context.new_cdp_session(raw_page), False


async def _read_frame_tree(cdp, page, raw_page, dedicated=False):
    """실제 Frame의 기본 실행 문맥으로 frameId를 찾는다(URL·이름 중복에도 안전)."""
    if page is raw_page or dedicated:
        return await cdp.send("Accessibility.getFullAXTree")
    marker = "__ibl_snapshot_" + uuid.uuid4().hex
    contexts = []

    def created(event):
        context = event["context"]
        if context.get("auxData", {}).get("isDefault"):
            contexts.append(context)
    cdp.on("Runtime.executionContextCreated", created)
    try:
        await page.evaluate("key => { globalThis[key] = true; }", marker)
        await cdp.send("Runtime.enable")
        for context in contexts:
            try:
                result = await cdp.send("Runtime.evaluate", {
                    "contextId": context["id"],
                    "expression": f"globalThis[{json.dumps(marker)}] === true",
                    "returnByValue": True,
                })
                if result.get("result", {}).get("value") is True:
                    return await cdp.send("Accessibility.getFullAXTree", {
                        "frameId": context["auxData"]["frameId"],
                    })
            except Exception:
                continue
        raise RuntimeError("활성 iframe의 접근성 문맥을 찾지 못했습니다")
    finally:
        cdp.remove_listener("Runtime.executionContextCreated", created)
        try:
            await asyncio.wait_for(
                page.evaluate("key => { delete globalThis[key]; }", marker), timeout=1)
        except Exception:
            pass


async def browser_snapshot(params: dict) -> dict:
    """현재 선택한 페이지/iframe의 접근성 트리와 프레임 문맥을 반환한다."""
    err = ensure_active()
    if err:
        return err
    session = BrowserSession.get_instance()
    page, raw_page = session.page, session.raw_page
    cdp = None
    try:
        session.clear_refs()
        frame = {"kind": "main" if page is raw_page else "iframe",
                 "name": "" if page is raw_page else page.name, "url": page.url}
        selectors = {}
        try:
            cdp, dedicated = await asyncio.wait_for(
                _frame_cdp(raw_page, page), timeout=CDP_TOTAL_TIMEOUT)
            result = await asyncio.wait_for(
                _read_frame_tree(cdp, page, raw_page, dedicated), timeout=CDP_TOTAL_TIMEOUT)
            ax_nodes = result.get("nodes", [])
        except Exception as exc:
            print(f"[browser_snapshot] CDP 실패, 현재 프레임 JS 폴백: {exc}")
            ax_nodes = await asyncio.wait_for(_fallback_snapshot_js(page), timeout=CDP_TOTAL_TIMEOUT)
        else:
            # selector 추출 실패는 이미 얻은 AX 신원을 버릴 이유가 아니다.
            try:
                selectors = await asyncio.wait_for(
                    _extract_selectors_via_cdp(raw_page, ax_nodes, cdp),
                    timeout=CDP_TOTAL_TIMEOUT)
            except Exception:
                pass
        elements = _extract_elements(ax_nodes, session, selectors)
        session._snapshot_url = page.url
        title = await asyncio.wait_for(page.title(), timeout=CDP_TOTAL_TIMEOUT)
        result = _finalize_snapshot(elements, page.url, title)
        result["frame"] = frame
        if not ax_nodes:
            result["message"] = "접근성 요소가 없습니다. content/evaluate로 현재 프레임을 확인하세요."
        return result
    except Exception as exc:
        return {"success": False, "error": f"스냅샷 캡처 실패: {exc}"}
    finally:
        if cdp is not None:
            try:
                await asyncio.wait_for(cdp.detach(), timeout=1)
            except Exception:
                pass


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
        "disclosuretriangle",
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
        role = str(role_obj.get("value") or "") if isinstance(role_obj, dict) else str(role_obj or "")

        name_obj = ax_node.get("name", {})
        name = str(name_obj.get("value") or "") if isinstance(name_obj, dict) else str(name_obj or "")

        value_obj = ax_node.get("value", {})
        value = value_obj.get("value", "") if isinstance(value_obj, dict) else value_obj
        # AX slider/progress values are numbers (YouTube's seek position included).
        # Keep zero and false visible, and only slice their display string.
        value = "" if value is None else str(value)

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


def _strip_for_output(el: dict) -> dict:
    """출력용 요소 사본 — ref 클릭에 불필요한 필드 제거.
    selector는 _ref_map에 그대로 남아 클릭은 정상(ref→_ref_map 해소). 여기선 출력 군살만 제거."""
    return {k: v for k, v in el.items() if k not in ("selector", "_interactive")}


def _finalize_snapshot(elements: list, url: str, title: str) -> dict:
    """스냅샷을 '직렬화 크기'에 묶어 반환한다.

    - interactive 요소(행동 표면)를 먼저 채우고, 남는 예산에 텍스트를 채운다.
    - 누적 크기가 MAX_RESULT_CHARS를 넘으면 거기서 멈추고, 생략 개수 + 좁히는 법(guide)을
      돌려준다 — 전부 토해 MCP 토큰 한도를 넘기고 파일 덤프로 빠지는 것을 원천 차단.
    - 페이지 크기·콘텐츠 종류와 무관하게 결과가 항상 한도 안쪽 → 매직 넘버 재튜닝 불필요.
    """
    total = len(elements)

    # 행동 표면을 먼저 보존: interactive → 텍스트 순
    interactive = [el for el in elements if el.get("_interactive")]
    text = [el for el in elements if not el.get("_interactive")]
    ordered = interactive + text

    included = []
    size = 0
    truncated = False
    for el in ordered:
        out = _strip_for_output(el)
        cost = len(json.dumps(out, ensure_ascii=False)) + 2  # +구분자
        if included and size + cost > MAX_RESULT_CHARS:
            truncated = True
            break
        included.append(out)
        size += cost

    result = {
        "success": True,
        "snapshot": included,
        "element_count": total,
        "shown_count": len(included),
        "url": url,
        "title": title,
    }

    if truncated:
        omitted = total - len(included)
        result["truncated"] = True  # truncation-scope: source — 접근성 스냅샷 문자 안전 상한; 작성자 선택 아님
        result["truncations"] = [{"scope": "selection", "source": "browser.snapshot",
                                  "unit": "elements", "retained": len(included),
                                  "total": total, "reason": "display_budget"}]
        result["omitted_count"] = omitted
        result["guide"] = (
            f"페이지가 커서 상위 {len(included)}개 요소(interactive 우선)만 표시하고 "
            f"{omitted}개를 생략했습니다. 특정 데이터·매물·링크는 "
            f'[limbs:browser]{{op:"evaluate", expression:"..."}} 로 좁혀 조회하세요.'
        )

    return result
