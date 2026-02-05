"""
tool_browser_direct.py - Playwright MCP 스타일 브라우저 자동화 도구

Accessibility Snapshot 기반으로 페이지 구조를 파악하고,
ref를 통해 정확한 요소 타겟팅을 수행합니다.

핵심 개념:
1. browser_snapshot으로 페이지의 접근성 트리를 캡처
2. 각 요소에 고유 ref (e1, e2, ...) 부여
3. browser_click, browser_type 등에서 ref로 요소 지정
4. 비전 모델 없이 구조화된 데이터로 상호작용

Version: 2.0.0 (Playwright MCP Style)
"""

import os
import re
import json
import asyncio
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# Playwright lazy import
_playwright_module = None


def _get_playwright():
    global _playwright_module
    if _playwright_module is None:
        from playwright.async_api import async_playwright
        _playwright_module = async_playwright
    return _playwright_module


class BrowserSession:
    """
    싱글톤 브라우저 세션.

    - 60초 비활성 시 자동 종료
    - ref 매핑 저장 (스냅샷에서 생성된 ref → 요소 선택자)
    - 콘솔 로그 수집
    """

    _instance = None
    _lock = asyncio.Lock() if hasattr(asyncio, 'Lock') else None

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._last_activity = 0.0
        self._timeout_seconds = 60
        self._cleanup_task = None
        self._headless = True

        # Playwright MCP 스타일 추가 기능
        self._ref_map: Dict[str, dict] = {}  # ref → {selector, role, name, ...}
        self._ref_counter = 0
        self._console_logs: List[dict] = []

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = BrowserSession()
        return cls._instance

    def _reset_timer(self):
        """활동 시 자동 종료 타이머 리셋"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
        self._last_activity = time.time()
        try:
            loop = asyncio.get_event_loop()
            self._cleanup_task = loop.create_task(self._auto_close())
        except RuntimeError:
            pass

    async def _auto_close(self):
        """비활성 타임아웃 시 자동 종료"""
        await asyncio.sleep(self._timeout_seconds)
        if time.time() - self._last_activity >= self._timeout_seconds:
            print("[브라우저] 60초 비활성 — 자동 종료")
            await self._close_internal()

    async def ensure_browser(self, headless=True):
        """브라우저가 실행 중인지 확인하고, 없으면 생성. Page 반환."""
        if self._page is None or self._page.is_closed():
            await self._start_browser(headless)
        elif self._browser and not self._browser.is_connected():
            await self._close_internal()
            await self._start_browser(headless)
        self._reset_timer()
        return self._page

    async def _start_browser(self, headless=True):
        """Playwright 브라우저 시작"""
        self._headless = headless
        async_playwright = _get_playwright()

        if self._playwright is None:
            self._playwright = await async_playwright().start()

        self._browser = await self._playwright.chromium.launch(
            headless=headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-first-run',
                '--no-default-browser-check',
            ]
        )
        self._context = await self._browser.new_context(
            viewport={'width': 1280, 'height': 720},
            locale='ko-KR',
            timezone_id='Asia/Seoul',
        )
        self._page = await self._context.new_page()

        # 콘솔 로그 수집 설정
        self._console_logs = []
        self._page.on("console", self._on_console_message)

        # ref 맵 초기화
        self._ref_map = {}
        self._ref_counter = 0

        print(f"[브라우저] 시작 (headless={headless})")

    def _on_console_message(self, msg):
        """콘솔 메시지 수집"""
        self._console_logs.append({
            "type": msg.type,
            "text": msg.text,
            "timestamp": datetime.now().isoformat(),
        })
        # 최대 1000개 유지
        if len(self._console_logs) > 1000:
            self._console_logs = self._console_logs[-1000:]

    @property
    def page(self):
        return self._page

    @property
    def is_active(self):
        try:
            return (
                self._page is not None
                and not self._page.is_closed()
                and self._browser is not None
                and self._browser.is_connected()
            )
        except Exception:
            return False

    def get_ref(self, ref: str) -> Optional[dict]:
        """ref로 요소 정보 조회"""
        return self._ref_map.get(ref)

    def clear_refs(self):
        """ref 맵 초기화"""
        self._ref_map = {}
        self._ref_counter = 0

    def add_ref(self, element_info: dict) -> str:
        """새 ref 생성 및 등록"""
        self._ref_counter += 1
        ref = f"e{self._ref_counter}"
        self._ref_map[ref] = element_info
        return ref

    async def close(self):
        """외부 호출용 종료"""
        await self._close_internal()

    async def _close_internal(self):
        """실제 리소스 정리"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            self._cleanup_task = None
        try:
            if self._page and not self._page.is_closed():
                await self._page.close()
        except Exception:
            pass
        try:
            if self._context:
                await self._context.close()
        except Exception:
            pass
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        self._ref_map = {}
        self._ref_counter = 0
        self._console_logs = []
        print("[브라우저] 종료 완료")


