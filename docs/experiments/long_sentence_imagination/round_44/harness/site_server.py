"""44회차 합성 도서관 대출 포털 — stdlib HTTP 서버. 상태(연장 기록)는 --state JSON 에 남긴다(검수 oracle 대조용).
사용: site_server.py --port 8931 --data <loans.json> --state <state.json> [--flaky]
--flaky: /loans?page=2 첫 요청 503, L03 연장 POST 는 '연장 횟수 초과' 오류 페이지(변형 자료)."""
import argparse, json, html, threading, urllib.parse, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http import cookies

TODAY = datetime.date(2026, 10, 9)
PAGE_SIZE = 5
NOTICE = "휴관일 안내: 10월 13일(월)은 정기 휴관일이며, 10월 24일(금)은 장서 점검으로 오후 1시부터 문을 닫습니다."
LOCK = threading.Lock()

def dot(d):  # 2026.10.09 표기(포털 표기 — 내 목록 CSV 의 2026-10-09 와 다름)
    return d.strftime("%Y.%m.%d")

class State:
    def __init__(self, path):
        self.path = path
        self.data = {"extended": [], "attempts": [], "logins": 0, "requests": 0, "page2_hits": 0}
        self.save()
    def save(self):
        with open(self.path, "w") as f: json.dump(self.data, f, ensure_ascii=False, indent=1)

class App:
    def __init__(self, data_path, state_path, flaky):
        with open(data_path) as f: cfg = json.load(f)
        self.account = cfg["account"]; self.loans = {l["id"]: dict(l) for l in cfg["loans"]}
        self.state = State(state_path); self.flaky = flaky; self.sessions = set()

def page(title, body, logged_in):
    nav = ('<a href="/loans?page=1">대출 현황</a> · <a href="/notice">공지</a> · <a href="/logout">로그아웃</a>' if logged_in else '<a href="/login">로그인</a>')
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{html.escape(title)} - 가상 동네도서관</title></head>
<body><header><h1>가상 동네도서관 이용자 포털</h1><p class="today">오늘: {dot(TODAY)}</p><nav>{nav}</nav></header><main>{body}</main>
<footer><small>가상 포털 — 훈련용 합성 자료</small></footer></body></html>"""

class Handler(BaseHTTPRequestHandler):
    app: App = None
    def log_message(self, *a): pass
    def _sid(self):
        c = cookies.SimpleCookie(self.headers.get("Cookie", "")); m = c.get("sid")
        return m.value if m and m.value in self.app.sessions else None
    def _send(self, code, body, headers=None):
        b = body.encode("utf-8"); self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(b)))
        for k, v in (headers or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(b)
    def _redirect(self, to, headers=None):
        self.send_response(303); self.send_header("Location", to)
        for k, v in (headers or {}).items(): self.send_header(k, v)
        self.send_header("Content-Length", "0"); self.end_headers()
    def do_GET(self):
        with LOCK: self.app.state.data["requests"] += 1; self.app.state.save()
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query); sid = self._sid()
        if u.path in ("/", "/login"):
            if sid: return self._redirect("/loans?page=1")
            err = '<p class="error">아이디 또는 비밀번호가 올바르지 않습니다.</p>' if q.get("err") else ""
            return self._send(200, page("로그인", f"""<h2>로그인</h2>{err}<form method="post" action="/login">
<label>이용자 ID <input type="text" name="user" autocomplete="username"></label><br>
<label>비밀번호 <input type="password" name="pw" autocomplete="current-password"></label><br>
<button type="submit">로그인</button></form>""", False))
        if u.path == "/logout":
            if sid: self.app.sessions.discard(sid)
            return self._redirect("/login")
        if not sid: return self._redirect("/login")
        if u.path == "/loans":
            p = int(q.get("page", ["1"])[0])
            if p == 2 and self.app.flaky:
                with LOCK:
                    self.app.state.data["page2_hits"] += 1; first = self.app.state.data["page2_hits"] == 1; self.app.state.save()
                if first: return self._send(503, page("일시적 오류", "<h2>일시적인 오류가 발생했습니다</h2><p>잠시 후 다시 시도해 주세요.</p>", True))
            ids = sorted(self.app.loans); total = len(ids); pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
            if p < 1 or p > pages: return self._send(404, page("없는 페이지", "<h2>페이지가 없습니다</h2>", True))
            rows = []
            for i in ids[(p - 1) * PAGE_SIZE: p * PAGE_SIZE]:
                l = self.app.loans[i]; due = datetime.date.fromisoformat(l["due"])
                st = "연장 완료" if l.get("extended") else ("연장 불가 (예약 대기 %d명)" % l["reserved"] if l.get("reserved") else "연장 가능")
                rows.append(f'<tr><td>{i}</td><td><a href="/loans/{i}">{html.escape(l["title"])}</a></td><td>{html.escape(l["author"])}</td><td>{dot(due)}</td><td>{st}</td></tr>')
            pager = " ".join(f'<a href="/loans?page={k}" aria-label="{k}페이지">{k}</a>' if k != p else f"<strong>{k}</strong>" for k in range(1, pages + 1))
            nxt = f'<a href="/loans?page={p+1}" rel="next">다음 ›</a>' if p < pages else ""
            body = f"""<h2>대출 현황</h2><p>총 {total}권 · {p}/{pages} 페이지</p>
