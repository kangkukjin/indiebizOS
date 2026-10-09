"""사건 전수 조사용 시험 페이지(stdlib). /t 의 요소 하나가 브라우저 사건 하나를 일으킨다. 요청은 --state 파일에 기록.
사용: census_server.py --port N --state FILE"""
import argparse, json, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
T = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>사건 시험</title></head><body style="height:4000px">
<h1>사건 시험</h1><p id="out">대기</p>
<a id="popup_blank" href="/p?x=blank" target="_blank">새 탭 링크</a>
<button id="popup_open" onclick="window.open('/p?x=open')">새 창 열기</button>
<a id="download_link" href="/dl" download="census.txt">내려받기 링크</a>
<button id="download_blob" onclick="const a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['blob-body'],{type:'text/plain'}));a.download='blob.txt';document.body.appendChild(a);a.click();">만들어 내려받기</button>
<input type="file" id="filechooser" aria-label="파일 고르기">
<a id="nav_ok" href="/p?x=nav">같은 탭 이동</a>
<a id="nav_404" href="/missing">없는 화면 이동</a>
<button id="pageerror" onclick="throw new Error('census-uncaught')">예외</button>
<button id="console_error" onclick="console.error('census-console')">콘솔 오류</button>
<button id="alert" onclick="alert('census-alert');document.getElementById('out').textContent='alert 뒤'">알림창</button>
<button id="confirm" onclick="document.getElementById('out').textContent='confirm='+confirm('census-confirm')">확인창</button>
<button id="fetch_500" onclick="fetch('/fail').then(r=>document.getElementById('out').textContent='fetch '+r.status)">실패 요청</button>
<button id="fetch_refused" onclick="fetch('http://127.0.0.1:1/x').catch(e=>document.getElementById('out').textContent='fetch 연결 실패')">연결 실패 요청</button>
<button id="dom_remove" onclick="document.body.innerHTML='<p>화면이 바뀜</p>'">화면 교체</button>
<button id="scroll_jump" onclick="window.scrollTo(0,3000)">멀리 스크롤</button>
<button id="history_push" onclick="history.pushState({},'','/t?pushed=1')">주소만 바꿈</button>
<button id="delayed_nav" onclick="setTimeout(()=>location='/p?x=late',700)">늦은 이동</button>
</body></html>"""
P = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>도착 화면</title></head><body><h1>도착 화면</h1><button id="self_close" onclick="window.close()">이 창 닫기</button></body></html>"""
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, required=True); ap.add_argument("--state", required=True); a = ap.parse_args()
    hits = []; lock = threading.Lock()
    class H(BaseHTTPRequestHandler):
        def log_message(self, *x): pass
        def do_GET(self):
            p = urlparse(self.path).path
            with lock:
                hits.append(self.path); open(a.state, "w").write(json.dumps(hits))
            code, body, ct, extra = 200, T, "text/html; charset=utf-8", {}
            if p == "/p": body = P
            elif p == "/dl": body, ct, extra = "census-file-body\n", "text/plain; charset=utf-8", {"Content-Disposition": 'attachment; filename="census.txt"'}
            elif p == "/fail": code, body, ct = 500, "fail", "text/plain"
            elif p == "/reset":
                with lock: hits.clear()
                body, ct = "ok", "text/plain"
            elif p != "/t": code, body = 404, "<html><head><title>없음</title></head><body><h1>404 없는 화면</h1></body></html>"
            b = body.encode(); self.send_response(code); self.send_header("Content-Type", ct); self.send_header("Content-Length", str(len(b)))
            for k, v in extra.items(): self.send_header(k, v)
            self.end_headers(); self.wfile.write(b)
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()
if __name__ == "__main__": main()
