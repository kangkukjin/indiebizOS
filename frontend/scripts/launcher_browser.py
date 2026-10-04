"""런처 실화면 검사의 공통 준비·전환 관측. 실제 API 쓰기 없이 빌드된 UI를 검사한다."""
import json
from urllib.parse import urlsplit

from playwright.sync_api import expect


def prepare_launcher(page, url, login=False):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.add_init_script("""localStorage.setItem('indiebiz_has_seen_guide','true');
      window.WebSocket=class {static OPEN=1;static CLOSED=3;readyState=1;
      constructor(){setTimeout(()=>this.onopen?.(),50)}close(){this.readyState=3}};""")
    origin = urlsplit(url).netloc

    def api(route):
        target = urlsplit(route.request.url)
        if target.netloc == origin and (target.path in {"/", "/launcher/app"} or target.path.startswith("/assets/")):
            route.continue_()
            return
        path = target.path
        payload = {}
        if login and path == "/projects":
            route.fulfill(status=401, content_type="application/json", body="{}")
            return
        if path == "/launcher/config":
            payload = {"has_password": login, "host": "desktop"}
        elif path in {"/projects", "/switches", "/folders"}:
            payload = {path[1:]: []}
        elif path == "/launcher/instruments":
            payload = {"instruments": []}
        elif path == "/launcher/app-layout":
            payload = {"version": 1, "positions": {}, "folders": {}, "membership": {},
                       "removed": [], "uninstalled": [], "promoted": []}
        elif path == "/health":
            payload = {"status": "ok"}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload),
                      headers={"Access-Control-Allow-Origin": "*"})
    page.route("**/*", api)
    return errors


def settled_style(locator, properties):
    """hover/focus 직후 전환의 끝을 관측한다. 임의 sleep이나 전환 중간 색 비교가 없다."""
    return locator.evaluate("""async (el, properties) => {
      await document.fonts.ready;
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      await Promise.all(el.getAnimations().filter(a => Number.isFinite(a.effect.getComputedTiming().endTime))
        .map(a => a.finished.catch(() => {})));
      const style = getComputedStyle(el);
      return Object.fromEntries(properties.map(key => [key, style[key]]));
    }""", properties)


def select_locale(page, picker, locale, *, keyboard=False):
    """일반 선택과 실제 키보드 선택을 구별하고 값·문서 언어까지 확인한다."""
    if keyboard:
        if locale != "en":
            raise ValueError("키보드 인수는 English의 문자 선택을 사용합니다")
        page.keyboard.press("Tab")
        picker.focus()
        expect(picker).to_be_focused()
        assert picker.evaluate("el => el.matches(':focus-visible')")
        picker.press("e")
        picker.press("Tab")
    else:
        picker.select_option(locale)
    expect(picker).to_have_value(locale)
    expect(page.locator("html")).to_have_attribute("lang", locale)
