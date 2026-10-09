"""브라우저 사건 × 조작 방식 전수 조사 — 사건마다 새 세션에서 한 번 일으키고, 그 조작의 영수증과 뒤이은 관측(탭·snapshot·콘솔·네트워크·확인창 기록)을 모은다.
읽기 전용(시스템 코드 미변경). 사용: census.py [--port 8990]  → evidence/census_events.json"""
import json, subprocess, sys, time, urllib.request
from pathlib import Path
HERE = Path(__file__).resolve().parent; EV = HERE.parent / 'evidence'
PORT = int(sys.argv[sys.argv.index('--port') + 1]) if '--port' in sys.argv else 8990
BASE = f'http://127.0.0.1:{PORT}'
TRIGGERS = ['popup_blank', 'popup_open', 'download_link', 'download_blob', 'filechooser', 'nav_ok', 'nav_404', 'pageerror', 'console_error', 'alert', 'confirm',
            'fetch_500', 'fetch_refused', 'dom_remove', 'scroll_jump', 'history_push', 'delayed_nav', 'self_close']
OPS = {'click': '[limbs:browser]{op:"click", selector:"#ID"}',
       'key': '[limbs:browser]{op:"press_key", key:"Enter"}',
       'eval': '[limbs:browser]{op:"evaluate", expression:"document.getElementById(\'ID\').click()"}'}
def program(trig, op):
    pre = ''
    if trig == 'self_close':   # 새 창을 먼저 열고 그 창으로 옮긴 뒤, 그 창이 스스로 닫히게 한다
        pre = '''$o = [limbs:browser]{op:"click", selector:"#popup_open"}
$ow = [limbs:browser]{op:"wait", timeout:500}
$ol = [limbs:browser]{op:"tab", mode:"list"}
$pp = filter($ol.tabs, ($t)=>contains($t.url,"/p?"))
$os = [limbs:browser]{op:"tab", mode:"switch", tab_id:$pp[0].tab_id}
'''
    if op == 'key': pre += f'$fo = [limbs:browser]{{op:"evaluate", expression:"document.getElementById(\'{trig}\').focus()"}}\n'
    return f'''#!ibl edition=2
$n = [limbs:browser]{{op:"navigate", url:"{BASE}/t", driver:"playwright", wait:"load"}}
{pre}$r = {{}}
[try]{{ $r = {OPS[op].replace("ID", trig)} }}[catch]{{ $r = {{raised:$error.message}} }}
$tabs0 = {{}}
[try]{{ $tabs0 = [limbs:browser]{{op:"tab", mode:"list"}} }}[catch]{{ $tabs0 = {{raised:$error.message}} }}
$snap0 = {{}}
[try]{{ $snap0 = [limbs:browser]{{op:"snapshot"}} }}[catch]{{ $snap0 = {{raised:$error.message}} }}
$w = {{}}
[try]{{ $w = [limbs:browser]{{op:"wait", timeout:1000}} }}[catch]{{ $w = {{raised:$error.message}} }}
$tabs = {{}}
[try]{{ $tabs = [limbs:browser]{{op:"tab", mode:"list"}} }}[catch]{{ $tabs = {{raised:$error.message}} }}
$snap = {{}}
[try]{{ $snap = [limbs:browser]{{op:"snapshot"}} }}[catch]{{ $snap = {{raised:$error.message}} }}
$sc = {{}}
[try]{{ $sc = [limbs:browser]{{op:"evaluate", expression:"({{y:window.scrollY, out:(document.getElementById('out')||{{}}).textContent||null}})"}} }}[catch]{{ $sc = {{raised:$error.message}} }}
$con = {{}}
[try]{{ $con = [limbs:browser]{{op:"logs", mode:"console"}} }}[catch]{{ $con = {{raised:$error.message}} }}
$net = {{}}
[try]{{ $net = [limbs:browser]{{op:"logs", mode:"network"}} }}[catch]{{ $net = {{raised:$error.message}} }}
$dlg = {{}}
[try]{{ $dlg = [limbs:browser]{{op:"dialog_info"}} }}[catch]{{ $dlg = {{raised:$error.message}} }}
$cz = {{}}
[try]{{ $cz = [limbs:browser]{{op:"close"}} }}[catch]{{ $cz = {{raised:$error.message}} }}
return {{receipt:$r, right_after:{{tabs:$tabs0, snap_url:get($snap0,"url"), snap_tab:get($snap0,"tab_id"), snap_raised:get($snap0,"raised")}}, after_1s:{{tabs:$tabs, snap_url:get($snap,"url"), snap_tab:get($snap,"tab_id"), snap_title:get($snap,"title"), snap_raised:get($snap,"raised"), page:$sc}}, console:$con, network:$net, dialog_info:$dlg}}
'''
def post(body):
    req = urllib.request.Request('http://127.0.0.1:8765/ibl/execute', data=json.dumps(body, ensure_ascii=False).encode(), headers={'Content-Type': 'application/json'})
    try: return json.load(urllib.request.urlopen(req, timeout=180))
    except Exception as e: return {'transport_error': str(e)}
def main():
    state = EV / 'census_server_hits.json'
    srv = subprocess.Popen([sys.executable, str(HERE / 'census_server.py'), '--port', str(PORT), '--state', str(state)]); time.sleep(0.8)
    only = [a for a in sys.argv[1:] if a in TRIGGERS] or TRIGGERS
    out = []
    try:
        for trig in only:
            for op in OPS:
                urllib.request.urlopen(f'{BASE}/reset').read()
                code = program(trig, op); t = time.time()
                r = post({'code': code, 'origin': 'training', 'project_id': '수동모드', 'task_id': f'lsi48-census-{trig}-{op}-{int(t)}', 'budget': {'steps': 200000, 'rows': 100000}})
                hits = [h for h in json.loads(state.read_text()) if h != '/reset'] if state.exists() else []
                v = r.get('value') if r.get('success') else {'program_failed': {k: r.get(k) for k in ('status', 'error', 'issues', 'transport_error')}}
                out.append({'trigger': trig, 'op': op, 'elapsed': round(time.time() - t, 2), 'server_hits': hits, 'observed': v})
                print(trig, op, round(time.time() - t, 1), 'ok' if r.get('success') else 'FAILED', flush=True)
    finally:
        srv.terminate()
    if only == TRIGGERS: (EV / 'census_events.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))
    else: print(json.dumps(out, ensure_ascii=False, indent=1)[:6000])
    state.unlink(missing_ok=True)
if __name__ == '__main__': main()
