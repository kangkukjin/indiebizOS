import json, re, sys, datetime
from urllib.parse import urlparse, urljoin
from playwright.sync_api import sync_playwright

inp, out = sys.argv[1], sys.argv[2]
acct = json.load(open(f"{inp}/account.json", encoding="utf-8"))
base = acct["portal_url"]
B = urlparse(base)
log = {"portal": f"{B.hostname}:{B.port}", "steps": []}

def same_origin(u):
    p = urlparse(u)
    return (p.hostname, p.port) == (B.hostname, B.port)

def norm(d):
    m = re.search(r"(\d{4})\D(\d{1,2})\D(\d{1,2})", d or "")
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else None

def today_of(page):
    m = re.search(r"오늘\s*:\s*([0-9.\-/ ]+)", page.inner_text("body"))
    return m.group(1).strip() if m else None

def detail_due(page):
    t = page.inner_text("body")
    m = re.search(r"반납일\s*\n\s*([0-9.\-/]+)", t)
    return (m.group(1) if m else None), t

with sync_playwright() as p:
    br = p.chromium.launch(headless=True)
    ctx = br.new_context(viewport={"width": 1000, "height": 700})
    page = ctx.new_page()
    page.goto(base)
    page.get_by_label("이용자 ID").fill(acct["user"])
    page.get_by_label("비밀번호").fill(acct["password"])
    page.get_by_role("button", name="로그인").click()
    page.wait_for_load_state()
    log["after_login_url"] = page.url
    log["login_ok"] = same_origin(page.url) and "로그아웃" in page.inner_text("body")
    log["today_raw"] = today_of(page)
    today = norm(log["today_raw"])
    log["today"] = today

    rows, pages = [], []
    while True:
        assert same_origin(page.url), page.url
        body = page.inner_text("body")
        hdr = re.search(r"총\s*(\d+)권\s*·\s*(\d+)/(\d+)", body)
        prow = []
        for tr in page.locator("table tbody tr").all():
            tds = tr.locator("td").all()
            if len(tds) < 5:
                continue
            vals = [td.inner_text().strip() for td in tds[:5]]
            a = tds[1].locator("a")
            href = urljoin(page.url, a.first.get_attribute("href")) if a.count() else None
            prow.append({"id": vals[0], "title": vals[1], "author": vals[2], "due_raw": vals[3],
                         "due": norm(vals[3]), "status": vals[4], "page": len(pages) + 1, "detail_url": href})
        pages.append({"page": len(pages) + 1, "url": page.url, "rows": len(prow),
                      "header": hdr.group(0) if hdr else None, "today_raw": today_of(page)})
        rows += prow
        nxt = page.get_by_role("link", name=re.compile("다음"))
        if nxt.count() == 0:
            break
        nxt.first.click()
        page.wait_for_load_state()
        if len(pages) > 50:
            break
    log["pages"] = pages
    log["rows"] = rows

    cutoff = (datetime.date.fromisoformat(today) + datetime.timedelta(days=3)).isoformat()
    log["cutoff"] = cutoff
    attempts = []
    for r in rows:
        if not r["due"] or r["due"] > cutoff:
            continue
        a = {"id": r["id"], "title": r["title"], "status_in_list": r["status"], "due_in_list": r["due"]}
        attempts.append(a)
        if "연장 가능" not in r["status"]:
            a.update(result="not_requested", reason=f"목록 상태가 '{r['status']}' — 신청하지 않음")
            continue
        page.goto(r["detail_url"])
        page.wait_for_load_state()
        before, btext = detail_due(page)
        a["pre_click_url"] = page.url
        if not same_origin(page.url) or r["id"] not in btext:
            a.update(result="aborted", reason="클릭 직전 포털 주소 또는 책 번호 불일치")
            continue
        a["before_due"] = norm(before)
        a["before_text"] = btext
        a["shot_before"] = f"{out}/shots/{r['id']}_before.png"
        page.screenshot(path=a["shot_before"], full_page=True)
        btn = page.get_by_role("button", name="연장 신청", exact=True)
        if btn.count() != 1:
            a.update(result="failed", reason=f"'연장 신청' 버튼 {btn.count()}개")
            continue
        dialogs = []
        def on_dialog(d, dialogs=dialogs):
            dialogs.append({"type": d.type, "message": d.message})
            d.accept()
        page.on("dialog", on_dialog)
        btn.click()
        page.wait_for_load_state()
        page.wait_for_timeout(500)
        page.remove_listener("dialog", on_dialog)
        a["dialogs"] = dialogs
        a["after_click_url"] = page.url
        a["after_click_text"] = page.inner_text("body")
        page.goto(r["detail_url"])
        page.wait_for_load_state()
        after, atext = detail_due(page)
        a["after_due"] = norm(after)
        a["after_text"] = atext
        a["shot_after"] = f"{out}/shots/{r['id']}_after.png"
        page.screenshot(path=a["shot_after"], full_page=True)
        if not dialogs:
            a.update(result="failed", reason="확인창이 뜨지 않음")
        elif a["after_due"] and a["before_due"] and a["after_due"] > a["before_due"]:
            a.update(result="success", reason="")
        else:
            a.update(result="failed", reason="신청 후 다시 읽은 반납일이 바뀌지 않음")
    log["attempts"] = attempts

    page.goto(base)
    page.get_by_role("link", name="공지").first.click()
    page.wait_for_load_state()
    log["notice_url"] = page.url
    frames = []
    for f in page.frames:
        if f == page.main_frame:
            continue
        try:
            frames.append({"name": f.name, "url": f.url, "text": f.inner_text("body")})
        except Exception as e:
            frames.append({"name": f.name, "url": f.url, "error": str(e)})
    log["notice_frames"] = frames
    log["notice_outer_text"] = page.inner_text("body")

    page.goto(base)
    lst = []
    pg = 1
    while True:
        for tr in page.locator("table tbody tr").all():
            tds = tr.locator("td").all()
            if len(tds) >= 5:
                lst.append([td.inner_text().strip() for td in tds[:5]])
        nxt = page.get_by_role("link", name=re.compile("다음"))
        if nxt.count() == 0 or pg > 50:
            break
        nxt.first.click(); page.wait_for_load_state(); pg += 1
    log["final_list"] = lst
    br.close()

json.dump(log, open(f"{out}/analysis/portal_run.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(log, ensure_ascii=False))
