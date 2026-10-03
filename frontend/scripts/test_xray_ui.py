"""X-Ray acceptance: actual compiled page and route, isolated fixture API data."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
from api_xray import xray_app  # noqa: E402
from launcher_surface_remote import localized_html  # noqa: E402

USER_TEXT = "사용자 원문 — 새로고침"
DATA = {
    "system_health": {"overall": "healthy", "services": {"scheduler": True}},
    "ibl": {"by_node": {"sense": {"count": 1, "verified": 1}},
            "all_actions": [{"node": "sense", "action": "search", "status": "verified", "count": 2}]},
    "projects": [{"name": USER_TEXT, "message_count": 7}],
    "packages": {"total": 2, "tool_count": 2},
}
FIXTURES = {
    "/xray/data": DATA,
    "/xray/goals": {"tasks": [{"original_request": USER_TEXT, "project_name": USER_TEXT}], "pending_count": 0},
    "/xray/tools": {"system_ai_tools": [], "agent_tools": [], "tool_parity": True,
                    "ibl_nodes": {}, "all_node_names": [], "total_ibl_actions": 0, "projects": []},
    "/xray/cognition": {"gear": {"current": "균형", "presets": ["절약", "균형", "최대"],
                                  "axes": {key: "중급" for key in ["분류", "평가", "실행", "의식"]}}},
    "/xray/memory": {},
    "/xray/docs": {"files": [{"name": "system.md", "size_lines": 20,
                              "sections": [{"title": USER_TEXT, "content": USER_TEXT, "level": 2}]}]},
}


@pytest.fixture(scope="module")
def server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/xray/app":
                live_url = os.environ.get("INDIEBIZ_VERIFY_BASE_URL") or os.environ.get("XRAY_LIVE_URL")
                if live_url:
                    from urllib.request import urlopen
                    with urlopen(live_url.rstrip("/") + "/xray/app", timeout=15) as response:
                        body = response.read()
                    assert body == json.loads((ROOT / "frontend/i18n/xray.json").read_text())["html"].encode()
                else:
                    body = asyncio.run(xray_app()).body
                kind = "text/html; charset=utf-8"
            elif path == "/host":
                body = b'''<select id="language"><option>en</option><option>ko</option></select>
                <iframe id="xray"></iframe><script>
                const child = new URL(location.href).searchParams.get('child');
                const frame = document.querySelector('iframe');
                frame.src=child+'/xray/app?ui_locale=en';
                document.querySelector('select').onchange=event=>frame.contentWindow.postMessage(
                  {type:'indiebiz:ui-locale',locale:event.target.value},child);
                </script>'''
                kind = "text/html"
            else:
                body = json.dumps(FIXTURES.get(path, {})).encode()
                kind = "application/json"
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


@pytest.fixture
def browser():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        yield browser
        browser.close()


def prepare(page):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.add_init_script("""window.WebSocket=class {static OPEN=1;static CLOSED=3;readyState=1;
      constructor(){setTimeout(()=>this.onopen?.(),50)}close(){}};""")
    return errors


def test_source_hash_route_and_missing_translation_fallback():
    raw = (ROOT / "data/xray/index.html").read_text()
    bundle = json.loads((ROOT / "frontend/i18n/xray.json").read_text())
    assert bundle["source_hash"] == hashlib.sha256(raw.encode()).hexdigest()
    assert asyncio.run(xray_app()).body.decode() == bundle["html"]
    assert localized_html(raw + "<!--changed-->", "xray") == raw + "<!--changed-->"
    catalog = json.loads((ROOT / "frontend/i18n/catalog.json").read_text())
    messages = [m for m in catalog["messages"].values() if m["context"].startswith("xray:")]
    assert len(messages) > 200
    assert all("en" in m["translations"] for m in messages)


def test_all_tabs_switch_reopen_and_preserve_content(server, browser):
    context = browser.new_context()
    page = context.new_page()
    errors = prepare(page)
    page.goto(server + "/xray/app?ui_locale=en")
    page.wait_for_selector(".tab-bar")
    assert page.locator("html").get_attribute("lang") == "en"
    assert page.get_by_text("Refresh", exact=True).count() == 1
    assert page.locator(".proj-name").inner_text() == USER_TEXT
    assert "scheduler" in page.locator("#tab-bodymap").inner_text()
    for tab in ["bodymap", "goals", "tools", "cognition", "memory", "dashboard", "docs"]:
        page.click(f'[data-tab="{tab}"]')
        page.wait_for_timeout(80)
        content = page.locator(f"#tab-{tab}").inner_text().replace(USER_TEXT, "")
        import re
        assert not re.search("[가-힣]", content), (tab, content)
    assert page.locator(".doc-text").inner_text() == USER_TEXT
    page.evaluate("window.__ui.setLocale('ko')")
    assert page.get_by_text("새로고침", exact=True).count() == 1
    assert page.locator('[data-tab="docs"]').get_attribute("class").endswith("active")
    assert page.locator(".doc-text").inner_text() == USER_TEXT
    sibling = context.new_page()
    prepare(sibling)
    sibling.goto(server + "/xray/app")
    sibling.wait_for_selector(".tab-bar")
    sibling.evaluate("window.__ui.setLocale('en')")
    page.wait_for_function("document.documentElement.lang==='en'")
    assert page.get_by_text("Refresh", exact=True).count() == 1
    assert page.locator(".doc-text").inner_text() == USER_TEXT
    page.reload()
    page.wait_for_selector(".tab-bar")
    assert page.locator("html").get_attribute("lang") == "en"
    page.evaluate("showNodeDetail('sense')")
    assert "Action details" in page.locator(".node-modal").inner_text()
    page.evaluate("window.__ui.setLocale('ko')")
    assert "액션 상세" in page.locator(".node-modal").inner_text()
    page.evaluate("window.__ui.setLocale('en'); fetchData()")
    page.wait_for_timeout(100)
    assert page.get_by_text("Refresh", exact=True).count() == 1
    assert not errors, errors
    context.close()


def test_cross_origin_parent_language_and_untrusted_message(server, browser):
    page = browser.new_page()
    errors = prepare(page)
    # localhost and 127.0.0.1 deliberately use different localStorage origins.
    parent = server.replace("127.0.0.1", "localhost")
    page.goto(parent + "/host?child=" + server)
    frame = page.frame_locator("#xray")
    frame.locator(".tab-bar").wait_for()
    assert frame.get_by_text("Refresh", exact=True).count() == 1
    page.select_option("#language", "ko")
    frame.get_by_text("새로고침", exact=True).wait_for()
    page.select_option("#language", "en")
    frame.get_by_text("Refresh", exact=True).wait_for()
    page.frames[1].evaluate("window.postMessage({type:'indiebiz:ui-locale',locale:'ko'},'*')")
    page.wait_for_timeout(50)
    assert frame.get_by_text("Refresh", exact=True).count() == 1
    assert not errors, errors


def test_failure_and_live_updates_follow_locale(server, browser):
    page = browser.new_page()
    errors = prepare(page)
    page.goto(server + "/xray/app?ui_locale=en")
    page.wait_for_selector(".tab-bar")
    page.route("**/xray/tools", lambda route: route.abort())
    page.click('[data-tab="tools"]')
    page.wait_for_function("document.getElementById('tools-panel').textContent.includes('Failed to load tools')")
    page.evaluate("ws.readyState=WebSocket.CLOSED; ws.onclose(); renderLiveFeed()")
    assert "Disconnected" in page.locator("#ws-status").inner_text()
    assert "Waiting for live events" in page.locator("#live-feed").inner_text()
    page.evaluate("window.__ui.setLocale('ko')")
    assert "연결 끊김" in page.locator("#ws-status").inner_text()
    page.evaluate("window.__ui.setLocale('en')")
    assert "Disconnected" in page.locator("#ws-status").inner_text()
    page.route("**/xray/data", lambda route: route.abort())
    page.reload()
    page.wait_for_function("document.body.textContent.includes('Failed to load data')")
    page.evaluate("window.__ui.setLocale('ko')")
    assert "데이터 로드 실패" in page.locator("body").inner_text()
    assert not errors, errors