# ─────────────────────────────────────────────
# 유틸리티 함수
# ─────────────────────────────────────────────

def _ensure_active():
    """브라우저 활성 확인. 비활성이면 에러 dict 반환."""
    session = BrowserSession.get_instance()
    if not session.is_active:
        return {"success": False, "error": "브라우저가 열려있지 않습니다. browser_navigate를 먼저 호출하세요."}
    session._reset_timer()
    return None


def _get_output_dir(project_path: str, subdir: str = "") -> Path:
    """출력 디렉토리 경로 반환"""
    base_dir = Path(project_path)
    out_dir = base_dir / "outputs"
    if subdir:
        out_dir = out_dir / subdir

    # 프로젝트 폴더가 아닐 수 있으므로 상위에서도 시도
    if not out_dir.exists():
        alt_dir = Path(__file__).parent.parent.parent.parent.parent / "outputs"
        if subdir:
            alt_dir = alt_dir / subdir
        out_dir = alt_dir

    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


# ─────────────────────────────────────────────
# 네비게이션 도구
# ─────────────────────────────────────────────

async def browser_navigate(params: dict, project_path: str = ".") -> dict:
    """브라우저를 열고 URL로 이동"""
    url = params.get("url", "")
    headless = params.get("headless", True)
    wait_for = params.get("wait_for", "load")

    if not url:
        return {"success": False, "error": "URL이 필요합니다."}

    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    try:
        session = BrowserSession.get_instance()
        page = await session.ensure_browser(headless=headless)

        # 새 페이지로 이동 시 ref 맵 초기화
        session.clear_refs()

        await page.goto(url, wait_until=wait_for, timeout=30000)

        title = await page.title()

        return {
            "success": True,
            "title": title,
            "url": page.url,
            "snapshot_hint": "페이지 구조를 파악하려면 browser_snapshot을 호출하세요."
        }
    except Exception as e:
        return {"success": False, "error": f"페이지 열기 실패: {str(e)}"}


async def browser_navigate_back(params: dict) -> dict:
    """브라우저 히스토리에서 이전 페이지로 이동"""
    err = _ensure_active()
    if err:
        return err

    try:
        session = BrowserSession.get_instance()
        page = session.page
        session.clear_refs()

        await page.go_back(wait_until="load", timeout=30000)

        return {
            "success": True,
            "title": await page.title(),
            "url": page.url
        }
    except Exception as e:
        return {"success": False, "error": f"뒤로 가기 실패: {str(e)}"}


async def browser_navigate_forward(params: dict) -> dict:
    """브라우저 히스토리에서 다음 페이지로 이동"""
    err = _ensure_active()
    if err:
        return err

    try:
        session = BrowserSession.get_instance()
        page = session.page
        session.clear_refs()

        await page.go_forward(wait_until="load", timeout=30000)

        return {
            "success": True,
            "title": await page.title(),
            "url": page.url
        }
    except Exception as e:
        return {"success": False, "error": f"앞으로 가기 실패: {str(e)}"}


# ─────────────────────────────────────────────
# Accessibility Snapshot (핵심!)
# ─────────────────────────────────────────────

