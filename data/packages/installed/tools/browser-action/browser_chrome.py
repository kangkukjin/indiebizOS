"""
browser_chrome.py - Chrome MCP 드라이버

Chrome 확장 프로그램의 MCP 서버에 SSE로 연결하여 실제 Chrome 브라우저를 제어.
기존 Playwright 모듈과 동일한 함수 시그니처를 유지하여 handler.py에서 드라이버만 전환.

장점: 로그인 상태 유지, 확장 프로그램 사용 가능, 실제 사용자 Chrome 세션 제어.
"""

import os
import re
import json
import asyncio
import base64
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

# ─────────────────────────────────────────────
# Chrome MCP 드라이버 (싱글톤)
# ─────────────────────────────────────────────

class ChromeMCPDriver:
    """Chrome MCP 서버에 SSE로 연결하여 브라우저 제어"""
    _instance: Optional["ChromeMCPDriver"] = None

    def __init__(self):
        self._session = None          # mcp ClientSession
        self._read_stream = None
        self._write_stream = None
        self._ctx = None              # async context manager
        self._session_ctx = None
        self._tab_id: Optional[int] = None
        self._ref_map: dict = {}      # e1 → ref_1 역매핑
        self._reverse_ref: dict = {}  # ref_1 → e1
        self._snapshot_url: str = ""
        self._connected = False
        self._url = ""
        self._connect_task = None

    @classmethod
    def get_instance(cls) -> "ChromeMCPDriver":
        if cls._instance is None:
            cls._instance = ChromeMCPDriver()
        return cls._instance

    def is_connected(self) -> bool:
        return self._connected and self._session is not None

    async def connect(self, url: str = None):
        """Chrome MCP 서버에 SSE로 연결"""
        if self._connected:
            await self.disconnect()

        url = url or os.environ.get("CHROME_MCP_URL", "http://localhost:12306/sse")
        self._url = url

        try:
            from mcp.client.sse import sse_client
            from mcp import ClientSession

            self._ctx = sse_client(url=url)
            self._read_stream, self._write_stream = await self._ctx.__aenter__()

            self._session_ctx = ClientSession(self._read_stream, self._write_stream)
            self._session = await self._session_ctx.__aenter__()
            await self._session.initialize()

            self._connected = True

            # 탭 컨텍스트 초기화
            await self._ensure_tab()

            return {"success": True, "url": url, "tab_id": self._tab_id}
        except Exception as e:
            self._connected = False
            raise ConnectionError(f"Chrome MCP 연결 실패: {e}")

    async def disconnect(self):
        """연결 해제"""
        try:
            if self._session_ctx:
                await self._session_ctx.__aexit__(None, None, None)
            if self._ctx:
                await self._ctx.__aexit__(None, None, None)
        except Exception:
            pass
        finally:
            self._session = None
            self._ctx = None
            self._session_ctx = None
            self._connected = False
            self._tab_id = None
            self._ref_map.clear()
            self._reverse_ref.clear()

    async def _ensure_tab(self):
        """활성 탭이 없으면 탭 컨텍스트 초기화"""
        if self._tab_id is not None:
            return
        result = await self.call_tool("tabs_context_mcp", {"createIfEmpty": True})
        tabs = result.get("tabs", [])
        if tabs:
            self._tab_id = tabs[0].get("id") or tabs[0]
        else:
            # 새 탭 생성
            result = await self.call_tool("tabs_create_mcp", {})
            self._tab_id = result.get("tabId") or result.get("id")

    async def call_tool(self, tool_name: str, params: dict) -> Any:
        """Chrome MCP 도구 호출"""
        if not self.is_connected():
            raise ConnectionError("Chrome MCP에 연결되지 않음. browser_chrome_connect를 먼저 호출하세요.")

        result = await self._session.call_tool(tool_name, params)

        # MCP 결과 파싱
        if hasattr(result, "content"):
            for block in result.content:
                if hasattr(block, "text"):
                    try:
                        return json.loads(block.text)
                    except (json.JSONDecodeError, TypeError):
                        return {"text": block.text}
                elif hasattr(block, "data"):
                    return {"image_data": block.data, "mime_type": getattr(block, "mimeType", "image/png")}
            return {"raw": str(result.content)}
        return {"raw": str(result)}

    def _to_chrome_ref(self, ref: str) -> str:
        """browser-action ref (e1) → Chrome MCP ref (ref_1)"""
        if ref and ref in self._ref_map:
            return self._ref_map[ref]
        # 이미 Chrome 형식이면 그대로
        if ref and ref.startswith("ref_"):
            return ref
        return ref

    def _to_local_ref(self, chrome_ref: str) -> str:
        """Chrome MCP ref (ref_1) → browser-action ref (e1)"""
        if chrome_ref in self._reverse_ref:
            return self._reverse_ref[chrome_ref]
        return chrome_ref

    def _build_ref_map(self, tree_text: str):
        """read_page 결과에서 ref 매핑 테이블 구축"""
        self._ref_map.clear()
        self._reverse_ref.clear()
        # Chrome MCP의 read_page는 ref_1, ref_2 등의 ref를 반환
        refs = re.findall(r'(ref_\d+)', tree_text)
        for i, chrome_ref in enumerate(refs):
            local_ref = f"e{i + 1}"
            self._ref_map[local_ref] = chrome_ref
            self._reverse_ref[chrome_ref] = local_ref


