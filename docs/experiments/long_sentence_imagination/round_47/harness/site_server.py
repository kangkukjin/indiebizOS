"""47회차 합성 공방 주문 콘솔 — 44~46회차에서 안 쓴 브라우저 손동작을 요구하는 화면. 상태는 --state JSON(검수 oracle).
/login → /orders(스크롤하면 12건씩 더 불러오는 목록, '보기' 메뉴는 마우스를 올려야 열림) → /orders?view=late
/board(칸 5개, 카드 끌어다 놓기=POST /api/move, 카드 더블클릭=메모 입력칸·Enter 저장·Escape 취소, 오른쪽 클릭=자체 메뉴 '우선 처리 표시')
/summary(fetch /api/summary, 폭 600 이하면 '모바일 요약' 만 보임, console.warn 1건)
--locked ID: 그 주문의 이동을 409 로 거절(화면은 낙관적으로 옮겨 보이고 '저장 실패' 알림은 1.5초 뒤 사라짐 — 새로 불러야 진실이 보인다)."""
import argparse, json, html, threading, urllib.parse, secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http import cookies
LOCK = threading.Lock()
COLS = ["접수", "제작 중", "지연", "오늘 처리", "출고"]
NAMES = ["김서연", "이도윤", "박하린", "최지호", "정유나", "강민재", "조은우", "윤채원", "장시우", "임다온"]
ITEMS = ["호두 도마", "참나무 트레이", "편백 수납함", "물푸레 스툴", "벚나무 액자", "단풍 컵받침", "삼나무 선반", "티크 수저"]
LATE = {"W-1004": 3, "W-1011": 12, "W-1017": 10, "W-1026": 7, "W-1033": 25}
def seed():
    out = []
    for i in range(40):
        oid = f"W-{1001 + i}"
        st = "지연" if oid in LATE else ["접수", "제작 중", "출고", "제작 중", "접수", "출고", "제작 중"][i % 7]
        out.append({"id": oid, "customer": NAMES[i % 10], "item": ITEMS[(i * 3) % 8], "qty": LATE.get(oid, 1 + (i * 5) % 9), "status": st,
                    "due": f"2026-10-{8 + (i % 6):02d}", "memo": "", "flag": False})
    return out
class App:
    def __init__(self, state_path, locked):
        self.orders = seed(); self.by = {o["id"]: o for o in self.orders}; self.sessions = set(); self.locked = locked; self.state_path = state_path
        self.state = {"logins": 0, "requests": 0, "orders_pages": 0, "api_orders": [], "late_views": 0, "board_views": 0, "summary_views": 0,
                      "moves": [], "memos": [], "flags": [], "locked": locked, "final": {}}; self.save()
    def save(self):
        self.state["final"] = {o["id"]: {"status": o["status"], "memo": o["memo"], "flag": o["flag"]} for o in self.orders if o["id"] in LATE or o["memo"] or o["flag"]}
        self.state["counts"] = {c: sum(1 for o in self.orders if o["status"] == c) for c in COLS}
        with open(self.state_path, "w") as f: json.dump(self.state, f, ensure_ascii=False, indent=1)