async def browser_snapshot(params: dict) -> dict:
    """
    현재 페이지의 Accessibility Snapshot 캡처.

    Playwright MCP Server의 핵심 기능.
    각 요소에 ref를 부여하여 후속 도구에서 사용.
    """
    err = _ensure_active()
    if err:
        return err

    session = BrowserSession.get_instance()
    page = session.page
    selector = params.get("selector")

    try:
        # ref 맵 초기화
        session.clear_refs()

        # Playwright의 accessibility.snapshot() 사용
        # interestingOnly=False로 모든 요소 포함
        snapshot = await page.accessibility.snapshot(interesting_only=False)

        if not snapshot:
            return {
                "success": True,
                "snapshot": [],
                "url": page.url,
                "title": await page.title(),
                "message": "페이지에 접근성 요소가 없습니다."
            }

        # 스냅샷을 평탄화하고 ref 부여
        elements = []

        def process_node(node: dict, depth: int = 0):
            """재귀적으로 노드 처리"""
            if not node:
                return

            role = node.get("role", "")
            name = node.get("name", "")
            value = node.get("value", "")

            # 상호작용 가능한 요소만 ref 부여
            interactive_roles = {
                "button", "link", "textbox", "searchbox", "combobox",
                "listbox", "option", "checkbox", "radio", "switch",
                "slider", "spinbutton", "tab", "tabpanel", "menuitem",
                "menuitemcheckbox", "menuitemradio", "treeitem",
                "gridcell", "row", "columnheader", "rowheader"
            }

            # 이름이나 값이 있는 요소, 또는 상호작용 가능한 역할
            is_interactive = role in interactive_roles
            has_content = bool(name or value)

            if is_interactive or (has_content and role not in {"generic", "none", "presentation"}):
                # 선택자 생성 (JavaScript로 요소 찾기용)
                selector_js = _generate_selector(node)

                element_info = {
                    "role": role,
                    "name": name[:100] if name else "",
                    "selector": selector_js,
                }

                if value:
                    element_info["value"] = value[:100]
                if node.get("focused"):
                    element_info["focused"] = True
                if node.get("disabled"):
                    element_info["disabled"] = True
                if node.get("checked") is not None:
                    element_info["checked"] = node.get("checked")
                if node.get("selected"):
                    element_info["selected"] = True

                ref = session.add_ref(element_info)

                elements.append({
                    "ref": ref,
                    **element_info
                })

            # 자식 노드 처리
            children = node.get("children", [])
            for child in children:
                process_node(child, depth + 1)

        process_node(snapshot)

        # 텍스트 형태로도 출력 (LLM 친화적)
        snapshot_text = _format_snapshot_text(elements)

        return {
            "success": True,
            "snapshot": elements,
            "snapshot_text": snapshot_text,
            "element_count": len(elements),
            "url": page.url,
            "title": await page.title()
        }
    except Exception as e:
        return {"success": False, "error": f"스냅샷 캡처 실패: {str(e)}"}


def _generate_selector(node: dict) -> str:
    """노드에서 선택자 생성"""
    role = node.get("role", "")
    name = node.get("name", "")

    # ARIA 역할 기반 선택자
    if name:
        # 이름으로 찾기 (가장 정확)
        escaped_name = name.replace('"', '\\"')[:50]
        return f'role={role}[name="{escaped_name}"]'
    elif role:
        return f'role={role}'
    return ""


def _format_snapshot_text(elements: List[dict]) -> str:
    """스냅샷을 텍스트 형태로 포맷"""
    lines = []
    for el in elements:
        ref = el.get("ref", "")
        role = el.get("role", "")
        name = el.get("name", "")
        value = el.get("value", "")

        parts = [f"[{ref}]", role]
        if name:
            parts.append(f'"{name}"')
        if value:
            parts.append(f"value={value}")
        if el.get("focused"):
            parts.append("(focused)")
        if el.get("disabled"):
            parts.append("(disabled)")
        if el.get("checked"):
            parts.append("(checked)")

        lines.append(" ".join(parts))

    return "\n".join(lines)


# ─────────────────────────────────────────────
# 상호작용 도구 (ref 기반)
# ─────────────────────────────────────────────

async def browser_click(params: dict) -> dict:
    """ref 기반으로 요소 클릭"""
    err = _ensure_active()
    if err:
        return err

    element_desc = params.get("element", "")
    ref = params.get("ref", "")

    if not ref:
        return {"success": False, "error": "ref가 필요합니다. browser_snapshot을 먼저 호출하세요."}

    session = BrowserSession.get_instance()
    page = session.page

    element_info = session.get_ref(ref)
    if not element_info:
        return {"success": False, "error": f"ref '{ref}'를 찾을 수 없습니다. browser_snapshot을 다시 호출하세요."}

    try:
        # 선택자로 요소 찾기
        selector = element_info.get("selector", "")
        role = element_info.get("role", "")
        name = element_info.get("name", "")

        locator = None

        # 1. role + name으로 시도
        if role and name:
            try:
                locator = page.get_by_role(role, name=name).first
                await locator.wait_for(state="visible", timeout=5000)
            except Exception:
                locator = None

        # 2. 텍스트로 시도
        if locator is None and name:
            try:
                locator = page.get_by_text(name, exact=False).first
                await locator.wait_for(state="visible", timeout=5000)
            except Exception:
                locator = None

        # 3. 역할만으로 시도
        if locator is None and role:
            try:
                locator = page.get_by_role(role).first
                await locator.wait_for(state="visible", timeout=5000)
            except Exception:
                locator = None

        if locator is None:
            return {"success": False, "error": f"요소를 찾을 수 없습니다: {element_desc} (ref={ref})"}

        await locator.click(timeout=10000)

        # 네비게이션 대기
        try:
            await page.wait_for_load_state("load", timeout=5000)
        except Exception:
            pass

        return {
            "success": True,
            "clicked": f"{element_desc} ({ref})",
            "url": page.url,
            "title": await page.title()
        }
    except Exception as e:
        return {"success": False, "error": f"클릭 실패: {str(e)}"}


