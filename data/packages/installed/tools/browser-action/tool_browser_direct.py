"""
tool_browser_direct.py - Playwright 직접 제어 브라우저 도구

Playwright Async API를 사용하여 asyncio 환경(FastAPI)과 호환.
BrowserSession 싱글톤으로 세션 유지, 60초 비활성 시 자동 종료.
"""

import os
import json
import asyncio
import time
from datetime import datetime
from pathlib import Path

# Playwright는 실제 사용 시점에 임포트 (lazy import)
_playwright_module = None


def _get_playwright():
    global _playwright_module
    if _playwright_module is None:
        from playwright.async_api import async_playwright
        _playwright_module = async_playwright
    return _playwright_module


class BrowserSession:
    """싱글톤 브라우저 세션. 60초 비활성 시 자동 종료."""

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
        print(f"[브라우저] 시작 (headless={headless})")

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
        print("[브라우저] 종료 완료")


# ─────────────────────────────────────────────
# 도구 함수들
# ─────────────────────────────────────────────

def _ensure_active():
    """브라우저 활성 확인. 비활성이면 에러 dict 반환, 활성이면 None."""
    session = BrowserSession.get_instance()
    if not session.is_active:
        return {"success": False, "error": "브라우저가 열려있지 않습니다. browser_open을 먼저 호출하세요."}
    session._reset_timer()
    return None


async def browser_open(params: dict, project_path: str = ".") -> dict:
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

        await page.goto(url, wait_until=wait_for, timeout=30000)

        title = await page.title()
        text = ""
        try:
            text = await page.inner_text('body')
        except Exception:
            pass
        text_preview = text[:2000] if len(text) > 2000 else text

        return {
            "success": True,
            "title": title,
            "url": page.url,
            "text_preview": text_preview
        }
    except Exception as e:
        return {"success": False, "error": f"페이지 열기 실패: {str(e)}"}


async def browser_click(params: dict) -> dict:
    """페이지에서 요소 클릭"""
    err = _ensure_active()
    if err:
        return err

    page = BrowserSession.get_instance().page
    text = params.get("text")
    selector = params.get("selector")
    role = params.get("role")
    name = params.get("name")

    try:
        if text:
            locator = page.get_by_text(text, exact=False).first
        elif selector:
            locator = page.locator(selector).first
        elif role:
            kwargs = {}
            if name:
                kwargs["name"] = name
            locator = page.get_by_role(role, **kwargs).first
        else:
            return {"success": False, "error": "text, selector, 또는 role 중 하나를 지정하세요."}

        await locator.wait_for(state="visible", timeout=10000)
        await locator.click(timeout=10000)

        # 네비게이션이 발생할 수 있으므로 잠시 대기
        try:
            await page.wait_for_load_state("load", timeout=5000)
        except Exception:
            pass

        return {
            "success": True,
            "clicked": text or selector or f"{role}:{name}",
            "current_url": page.url,
            "current_title": await page.title()
        }
    except Exception as e:
        return {"success": False, "error": f"클릭 실패: {str(e)}"}


async def browser_type(params: dict) -> dict:
    """입력 필드에 텍스트 입력"""
    err = _ensure_active()
    if err:
        return err

    page = BrowserSession.get_instance().page
    text = params.get("text", "")
    selector = params.get("selector")
    label = params.get("label")
    clear = params.get("clear", False)
    press_enter = params.get("press_enter", False)

    if not text and not press_enter:
        return {"success": False, "error": "text가 필요합니다."}

    try:
        if selector:
            locator = page.locator(selector).first
        elif label:
            locator = page.get_by_label(label).first
        else:
            # 포커스된 요소에 입력 시도
            locator = None

        if locator:
            await locator.wait_for(state="visible", timeout=10000)
            if clear:
                await locator.clear()
            await locator.fill(text)
            if press_enter:
                await locator.press("Enter")
        else:
            # selector/label 없으면 키보드로 직접 입력
            if clear:
                await page.keyboard.press("Control+a")
                await page.keyboard.press("Backspace")
            await page.keyboard.type(text)
            if press_enter:
                await page.keyboard.press("Enter")

        # 엔터 후 페이지 로드 대기
        if press_enter:
            try:
                await page.wait_for_load_state("load", timeout=5000)
            except Exception:
                pass

        return {
            "success": True,
            "typed_text": text,
            "field": selector or label or "(focused element)",
            "current_url": page.url
        }
    except Exception as e:
        return {"success": False, "error": f"입력 실패: {str(e)}"}


