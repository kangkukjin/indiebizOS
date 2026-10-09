"""46회차 합성 숙소 포털 — 한 코드로 두 사이트(--site A 바다숙소 / --site B 산장숙소). 상태는 --state JSON(검수 oracle).
흐름: /login → 쿠키 동의 모달(DOM 오버레이, '동의' 누르기 전엔 클릭 차단) → /search(날짜 선택 위젯: 달력 버튼, 인원 스테퍼 +/-)
      → /rooms?checkin&nights&guests(객실 표) → /hold/{room}(약관 iframe 체크 → '예약 보류 신청' → confirm() ) → /hold/done/{id}
--expire N: 로그인 뒤 요청 N회마다 세션 만료(재로그인 필요) — B 기본 8.   --flaky: 첫 객실 조회 뒤 최저가 방 요금 인상(보류 확인 금액 ≠ 비교표)."""
import argparse, json, html, threading, urllib.parse, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http import cookies
LOCK = threading.Lock()
SITES = {
 "A": {"name": "가상 바다숙소", "rooms": [
    {"id": "A1", "name": "스탠다드 더블", "breakfast": False, "price": 95000, "left": 4},
    {"id": "A2", "name": "디럭스 오션뷰", "breakfast": True, "price": 125000, "left": 2},
    {"id": "A3", "name": "스위트", "breakfast": True, "price": 210000, "left": 1}], "expire": 0, "flaky_room": "A1"},
 "B": {"name": "가상 산장숙소", "rooms": [
    {"id": "B1", "name": "통나무 캐빈", "breakfast": False, "price": 88000, "left": 3},
    {"id": "B2", "name": "로지 트윈", "breakfast": True, "price": 118000, "left": 2},
    {"id": "B3", "name": "패밀리 룸", "breakfast": True, "price": 150000, "left": 0}], "expire": 8, "flaky_room": "B1"},
}
class App:
    def __init__(self, site, state_path, flaky, expire, account):
        self.site = site; self.cfg = json.loads(json.dumps(SITES[site])); self.rooms = {r["id"]: r for r in self.cfg["rooms"]}
        self.expire = expire if expire is not None else self.cfg["expire"]; self.flaky = flaky; self.account = account
        self.sessions = {}; self.consented = set(); self.state_path = state_path; self.seq = 0
        self.state = {"site": site, "logins": 0, "requests": 0, "expired_sessions": 0, "rooms_reads": 0, "holds": [], "rejections": [], "consents": 0, "price_bumped": False}; self.save()
    def save(self):
        with open(self.state_path, "w") as f: json.dump(self.state, f, ensure_ascii=False, indent=1)

def page(title, body, logged_in, consented, extra=""):
    nav = ('<a href="/search">검색</a> · <a href="/logout">로그아웃</a>' if logged_in else '<a href="/login">로그인</a>')
    overlay = "" if consented or not logged_in else '<div id="consent" style="position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center"><div style="background:#fff;padding:24px" role="dialog" aria-label="쿠키 동의"><p>이 사이트는 쿠키를 사용합니다.</p><form method="post" action="/consent"><button type="submit" name="choice" value="essential">필수만 동의</button> <button type="submit" name="choice" value="all">모두 동의</button></form></div></div>'
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{html.escape(title)} - {html.escape(SITE_NAME[0])}</title>{extra}</head><body><header><h1>{html.escape(SITE_NAME[0])}</h1><nav>{nav}</nav></header><main>{body}</main>{overlay}<footer><small>가상 포털 — 훈련용 합성 자료</small></footer></body></html>"""
SITE_NAME = [""]
SEARCH_JS = """<script>
function pick(d){document.getElementById('checkin').value=d;document.getElementById('cal').style.display='none';document.getElementById('picked').textContent='선택: '+d;}
function openCal(){document.getElementById('cal').style.display='block';}
function step(n){const g=document.getElementById('guests');g.value=Math.max(1,Math.min(6,parseInt(g.value||'1')+n));document.getElementById('gshow').textContent=g.value+'명';}
</script>"""
class Handler(BaseHTTPRequestHandler):
    app: App = None
    def log_message(self, *a): pass
    def _sid(self):
        c = cookies.SimpleCookie(self.headers.get("Cookie", "")); m = c.get("sid")
        if not m or m.value not in self.app.sessions: return None
        s = self.app.sessions[m.value]; s["n"] += 1
        if self.app.expire and s["n"] > self.app.expire:
            del self.app.sessions[m.value]
            with LOCK: self.app.state["expired_sessions"] += 1; self.app.save()
            return None
        return m.value
    def _send(self, code, body, ctype="text/html; charset=utf-8", headers=None):
        b = body.encode("utf-8"); self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b)))
        for k, v in (headers or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(b)
    def _redirect(self, to, headers=None):
        self.send_response(303); self.send_header("Location", to)
        for k, v in (headers or {}).items(): self.send_header(k, v)
        self.send_header("Content-Length", "0"); self.end_headers()
    def _count(self):
        with LOCK: self.app.state["requests"] += 1; self.app.save()
    def do_GET(self):
        if self.path.startswith("/favicon"): return self._send(404, "")   # 브라우저 자동 요청은 세션 만료 카운트에서 제외(exp 변형 보정, 16:20)
        self._count(); u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query); sid = self._sid(); cons = sid in self.app.consented if sid else False
        if u.path in ("/", "/login"):
            if sid: return self._redirect("/search")
            err = '<p class="error">아이디 또는 비밀번호가 올바르지 않습니다.</p>' if q.get("err") else ('<p class="notice" id="expired">세션이 만료되었습니다. 다시 로그인해 주세요.</p>' if q.get("expired") else "")
            return self._send(200, page("로그인", f'<h2>로그인</h2>{err}<form method="post" action="/login"><label>이용자 ID <input type="text" name="user"></label><br><label>비밀번호 <input type="password" name="pw"></label><br><button type="submit">로그인</button></form>', False, True))
        if u.path == "/logout":
            if sid: self.app.sessions.pop(sid, None)
            return self._redirect("/login")
        if not sid: return self._redirect("/login?expired=1" if self.headers.get("Cookie") else "/login")
        if u.path == "/search":
            days = "".join(f'<button type="button" aria-label="{d}" onclick="pick(\'{d}\')">{int(d[-2:])}</button>' for d in [f"2026-11-{i:02d}" for i in range(1, 31)])
            body = f"""<h2>객실 검색</h2><form method="get" action="/rooms">