async def browser_type(params: dict) -> dict:
    """ref 기반으로 입력 필드에 텍스트 입력"""
    err = _ensure_active()
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

    element_info = session.get_ref(ref)
    if not element_info:
        return {"success": False, "error": f"ref '{ref}'를 찾을 수 없습니다. browser_snapshot을 다시 호출하세요."}

    try:
        role = element_info.get("role", "")
        name = element_info.get("name", "")

        locator = None

        # 입력 필드 찾기
        if role in ("textbox", "searchbox", "combobox", "spinbutton"):
            if name:
                try:
                    locator = page.get_by_role(role, name=name).first
                    await locator.wait_for(state="visible", timeout=5000)
                except Exception:
                    locator = None

            if locator is None:
                try:
                    locator = page.get_by_role(role).first
                    await locator.wait_for(state="visible", timeout=5000)
                except Exception:
                    locator = None

        # label로 시도
        if locator is None and name:
            try:
                locator = page.get_by_label(name).first
                await locator.wait_for(state="visible", timeout=5000)
            except Exception:
                locator = None

        # placeholder로 시도
        if locator is None and name:
            try:
                locator = page.get_by_placeholder(name).first
                await locator.wait_for(state="visible", timeout=5000)
            except Exception:
                locator = None

        if locator is None:
            return {"success": False, "error": f"입력 필드를 찾을 수 없습니다: {element_desc} (ref={ref})"}

        if clear:
            await locator.clear()

        await locator.fill(text)

        if submit:
            await locator.press("Enter")
            try:
                await page.wait_for_load_state("load", timeout=5000)
            except Exception:
                pass

        return {
            "success": True,
            "typed": text,
            "element": f"{element_desc} ({ref})",
            "submitted": submit,
            "url": page.url
        }
    except Exception as e:
        return {"success": False, "error": f"입력 실패: {str(e)}"}


async def browser_select_option(params: dict) -> dict:
    """드롭다운에서 옵션 선택"""
    err = _ensure_active()
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

    element_info = session.get_ref(ref)
    if not element_info:
        return {"success": False, "error": f"ref '{ref}'를 찾을 수 없습니다."}

    try:
        name = element_info.get("name", "")

        # combobox 또는 listbox 찾기
        locator = None

        if name:
            try:
                locator = page.get_by_role("combobox", name=name).first
                await locator.wait_for(state="visible", timeout=5000)
            except Exception:
                try:
                    locator = page.get_by_label(name).first
                    await locator.wait_for(state="visible", timeout=5000)
                except Exception:
                    locator = None

        if locator is None:
            return {"success": False, "error": f"select 요소를 찾을 수 없습니다: {element_desc}"}

        await locator.select_option(values)

        return {
            "success": True,
            "selected": values,
            "element": f"{element_desc} ({ref})"
        }
    except Exception as e:
        return {"success": False, "error": f"옵션 선택 실패: {str(e)}"}


async def browser_hover(params: dict) -> dict:
    """요소 위에 마우스 올리기"""
    err = _ensure_active()
    if err:
        return err

    element_desc = params.get("element", "")
    ref = params.get("ref", "")

    if not ref:
        return {"success": False, "error": "ref가 필요합니다."}

    session = BrowserSession.get_instance()
    page = session.page

    element_info = session.get_ref(ref)
    if not element_info:
        return {"success": False, "error": f"ref '{ref}'를 찾을 수 없습니다."}

    try:
        role = element_info.get("role", "")
        name = element_info.get("name", "")

        locator = None

        if role and name:
            try:
                locator = page.get_by_role(role, name=name).first
            except Exception:
                pass

        if locator is None and name:
            locator = page.get_by_text(name, exact=False).first

        if locator is None:
            return {"success": False, "error": f"요소를 찾을 수 없습니다: {element_desc}"}

        await locator.hover(timeout=10000)

        return {
            "success": True,
            "hovered": f"{element_desc} ({ref})"
        }
    except Exception as e:
        return {"success": False, "error": f"hover 실패: {str(e)}"}


