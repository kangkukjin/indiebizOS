"""45회차 합성 체육센터 강좌 신청 포털 — stdlib HTTP 서버. 상태(접수·업로드 지문·거절)는 --state JSON(검수 oracle).
사용: site_server.py --port 8941 --data <data.json> --state <state.json> [--flaky]
--flaky: 강좌 목록을 한 번 읽은 뒤 C07 이 정원 마감으로 바뀌고(신청 시 거절), 첫 번째 접수 코드 제출은 '일시 오류' 로 거절(재제출 필요).
흐름: /login → /courses(큰 목록, 요소 150+) → /apply(지역→센터→강좌 연쇄 select, 비동기) → prompt(접수 코드) → POST /apply → /receipt/{id}"""
import argparse, json, html, hashlib, threading, urllib.parse, datetime, re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http import cookies

LOCK = threading.Lock()

class State:
    def __init__(self, path):
        self.path = path
        self.data = {"applications": [], "rejections": [], "uploads": [], "logins": 0, "requests": 0, "courses_reads": 0, "api_calls": []}
        self.save()
    def save(self):
        with open(self.path, "w") as f: json.dump(self.data, f, ensure_ascii=False, indent=1)

class App:
    def __init__(self, data_path, state_path, flaky):
        cfg = json.load(open(data_path))
        self.account = cfg["account"]; self.regions = cfg["regions"]; self.courses = {c["id"]: dict(c) for c in cfg["courses"]}
        self.codes = cfg["codes"]; self.state = State(state_path); self.flaky = flaky; self.sessions = set(); self.seq = 0; self.flaky_code_rejected = False

def page(title, body, logged_in, extra_head=""):
    nav = ('<a href="/courses">강좌 목록</a> · <a href="/apply">수강 신청</a> · <a href="/logout">로그아웃</a>' if logged_in else '<a href="/login">로그인</a>')
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{html.escape(title)} - 가상 구민체육센터</title>{extra_head}</head>
<body><header><h1>가상 구민체육센터 수강 신청</h1><nav>{nav}</nav></header><main>{body}</main><footer><small>가상 포털 — 훈련용 합성 자료</small></footer></body></html>"""

APPLY_JS = """<script>
async function loadCenters(){const r=document.getElementById('region').value;const c=document.getElementById('center');const k=document.getElementById('course');
 c.innerHTML='<option value="">불러오는 중…</option>';k.innerHTML='<option value="">센터를 먼저 고르세요</option>';
 if(!r){c.innerHTML='<option value="">지역을 먼저 고르세요</option>';return;}
 const res=await fetch('/api/centers?region='+encodeURIComponent(r));const j=await res.json();
 c.innerHTML='<option value="">센터 선택</option>'+j.map(x=>'<option value="'+x.id+'">'+x.name+'</option>').join('');}
async function loadCourses(){const c=document.getElementById('center').value;const k=document.getElementById('course');
 k.innerHTML='<option value="">불러오는 중…</option>';if(!c){k.innerHTML='<option value="">센터를 먼저 고르세요</option>';return;}
 const res=await fetch('/api/courses?center='+encodeURIComponent(c));const j=await res.json();
 k.innerHTML='<option value="">강좌 선택</option>'+j.map(x=>'<option value="'+x.id+'">'+x.name+' ('+x.fee.toLocaleString()+'원, 잔여 '+x.remaining+')</option>').join('');}
function onSubmit(f){const code=prompt('접수 코드를 입력하세요');if(code===null||code===''){return false;}document.getElementById('code').value=code;return true;}
</script>"""

class Handler(BaseHTTPRequestHandler):
    app: App = None
    def log_message(self, *a): pass
    def _sid(self):
        c = cookies.SimpleCookie(self.headers.get("Cookie", "")); m = c.get("sid")
        return m.value if m and m.value in self.app.sessions else None
    def _send(self, code, body, ctype="text/html; charset=utf-8", headers=None):
        b = body.encode("utf-8") if isinstance(body, str) else body; self.send_response(code)
        self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b)))
        for k, v in (headers or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(b)
    def _redirect(self, to, headers=None):
        self.send_response(303); self.send_header("Location", to)
        for k, v in (headers or {}).items(): self.send_header(k, v)
        self.send_header("Content-Length", "0"); self.end_headers()
    def _count(self):
        with LOCK: self.app.state.data["requests"] += 1; self.app.state.save()
    def do_GET(self):
        self._count(); u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query); sid = self._sid()
        if u.path in ("/", "/login"):
            if sid: return self._redirect("/courses")
            err = '<p class="error">아이디 또는 비밀번호가 올바르지 않습니다.</p>' if q.get("err") else ""
            return self._send(200, page("로그인", f"""<h2>로그인</h2>{err}<form method="post" action="/login">