async def browser_screenshot(params: dict, project_path: str = ".") -> dict:
    """현재 페이지 스크린샷 저장"""
    err = _ensure_active()
    if err:
        return err

    page = BrowserSession.get_instance().page
    full_page = params.get("full_page", False)
    selector = params.get("selector")

    try:
        # 출력 디렉토리
        base_dir = Path(project_path)
        # indiebizOS 루트의 outputs 사용
        out_dir = base_dir / "outputs" / "screenshots"
        if not out_dir.exists():
            # project_path가 프로젝트 폴더일 수 있으므로 상위에서도 시도
            alt_dir = Path(__file__).parent.parent.parent.parent.parent / "outputs" / "screenshots"
            out_dir = alt_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"screenshot_{timestamp}.png"
        filepath = out_dir / filename

        if selector:
            element = page.locator(selector).first
            await element.screenshot(path=str(filepath))
        else:
            await page.screenshot(path=str(filepath), full_page=full_page)

        abs_path = str(filepath.resolve())
        return {
            "success": True,
            "file_path": abs_path,
            "message": f"스크린샷 저장: {abs_path}"
        }
    except Exception as e:
        return {"success": False, "error": f"스크린샷 실패: {str(e)}"}


async def browser_get_content(params: dict) -> dict:
    """현재 페이지 텍스트 추출"""
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


async def browser_get_interactive(params: dict) -> dict:
    """페이지의 상호작용 가능한 요소 목록 반환"""
    err = _ensure_active()
    if err:
        return err

    page = BrowserSession.get_instance().page
    scope = params.get("selector", "body")

    try:
        elements = await page.evaluate('''(scope) => {
            const container = scope === 'body'
                ? document.body
                : document.querySelector(scope);
            if (!container) return [];

            const sels =
                'a[href], button, input, select, textarea, ' +
                '[role="button"], [role="link"], [role="tab"], ' +
                '[role="menuitem"], [role="checkbox"], [role="radio"], ' +
                '[onclick], [tabindex]:not([tabindex="-1"])';

            const els = container.querySelectorAll(sels);
            const results = [];
            const seen = new Set();

            for (const el of els) {
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden') continue;

                const rect = el.getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) continue;

                const tag = el.tagName.toLowerCase();
                const elType = el.type || el.getAttribute('role') || '';
                const text = (el.innerText || el.value || '').trim().substring(0, 80);
                const href = el.href || '';
                const elName = el.name || el.getAttribute('aria-label') || '';
                const id = el.id || '';
                const placeholder = el.placeholder || '';

                // 고유 선택자 생성
                let selector = '';
                if (id) {
                    selector = '#' + CSS.escape(id);
                } else if (el.name && tag !== 'a') {
                    selector = tag + '[name="' + el.name + '"]';
                } else {
                    selector = tag;
                    if (el.className && typeof el.className === 'string') {
                        const cls = el.className.split(' ')
                            .filter(c => c && !c.includes(':') && c.length < 30)
                            .slice(0, 2).join('.');
                        if (cls) selector += '.' + cls;
                    }
                }

                // 중복 제거
                const key = selector + '|' + text;
                if (seen.has(key)) continue;
                seen.add(key);

                const info = { tag, type: elType, text, selector };
                if (href) info.href = href;
                if (elName) info.name = elName;
                if (id) info.id = id;
                if (placeholder) info.placeholder = placeholder;
                if (el.disabled) info.disabled = true;

                if (text || placeholder || elName || href) {
                    results.push(info);
                }
            }

            return results.slice(0, 50);
        }''', scope)

        return {
            "success": True,
            "elements": elements,
            "count": len(elements),
            "url": page.url
        }
    except Exception as e:
        return {"success": False, "error": f"요소 조회 실패: {str(e)}"}


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

        # 스크롤 위치 반환
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


async def browser_evaluate(params: dict) -> dict:
    """페이지에서 JavaScript 실행"""
    err = _ensure_active()
    if err:
        return err

    page = BrowserSession.get_instance().page
    expression = params.get("expression", "")

    if not expression:
        return {"success": False, "error": "expression이 필요합니다."}

    try:
        result = await page.evaluate(expression)
        # JSON 직렬화 가능 여부 확인
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
    """브라우저 세션 종료"""
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