async def browser_drag(params: dict) -> dict:
    """요소 드래그"""
    err = _ensure_active()
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

    source_info = session.get_ref(source_ref)
    target_info = session.get_ref(target_ref)

    if not source_info:
        return {"success": False, "error": f"source ref '{source_ref}'를 찾을 수 없습니다."}
    if not target_info:
        return {"success": False, "error": f"target ref '{target_ref}'를 찾을 수 없습니다."}

    try:
        # 소스 요소 찾기
        source_name = source_info.get("name", "")
        source_role = source_info.get("role", "")

        source_locator = None
        if source_role and source_name:
            source_locator = page.get_by_role(source_role, name=source_name).first
        elif source_name:
            source_locator = page.get_by_text(source_name).first

        # 타겟 요소 찾기
        target_name = target_info.get("name", "")
        target_role = target_info.get("role", "")

        target_locator = None
        if target_role and target_name:
            target_locator = page.get_by_role(target_role, name=target_name).first
        elif target_name:
            target_locator = page.get_by_text(target_name).first

        if not source_locator or not target_locator:
            return {"success": False, "error": "소스 또는 타겟 요소를 찾을 수 없습니다."}

        await source_locator.drag_to(target_locator)

        return {
            "success": True,
            "dragged": f"{source_desc} → {target_desc}"
        }
    except Exception as e:
        return {"success": False, "error": f"드래그 실패: {str(e)}"}


async def browser_press_key(params: dict) -> dict:
    """키보드 키 누르기"""
    err = _ensure_active()
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


# ─────────────────────────────────────────────
# 스크롤 및 대기
# ─────────────────────────────────────────────

async def browser_scroll(params: dict) -> dict:
    """페이지 스크롤"""
    err = _ensure_active()
    if err:
        return err

    page = BrowserSession.get_instance().page
    direction = params.get("direction", "down")
    amount = params.get("amount", 500)
    to_bottom = params.get("to_bottom", False)
    to_top = params.get("to_top", False)

    try:
        if to_bottom:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        elif to_top:
            await page.evaluate("window.scrollTo(0, 0)")
        else:
            delta = amount if direction == "down" else -amount
            await page.evaluate(f"window.scrollBy(0, {delta})")

        scroll_info = await page.evaluate('''() => ({
            scrollY: Math.round(window.scrollY),
            scrollHeight: document.body.scrollHeight,
            viewportHeight: window.innerHeight
        })''')

        return {
            "success": True,
            "scroll_position": scroll_info["scrollY"],
            "page_height": scroll_info["scrollHeight"],
            "viewport_height": scroll_info["viewportHeight"]
        }
    except Exception as e:
        return {"success": False, "error": f"스크롤 실패: {str(e)}"}


async def browser_wait_for(params: dict) -> dict:
    """특정 조건 대기"""
    err = _ensure_active()
    if err:
        return err

    page = BrowserSession.get_instance().page
    selector = params.get("selector")
    text = params.get("text")
    url_pattern = params.get("url")
    timeout = params.get("timeout", 30000)

    try:
        if selector:
            await page.wait_for_selector(selector, timeout=timeout)
            return {"success": True, "waited_for": f"selector: {selector}"}

        elif text:
            await page.wait_for_function(
                f'document.body.innerText.includes("{text}")',
                timeout=timeout
            )
            return {"success": True, "waited_for": f"text: {text}"}

        elif url_pattern:
            await page.wait_for_url(re.compile(url_pattern), timeout=timeout)
            return {"success": True, "waited_for": f"url: {url_pattern}"}

        else:
            # 단순 대기
            await asyncio.sleep(timeout / 1000)
            return {"success": True, "waited_for": f"{timeout}ms"}

    except Exception as e:
        return {"success": False, "error": f"대기 실패: {str(e)}"}


# ─────────────────────────────────────────────
# 콘텐츠 추출 및 스크린샷
# ─────────────────────────────────────────────