<label>이용자 ID <input type="text" name="user"></label><br><label>비밀번호 <input type="password" name="pw"></label><br><button type="submit">로그인</button></form>""", False))
        if u.path == "/logout":
            if sid: self.app.sessions.discard(sid)
            return self._redirect("/login")
        if not sid: return self._redirect("/login")
        if u.path == "/courses":
            with LOCK: self.app.state.data["courses_reads"] += 1; self.app.state.save()
            rows = []
            for cid in sorted(self.app.courses):
                c = self.app.courses[cid]; rem = self._remaining(c)
                rows.append(f'<tr><td>{cid}</td><td><a href="/courses/{cid}">{html.escape(c["name"])}</a></td><td>{html.escape(c["center_name"])}</td><td>{html.escape(c["schedule"])}</td><td>{c["fee"]:,}원</td><td>{"마감" if rem <= 0 else f"잔여 {rem}"}</td><td><button type="button" onclick="location.href=\'/apply?course={cid}\'">신청</button></td></tr>')
            body = f"<h2>강좌 목록</h2><p>총 {len(rows)}개 강좌</p><table id=\"courses\"><thead><tr><th>번호</th><th>강좌</th><th>센터</th><th>시간</th><th>수강료</th><th>정원</th><th></th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
            return self._send(200, page("강좌 목록", body, True))
        if u.path.startswith("/courses/"):
            cid = u.path.split("/")[2]; c = self.app.courses.get(cid)
            if not c: return self._send(404, page("없음", "<h2>강좌를 찾을 수 없습니다</h2>", True))
            return self._send(200, page(c["name"], f'<h2>{html.escape(c["name"])}</h2><dl><dt>번호</dt><dd>{cid}</dd><dt>센터</dt><dd>{html.escape(c["center_name"])}</dd><dt>시간</dt><dd>{html.escape(c["schedule"])}</dd><dt>수강료</dt><dd id="fee">{c["fee"]:,}원</dd><dt>정원</dt><dd>{"마감" if self._remaining(c) <= 0 else f"잔여 {self._remaining(c)}"}</dd></dl>', True))
        if u.path == "/api/centers":
            import time; time.sleep(0.4)
            r = q.get("region", [""])[0]; out = [{"id": c["id"], "name": c["name"]} for c in self.app.regions.get(r, [])]
            with LOCK: self.app.state.data["api_calls"].append({"api": "centers", "region": r}); self.app.state.save()
            return self._send(200, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")
        if u.path == "/api/courses":
            import time; time.sleep(0.6)
            cen = q.get("center", [""])[0]
            out = [{"id": cid, "name": c["name"], "fee": c["fee"], "remaining": self._remaining(c)} for cid, c in sorted(self.app.courses.items()) if c["center"] == cen]
            with LOCK: self.app.state.data["api_calls"].append({"api": "courses", "center": cen}); self.app.state.save()
            return self._send(200, json.dumps(out, ensure_ascii=False), "application/json; charset=utf-8")
        if u.path == "/apply":
            err = ""
            if q.get("err"): err = f'<p class="error" id="error">{html.escape(q["err"][0])}</p>'
            body = f"""<h2>수강 신청</h2>{err}<form method="post" action="/apply" enctype="multipart/form-data" onsubmit="return onSubmit(this)">
<label>지역 <select id="region" name="region" onchange="loadCenters()"><option value="">지역 선택</option>{''.join(f'<option value="{r}">{r}</option>' for r in self.app.regions)}</select></label><br>
<label>센터 <select id="center" name="center" onchange="loadCourses()"><option value="">지역을 먼저 고르세요</option></select></label><br>
<label>강좌 <select id="course" name="course"><option value="">센터를 먼저 고르세요</option></select></label><br>
<label>신청자 이름 <input type="text" name="name" id="name"></label><br>
<label>생년월일 <input type="text" name="birth" id="birth" placeholder="YYYY-MM-DD"></label><br>
<label>증명서 파일 <input type="file" name="cert" id="cert"></label><br>
<label><input type="checkbox" name="agree" id="agree" value="y"> 환불 규정에 동의합니다</label><br>
<input type="hidden" name="code" id="code"><button type="submit" id="submit">신청 제출</button></form>"""
            return self._send(200, page("수강 신청", body, True, APPLY_JS))
        if u.path.startswith("/receipt/"):
            rid = u.path.split("/")[2]; a = next((x for x in self.app.state.data["applications"] if x["id"] == rid), None)
            if not a: return self._send(404, page("없음", "<h2>접수 내역이 없습니다</h2>", True))
            body = f"""<h2>접수 완료</h2><p id="done">신청이 접수되었습니다.</p><table id="receipt"><tr><th>접수번호</th><td>{rid}</td></tr><tr><th>신청자</th><td>{html.escape(a["name"])}</td></tr>