CSS = """<style>body{font-family:sans-serif;margin:0}header{padding:8px 16px;background:#eee}main{padding:16px}
table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:0 12px;height:70px}
.menu{display:inline-block;position:relative}.sub{display:none;position:absolute;background:#fff;border:1px solid #999;margin:0;padding:8px 16px;list-style:none;white-space:nowrap}.menu:hover .sub{display:block}
.board{display:flex;gap:12px}.col{flex:1;min-width:150px;background:#f4f4f4;padding:8px;min-height:400px}.card{background:#fff;border:1px solid #bbb;margin:6px 0;padding:6px;cursor:grab}
#ctx{position:fixed;background:#fff;border:1px solid #333;padding:6px}#toast{position:fixed;right:16px;bottom:16px;background:#c00;color:#fff;padding:8px}
.narrow{display:none}@media (max-width:600px){.wide{display:none}.narrow{display:block}}</style>"""
def page(title, body, logged_in=True, script=""):
    nav = ('<a href="/orders">주문 목록</a> · <a href="/board">보드</a> · <a href="/summary">요약</a>' if logged_in else '<a href="/login">로그인</a>')
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{html.escape(title)} - 가상 공방 주문 콘솔</title>{CSS}</head><body><header><h1>가상 공방 주문 콘솔</h1><nav>{nav}</nav></header><main>{body}</main><footer><small>훈련용 합성 자료</small></footer>{script}</body></html>"""
def row(o): return f'<tr data-id="{o["id"]}"><td>{o["id"]}</td><td>{html.escape(o["customer"])}</td><td>{html.escape(o["item"])}</td><td>{o["qty"]}</td><td>{o["status"]}</td><td>{o["due"]}</td></tr>'
ORDERS_JS = """<script>
let loaded=12,total=40,busy=false;
function more(){ if(busy||loaded>=total) return; busy=true;
  setTimeout(()=>fetch('/api/orders?offset='+loaded).then(r=>r.json()).then(d=>{ const tb=document.getElementById('rows');
    d.rows.forEach(o=>{const tr=document.createElement('tr');tr.dataset.id=o.id;[o.id,o.customer,o.item,o.qty,o.status,o.due].forEach(v=>{const td=document.createElement('td');td.textContent=v;tr.appendChild(td);});tb.appendChild(tr);});
    loaded+=d.rows.length; busy=false;
    document.getElementById('status').textContent = loaded>=total ? '모두 불러왔습니다 ('+loaded+'건)' : loaded+' / '+total+'건 표시 — 아래로 스크롤하면 더 불러옵니다'; }),300); }
window.addEventListener('scroll',()=>{ if(window.innerHeight+window.scrollY >= document.body.offsetHeight-80) more(); });
</script>"""
BOARD_JS = """<script>
let dragId=null;
function toast(t){const d=document.getElementById('toast');d.textContent=t;d.style.display='block';setTimeout(()=>{d.style.display='none';d.textContent='';},1500);}
function post(u,b){return fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});}
function counts(){document.querySelectorAll('.col').forEach(c=>{c.querySelector('.n').textContent=c.querySelectorAll('.card').length+'건';});}
function closeCtx(){const m=document.getElementById('ctx');if(m)m.remove();}
document.querySelectorAll('.card').forEach(c=>{
  c.addEventListener('dragstart',e=>{dragId=c.dataset.id;e.dataTransfer.setData('text/plain',dragId);});
  c.addEventListener('dblclick',()=>{ if(c.querySelector('input')) return; const sp=c.querySelector('.memo'); const old=sp.dataset.memo||'';
    const inp=document.createElement('input'); inp.value=old; inp.setAttribute('aria-label',c.dataset.id+' 메모 입력'); sp.style.display='none'; c.appendChild(inp); inp.focus();
    inp.addEventListener('keydown',ev=>{ if(ev.key==='Enter'){ const v=inp.value; post('/api/memo',{id:c.dataset.id,memo:v}).then(r=>{ if(r.ok){sp.dataset.memo=v;sp.textContent='메모: '+(v||'없음');} else toast('메모 저장 실패: '+c.dataset.id); inp.remove(); sp.style.display=''; }); }
      if(ev.key==='Escape'){ inp.remove(); sp.style.display=''; } }); });
  c.addEventListener('contextmenu',e=>{ e.preventDefault(); closeCtx(); const m=document.createElement('div'); m.id='ctx'; m.setAttribute('role','menu'); m.setAttribute('aria-label',c.dataset.id+' 카드 메뉴'); m.style.left=e.clientX+'px'; m.style.top=e.clientY+'px';
    const b=document.createElement('button'); b.textContent='우선 처리 표시'; b.setAttribute('role','menuitem');
    b.onclick=()=>post('/api/flag',{id:c.dataset.id,flag:true}).then(r=>{ if(r.ok){ if(!c.querySelector('.flag')){const s=document.createElement('strong');s.className='flag';s.textContent=' ★우선';c.querySelector('.head').appendChild(s);} } else toast('표시 실패'); closeCtx(); });
    const x=document.createElement('button'); x.textContent='메뉴 닫기'; x.setAttribute('role','menuitem'); x.onclick=closeCtx; m.appendChild(b); m.appendChild(x); document.body.appendChild(m); });
});
document.addEventListener('keydown',e=>{ if(e.key==='Escape') closeCtx(); });
document.querySelectorAll('.col').forEach(col=>{
  col.addEventListener('dragover',e=>e.preventDefault());
  col.addEventListener('drop',e=>{ e.preventDefault(); const id=e.dataTransfer.getData('text/plain')||dragId; const card=document.querySelector('.card[data-id="'+id+'"]'); if(!card) return;
    col.querySelector('.cards').appendChild(card); counts();
    post('/api/move',{id:id,to:col.dataset.col}).then(r=>{ if(!r.ok){ toast('저장 실패: '+id); console.error('move failed '+id+' '+r.status); } }); });
});
</script>"""
SUMMARY_JS = """<script>
console.warn('재고 경고: 호두나무 원목 잔량 2장');
fetch('/api/summary').then(r=>r.json()).then(d=>{ const w=document.getElementById('wide'), n=document.getElementById('narrow');
  w.innerHTML='<table><tr><th>칸</th><th>건수</th></tr>'+d.cols.map(c=>'<tr><td>'+c.name+'</td><td>'+c.n+'</td></tr>').join('')+'<tr><td>우선 표시</td><td>'+d.flagged+'</td></tr></table>';
  n.innerHTML='<h3>모바일 요약</h3><ul>'+d.cols.map(c=>'<li>'+c.name+' '+c.n+'건</li>').join('')+'<li>우선 표시 '+d.flagged+'건</li></ul>'; document.getElementById('ready').textContent='요약 준비됨'; });