async def browser_screenshot(params: dict, project_path: str = ".") -> dict:
    """스크린샷 저장"""
    err = _ensure_active()
    if err:
        return err

    page = BrowserSession.get_instance().page
    full_page = params.get("full_page", False)
    selector = params.get("selector")

    try:
        out_dir = _get_output_dir(project_path, "screenshots")
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"screenshot_{timestamp}.png"
        filepath = out_dir / filename

        if selector:
            element = page.locator(selector).first
            await element.screenshot(path=str(filepath))
        else:
            await page.screenshot(path=str(filepath), full_page=full_page)

        return {
            "success": True,
            "file_path": str(filepath.resolve())
        }
    except Exception as e:
        return {"success": False, "error": f"스크린샷 실패: {str(e)}"}


async def browser_get_content(params: dict) -> dict:
    """페이지 텍스트 추출"""
    err = _ensure_active()
    if err:
        return err

    page = BrowserSession.get_instance().page
    selector = params.get("selector")
    max_length = params.get("max_length", 10000)

    try:
        if selector:
            text = await page.locator(selector).first.inner_text(timeout=10000)
        else:
            text = await page.inner_text('body')

        if len(text) > max_length:
            text = text[:max_length] + f"\n\n... (총 {len(text)}자 중 {max_length}자까지 표시)"

        return {
            "success": True,
            "title": await page.title(),
            "url": page.url,
            "text": text,
            "length": len(text)
        }
    except Exception as e:
        return {"success": False, "error": f"콘텐츠 추출 실패: {str(e)}"}


async def browser_console_logs(params: dict) -> dict:
    """콘솔 로그 조회"""
    err = _ensure_active()
    if err:
        return err

    session = BrowserSession.get_instance()
    log_type = params.get("type", "all")
    search = params.get("search", "")
    limit = params.get("limit", 100)
    clear = params.get("clear", False)

    logs = session._console_logs.copy()

    # 타입 필터
    if log_type != "all":
        logs = [l for l in logs if l["type"] == log_type]

    # 텍스트 검색
    if search:
        logs = [l for l in logs if search.lower() in l["text"].lower()]

    # 제한
    logs = logs[-limit:]

    # 클리어
    if clear:
        session._console_logs = []

    return {
        "success": True,
        "logs": logs,
        "count": len(logs)
    }


async def browser_save_pdf(params: dict, project_path: str = ".") -> dict:
    """페이지를 PDF로 저장"""
    err = _ensure_active()
    if err:
        return err

    page = BrowserSession.get_instance().page
    format_size = params.get("format", "A4")
    landscape = params.get("landscape", False)
    print_background = params.get("print_background", True)

    try:
        out_dir = _get_output_dir(project_path, "pdfs")
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"page_{timestamp}.pdf"
        filepath = out_dir / filename

        await page.pdf(
            path=str(filepath),
            format=format_size,
            landscape=landscape,
            print_background=print_background
        )

        return {
            "success": True,
            "file_path": str(filepath.resolve())
        }
    except Exception as e:
        return {"success": False, "error": f"PDF 저장 실패: {str(e)}"}


async def browser_evaluate(params: dict) -> dict:
    """JavaScript 실행"""
    err = _ensure_active()
    if err:
        return err

    page = BrowserSession.get_instance().page
    expression = params.get("expression", "")

    if not expression:
        return {"success": False, "error": "expression이 필요합니다."}

    try:
        result = await page.evaluate(expression)

        # JSON 직렬화 확인
        try:
            json.dumps(result, ensure_ascii=False)
        except (TypeError, ValueError):
            result = str(result)

        return {
            "success": True,
            "result": result
        }
    except Exception as e:
        return {"success": False, "error": f"JavaScript 실행 실패: {str(e)}"}


async def browser_close(params: dict = None) -> dict:
    """브라우저 종료"""
    try:
        session = BrowserSession.get_instance()
        was_active = session.is_active
        await session.close()
        return {
            "success": True,
            "message": "브라우저 종료 완료" if was_active else "브라우저가 이미 종료 상태입니다."
        }
    except Exception as e:
        return {"success": False, "error": f"종료 실패: {str(e)}"}


# ─────────────────────────────────────────────
# 하위 호환성 (기존 도구 이름 지원)
# ─────────────────────────────────────────────

# browser_open → browser_navigate 별칭
async def browser_open(params: dict, project_path: str = ".") -> dict:
    """browser_navigate 별칭 (하위 호환성)"""
    return await browser_navigate(params, project_path)


# browser_get_interactive → browser_snapshot 별칭
async def browser_get_interactive(params: dict) -> dict:
    """browser_snapshot 별칭 (하위 호환성)"""
    result = await browser_snapshot(params)
    if result.get("success"):
        # 기존 형식으로 변환
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