<label>체크인 <input type="text" id="checkin" name="checkin" readonly placeholder="날짜 선택 버튼을 누르세요"></label> <button type="button" onclick="openCal()">날짜 선택</button> <span id="picked"></span>
<div id="cal" style="display:none" role="group" aria-label="2026년 11월 달력">{days}</div><br>
<label>박수 <select name="nights" id="nights"><option value="1">1박</option><option value="2">2박</option><option value="3">3박</option></select></label><br>
<label>인원 <input type="hidden" id="guests" name="guests" value="1"><button type="button" aria-label="인원 줄이기" onclick="step(-1)">−</button> <span id="gshow">1명</span> <button type="button" aria-label="인원 늘리기" onclick="step(1)">+</button></label><br>
<button type="submit">검색</button></form>"""
            return self._send(200, page("객실 검색", body, True, cons, SEARCH_JS))
        if u.path == "/rooms":
            ci = q.get("checkin", [""])[0]; nights = int(q.get("nights", ["1"])[0]); guests = int(q.get("guests", ["1"])[0])
            if not ci: return self._send(200, page("검색 오류", '<h2>체크인 날짜를 선택하세요</h2><p><a href="/search">← 검색</a></p>', True, cons))
            with LOCK:
                self.app.state["rooms_reads"] += 1
                if self.app.flaky and self.app.state["rooms_reads"] == 1 and not self.app.state["price_bumped"]:
                    pass
                self.app.save()
            rows = []
            for rid, r in self.app.rooms.items():
                tot = r["price"] * nights
                left = "마감" if r["left"] <= 0 else f"잔여 {r['left']}"
                link = "" if r["left"] <= 0 else f'<a href="/hold/{rid}?checkin={ci}&nights={nights}&guests={guests}">예약 보류</a>'
                bf = "포함" if r["breakfast"] else "불포함"
                rows.append(f'<tr><td>{rid}</td><td>{html.escape(r["name"])}</td><td>{bf}</td><td>{r["price"]:,}원</td><td>{tot:,}원</td><td>{left}</td><td>{link}</td></tr>')
            if self.app.flaky and not self.app.state["price_bumped"]:   # 첫 조회를 보여준 뒤 최저가 방 요금 인상
                with LOCK: self.app.rooms[self.app.cfg["flaky_room"]]["price"] += 11000; self.app.state["price_bumped"] = True; self.app.save()
            body = f'<h2>객실 요금 — 체크인 {ci}, {nights}박, {guests}명</h2><table id="rooms"><thead><tr><th>번호</th><th>객실</th><th>조식</th><th>1박 요금</th><th>총액</th><th>잔여</th><th></th></tr></thead><tbody>{"".join(rows)}</tbody></table><p><a href="/search">← 검색</a></p>'
            return self._send(200, page("객실 요금", body, True, cons))
        if u.path.startswith("/hold/done/"):
            hid = u.path.split("/")[3]; h = next((x for x in self.app.state["holds"] if x["id"] == hid), None)
            if not h: return self._send(404, page("없음", "<h2>보류 내역이 없습니다</h2>", True, cons))
            body = f'<h2>예약 보류 완료</h2><p id="done">보류가 접수되었습니다. 결제는 하지 않았습니다.</p><table id="hold"><tr><th>보류번호</th><td>{hid}</td></tr><tr><th>숙소</th><td>{html.escape(self.app.cfg["name"])}</td></tr><tr><th>객실</th><td>{h["room"]} {html.escape(h["room_name"])}</td></tr><tr><th>체크인</th><td>{h["checkin"]}</td></tr><tr><th>박수</th><td>{h["nights"]}박</td></tr><tr><th>인원</th><td>{h["guests"]}명</td></tr><tr><th>총액</th><td>{h["total"]:,}원</td></tr><tr><th>조식</th><td>{"포함" if h["breakfast"] else "불포함"}</td></tr><tr><th>보류 시각</th><td>{h["at"]}</td></tr></table>'
            return self._send(200, page("보류 완료", body, True, cons))
        if u.path.startswith("/hold/"):
            rid = u.path.split("/")[2]; r = self.app.rooms.get(rid)
            if not r: return self._send(404, page("없음", "<h2>객실 없음</h2>", True, cons))
            ci = q.get("checkin", [""])[0]; nights = int(q.get("nights", ["1"])[0]); guests = int(q.get("guests", ["1"])[0]); tot = r["price"] * nights
            body = f"""<h2>예약 보류 — {html.escape(r["name"])}</h2><p>체크인 {ci} · {nights}박 · {guests}명 · 총액 <span id="total">{tot:,}원</span></p>