</script>"""
class Handler(BaseHTTPRequestHandler):
    app: App = None
    def log_message(self, *a): pass
    def _sid(self):
        m = cookies.SimpleCookie(self.headers.get("Cookie", "")).get("sid")
        return m.value if m and m.value in self.app.sessions else None
    def _send(self, code, body, ctype="text/html; charset=utf-8", headers=None):
        b = body.encode("utf-8"); self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b)))
        for k, v in (headers or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(b)
    def _json(self, code, obj): self._send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")
    def _redirect(self, to, headers=None):
        self.send_response(303); self.send_header("Location", to)
        for k, v in (headers or {}).items(): self.send_header(k, v)
        self.send_header("Content-Length", "0"); self.end_headers()
    def _bump(self, key, item=None):
        with LOCK:
            if item is None: self.app.state[key] += 1
            else: self.app.state[key].append(item)
            self.app.save()
    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query); app = self.app
        if u.path == "/favicon.ico": return self._send(404, "")
        self._bump("requests")
        if u.path == "/login":
            return self._send(200, page("로그인", '<h2>로그인</h2><form method="post" action="/login"><label>담당자 ID <input name="user"></label> <label>비밀번호 <input name="password" type="password"></label> <button type="submit">로그인</button></form>', False))
        if not self._sid(): return self._redirect("/login")
        if u.path in ("/", "/orders"):
            view = (q.get("view") or ["all"])[0]
            menu = '<div class="menu"><button type="button" aria-haspopup="true">보기 ▾</button><ul class="sub"><li><a href="/orders?view=all">전체</a></li><li><a href="/orders?view=late">지연만</a></li></ul></div>'
            head = '<table><thead><tr><th>번호</th><th>고객</th><th>품목</th><th>수량</th><th>상태</th><th>납기</th></tr></thead><tbody id="rows">'
            if view == "late":
                self._bump("late_views"); rows = [o for o in app.orders if o["status"] == "지연"]
                return self._send(200, page("지연 주문", f'<h2>지연 주문</h2>{menu}<p id="status">지연 {len(rows)}건</p>{head}{"".join(row(o) for o in rows)}</tbody></table>'))
            self._bump("orders_pages")
            return self._send(200, page("주문 목록", f'<h2>주문 목록</h2>{menu}<p id="status">12 / 40건 표시 — 아래로 스크롤하면 더 불러옵니다</p>{head}{"".join(row(o) for o in app.orders[:12])}</tbody></table>', script=ORDERS_JS))
        if u.path == "/api/orders":
            off = int((q.get("offset") or ["0"])[0]); self._bump("api_orders", off)
            return self._json(200, {"rows": app.orders[off:off + 12], "total": 40})
        if u.path == "/board":
            self._bump("board_views"); cols = ""
            for c in COLS:
                cards = "".join(f'<div class="card" draggable="true" data-id="{o["id"]}" role="button" tabindex="0" aria-label="{o["id"]} {html.escape(o["customer"])} {html.escape(o["item"])} {o["qty"]}개"><span class="head">{o["id"]} · {html.escape(o["item"])} {o["qty"]}개{" <strong class=flag>★우선</strong>" if o["flag"] else ""}</span><br><span class="memo" data-memo="{html.escape(o["memo"])}">메모: {html.escape(o["memo"]) or "없음"}</span></div>' for o in app.orders if o["status"] == c)
                cols += f'<section class="col" data-col="{c}" role="region" aria-label="{c} 칸"><h3>{c} <span class="n">{sum(1 for o in app.orders if o["status"] == c)}건</span></h3><div class="cards">{cards}</div></section>'
            return self._send(200, page("보드", f'<h2>보드</h2><p>카드를 끌어 칸을 옮깁니다. 더블클릭: 메모 수정(Enter 저장·Esc 취소). 오른쪽 클릭: 카드 메뉴.</p><div class="board">{cols}</div><div id="toast" role="status" style="display:none"></div>', script=BOARD_JS))
        if u.path == "/summary":
            self._bump("summary_views")
            return self._send(200, page("요약", '<h2>요약</h2><p id="ready">불러오는 중…</p><div id="wide" class="wide"></div><div id="narrow" class="narrow"></div>', script=SUMMARY_JS))
        if u.path == "/api/summary":
            return self._json(200, {"cols": [{"name": c, "n": sum(1 for o in app.orders if o["status"] == c)} for c in COLS], "flagged": sum(1 for o in app.orders if o["flag"])})
        return self._send(404, page("없음", "<p>없는 화면</p>"))
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0); raw = self.rfile.read(n).decode("utf-8"); app = self.app; self._bump("requests")
        if self.path == "/login":
            f = urllib.parse.parse_qs(raw)
            if (f.get("user") or [""])[0] and (f.get("password") or [""])[0]:
                sid = secrets.token_hex(8); app.sessions.add(sid); self._bump("logins")
                return self._redirect("/orders", {"Set-Cookie": f"sid={sid}; Path=/"})
            return self._redirect("/login")
        if not self._sid(): return self._json(401, {"error": "login"})
        b = json.loads(raw or "{}"); o = app.by.get(b.get("id"))
        if not o: return self._json(404, {"error": "no order"})
        if self.path == "/api/move":
            ok = b.get("to") in COLS and o["id"] != app.locked
            with LOCK:
                app.state["moves"].append({"id": o["id"], "from": o["status"], "to": b.get("to"), "ok": ok})
                if ok: o["status"] = b["to"]
                app.save()
            return self._json(200, {"ok": True}) if ok else self._json(409, {"error": "다른 담당자가 편집 중"})
        if self.path == "/api/memo":
            with LOCK: o["memo"] = str(b.get("memo") or ""); app.state["memos"].append({"id": o["id"], "memo": o["memo"]}); app.save()
            return self._json(200, {"ok": True})
        if self.path == "/api/flag":
            with LOCK: o["flag"] = bool(b.get("flag")); app.state["flags"].append({"id": o["id"], "flag": o["flag"]}); app.save()
            return self._json(200, {"ok": True})
        return self._json(404, {"error": "no api"})
def main():
    p = argparse.ArgumentParser(); p.add_argument("--port", type=int, required=True); p.add_argument("--state", required=True); p.add_argument("--locked", default=None)
    a = p.parse_args(); Handler.app = App(a.state, a.locked)
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()
if __name__ == "__main__":
    main()
