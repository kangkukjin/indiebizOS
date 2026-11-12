"""웹 화면을 한 번 열어 오류·관측값·화면을 받는다.

수정한 웹앱이나 배포한 페이지가 뜨는지 확인할 때마다 브라우저 기동·오류 수집·대기·캡처를 새로
짜지 않기 위한 관측 도구다. 열고, 기다리고, 주어진 식을 평가하고, 원하면 화면을 저장한다.
클릭·입력 같은 조작과 합격 판정은 하지 않는다.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
import boot_paths  # noqa: E402,F401

MAX_MESSAGES = 30
MAX_VALUE_CHARS = 4000


def _integer(args, key, default, low, high):
    value = args.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{key}는 {low}~{high} 사이 정수여야 합니다.")
    return value


def _viewport(text):
    try:
        width, height = (int(part) for part in str(text).lower().split("x"))
    except ValueError as exc:
        raise ValueError('viewport는 "1280x800" 꼴이어야 합니다.') from exc
    if not (200 <= width <= 4000 and 200 <= height <= 4000):
        raise ValueError("viewport 크기는 200~4000 사이여야 합니다.")
    return {"width": width, "height": height}


def _clip(messages):
    kept = [str(m)[:500] for m in messages[:MAX_MESSAGES]]
    return kept, max(0, len(messages) - MAX_MESSAGES)


def run(args):
    url = args.get("url")
    if not isinstance(url, str) or not url.startswith(("http://", "https://", "file://")):
        raise ValueError("url은 http(s):// 또는 file:// 주소여야 합니다.")
    viewport = _viewport(args.get("viewport", "1280x800"))
    timeout = _integer(args, "timeout_ms", 30000, 1000, 120000)
    settle = _integer(args, "wait_ms", 500, 0, 30000)
    expressions = args.get("evaluate") or []
    if not isinstance(expressions, list) or any(not isinstance(e, str) or not e.strip() for e in expressions):
        raise ValueError("evaluate는 자바스크립트 식 문자열 목록이어야 합니다.")
    wait_function = args.get("wait_function")
    launch = []
    if args.get("webgl"):
        launch = ["--enable-gpu", "--ignore-gpu-blocklist"] + (["--use-angle=metal"] if sys.platform == "darwin" else [])

    from playwright.sync_api import Error, sync_playwright
    page_errors, console_errors, results = [], [], []
    out = {"url": url, "viewport": f'{viewport["width"]}x{viewport["height"]}', "loaded": False,
           "http_status": None, "final_url": None, "title": None, "screenshot": None}
    started = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch(args=launch)
        try:
            page = browser.new_context(viewport=viewport).new_page()
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
            try:
                response = page.goto(url, timeout=timeout, wait_until="load")
                out.update(loaded=True, http_status=response.status if response else None)
                if wait_function:
                    page.wait_for_function(wait_function, timeout=timeout)
                if settle:
                    page.wait_for_timeout(settle)
            except Error as exc:
                out["load_error"] = str(exc).splitlines()[0][:500]
            out.update(final_url=page.url, title=page.title() if out["loaded"] else None)
            for expression in expressions:
                try:
                    value = json.dumps(page.evaluate(expression), ensure_ascii=False, default=str)
                    row = {"expr": expression, "ok": True, "value": json.loads(value) if len(value) <= MAX_VALUE_CHARS
                           else value[:MAX_VALUE_CHARS], "clipped": len(value) > MAX_VALUE_CHARS}
                except Error as exc:
                    row = {"expr": expression, "ok": False, "error": str(exc).splitlines()[0][:500]}
                results.append(row)
            if args.get("screenshot"):
                from runtime_utils import get_base_path
                folder = get_base_path() / "data" / "outputs" / "web_checks"
                folder.mkdir(parents=True, exist_ok=True)
                name = time.strftime("%Y%m%d_%H%M%S_") + hashlib.sha256(url.encode()).hexdigest()[:8] + ".png"
                page.screenshot(path=str(folder / name), full_page=bool(args.get("full_page")))
                out["screenshot"] = str(folder / name)
        finally:
            browser.close()
    out["page_errors"], out["page_errors_omitted"] = _clip(page_errors)
    out["console_errors"], out["console_errors_omitted"] = _clip(console_errors)
    out.update(results=results, elapsed_ms=int((time.time() - started) * 1000),
               clean=bool(out["loaded"] and "load_error" not in out and not page_errors and not console_errors
                          and all(row["ok"] for row in results)))
    return out


if __name__ == "__main__":
    try:
        print(json.dumps(run(json.load(sys.stdin)), ensure_ascii=False, allow_nan=False))
    except (KeyError, ValueError, TypeError) as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
