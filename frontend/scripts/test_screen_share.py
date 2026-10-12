"""Built viewer: JPEG rendering, normalized input, Unicode, disconnection."""
import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import expect, sync_playwright


def test_screen_share(tmp_path):
    root = Path(__file__).resolve().parents[1]
    server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(SimpleHTTPRequestHandler, directory=str(root / 'dist')))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1000, 'height': 750})
            errors, requests = [], []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.add_init_script('''window.sent=[];window.sockets=[];
              window.WebSocket=class {static OPEN=1;readyState=1;bufferedAmount=0;
                constructor(url){this.url=url;window.sockets.push(this);setTimeout(()=>{
                  if(this.readyState!==1)return;
                  this.onmessage?.({data:JSON.stringify({type:'status',state:'running'})});
                  const c=document.createElement('canvas');c.width=800;c.height=600;
                  const ctx=c.getContext('2d');ctx.fillStyle='rgb(20,100,200)';ctx.fillRect(0,0,800,600);
                  c.toBlob(b=>this.onmessage?.({data:b}),'image/jpeg');},30);}
                send(s){window.sent.push(JSON.parse(s));}
                close(){this.readyState=3;this.onclose?.();}};''')

            def api(route):
                requests.append((route.request.method, route.request.url))
                route.fulfill(status=200, content_type='application/json', body='{}', headers={'Access-Control-Allow-Origin': '*'})
            page.route('**/remote-pcs/screens**', api)
            page.goto(f'http://127.0.0.1:{server.server_port}/#/remote-screen/guestpc-abc')
            canvas = page.get_by_label('원격 PC 화면')
            expect(canvas).to_have_attribute('width', '800')
            assert len([r for r in requests if r[0] == 'POST']) == 1
            assert canvas.evaluate("c=>Array.from(c.getContext('2d').getImageData(10,10,1,1).data)")[2] > 180
            canvas.click(position={'x': 400, 'y': 300})
            page.keyboard.press('a')
            page.keyboard.press('Control+a')
            page.get_by_label('원격 키보드 입력').evaluate("el=>{const e=new Event('compositionend',{bubbles:true});e.data='한글';el.dispatchEvent(e)}")
            page.evaluate("window.dispatchEvent(new Event('blur'))")
            sent = page.evaluate('window.sent')
            assert any(m['type'] == 'pointer' and m['buttons'] == 1 and abs(m['x'] - .5) < .02 for m in sent)
            assert any(m['type'] == 'key' and m['code'] == 'KeyA' and m['down'] for m in sent)
            assert any(m['type'] == 'key' and m['code'] == 'KeyA' and not m['down'] for m in sent)
            assert any(m['type'] == 'text' and m['text'] == '한글' for m in sent)
            assert sent[-1] == {'type': 'reset'}
            page.evaluate("window.sockets.at(-1).onmessage({data:JSON.stringify({type:'status',state:'closed',message:'연결 종료'})});window.sockets.at(-1).close()")
            expect(page.get_by_role('status')).to_contain_text('연결 종료')
            count = len(sent)
            page.get_by_label('원격 키보드 입력').press('x')
            assert len(page.evaluate('window.sent')) == count
            page.screenshot(path=str(tmp_path / 'screen-share.png'))
            assert not errors, errors
            page.evaluate("window.dispatchEvent(new Event('pagehide'))")
            page.wait_for_timeout(100)
            assert any(method == 'DELETE' for method, _ in requests)
            browser.close()
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
