"""Remote picker acceptance on generated/live HTML with isolated API fixtures."""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

import pytest
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def launcher():
    html = json.loads((ROOT / "i18n/remote.json").read_text())["html"]
    live = os.environ.get("INDIEBIZ_VERIFY_BASE_URL")
    if live:
        with urlopen(live.rstrip("/") + "/launcher/app", timeout=15) as response:
            loaded = response.read().decode()
        assert loaded == html, "Live remote launcher must serve the verified bundle"
        html = loaded

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/launcher/app":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html.encode())))
            self.end_headers()
            self.wfile.write(html.encode())

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}/launcher/app"
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(headless=True)
        yield instance
        instance.close()


def prepare(page, url, login):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.add_init_script("""window.WebSocket=class {static OPEN=1;readyState=1;
      constructor(){setTimeout(()=>this.onopen?.(),50)}close(){}};""")

    def api(route):
        if route.request.url == url:
            route.continue_()
            return
        path = urlsplit(route.request.url).path
        payload = {}
        if login and path == "/projects":
            route.fulfill(status=401, content_type="application/json", body="{}")
            return
        if path == "/launcher/config":
            payload = {"has_password": login, "host": "desktop"}
        elif path in ["/projects", "/switches", "/folders"]:
            payload = {path[1:]: []}
        elif path == "/launcher/instruments":
            payload = {"instruments": []}
        elif path == "/launcher/app-layout":
            payload = {"version": 1, "positions": {}, "folders": {},
                       "membership": {}, "removed": [], "uninstalled": [], "promoted": []}
        elif path == "/health":
            payload = {"status": "ok"}
        if urlsplit(route.request.url).netloc != urlsplit(url).netloc:
            route.fulfill(status=200, body="")
        else:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))
    page.route("**/*", api)
    return errors


@pytest.mark.parametrize("width", [320, 390, 1280])
@pytest.mark.parametrize("login", [False, True])
def test_remote_picker_layout_language_and_keyboard(launcher, browser, width, login, tmp_path):
    context = browser.new_context(viewport={"width": width, "height": 800})
    page = context.new_page()
    errors = prepare(page, launcher, login)
    page.goto(launcher)
    scope = ".login-box" if login else ".top"
    picker = page.locator(scope).get_by_label("Language / 언어")
    expect(picker).to_be_visible()
    wrapper = picker.locator("..")
    assert wrapper.locator('svg[aria-hidden="true"]').count() == 2
    for locale in ["en", "ja", "ko"]:
        picker.select_option(locale)
        expect(page.locator("html")).to_have_attribute("lang", locale)
        expect(page.locator(".ui-language").nth(0)).to_have_value(locale)
        expect(page.locator(".ui-language").nth(1)).to_have_value(locale)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        box = picker.bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= width
    # Compare actual browser styles with the neighbouring header control.
    styles = picker.evaluate("""el => {
      const a=getComputedStyle(el), b=getComputedStyle(document.querySelector('.clipmac'));
      return ['height','borderRadius','backgroundColor','color','fontSize','fontWeight','borderColor']
        .map(key=>[key,a[key],b[key]]);
    }""")
    assert all(a == b for _, a, b in styles), styles
    page.keyboard.press("Tab")
    picker.focus()
    assert picker.evaluate("el=>el.matches(':focus-visible')")
    assert picker.evaluate("el=>getComputedStyle(el).outlineStyle") == "solid"
    picker.press("e")
    picker.press("Tab")
    expect(picker).to_have_value("en")
    expect(page.locator("html")).to_have_attribute("lang", "en")
    picker.select_option("ja")
    page.reload()
    expect(picker).to_have_value("ja")
    expect(page.locator("html")).to_have_attribute("lang", "ja")
    sibling = context.new_page()
    sibling_errors = prepare(sibling, launcher, login)
    sibling.goto(launcher)
    other = sibling.locator(scope).get_by_label("Language / 언어")
    expect(other).to_have_value("ja")
    other.select_option("ko")
    expect(picker).to_have_value("ko")
    expect(page.locator("html")).to_have_attribute("lang", "ko")
    page.screenshot(path=str(tmp_path / "remote-picker.png"))
    assert not errors + sibling_errors, errors + sibling_errors
    context.close()