# ─────────────────────────────────────────────
# 연결 관리 도구
# ─────────────────────────────────────────────

async def browser_chrome_connect(params: dict) -> dict:
    """Chrome MCP 서버에 연결"""
    driver = ChromeMCPDriver.get_instance()
    url = params.get("url")
    try:
        result = await driver.connect(url)
        return {"success": True, "message": f"Chrome MCP 연결 성공", **result}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def browser_chrome_disconnect(params: dict) -> dict:
    """Chrome MCP 연결 해제"""
    driver = ChromeMCPDriver.get_instance()
    await driver.disconnect()
    return {"success": True, "message": "Chrome MCP 연결 해제됨"}


async def browser_chrome_status(params: dict) -> dict:
    """Chrome MCP 연결 상태 확인"""
    driver = ChromeMCPDriver.get_instance()
    return {
        "success": True,
        "connected": driver.is_connected(),
        "url": driver._url,
        "tab_id": driver._tab_id,
        "refs_count": len(driver._ref_map)
    }


# ─────────────────────────────────────────────
# 헬퍼
# ─────────────────────────────────────────────

def _get_driver() -> ChromeMCPDriver:
    d = ChromeMCPDriver.get_instance()
    if not d.is_connected():
        raise ConnectionError("Chrome MCP 미연결. browser_chrome_connect를 먼저 호출하세요.")
    return d


def _output_dir(project_path: str = None) -> Path:
    base = Path(project_path) if project_path and project_path != "." else Path.cwd()
    out = base / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    return out


# ─────────────────────────────────────────────
# 네비게이션
# ─────────────────────────────────────────────

async def browser_navigate(params: dict, project_path: str = None) -> dict:
    d = _get_driver()
    url = params.get("url", "")
    if not url:
        return {"success": False, "error": "url 파라미터 필요"}

    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    try:
        result = await d.call_tool("navigate", {"url": url, "tabId": d._tab_id})
        # ref 초기화 (페이지 변경)
        d._ref_map.clear()
        d._reverse_ref.clear()
        return {
            "success": True,
            "url": url,
            "tab_id": d._tab_id,
            "driver": "chrome",
            **({k: v for k, v in result.items() if k != "raw"} if isinstance(result, dict) else {})
        }
    except Exception as e:
        return {"success": False, "error": f"네비게이션 실패: {e}"}


