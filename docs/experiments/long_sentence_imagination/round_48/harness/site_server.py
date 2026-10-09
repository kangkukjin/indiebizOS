"""48회차 합성 상점 관리 콘솔(stdlib). 자동완성 검색 · 새 탭 편집(range 슬라이더·contenteditable) · 포인터 이벤트 정렬 목록 ·
비동기 내보내기 뒤 첨부 내려받기(세션 쿠키 필요) · --fail-save-once ID(그 상품의 첫 저장만 500).
사용: site_server.py --port N --state FILE [--fail-save-once P-05]   — state FILE 이 oracle(요청 기록·최종 상태)."""
import argparse, json, secrets, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

NAMES = ["호두 도마", "호두 트레이", "호두 수저 세트", "유리 화병 소", "유리 화병 대", "유리 컵 2P", "린넨 앞치마", "린넨 키친타월",
         "황동 촛대", "황동 문진", "도자 머그 백", "도자 머그 청", "도자 접시 소", "도자 접시 대", "면 행주 3P", "면 장바구니",
         "삼베 수세미", "밀랍 초 2P", "밀랍 랩", "대나무 칫솔", "대나무 빨대", "편백 도마", "편백 받침", "옻칠 젓가락"]
PRICES = [38000, 29000, 24000, 18000, 32000, 16000, 27000, 12000, 45000, 21000, 19000, 19000, 14000, 26000, 11000, 15000,
          10000, 17000, 13000, 10000, 10000, 52000, 12000, 23000]
DISPLAY0 = ["P-09", "P-01", "P-22", "P-05", "P-11", "P-07", "P-18", "P-24"]


def seed():
    return {f"P-{i + 1:02d}": {"id": f"P-{i + 1:02d}", "name": n, "price": PRICES[i], "desc": f"{n} 기본 문구"} for i, n in enumerate(NAMES)}


CSS = "body{font-family:sans-serif;margin:16px}nav a{margin-right:12px}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:4px 8px}" \
      "#sug{list-style:none;padding:0;margin:0;border:1px solid #999;width:260px}#sug li{padding:4px 8px;cursor:pointer}#sug li[aria-selected=true]{background:#def}" \
      "#list{list-style:none;padding:0;width:320px}#list li{border:1px solid #888;margin:4px 0;padding:10px;background:#fff;cursor:grab;user-select:none}#list li.dragging{opacity:.5}" \
      "#desc{border:1px solid #999;min-height:40px;padding:6px;width:360px}"
NAV = '<nav><a href="/products">상품</a><a href="/display">진열</a><a href="/export">내보내기</a></nav>'


def page(title, body, script=""):
    return f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{title} — 가상 상점 관리</title><style>{CSS}</style></head><body><h1>{title}</h1>{NAV}{body}<script>{script}</script></body></html>'


JS_PRODUCTS = """
const q=document.getElementById('q'),sug=document.getElementById('sug');let t=null,act=-1,items=[];
function render(){sug.innerHTML='';items.forEach((it,i)=>{const li=document.createElement('li');li.setAttribute('role','option');li.id='opt'+i;li.textContent=it.name;li.dataset.id=it.id;li.setAttribute('aria-selected',i===act?'true':'false');li.addEventListener('click',()=>pick(it));sug.appendChild(li);});q.setAttribute('aria-expanded',items.length?'true':'false');}
function pick(it){location.href='/products?pick='+it.id;}
q.addEventListener('input',()=>{clearTimeout(t);t=setTimeout(async()=>{const v=q.value.trim();if(!v){items=[];act=-1;render();return;}const r=await fetch('/api/suggest?q='+encodeURIComponent(v));items=await r.json();act=-1;render();},250);});
q.addEventListener('keydown',e=>{if(e.key==='ArrowDown'){act=Math.min(items.length-1,act+1);render();e.preventDefault();}else if(e.key==='ArrowUp'){act=Math.max(0,act-1);render();e.preventDefault();}else if(e.key==='Enter'&&act>=0){pick(items[act]);}else if(e.key==='Escape'){items=[];render();}});
"""
JS_EDIT = """
const p=document.getElementById('price'),pv=document.getElementById('pv'),msg=document.getElementById('msg');
function show(){pv.textContent=Number(p.value).toLocaleString('ko-KR')+'원';}p.addEventListener('input',show);show();
document.getElementById('save').addEventListener('click',async()=>{msg.textContent='저장 중…';const r=await fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:PID,price:Number(p.value),desc:document.getElementById('desc').innerText.trim()})});
if(r.ok){const j=await r.json();msg.textContent='저장됨 — 판매가 '+j.price.toLocaleString('ko-KR')+'원';}else{msg.textContent='저장 실패('+r.status+') — 다시 시도하세요';}});
"""
JS_DISPLAY = """
const list=document.getElementById('list'),st=document.getElementById('st');let drag=null,n=0;
list.addEventListener('mousedown',e=>{const li=e.target.closest('li');if(li){drag=li;li.classList.add('dragging');e.preventDefault();}});
document.addEventListener('mousemove',e=>{if(!drag)return;const el=document.elementFromPoint(e.clientX,e.clientY);const over=el&&el.closest('#list li');if(over&&over!==drag){const r=over.getBoundingClientRect();list.insertBefore(drag,e.clientY>r.top+r.height/2?over.nextSibling:over);}});
document.addEventListener('mouseup',async()=>{if(!drag)return;drag.classList.remove('dragging');drag=null;st.textContent='순서 저장 중…';const order=[...list.children].map(li=>li.dataset.id);
const r=await fetch('/api/order',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({order})});n++;st.textContent=r.ok?'순서 저장됨('+n+'번째)':'순서 저장 실패';});
"""
JS_EXPORT = """
const b=document.getElementById('start'),pg=document.getElementById('pg'),dl=document.getElementById('dl');
b.addEventListener('click',async()=>{b.disabled=true;const j=await (await fetch('/api/export',{method:'POST'})).json();
const tick=async()=>{const s=await (await fetch('/api/export/status?job='+j.job)).json();pg.textContent='진행 '+s.progress+'%';if(s.done){pg.textContent='내보내기 완료 — '+s.rows+'행';dl.innerHTML='<a href="/files/'+s.token+'.csv" download="display.csv">진열표 내려받기</a>';b.disabled=false;}else setTimeout(tick,400);};tick();});
"""