<table id="loans"><thead><tr><th>번호</th><th>제목</th><th>저자</th><th>반납일</th><th>상태</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<div class="pager">{pager} {nxt}</div>"""
            return self._send(200, page("대출 현황", body, True))
        if u.path.startswith("/loans/"):
            i = u.path.split("/")[2]; l = self.app.loans.get(i)
            if not l: return self._send(404, page("없음", "<h2>해당 대출을 찾을 수 없습니다</h2>", True))
            due = datetime.date.fromisoformat(l["due"]); msg = ""
            if q.get("done"): msg = f'<p class="ok">연장이 완료되었습니다. 새 반납일: {dot(due)}</p>'
            if q.get("fail"): msg = f'<p class="error">연장할 수 없습니다: {html.escape(q["fail"][0])}</p>'
            if l.get("extended"): action = "<p>이미 연장되었습니다.</p>"
            elif l.get("reserved"): action = f'<button type="button" disabled>연장 불가 (예약 대기 {l["reserved"]}명)</button>'
            else: action = f'<form method="post" action="/loans/{i}/extend" onsubmit="return confirm(\'{html.escape(l["title"])}을(를) 연장하시겠습니까?\')"><button type="submit">연장 신청</button></form>'
            body = f"""<h2>{html.escape(l["title"])}</h2>{msg}<dl><dt>번호</dt><dd>{i}</dd><dt>저자</dt><dd>{html.escape(l["author"])}</dd>
<dt>반납일</dt><dd id="due">{dot(due)}</dd><dt>연장 횟수</dt><dd>{l.get("ext_count", 0)}/2</dd></dl>{action}<p><a href="/loans?page=1">← 대출 현황</a></p>"""
            return self._send(200, page(l["title"], body, True))
        if u.path == "/notice":
            return self._send(200, page("공지", '<h2>공지</h2><iframe name="notice" src="/notice_frame" width="600" height="200"></iframe>', True))
        if u.path == "/notice_frame":
            return self._send(200, f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>공지 본문</title></head><body><p id="holiday">{NOTICE}</p><p>기타: 3층 열람실은 10월 한 달 좌석 예약제로 운영합니다.</p></body></html>')
        return self._send(404, page("없음", "<h2>없는 주소</h2>", True))
    def do_POST(self):
        with LOCK: self.app.state.data["requests"] += 1; self.app.state.save()
        n = int(self.headers.get("Content-Length", "0")); form = urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8"))
        u = urllib.parse.urlparse(self.path)
        if u.path == "/login":
            user = form.get("user", [""])[0]; pw = form.get("pw", [""])[0]
            if user == self.app.account["user"] and pw == self.app.account["password"]:
                sid = "s%d" % (len(self.app.sessions) + 1 + self.app.state.data["logins"]); self.app.sessions.add(sid)
                with LOCK: self.app.state.data["logins"] += 1; self.app.state.save()
                return self._redirect("/loans?page=1", {"Set-Cookie": f"sid={sid}; Path=/; HttpOnly"})
            return self._redirect("/login?err=1")
        sid = self._sid()
        if not sid: return self._redirect("/login")
        if u.path.startswith("/loans/") and u.path.endswith("/extend"):
            i = u.path.split("/")[2]; l = self.app.loans.get(i)
            if not l: return self._send(404, page("없음", "<h2>없음</h2>", True))
            with LOCK:
                reason = None
                if l.get("reserved"): reason = "예약 대기자가 있습니다"
                elif l.get("extended"): reason = "이미 연장되었습니다"
                elif self.app.flaky and l.get("fail_flaky"): reason = "연장 횟수 초과"
                self.app.state.data["attempts"].append({"id": i, "ok": reason is None, "reason": reason})
                if reason is None:
                    l["due"] = (datetime.date.fromisoformat(l["due"]) + datetime.timedelta(days=14)).isoformat()
                    l["extended"] = True; l["ext_count"] = l.get("ext_count", 0) + 1; self.app.state.data["extended"].append(i)
                self.app.state.save()
            return self._redirect(f"/loans/{i}?done=1" if reason is None else f"/loans/{i}?fail=" + urllib.parse.quote(reason))
        return self._send(404, page("없음", "<h2>없는 주소</h2>", True))

def main():
    p = argparse.ArgumentParser(); p.add_argument("--port", type=int, required=True); p.add_argument("--data", required=True)
    p.add_argument("--state", required=True); p.add_argument("--flaky", action="store_true"); a = p.parse_args()
    Handler.app = App(a.data, a.state, a.flaky)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler); print("serving", a.port, flush=True); srv.serve_forever()

if __name__ == "__main__":
    main()
