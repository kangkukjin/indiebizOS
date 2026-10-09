"""대조 실험 — 같은 화면·같은 조건(스크롤 0, 대상=칸 영역)에서 Playwright 의 locator.drag_to 를 직접 부른다. IBL 을 거치지 않는다."""
import json, sys
from playwright.sync_api import sync_playwright
u = sys.argv[1]
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={'width': 1280, 'height': 720})
    pg.goto(u + 'login'); pg.fill('input[name=user]', 'x'); pg.fill('input[name=password]', 'x'); pg.press('input[name=password]', 'Enter'); pg.goto(u + 'board')
    y0 = pg.evaluate('window.scrollY')
    pg.get_by_role('button', name='W-1004 최지호 참나무 트레이 3개').drag_to(pg.get_by_role('region', name='오늘 처리 칸'))
    pg.wait_for_timeout(300)
    print(json.dumps({'scrollY_before': y0, 'scrollY_after': pg.evaluate('window.scrollY'), 'today': pg.evaluate("Array.from(document.querySelectorAll('.col[data-col=\"오늘 처리\"] .card')).map(x=>x.dataset.id)")}, ensure_ascii=False)); b.close()
