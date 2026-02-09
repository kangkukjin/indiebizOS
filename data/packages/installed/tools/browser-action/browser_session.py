"""
browser_session.py - BrowserSession 싱글톤 + 공통 유틸리티

브라우저 세션 관리, ref 매핑, locator 탐색, 출력 경로 등
모든 브라우저 도구 모듈이 공유하는 핵심 컴포넌트.

Version: 3.0.0
"""

import os
import re
import json
import asyncio
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse

# ─────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────
NAVIGATE_TIMEOUT = 30000
LOCATOR_TIMEOUT = 5000
ACTION_TIMEOUT = 10000
WAIT_DEFAULT_TIMEOUT = 30000
AUTO_CLOSE_SECONDS = 120
MAX_CONSOLE_LOGS = 1000
BLOCKED_URL_SCHEMES = {"javascript:", "data:", "file:", "vbscript:"}

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

    - 120초 비활성 시 자동 종료
    - 다중 탭 관리 (tab_id → Page)
    - iframe 전환 지원
    - ref 매핑 저장 (스냅샷에서 생성된 ref → 요소 정보)
    - 콘솔 로그 수집
    """

    _instance = None

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._last_activity = 0.0
        self._timeout_seconds = AUTO_CLOSE_SECONDS
        self._cleanup_task = None
        self._headless = True

        # 탭 관리
        self._pages: Dict[str, Any] = {}
        self._tab_counter = 0
        self._active_tab_id: str = ""

        # iframe 관리
        self._active_frame = None

        # ref 매핑
        self._ref_map: Dict[str, dict] = {}
        self._ref_counter = 0
        self._snapshot_url: Optional[str] = None

        # 콘솔 로그
        self._console_logs: deque = deque(maxlen=MAX_CONSOLE_LOGS)

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = BrowserSession()
        return cls._instance

    def _reset_timer(self):
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
        self._last_activity = time.time()
        try:
            loop = asyncio.get_event_loop()
            self._cleanup_task = loop.create_task(self._auto_close())
        except RuntimeError:
            pass

    async def _auto_close(self):
        await asyncio.sleep(self._timeout_seconds)
        if time.time() - self._last_activity >= self._timeout_seconds:
            print(f"[브라우저] {self._timeout_seconds}초 비활성 — 자동 종료")
            await self._close_internal()

    async def ensure_browser(self, headless=True):
        """브라우저가 실행 중인지 확인하고, 없으면 생성. Page 반환."""
        if not self._pages or self._active_tab_id not in self._pages:
            await self._start_browser(headless)
        elif self._browser and not self._browser.is_connected():
            await self._close_internal()
            await self._start_browser(headless)
        elif self._headless != headless:
            print(f"[브라우저] headless 모드 변경 ({self._headless} → {headless}), 재시작")
            await self._close_internal()
            await self._start_browser(headless)
        self._reset_timer()
        return self.page

    async def _start_browser(self, headless=True):
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

        # 새 탭(팝업) 자동 감지
        self._context.on("page", self._on_new_page)

        # 첫 번째 페이지 생성
        page = await self._context.new_page()
        self._tab_counter = 1
        tab_id = "t1"
        self._pages[tab_id] = page
        self._active_tab_id = tab_id
        self._active_frame = None

        # 콘솔 로그 수집 설정
        self._console_logs = deque(maxlen=MAX_CONSOLE_LOGS)
        page.on("console", self._on_console_message)

        # ref 맵 초기화
        self._ref_map = {}
        self._ref_counter = 0

        print(f"[브라우저] 시작 (headless={headless})")

    def _on_new_page(self, page):
        """새 탭/팝업 자동 감지 핸들러"""
        self._tab_counter += 1
        tab_id = f"t{self._tab_counter}"
        self._pages[tab_id] = page
        self._active_tab_id = tab_id
        self._active_frame = None
        page.on("console", self._on_console_message)
        print(f"[브라우저] 새 탭 감지: {tab_id}")

    def _on_console_message(self, msg):
        self._console_logs.append({
            "type": msg.type,
            "text": msg.text,
            "timestamp": datetime.now().isoformat(),
        })

    @property
    def page(self):
        """현재 활성 탭의 Page 반환 (iframe 전환 시 frame 반환)"""
        if self._active_frame:
            return self._active_frame
        return self._pages.get(self._active_tab_id)

    @property
    def raw_page(self):
        """iframe 무시, 실제 Page 객체 반환"""
        return self._pages.get(self._active_tab_id)

    @property
    def is_active(self):
        try:
            page = self._pages.get(self._active_tab_id)
            return (
                page is not None
                and not page.is_closed()
                and self._browser is not None
                and self._browser.is_connected()
            )
        except Exception:
            return False

    # ── ref 관리 ──

    def get_ref(self, ref: str) -> Optional[dict]:
        return self._ref_map.get(ref)

    def clear_refs(self):
        self._ref_map = {}
        self._ref_counter = 0
        self._snapshot_url = None

    def add_ref(self, element_info: dict) -> str:
        self._ref_counter += 1
        ref = f"e{self._ref_counter}"
        self._ref_map[ref] = element_info
        return ref

    # ── 탭 관리 ──

    @property
    def active_tab_id(self):
        return self._active_tab_id

    @property
    def tab_ids(self):
        return list(self._pages.keys())

    def get_tab_page(self, tab_id: str):
        return self._pages.get(tab_id)

    async def new_tab(self, url: str = None) -> str:
        """새 탭 생성. tab_id 반환."""
        if not self._context:
            return ""
        page = await self._context.new_page()
        self._tab_counter += 1
        tab_id = f"t{self._tab_counter}"
        self._pages[tab_id] = page
        self._active_tab_id = tab_id
        self._active_frame = None
        page.on("console", self._on_console_message)
        self.clear_refs()

        if url:
            url_lower = url.lower().strip()
            for scheme in BLOCKED_URL_SCHEMES:
                if url_lower.startswith(scheme):
                    return tab_id
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            await page.goto(url, wait_until="load", timeout=NAVIGATE_TIMEOUT)

        return tab_id

    def switch_tab(self, tab_id: str) -> bool:
        """탭 전환. 성공 여부 반환."""
        if tab_id not in self._pages:
            return False
        page = self._pages[tab_id]
        if page.is_closed():
            del self._pages[tab_id]
            return False
        self._active_tab_id = tab_id
        self._active_frame = None
        self.clear_refs()
        return True

    async def close_tab(self, tab_id: str = None) -> bool:
        """탭 닫기. 활성 탭이면 다른 탭으로 전환."""
        target_id = tab_id or self._active_tab_id
        if target_id not in self._pages:
            return False

        page = self._pages[target_id]
        try:
            if not page.is_closed():
                await page.close()
        except Exception:
            pass
        del self._pages[target_id]

        # 활성 탭이 닫혔으면 다른 탭으로 전환
        if target_id == self._active_tab_id:
            self._active_frame = None
            if self._pages:
                self._active_tab_id = list(self._pages.keys())[-1]
            else:
                self._active_tab_id = ""
            self.clear_refs()

        return True

    # ── iframe 관리 ──

    def set_active_frame(self, frame):
        self._active_frame = frame
        self.clear_refs()

    def reset_frame(self):
        self._active_frame = None
        self.clear_refs()

    # ── 종료 ──

    async def close(self):
        await self._close_internal()

    async def _close_internal(self):
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            self._cleanup_task = None
        for tab_id, page in list(self._pages.items()):
            try:
                if not page.is_closed():
                    await page.close()
            except Exception:
                pass
        self._pages.clear()
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
        self._context = None
        self._browser = None
        self._playwright = None
        self._active_tab_id = ""
        self._active_frame = None
        self._tab_counter = 0
        self._ref_map = {}
        self._ref_counter = 0
        self._snapshot_url = None
        self._console_logs = deque(maxlen=MAX_CONSOLE_LOGS)
        print("[브라우저] 종료 완료")


# ─────────────────────────────────────────────
# 유틸리티 함수
# ─────────────────────────────────────────────

def ensure_active():
    """브라우저 활성 확인. 비활성이면 에러 dict 반환."""
    session = BrowserSession.get_instance()
    if not session.is_active:
        return {"success": False, "error": "브라우저가 열려있지 않습니다. browser_navigate를 먼저 호출하세요."}
    session._reset_timer()
    return None


def check_stale_ref(session, ref: str) -> Optional[dict]:
    """ref 유효성 검증."""
    element_info = session.get_ref(ref)
    if not element_info:
        return {"success": False, "error": f"ref '{ref}'를 찾을 수 없습니다. browser_snapshot을 다시 호출하세요."}

    if session._snapshot_url and session.page:
        try:
            current_url = session.page.url
            if current_url != session._snapshot_url:
                element_info["_stale_warning"] = (
                    f"주의: 스냅샷 이후 URL이 변경되었습니다 "
                    f"({session._snapshot_url} → {current_url}). "
                    f"ref가 유효하지 않을 수 있습니다."
                )
        except Exception:
            pass

    return None


async def find_locator(page, element_info: dict, input_mode: bool = False):
    """
    공통 locator 찾기 로직.
    element_info에서 role/name을 기반으로 다양한 전략으로 요소를 찾는다.
    """
    role = element_info.get("role", "")
    name = element_info.get("name", "")

    # 1. role + name으로 시도
    if role and name:
        try:
            locator = page.get_by_role(role, name=name).first
            await locator.wait_for(state="visible", timeout=LOCATOR_TIMEOUT)
            return locator
        except Exception:
            pass

    # 2. 입력 필드 전용: role만으로 시도
    if input_mode and role in ("textbox", "searchbox", "combobox", "spinbutton"):
        try:
            locator = page.get_by_role(role).first
            await locator.wait_for(state="visible", timeout=LOCATOR_TIMEOUT)
            return locator
        except Exception:
            pass

    # 3. 텍스트로 시도
    if name:
        try:
            locator = page.get_by_text(name, exact=False).first
            await locator.wait_for(state="visible", timeout=LOCATOR_TIMEOUT)
            return locator
        except Exception:
            pass

    # 4. 입력 필드 전용: label, placeholder
    if input_mode and name:
        for getter in (page.get_by_label, page.get_by_placeholder):
            try:
                locator = getter(name).first
                await locator.wait_for(state="visible", timeout=LOCATOR_TIMEOUT)
                return locator
            except Exception:
                pass

    # 5. 역할만으로 시도 (비입력 모드)
    if not input_mode and role:
        try:
            locator = page.get_by_role(role).first
            await locator.wait_for(state="visible", timeout=LOCATOR_TIMEOUT)
            return locator
        except Exception:
            pass

    return None


def get_output_dir(project_path: str, subdir: str = "") -> Path:
    """출력 디렉토리 경로 반환"""
    base_dir = Path(project_path)
    out_dir = base_dir / "outputs"
    if subdir:
        out_dir = out_dir / subdir

    if not base_dir.exists() or str(base_dir) == ".":
        pkg_dir = Path(__file__).parent
        for parent in pkg_dir.parents:
            candidate = parent / "outputs"
            if parent.name == "indiebizOS" or candidate.exists():
                out_dir = candidate / subdir if subdir else candidate
                break

    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def get_cookies_dir() -> Path:
    """쿠키 저장 디렉토리 경로 반환"""
    pkg_dir = Path(__file__).parent
    for parent in pkg_dir.parents:
        if parent.name == "indiebizOS":
            cookies_dir = parent / "data" / "browser_cookies"
            cookies_dir.mkdir(parents=True, exist_ok=True)
            return cookies_dir
    # 폴백
    cookies_dir = pkg_dir / "cookies"
    cookies_dir.mkdir(parents=True, exist_ok=True)
    return cookies_dir


def format_snapshot_text(elements: List[dict]) -> str:
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
