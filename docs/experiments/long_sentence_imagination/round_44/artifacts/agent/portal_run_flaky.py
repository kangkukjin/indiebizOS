import json, re, sys, datetime
from urllib.parse import urlparse, urljoin
from playwright.sync_api import sync_playwright

# 44회차 불안정판: 직전 out/scripts/portal_run.py + 페이지별 일시 오류 재시도 + 연장 거절 판독
inp, out = sys.argv[1], sys.argv[2]
MAX_TRY = 3
acct = json.load(open(f"{inp}/account.json", encoding="utf-8"))
base = acct["portal_url"]
B = urlparse(base)
log = {"portal": f"{B.hostname}:{B.port}", "max_try": MAX_TRY, "fetches": []}

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

def is_error(status, body, ok_check):
    if status is not None and status >= 500:
        return f"HTTP {status}"
    if "일시적인 오류" in body or "일시적 오류" in body:
        return "본문에 '일시적인 오류'"
    if ok_check and not ok_check(body):
        return "정상 화면 표지 없음"
    return None

def fetch(page, url, label, ok_check=None, click=None):
    """같은 주소를 MAX_TRY 회까지 요청. 시도마다 상태·오류 문구 기록."""
    rec = {"label": label, "url": url, "attempts": []}
    log["fetches"].append(rec)
    for i in range(1, MAX_TRY + 1):
        if click and i == 1:
            with page.expect_navigation():
                click()
            resp_status = None
            nav_url = page.url
        else:
            resp = page.goto(url)
            resp_status = resp.status if resp else None
            nav_url = page.url
        page.wait_for_load_state()
        body = page.inner_text("body")
        err = is_error(resp_status, body, ok_check)
        a = {"try": i, "url": nav_url, "status": resp_status, "error": err}
        if err:
            first = [l for l in body.splitlines() if "오류" in l][:2]
            a["error_text"] = first
            page.screenshot(path=f"{out}/shots/err_{label}_try{i}.png", full_page=True)
            a["shot"] = f"{out}/shots/err_{label}_try{i}.png"
        rec["attempts"].append(a)
        if not err:
            rec["final"] = "ok"
            rec["tries"] = i
            return True
        url = nav_url if same_origin(nav_url) else url
    rec["final"] = "unconfirmed"
    rec["tries"] = MAX_TRY
    return False

has_list = lambda b: re.search(r"총\s*\d+권", b) is not None

def read_list_page(page, pno):
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
                     "due": norm(vals[3]), "status": vals[4], "page": pno, "detail_url": href})
    nxt = page.get_by_role("link", name=re.compile("다음"))
    nhref = urljoin(page.url, nxt.first.get_attribute("href")) if nxt.count() else None
    return hdr, prow, nhref

def read_all(page, first_url, tag):
    rows, pages, url, pno, total, npages = [], [], first_url, 1, None, None
    while url and pno <= 50:
        ok = fetch(page, url, f"{tag}_p{pno}", ok_check=has_list)
        if not ok:
            pages.append({"page": pno, "url": url, "status": "unconfirmed", "rows": None})
            # 다음 주소를 화면에서 못 얻으므로 같은 규칙(page=N+1)으로만 이어 감 — 기록에 명시
            if npages and pno < npages:
                url = re.sub(r"page=\d+", f"page={pno + 1}", url); pno += 1
                pages[-1]["next_by_rule"] = url
                continue
            break
        hdr, prow, nhref = read_list_page(page, pno)
        if hdr:
            total, npages = int(hdr.group(1)), int(hdr.group(3))
        pages.append({"page": pno, "url": page.url, "status": "ok", "rows": len(prow),
                      "header": hdr.group(0) if hdr else None, "today_raw": today_of(page)})
        rows += prow
        url = nhref; pno += 1
    return rows, pages, total, npages

def msg_lines(text, title):
    """제목 줄과 '번호' 줄 사이의 결과 메시지(원문)."""
    ls = [l.strip() for l in text.splitlines() if l.strip()]
    try:
        s = ls.index(title) + 1
    except ValueError:
        s = 0
    e = ls.index("번호") if "번호" in ls[s:] else len(ls)
    return ls[s:e]