async def browser_navigate_back(params: dict) -> dict:
    d = _get_driver()
    try:
        result = await d.call_tool("navigate", {"url": "back", "tabId": d._tab_id})
        d._ref_map.clear()
        d._reverse_ref.clear()
        return {"success": True, "action": "back", "driver": "chrome"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def browser_navigate_forward(params: dict) -> dict:
    d = _get_driver()
    try:
        result = await d.call_tool("navigate", {"url": "forward", "tabId": d._tab_id})
        d._ref_map.clear()
        d._reverse_ref.clear()
        return {"success": True, "action": "forward", "driver": "chrome"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────
# 스냅샷 / 검색
# ─────────────────────────────────────────────

async def browser_snapshot(params: dict) -> dict:
    d = _get_driver()
    try:
        result = await d.call_tool("read_page", {"tabId": d._tab_id, "filter": "all"})

        # 결과를 텍스트로 변환하고 ref 매핑 구축
        tree_text = result.get("text", "") if isinstance(result, dict) else str(result)
        d._build_ref_map(tree_text)

        # ref_N → eN 치환하여 기존 Playwright 형식과 호환
        display_text = tree_text
        for chrome_ref, local_ref in d._reverse_ref.items():
            display_text = display_text.replace(chrome_ref, local_ref)

        return {
            "success": True,
            "snapshot": display_text,
            "element_count": len(d._ref_map),
            "driver": "chrome"
        }
    except Exception as e:
        return {"success": False, "error": f"스냅샷 실패: {e}"}


async def browser_find(params: dict) -> dict:
    """자연어로 페이지 요소 검색 (Chrome MCP 전용)"""
    d = _get_driver()
    query = params.get("query", "")
    if not query:
        return {"success": False, "error": "query 파라미터 필요"}

    try:
        result = await d.call_tool("find", {"query": query, "tabId": d._tab_id})
        return {"success": True, "results": result, "driver": "chrome"}
    except Exception as e:
        return {"success": False, "error": f"검색 실패: {e}"}


# ─────────────────────────────────────────────
# 상호작용
# ─────────────────────────────────────────────

async def _click_action(params: dict, action: str) -> dict:
    """click/dblclick/rightclick 공통 로직"""
    d = _get_driver()
    ref = params.get("ref")
    selector = params.get("selector")

    try:
        if ref:
            chrome_ref = d._to_chrome_ref(ref)
            result = await d.call_tool("computer", {
                "action": action,
                "ref": chrome_ref,
                "tabId": d._tab_id
            })
        elif selector:
            # selector → find로 요소 찾기 → click
            result = await d.call_tool("computer", {
                "action": action,
                "ref": selector,  # Chrome MCP도 CSS selector를 ref로 사용 가능할 수 있음
                "tabId": d._tab_id
            })
        else:
            return {"success": False, "error": "ref 또는 selector 필요"}

        return {"success": True, "action": action, "driver": "chrome"}
    except Exception as e:
        return {"success": False, "error": f"{action} 실패: {e}"}


async def browser_click(params: dict) -> dict:
    return await _click_action(params, "left_click")

async def browser_dblclick(params: dict) -> dict:
    return await _click_action(params, "double_click")

async def browser_rightclick(params: dict) -> dict:
    return await _click_action(params, "right_click")


async def browser_type(params: dict) -> dict:
    d = _get_driver()
    ref = params.get("ref")
    selector = params.get("selector")
    text = params.get("text", "")
    submit = params.get("submit", False)
    clear = params.get("clear", True)

    try:
        target_ref = None
        if ref:
            target_ref = d._to_chrome_ref(ref)
        elif selector:
            target_ref = selector

        if target_ref:
            # 먼저 필드 클리어
            if clear:
                await d.call_tool("computer", {
                    "action": "triple_click",
                    "ref": target_ref,
                    "tabId": d._tab_id
                })

            # form_input으로 값 설정
            await d.call_tool("form_input", {
                "ref": target_ref,
                "value": text,
                "tabId": d._tab_id
            })
        else:
            # ref 없이 타이핑 (현재 포커스된 요소에)
            await d.call_tool("computer", {
                "action": "type",
                "text": text,
                "tabId": d._tab_id
            })

        if submit:
            await d.call_tool("computer", {
                "action": "key",
                "text": "Return",
                "tabId": d._tab_id
            })

        return {"success": True, "typed": text, "submitted": submit, "driver": "chrome"}
    except Exception as e:
        return {"success": False, "error": f"입력 실패: {e}"}


async def browser_select_option(params: dict) -> dict:
    d = _get_driver()
    ref = params.get("ref")
    selector = params.get("selector")
    values = params.get("values", [])

    try:
        target_ref = d._to_chrome_ref(ref) if ref else selector
        if not target_ref:
            return {"success": False, "error": "ref 또는 selector 필요"}

        value = values[0] if values else ""
        await d.call_tool("form_input", {
            "ref": target_ref,
            "value": value,
            "tabId": d._tab_id
        })
        return {"success": True, "selected": value, "driver": "chrome"}
    except Exception as e:
        return {"success": False, "error": f"선택 실패: {e}"}


async def browser_check(params: dict) -> dict:
    d = _get_driver()
    ref = params.get("ref")
    selector = params.get("selector")
    checked = params.get("checked", True)

    try:
        target_ref = d._to_chrome_ref(ref) if ref else selector
        if not target_ref:
            return {"success": False, "error": "ref 또는 selector 필요"}

        await d.call_tool("form_input", {
            "ref": target_ref,
            "value": checked,
            "tabId": d._tab_id
        })
        return {"success": True, "checked": checked, "driver": "chrome"}
    except Exception as e:
        return {"success": False, "error": f"체크 실패: {e}"}


async def browser_hover(params: dict) -> dict:
    d = _get_driver()
    ref = params.get("ref")
    selector = params.get("selector")

    try:
        target_ref = d._to_chrome_ref(ref) if ref else selector
        if not target_ref:
            return {"success": False, "error": "ref 또는 selector 필요"}

        await d.call_tool("computer", {
            "action": "hover",
            "ref": target_ref,
            "tabId": d._tab_id
        })
        return {"success": True, "action": "hover", "driver": "chrome"}
    except Exception as e:
        return {"success": False, "error": f"호버 실패: {e}"}


async def browser_drag(params: dict) -> dict:
    d = _get_driver()
    source_ref = params.get("source_ref")
    target_ref = params.get("target_ref")

    if not source_ref or not target_ref:
        return {"success": False, "error": "source_ref와 target_ref 필요"}

    try:
        chrome_source = d._to_chrome_ref(source_ref)
        chrome_target = d._to_chrome_ref(target_ref)

        # 드래그는 좌표 기반이므로 요소 위치를 먼저 파악해야 함
        # Chrome MCP의 computer tool은 coordinate 기반 드래그 지원
        await d.call_tool("computer", {
            "action": "left_click_drag",
            "start_coordinate": [0, 0],  # 실제로는 요소 좌표 필요
            "coordinate": [0, 0],
            "ref": chrome_source,  # ref 기반 시도
            "tabId": d._tab_id
        })
        return {"success": True, "action": "drag", "driver": "chrome"}
    except Exception as e:
        return {"success": False, "error": f"드래그 실패: {e}"}


async def browser_press_key(params: dict) -> dict:
    d = _get_driver()
    key = params.get("key", "")
    if not key:
        return {"success": False, "error": "key 파라미터 필요"}

    # Playwright 키 이름 → Chrome MCP 키 이름 변환
    key_map = {
        "Enter": "Return",
        "Escape": "Escape",
        "Tab": "Tab",
        "Backspace": "Backspace",
        "Delete": "Delete",
        "ArrowUp": "ArrowUp",
        "ArrowDown": "ArrowDown",
        "ArrowLeft": "ArrowLeft",
        "ArrowRight": "ArrowRight",
    }
    chrome_key = key_map.get(key, key)

    try:
        await d.call_tool("computer", {
            "action": "key",
            "text": chrome_key,
            "tabId": d._tab_id
        })
        return {"success": True, "key": key, "driver": "chrome"}
    except Exception as e:
        return {"success": False, "error": f"키 입력 실패: {e}"}


async def browser_upload_file(params: dict) -> dict:
    d = _get_driver()
    ref = params.get("ref")
    selector = params.get("selector")
    files = params.get("files", [])

    if not files:
        return {"success": False, "error": "files 파라미터 필요"}

    try:
        target_ref = d._to_chrome_ref(ref) if ref else selector
        if not target_ref:
            return {"success": False, "error": "ref 또는 selector 필요"}

        await d.call_tool("file_upload", {
            "paths": files,
            "ref": target_ref,
            "tabId": d._tab_id
        })
        return {"success": True, "uploaded": files, "driver": "chrome"}
    except Exception as e:
        return {"success": False, "error": f"업로드 실패: {e}"}


# ─────────────────────────────────────────────
# 콘텐츠 및 출력
# ─────────────────────────────────────────────

async def browser_scroll(params: dict) -> dict:
    d = _get_driver()
    direction = params.get("direction", "down")
    amount = params.get("amount", 500)
    to_bottom = params.get("to_bottom", False)
    to_top = params.get("to_top", False)

    try:
        if to_bottom or to_top:
            # JS로 맨 위/아래로 스크롤
            expr = "window.scrollTo(0, document.body.scrollHeight)" if to_bottom else "window.scrollTo(0, 0)"
            await d.call_tool("javascript_tool", {
                "action": "javascript_exec",
                "text": expr,
                "tabId": d._tab_id
            })
        else:
            scroll_dir = "down" if direction == "down" else "up"
            ticks = max(1, amount // 100)
            await d.call_tool("computer", {
                "action": "scroll",
                "coordinate": [640, 400],  # 화면 중앙
                "scroll_direction": scroll_dir,
                "scroll_amount": min(ticks, 10),
                "tabId": d._tab_id
            })

        return {"success": True, "direction": direction, "driver": "chrome"}
    except Exception as e:
        return {"success": False, "error": f"스크롤 실패: {e}"}


async def browser_wait_for(params: dict) -> dict:
    d = _get_driver()
    selector = params.get("selector")
    text = params.get("text")
    url_pattern = params.get("url")
    timeout = params.get("timeout", 10000)

    max_attempts = max(1, timeout // 1000)

    try:
        for _ in range(max_attempts):
            if selector:
                result = await d.call_tool("javascript_tool", {
                    "action": "javascript_exec",
                    "text": f"!!document.querySelector('{selector}')",
                    "tabId": d._tab_id
                })
                if result.get("text") == "true" or result == True:
                    return {"success": True, "found": "selector", "driver": "chrome"}

            if text:
                result = await d.call_tool("javascript_tool", {
                    "action": "javascript_exec",
                    "text": f"document.body.innerText.includes('{text}')",
                    "tabId": d._tab_id
                })
                if result.get("text") == "true" or result == True:
                    return {"success": True, "found": "text", "driver": "chrome"}

            if url_pattern:
                result = await d.call_tool("javascript_tool", {
                    "action": "javascript_exec",
                    "text": "window.location.href",
                    "tabId": d._tab_id
                })
                current_url = result.get("text", "")
                if re.search(url_pattern, current_url):
                    return {"success": True, "found": "url", "driver": "chrome"}

            await asyncio.sleep(1)

        return {"success": False, "error": f"타임아웃 ({timeout}ms)"}
    except Exception as e:
        return {"success": False, "error": f"대기 실패: {e}"}


async def browser_screenshot(params: dict, project_path: str = None) -> dict:
    d = _get_driver()
    try:
        result = await d.call_tool("computer", {
            "action": "screenshot",
            "tabId": d._tab_id
        })

        # 이미지 데이터가 있으면 파일로 저장
        if isinstance(result, dict) and "image_data" in result:
            out_dir = _output_dir(project_path)
            filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            filepath = out_dir / filename
            img_data = base64.b64decode(result["image_data"])
            filepath.write_bytes(img_data)
            return {"success": True, "path": str(filepath), "driver": "chrome"}

        return {"success": True, "result": result, "driver": "chrome"}
    except Exception as e:
        return {"success": False, "error": f"스크린샷 실패: {e}"}


async def browser_get_content(params: dict) -> dict:
    d = _get_driver()
    selector = params.get("selector")
    max_length = params.get("max_length", 10000)

    try:
        if selector:
            result = await d.call_tool("javascript_tool", {
                "action": "javascript_exec",
                "text": f"document.querySelector('{selector}')?.innerText?.substring(0, {max_length}) || ''",
                "tabId": d._tab_id
            })
        else:
            result = await d.call_tool("get_page_text", {"tabId": d._tab_id})

        text = result.get("text", "") if isinstance(result, dict) else str(result)
        if len(text) > max_length:
            text = text[:max_length]

        return {"success": True, "content": text, "length": len(text), "driver": "chrome"}
    except Exception as e:
        return {"success": False, "error": f"콘텐츠 추출 실패: {e}"}


async def browser_get_html(params: dict) -> dict:
    d = _get_driver()
    selector = params.get("selector")
    outer = params.get("outer", True)
    max_length = params.get("max_length", 50000)

    try:
        if selector:
            prop = "outerHTML" if outer else "innerHTML"
            expr = f"document.querySelector('{selector}')?.{prop}?.substring(0, {max_length}) || ''"
        else:
            expr = f"document.documentElement.outerHTML.substring(0, {max_length})"

        result = await d.call_tool("javascript_tool", {
            "action": "javascript_exec",
            "text": expr,
            "tabId": d._tab_id
        })

        html = result.get("text", "") if isinstance(result, dict) else str(result)
        return {"success": True, "html": html, "length": len(html), "driver": "chrome"}
    except Exception as e:
        return {"success": False, "error": f"HTML 추출 실패: {e}"}


async def browser_console_logs(params: dict) -> dict:
    d = _get_driver()
    log_type = params.get("type", "all")
    search = params.get("search")
    limit = params.get("limit", 100)

    try:
        mcp_params = {"tabId": d._tab_id, "limit": limit}
        if log_type == "error":
            mcp_params["onlyErrors"] = True
        if search:
            mcp_params["pattern"] = search

        result = await d.call_tool("read_console_messages", mcp_params)
        return {"success": True, "logs": result, "driver": "chrome"}
    except Exception as e:
        return {"success": False, "error": f"콘솔 로그 조회 실패: {e}"}


async def browser_network_logs(params: dict) -> dict:
    d = _get_driver()
    action = params.get("action", "get")
    url_filter = params.get("url_filter")
    limit = params.get("limit", 50)

    try:
        # Chrome MCP는 항상 캡처 중이므로 start/stop은 무시
        if action in ("start", "stop", "clear"):
            return {"success": True, "action": action, "message": "Chrome 드라이버에서는 항상 캡처됨", "driver": "chrome"}

        mcp_params = {"tabId": d._tab_id, "limit": limit}
        if url_filter:
            mcp_params["urlPattern"] = url_filter

        result = await d.call_tool("read_network_requests", mcp_params)
        return {"success": True, "logs": result, "driver": "chrome"}
    except Exception as e:
        return {"success": False, "error": f"네트워크 로그 조회 실패: {e}"}


async def browser_dialog_info(params: dict) -> dict:
    # Chrome MCP에는 직접적인 dialog 조회 기능이 없음
    return {"success": True, "dialog": None, "message": "Chrome 드라이버에서는 다이얼로그가 브라우저에서 직접 처리됨", "driver": "chrome"}


async def browser_save_pdf(params: dict, project_path: str = None) -> dict:
    d = _get_driver()
    try:
        # window.print()로 PDF 저장 트리거 (제한적)
        await d.call_tool("javascript_tool", {
            "action": "javascript_exec",
            "text": "window.print()",
            "tabId": d._tab_id
        })
        return {"success": True, "message": "PDF 인쇄 대화상자가 Chrome에서 열렸습니다", "driver": "chrome"}
    except Exception as e:
        return {"success": False, "error": f"PDF 저장 실패: {e}"}


async def browser_evaluate(params: dict) -> dict:
    d = _get_driver()
    expression = params.get("expression", "")
    if not expression:
        return {"success": False, "error": "expression 파라미터 필요"}

    try:
        result = await d.call_tool("javascript_tool", {
            "action": "javascript_exec",
            "text": expression,
            "tabId": d._tab_id
        })
        value = result.get("text", result) if isinstance(result, dict) else result
        return {"success": True, "result": value, "driver": "chrome"}
    except Exception as e:
        return {"success": False, "error": f"JS 실행 실패: {e}"}


async def browser_resize(params: dict) -> dict:
    d = _get_driver()
    width = params.get("width", 1280)
    height = params.get("height", 720)

    try:
        await d.call_tool("resize_window", {
            "width": width,
            "height": height,
            "tabId": d._tab_id
        })
        return {"success": True, "width": width, "height": height, "driver": "chrome"}
    except Exception as e:
        return {"success": False, "error": f"리사이즈 실패: {e}"}


async def browser_vision(params: dict, project_path: str = None) -> dict:
    d = _get_driver()
    try:
        result = await d.call_tool("computer", {
            "action": "screenshot",
            "tabId": d._tab_id
        })

        if isinstance(result, dict) and "image_data" in result:
            return {
                "success": True,
                "image": result["image_data"],
                "mime_type": result.get("mime_type", "image/png"),
                "driver": "chrome"
            }
        return {"success": True, "result": result, "driver": "chrome"}
    except Exception as e:
        return {"success": False, "error": f"비전 캡처 실패: {e}"}


async def browser_close(params: dict) -> dict:
    d = _get_driver()
    try:
        if d._tab_id:
            await d.call_tool("tabs_close_mcp", {"tabId": d._tab_id})
        d._tab_id = None
        d._ref_map.clear()
        d._reverse_ref.clear()
        return {"success": True, "message": "Chrome 탭 닫힘", "driver": "chrome"}
    except Exception as e:
        return {"success": False, "error": f"닫기 실패: {e}"}


# ─────────────────────────────────────────────
# 탭 관리
# ─────────────────────────────────────────────

async def browser_tab_list(params: dict) -> dict:
    d = _get_driver()
    try:
        result = await d.call_tool("tabs_context_mcp", {})
        tabs = result.get("tabs", []) if isinstance(result, dict) else []
        formatted = []
        for i, tab in enumerate(tabs):
            tab_id = tab.get("id") or tab if isinstance(tab, (int, str)) else i
            formatted.append({
                "id": f"t{i + 1}",
                "chrome_id": tab_id,
                "active": tab_id == d._tab_id
            })
        return {"success": True, "tabs": formatted, "driver": "chrome"}
    except Exception as e:
        return {"success": False, "error": f"탭 목록 조회 실패: {e}"}


async def browser_tab_new(params: dict) -> dict:
    d = _get_driver()
    url = params.get("url")

    try:
        result = await d.call_tool("tabs_create_mcp", {})
        new_tab_id = result.get("tabId") or result.get("id")

        if new_tab_id:
            d._tab_id = new_tab_id
            d._ref_map.clear()
            d._reverse_ref.clear()

        if url:
            await d.call_tool("navigate", {"url": url, "tabId": d._tab_id})

        return {"success": True, "tab_id": d._tab_id, "driver": "chrome"}
    except Exception as e:
        return {"success": False, "error": f"새 탭 생성 실패: {e}"}


async def browser_tab_switch(params: dict) -> dict:
    d = _get_driver()
    tab_id = params.get("tab_id", "")

    try:
        # t1, t2 형식 → 실제 chrome tab id로 변환
        result = await d.call_tool("tabs_context_mcp", {})
        tabs = result.get("tabs", []) if isinstance(result, dict) else []

        # tN 인덱스에서 N 추출
        idx = 0
        if tab_id.startswith("t"):
            try:
                idx = int(tab_id[1:]) - 1
            except ValueError:
                idx = 0

        if 0 <= idx < len(tabs):
            chrome_id = tabs[idx].get("id") or tabs[idx]
            d._tab_id = chrome_id
            d._ref_map.clear()
            d._reverse_ref.clear()
            return {"success": True, "tab_id": tab_id, "chrome_id": chrome_id, "driver": "chrome"}
        else:
            return {"success": False, "error": f"탭 인덱스 범위 초과: {tab_id}"}
    except Exception as e:
        return {"success": False, "error": f"탭 전환 실패: {e}"}


async def browser_tab_close(params: dict) -> dict:
    d = _get_driver()
    tab_id = params.get("tab_id")

    try:
        close_id = d._tab_id
        if tab_id and tab_id.startswith("t"):
            # 특정 탭 닫기 - 인덱스 변환 필요
            result = await d.call_tool("tabs_context_mcp", {})
            tabs = result.get("tabs", []) if isinstance(result, dict) else []
            idx = int(tab_id[1:]) - 1
            if 0 <= idx < len(tabs):
                close_id = tabs[idx].get("id") or tabs[idx]

        if close_id:
            await d.call_tool("tabs_close_mcp", {"tabId": close_id})
            if close_id == d._tab_id:
                d._tab_id = None
                d._ref_map.clear()
                d._reverse_ref.clear()
                # 남은 탭으로 전환
                await d._ensure_tab()

        return {"success": True, "closed": tab_id or "current", "driver": "chrome"}
    except Exception as e:
        return {"success": False, "error": f"탭 닫기 실패: {e}"}


# ─────────────────────────────────────────────
# iframe (Chrome에서는 read_page가 iframe 포함)
# ─────────────────────────────────────────────

async def browser_iframe_list(params: dict) -> dict:
    return {"success": True, "iframes": [], "message": "Chrome 드라이버에서는 read_page가 iframe을 포함합니다", "driver": "chrome"}

async def browser_iframe_switch(params: dict) -> dict:
    return {"success": True, "message": "Chrome 드라이버에서는 iframe 전환이 불필요합니다 (read_page에 포함)", "driver": "chrome"}

async def browser_iframe_reset(params: dict) -> dict:
    return {"success": True, "message": "Chrome 드라이버에서는 iframe 리셋이 불필요합니다", "driver": "chrome"}


# ─────────────────────────────────────────────
# 쿠키 (실제 Chrome이므로 불필요)
# ─────────────────────────────────────────────

async def browser_cookies_save(params: dict, project_path: str = None) -> dict:
    return {"success": True, "message": "Chrome 드라이버에서는 쿠키가 실제 Chrome에 자동 저장됩니다", "driver": "chrome"}

async def browser_cookies_load(params: dict, project_path: str = None) -> dict:
    return {"success": True, "message": "Chrome 드라이버에서는 쿠키가 실제 Chrome에서 자동 로드됩니다", "driver": "chrome"}