<form method="post" action="/hold/{rid}" onsubmit="return document.getElementById('agreed').value==='y' && confirm('예약 보류를 신청합니까? 결제는 하지 않습니다.')">
<input type="hidden" name="checkin" value="{ci}"><input type="hidden" name="nights" value="{nights}"><input type="hidden" name="guests" value="{guests}"><input type="hidden" id="agreed" name="agreed" value="">
<iframe name="terms" src="/terms_frame" width="500" height="120"></iframe><br><button type="submit">예약 보류 신청</button></form>
<script>window.addEventListener('message',e=>{{if(e.data==='agreed')document.getElementById('agreed').value='y';}});</script>"""
            return self._send(200, page("예약 보류", body, True, cons))
        if u.path == "/terms_frame":
            return self._send(200, '<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>약관</title></head><body><p>보류는 24시간 유지되며 결제는 발생하지 않습니다.</p><label><input type="checkbox" id="agree" onchange="parent.postMessage(this.checked?\'agreed\':\'no\',\'*\')"> 보류 약관에 동의합니다</label></body></html>')
        return self._send(404, page("없음", "<h2>없는 주소</h2>", True, cons))
    def do_POST(self):
        self._count(); u = urllib.parse.urlparse(self.path); n = int(self.headers.get("Content-Length", "0")); form = urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8"))
        if u.path == "/login":
            if form.get("user", [""])[0] == self.app.account["user"] and form.get("pw", [""])[0] == self.app.account["password"]:
                with LOCK: self.app.state["logins"] += 1; sid = f"{self.app.site}s{self.app.state['logins']}"; self.app.sessions[sid] = {"n": 0}; self.app.save()
                return self._redirect("/search", {"Set-Cookie": f"sid={sid}; Path=/; HttpOnly"})
            return self._redirect("/login?err=1")
        sid = self._sid()
        if not sid: return self._redirect("/login?expired=1")
        if u.path == "/consent":
            self.app.consented.add(sid)
            with LOCK: self.app.state["consents"] += 1; self.app.save()
            return self._redirect("/search")
        if u.path.startswith("/hold/"):
            rid = u.path.split("/")[2]; r = self.app.rooms.get(rid)
            if not r: return self._send(404, page("없음", "<h2>객실 없음</h2>", True, True))
            if form.get("agreed", [""])[0] != "y":
                with LOCK: self.app.state["rejections"].append({"room": rid, "reason": "약관 미동의"}); self.app.save()
                return self._send(200, page("보류 거절", '<h2>약관에 동의해야 합니다</h2>', True, True))
            if r["left"] <= 0:
                with LOCK: self.app.state["rejections"].append({"room": rid, "reason": "마감"}); self.app.save()
                return self._send(200, page("보류 거절", '<h2>마감된 객실입니다</h2>', True, True))
            nights = int(form.get("nights", ["1"])[0])
            with LOCK:
                self.app.seq += 1; hid = f"H{self.app.site}{self.app.seq:03d}"
                h = {"id": hid, "room": rid, "room_name": r["name"], "checkin": form.get("checkin", [""])[0], "nights": nights, "guests": int(form.get("guests", ["1"])[0]), "total": r["price"] * nights, "breakfast": r["breakfast"], "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                self.app.state["holds"].append(h); r["left"] -= 1; self.app.save()
            return self._redirect(f"/hold/done/{hid}")
        return self._send(404, page("없음", "<h2>없는 주소</h2>", True, True))

def main():
    p = argparse.ArgumentParser(); p.add_argument("--site", choices=["A", "B"], required=True); p.add_argument("--port", type=int, required=True); p.add_argument("--state", required=True)
    p.add_argument("--flaky", action="store_true"); p.add_argument("--expire", type=int, default=None); p.add_argument("--account", required=True); a = p.parse_args()
    Handler.app = App(a.site, a.state, a.flaky, a.expire, json.loads(a.account)); SITE_NAME[0] = Handler.app.cfg["name"]
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler); print("serving", a.site, a.port, flush=True); srv.serve_forever()
if __name__ == "__main__":
    main()