with sync_playwright() as p:
    br = p.chromium.launch(headless=True)
    ctx = br.new_context(viewport={"width": 1000, "height": 700})
    page = ctx.new_page()
    fetch(page, base, "login_form", ok_check=lambda b: "비밀번호" in b or "로그아웃" in b)
    page.get_by_label("이용자 ID").fill(acct["user"])
    page.get_by_label("비밀번호").fill(acct["password"])
    page.get_by_role("button", name="로그인").click()
    page.wait_for_load_state()
    log["after_login_url"] = page.url
    log["after_login_landing_error"] = is_error(None, page.inner_text("body"), has_list)
    log["login_ok"] = same_origin(page.url) and "로그아웃" in page.inner_text("body")
    first_url = page.url if "loans" in page.url else urljoin(base, "loans?page=1")
    rows, pages, total, npages = read_all(page, first_url, "list")
    log["pages"], log["rows"] = pages, rows
    log["total_header"], log["pages_header"] = total, npages
    log["today_raw"] = next((x["today_raw"] for x in pages if x.get("today_raw")), None)
    log["today_values"] = sorted({x["today_raw"] for x in pages if x.get("today_raw")})
    today = norm(log["today_raw"])
    log["today"] = today

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
        if not fetch(page, r["detail_url"], f"detail_{r['id']}_before", ok_check=lambda b: "반납일" in b):
            a.update(result="unconfirmed", reason="상세 화면 재시도 상한 초과 — 신청하지 않음")
            continue
        before, btext = detail_due(page)
        a["pre_click_url"] = page.url
        if not same_origin(page.url) or not page.url.rstrip("/").endswith(r["id"]) or r["id"] not in btext:
            a.update(result="aborted", reason="클릭 직전 포털 주소 또는 책 번호 불일치")
            continue
        a["pre_click_check"] = {"host_port": f"{urlparse(page.url).hostname}:{urlparse(page.url).port}", "id_in_url": True, "id_in_body": True}
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
        page.wait_for_timeout(700)
        page.remove_listener("dialog", on_dialog)
        a["dialogs"] = dialogs
        a["after_click_url"] = page.url
        atxt = page.inner_text("body")
        a["after_click_text"] = atxt
        a["result_message"] = msg_lines(atxt, r["title"])
        a["after_click_error"] = is_error(None, atxt, None)
        a["shot_after_click"] = f"{out}/shots/{r['id']}_after_click.png"
        page.screenshot(path=a["shot_after_click"], full_page=True)
        if not fetch(page, r["detail_url"], f"detail_{r['id']}_after", ok_check=lambda b: "반납일" in b):
            a.update(result="unconfirmed", reason="신청 후 상세 재조회 실패 — 결과 미확인")
            continue
        after, atext = detail_due(page)
        a["after_due"] = norm(after)
        a["after_text"] = atext
        a["shot_after"] = f"{out}/shots/{r['id']}_after.png"
        page.screenshot(path=a["shot_after"], full_page=True)
        changed = bool(a["after_due"] and a["before_due"] and a["after_due"] > a["before_due"])
        if not dialogs:
            a.update(result="failed", reason="확인창이 뜨지 않음")
        elif changed:
            a.update(result="success", reason="")
        else:
            msg = " / ".join(a["result_message"]) or "(메시지 없음)"
            a.update(result="failed", reason=msg)
    log["attempts"] = attempts

    fetch(page, base, "home_for_notice", ok_check=lambda b: "공지" in b)
    page.get_by_role("link", name="공지").first.click()
    page.wait_for_load_state()
    if is_error(None, page.inner_text("body"), None):
        fetch(page, page.url, "notice", ok_check=None)
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

    frows, fpages, ftotal, _ = read_all(page, first_url, "final")
    log["final_list"] = [[x["id"], x["title"], x["author"], x["due_raw"], x["status"]] for x in frows]
    log["final_pages"] = fpages
    br.close()

json.dump(log, open(f"{out}/analysis/portal_run.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({k: log[k] for k in ("portal", "login_ok", "today_raw", "cutoff", "total_header", "pages_header")}, ensure_ascii=False))