class App:
    def __init__(self, state_path, fail_once):
        self.lock = threading.Lock(); self.path = state_path; self.fail_once = fail_once; self.failed = set()
        self.products = seed(); self.display = list(DISPLAY0); self.jobs = {}; self.files = {}
        self.log = {"suggest": [], "picks": [], "edit_views": [], "saves": [], "orders": [], "exports": 0, "downloads": [], "denied": [], "display_views": 0}
        self.flush()

    def flush(self):
        out = dict(self.log); out["display"] = self.display; out["final"] = {i: self.products[i] for i in self.products}
        with open(self.path, "w") as f: json.dump(out, f, ensure_ascii=False, indent=1)

    def csv(self):
        rows = ["순위,상품번호,상품명,판매가,진열 문구"]
        for k, i in enumerate(self.display):
            p = self.products[i]; rows.append(f'{k + 1},{i},{p["name"]},{p["price"]},"{p["desc"]}"')
        return "﻿" + "\r\n".join(rows) + "\r\n"


def make_handler(app):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def send(self, code, body, ctype="text/html; charset=utf-8", extra=None):
            b = body.encode() if isinstance(body, str) else body
            self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b))); self.send_header("Cache-Control", "no-store")
            if "sid=" not in (self.headers.get("Cookie") or "") and ctype.startswith("text/html"): self.send_header("Set-Cookie", f"sid={secrets.token_hex(8)}; Path=/; HttpOnly")
            for k, v in (extra or {}).items(): self.send_header(k, v)
            self.end_headers(); self.wfile.write(b)

        def js(self, obj, code=200): self.send(code, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

        def authed(self): return "sid=" in (self.headers.get("Cookie") or "")

        def do_GET(self):
            u = urlparse(self.path); q = parse_qs(u.query); p = u.path
            with app.lock:
                if p in ("/", "/products"):
                    pick = (q.get("pick") or [None])[0]; rows = [app.products[pick]] if pick in app.products else list(app.products.values())
                    if pick in app.products: app.log["picks"].append(pick)
                    trs = "".join(f'<tr><td>{r["id"]}</td><td>{r["name"]}</td><td>{r["price"]:,}원</td><td><a href="/edit/{r["id"]}" target="_blank" aria-label="{r["name"]} 편집">편집</a></td></tr>' for r in rows)
                    head = f'<p id="picked">선택: {rows[0]["name"]} ({rows[0]["id"]}) — <a href="/products">전체 보기</a></p>' if pick in app.products else f'<p>전체 {len(rows)}개</p>'
                    body = f'<p><label for="q">상품 검색</label> <input id="q" role="combobox" aria-controls="sug" aria-expanded="false" autocomplete="off" placeholder="이름 일부"></p><ul id="sug" role="listbox" aria-label="검색 제안"></ul>{head}<table><tr><th>번호</th><th>상품명</th><th>판매가</th><th></th></tr>{trs}</table>'
                    app.flush(); return self.send(200, page("상품 관리", body, JS_PRODUCTS))
                if p == "/api/suggest":
                    if not self.authed(): return self.js({"error": "no session"}, 403)
                    v = (q.get("q") or [""])[0]; app.log["suggest"].append(v); app.flush()
                    return self.js([{"id": r["id"], "name": r["name"]} for r in app.products.values() if v and v in r["name"]][:6])
                if p.startswith("/edit/"):
                    r = app.products.get(p.split("/")[-1])
                    if not r: return self.send(404, page("없는 상품", ""))
                    app.log["edit_views"].append(r["id"]); app.flush()
                    body = f'<p>상품번호 {r["id"]}</p><p><label for="price">판매가</label> <input type="range" id="price" min="10000" max="60000" step="1000" value="{r["price"]}"> <output id="pv" for="price"></output></p>' \
                           f'<p id="dl">진열 문구</p><div id="desc" contenteditable="true" role="textbox" aria-labelledby="dl">{r["desc"]}</div><p><button id="save">저장</button> <span id="msg" role="status"></span></p>'
                    return self.send(200, page(f'상품 편집 — {r["name"]}', body, f'const PID="{r["id"]}";' + JS_EDIT))
                if p == "/display":
                    app.log["display_views"] += 1; app.flush()
                    lis = "".join(f'<li role="button" tabindex="0" data-id="{i}" aria-label="{app.products[i]["name"]} 진열 항목">{app.products[i]["name"]} <small>{i}</small></li>' for i in app.display)
                    return self.send(200, page("진열 순서", f'<p>항목을 끌어 순서를 바꾸면 바로 저장됩니다. <span id="st" role="status">변경 없음</span></p><ol id="list">{lis}</ol>', JS_DISPLAY))
                if p == "/export":
                    return self.send(200, page("내보내기", '<p><button id="start">내보내기 시작</button> <span id="pg" role="status">대기</span></p><p id="dl"></p>', JS_EXPORT))
                if p == "/api/export/status":
                    j = app.jobs.get((q.get("job") or [""])[0])
                    if not j: return self.js({"error": "no job"}, 404)
                    el = time.time() - j["t"]; done = el >= 1.6
                    return self.js({"progress": 100 if done else int(el / 1.6 * 100 // 20 * 20), "done": done, "token": j["token"] if done else None, "rows": j["rows"]})
                if p.startswith("/files/"):
                    tok = p.split("/")[-1].replace(".csv", ""); ok = self.authed() and tok in app.files
                    (app.log["downloads"] if ok else app.log["denied"]).append(tok); app.flush()
                    if not ok: return self.send(403, "forbidden", "text/plain; charset=utf-8")
                    return self.send(200, app.files[tok], "text/csv; charset=utf-8", {"Content-Disposition": 'attachment; filename="display.csv"'})
                if p == "/favicon.ico": return self.send(204, "")
                return self.send(404, page("없는 화면", ""))

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0); raw = self.rfile.read(n) if n else b"{}"
            try: d = json.loads(raw or b"{}")
            except Exception: d = {}
            with app.lock:
                if not self.authed(): return self.js({"error": "no session"}, 403)
                if self.path == "/api/save":
                    i = d.get("id")
                    if i == app.fail_once and i not in app.failed:
                        app.failed.add(i); app.log["saves"].append({"id": i, "price": d.get("price"), "desc": d.get("desc"), "ok": False}); app.flush(); return self.js({"error": "일시 오류"}, 500)
                    if i not in app.products: return self.js({"error": "no product"}, 404)
                    app.products[i]["price"] = int(d.get("price")); app.products[i]["desc"] = str(d.get("desc"))
                    app.log["saves"].append({"id": i, "price": d.get("price"), "desc": d.get("desc"), "ok": True}); app.flush(); return self.js(app.products[i])
                if self.path == "/api/order":
                    o = d.get("order") or []
                    if sorted(o) != sorted(app.display): return self.js({"error": "bad order"}, 400)
                    app.display = o; app.log["orders"].append(o); app.flush(); return self.js({"ok": True})
                if self.path == "/api/export":
                    job = secrets.token_hex(4); tok = secrets.token_hex(6); app.files[tok] = app.csv(); app.jobs[job] = {"t": time.time(), "token": tok, "rows": len(app.display)}
                    app.log["exports"] += 1; app.flush(); return self.js({"job": job})
                return self.js({"error": "not found"}, 404)
    return H


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, required=True); ap.add_argument("--state", required=True); ap.add_argument("--fail-save-once", default=None)
    a = ap.parse_args(); ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(App(a.state, a.fail_save_once))).serve_forever()
