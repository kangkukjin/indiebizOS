#!/usr/bin/env python3
"""ci_playwright_smoke.py — '받은 곳'과 '보는 곳'이 같은가를 실제 렌더로 증명한다.

부팅 스모크(ci_boot_smoke.py)로는 이 부류가 안 잡힌다: 브라우저가 어긋나 있어도
import 도 부팅도 /health 도 전부 초록이고, 슬라이드·강의영상·글자얹기·browser-action 이
*돌 때* 처음 터진다(2026-08-15 실측). 그래서 CI 는 한 번 실제로 굽는다.

백엔드와 같은 순서로 환경을 세우고(runtime_utils.setup_bundled_runtime_paths),
①chromium 실행파일이 그 주소 안에 있는지 ②정말 떠서 PNG 를 굽는지 를 본다.
①이 핵심 단언 — 실행파일이 기본 캐시에서 나오면 그 순간 드리프트다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "base"))


def main() -> int:
    from runtime_utils import (setup_bundled_runtime_paths, get_playwright_browsers_path,
                               check_playwright_browsers)
    setup_bundled_runtime_paths()      # 백엔드 부팅과 같은 배선
    browsers = get_playwright_browsers_path().resolve()
    print(f"브라우저 주소: {browsers}")

    res = check_playwright_browsers()
    if not res["ok"]:
        print(f"✗ 정합 점검 실패: {res['note']}")
        return 1
    print(f"✓ 정합 점검 통과 (playwright {res['playwright_version']})")

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        exe = Path(p.chromium.executable_path).resolve()
        print(f"chromium 실행파일: {exe}")
        # ★핵심 단언 — 우리가 받은 곳에서 나와야 한다(기본 캐시에서 나오면 드리프트)
        if browsers not in exe.parents:
            print(f"✗ 드리프트: 실행파일이 {browsers} 밖에 있다 — "
                  f"설치와 실행이 다른 곳을 보고 있다")
            return 1

        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 400, "height": 200})
            page.set_content("<h1 style='font:700 40px sans-serif'>IndieBiz</h1>")
            png = page.screenshot(type="png")
        finally:
            browser.close()

    if not png or not png.startswith(b"\x89PNG"):
        print(f"✗ 렌더 결과가 PNG 가 아님 ({len(png or b'')} bytes)")
        return 1
    print(f"✓ 실제 렌더 성공 — PNG {len(png)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