<tr><th>생년월일</th><td>{a["birth"]}</td></tr><tr><th>강좌</th><td>{a["course"]} {html.escape(a["course_name"])}</td></tr><tr><th>센터</th><td>{html.escape(a["center_name"])}</td></tr><tr><th>수강료</th><td>{a["fee"]:,}원</td></tr>
<tr><th>증명서</th><td>{html.escape(a["upload_name"])} ({a["upload_bytes"]} bytes)</td></tr><tr><th>접수 시각</th><td>{a["at"]}</td></tr></table><p><a href="/apply">다른 신청</a></p>"""
            return self._send(200, page("접수 완료", body, True))
        return self._send(404, page("없음", "<h2>없는 주소</h2>", True))
    def _remaining(self, c):
        taken = sum(1 for a in self.app.state.data["applications"] if a["course"] == c["id"])
        cap = c["capacity"]
        if self.app.flaky and c.get("flaky_full") and self.app.state.data["courses_reads"] >= 1: cap = 0
        return cap - taken
    def _parse_multipart(self, body, ctype):
        m = re.search(r'boundary=([^;]+)', ctype); b = m.group(1).strip('"').encode(); fields = {}; files = {}
        for part in body.split(b"--" + b)[1:]:
            if part.strip() in (b"", b"--"): continue
            head, _, data = part.partition(b"\r\n\r\n"); data = data[:-2] if data.endswith(b"\r\n") else data
            h = head.decode("utf-8", "replace"); nm = re.search(r'name="([^"]+)"', h); fn = re.search(r'filename="([^"]*)"', h)
            if fn: files[nm.group(1)] = (fn.group(1), data)
            else: fields[nm.group(1)] = data.decode("utf-8")
        return fields, files
    def do_POST(self):
        self._count(); u = urllib.parse.urlparse(self.path); n = int(self.headers.get("Content-Length", "0")); raw = self.rfile.read(n)
        if u.path == "/login":
            form = urllib.parse.parse_qs(raw.decode("utf-8")); user = form.get("user", [""])[0]; pw = form.get("pw", [""])[0]
            if user == self.app.account["user"] and pw == self.app.account["password"]:
                with LOCK: self.app.state.data["logins"] += 1; sid = "s%d" % self.app.state.data["logins"]; self.app.sessions.add(sid); self.app.state.save()
                return self._redirect("/courses", {"Set-Cookie": f"sid={sid}; Path=/; HttpOnly"})
            return self._redirect("/login?err=1")
        if not self._sid(): return self._redirect("/login")
        if u.path == "/apply":
            fields, files = self._parse_multipart(raw, self.headers.get("Content-Type", ""))
            name = fields.get("name", "").strip(); course = fields.get("course", ""); code = fields.get("code", ""); agree = fields.get("agree") == "y"
            cert = files.get("cert"); c = self.app.courses.get(course)
            def reject(reason):
                with LOCK: self.app.state.data["rejections"].append({"name": name, "course": course, "reason": reason}); self.app.state.save()
                return self._redirect("/apply?err=" + urllib.parse.quote(reason))
            if not c: return reject("강좌를 선택하세요")
            if not name or not fields.get("birth"): return reject("신청자 이름과 생년월일을 입력하세요")
            if not agree: return reject("환불 규정 동의가 필요합니다")
            if not cert or not cert[1]: return reject("증명서 파일이 없습니다")
            if self.app.flaky and not self.app.flaky_code_rejected:
                self.app.flaky_code_rejected = True; return reject("접수 코드를 확인하지 못했습니다(일시 오류). 다시 제출해 주세요")
            if self.app.codes.get(name) != code: return reject("접수 코드가 올바르지 않습니다")
            with LOCK:
                if self._remaining(c) <= 0:
                    self.app.state.data["rejections"].append({"name": name, "course": course, "reason": "정원 마감"}); self.app.state.save()
                    return self._redirect("/apply?err=" + urllib.parse.quote(f"정원 마감: {course} 은(는) 더 이상 신청할 수 없습니다"))
                self.app.seq += 1; rid = f"R{self.app.seq:03d}"; sha = hashlib.sha256(cert[1]).hexdigest()
                a = {"id": rid, "name": name, "birth": fields.get("birth"), "course": course, "course_name": c["name"], "center_name": c["center_name"], "fee": c["fee"],
                     "upload_name": cert[0], "upload_bytes": len(cert[1]), "upload_sha256": sha, "code": code, "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                self.app.state.data["applications"].append(a); self.app.state.data["uploads"].append({"name": cert[0], "sha256": sha}); self.app.state.save()
            return self._redirect(f"/receipt/{rid}")
        return self._send(404, page("없음", "<h2>없는 주소</h2>", True))

def main():
    p = argparse.ArgumentParser(); p.add_argument("--port", type=int, required=True); p.add_argument("--data", required=True)
    p.add_argument("--state", required=True); p.add_argument("--flaky", action="store_true"); a = p.parse_args()
    Handler.app = App(a.data, a.state, a.flaky)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler); print("serving", a.port, flush=True); srv.serve_forever()

if __name__ == "__main__":
    main()
