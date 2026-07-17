"""portal_html.py — 개인 포털 공개 홈 HTML 렌더러 (디자인 단일 소스).

backend/api_portal.py 가 importlib 로 공유한다(가족신문 newspaper_html.py 선례).
손님과 회원이 같은 홈의 다른 절단면을 본다 — 잠긴 타일도 보여준다(획득 표면).
가입/로그인은 네이버식(아이디+비밀번호+자동 로그인) — <form>+autocomplete 시맨틱으로
브라우저 비밀번호 관리자(저장·자동완성)가 붙게 한다. JS fetch 는 encodeURIComponent 불필요
(JSON body)지만 공개 페이지 JS 일반 규칙은 유지.
"""

import html as _html


def _esc(s) -> str:
    return _html.escape(str(s if s is not None else ""), quote=True)


_LEVEL_LABELS = {0: "손님", 1: "이웃", 2: "가족"}

_CSS = """
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Noto Sans KR',sans-serif;
 background:#f6f1e7;color:#3a332a;line-height:1.6}
.wrap{max-width:560px;margin:0 auto;padding:20px 16px 60px}
/* PC: 본문+사이드바(로그인·안내) 2단, 타일은 폭 따라 증식. 폰(<900px)은 위 1단 그대로. */
@media(min-width:900px){
 .wrap{max-width:1060px;padding:32px 28px 80px;display:grid;grid-template-columns:1fr;gap:0 36px;align-items:start}
 .wrap.cols{grid-template-columns:minmax(0,1fr) 360px}
 header,footer{grid-column:1/-1}
 header h1{font-size:34px}
 aside{position:sticky;top:24px}
}
header{padding:26px 4px 14px;border-bottom:3px double #b9a888;margin-bottom:18px}
header h1{font-size:26px;letter-spacing:1px;color:#2e2820}
header p.intro{margin-top:8px;font-size:14px;color:#6d6252;white-space:pre-wrap}
.hello{margin-top:10px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.hello .chip{display:inline-block;background:#fff;border:1px solid #d9cbb0;border-radius:20px;
 padding:5px 14px;font-size:13px;color:#4a4335}
.hello b{color:#8a5a2b}
.hello button{background:none;border:none;color:#a2937a;font-size:12px;text-decoration:underline;cursor:pointer}
h2.sec{font-size:13px;letter-spacing:2px;color:#9a8a6e;margin:22px 4px 10px;text-transform:uppercase}
.tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
@media(min-width:900px){.tiles{grid-template-columns:repeat(auto-fill,minmax(128px,1fr));gap:12px}}
a.tile,div.tile{background:#fff;border:1px solid #e2d6bd;border-radius:14px;padding:16px 8px;text-align:center;
 text-decoration:none;color:#3a332a;box-shadow:0 1px 3px rgba(90,70,40,.08);transition:border-color .12s,transform .12s}
a.tile:hover{border-color:#b98d4f;transform:translateY(-2px)}
a.tile:active{transform:scale(.97)}
.tile .em{font-size:30px;display:block;margin-bottom:6px}
.tile .nm{font-size:13px;font-weight:600;display:block}
.tile .lk{font-size:11px;color:#a2937a;display:block;margin-top:3px}
div.tile.locked{opacity:.55;background:#efe8da}
.card{background:#fff;border:1px solid #e2d6bd;border-radius:14px;padding:16px;margin-bottom:12px;
 box-shadow:0 1px 3px rgba(90,70,40,.08)}
.card h3{font-size:15px;margin-bottom:8px;color:#2e2820}
.card p.m{font-size:13px;color:#6d6252}
input.f{width:100%;padding:12px 13px;border:1px solid #d9cbb0;border-radius:10px;font-size:15px;
 background:#fbf8f1;margin-bottom:8px}
input.f:focus{outline:none;border-color:#b98d4f}
button.go{width:100%;padding:13px;background:#8a5a2b;color:#fff;border:none;border-radius:10px;
 font-size:15px;font-weight:700;cursor:pointer}
button.go:disabled{background:#c9bda6}
.authtabs{display:flex;gap:6px;margin-bottom:12px}
.authtabs button{flex:1;padding:9px;border:1px solid #d9cbb0;background:#fbf8f1;border-radius:10px;
 font-size:14px;font-weight:600;color:#8a7a60;cursor:pointer}
.authtabs button.on{background:#8a5a2b;border-color:#8a5a2b;color:#fff}
.chk{display:flex;align-items:center;gap:7px;font-size:13px;color:#6d6252;margin:2px 0 10px}
.chk input{width:16px;height:16px;accent-color:#8a5a2b}
.err{color:#a33;font-size:13px;margin-top:8px;min-height:16px}
footer{margin-top:34px;padding-top:14px;border-top:1px solid #e2d6bd;font-size:11px;color:#a2937a;
 text-align:center}
.empty{color:#a2937a;font-size:13px;padding:14px 4px}
"""


def render_home(portal: dict, viewer, tiles: list) -> str:
    """포털 공개 홈 — viewer=None(손님) 또는 회원 dict. tiles=visible_tiles() 결과."""
    title = portal.get("title") or "우리 마을"
    intro = portal.get("intro") or ""

    hello = ""
    pwcard = ""
    if viewer:
        lv = int(viewer.get("level", 0))
        hello = (f'<div class="hello"><span class="chip">👋 <b>{_esc(viewer.get("name"))}</b>님 · '
                 f'레벨 {lv} ({_esc(_LEVEL_LABELS.get(lv, lv))})</span>'
                 f'<button onclick="togglePw()">비밀번호 변경</button>'
                 f'<button onclick="doLogout()">로그아웃</button></div>')
        pwcard = """
<div class="card" id="pwcard" style="display:none;margin-top:12px">
 <h3>🔑 비밀번호 변경</h3>
 <form onsubmit="return doChangePw(event)">
  <input class="f" id="npw" type="password" autocomplete="new-password" placeholder="새 비밀번호 (4자 이상)">
  <button class="go" id="npb" type="submit">바꾸기</button>
 </form>
 <div class="err" id="pwe"></div>
</div>"""

    inst_tiles, content_tiles = [], []
    for t in tiles:
        em, nm = _esc(t["icon"]), _esc(t["name"])
        if t["unlocked"]:
            href = _esc(t["url"] if t["kind"] == "content" else f"inst/{t['key']}")
            lk = "열람" if t["kind"] == "content" else "사용"
            h = f'<a class="tile" href="{href}"><span class="em">{em}</span><span class="nm">{nm}</span><span class="lk">{lk} →</span></a>'
        else:
            need = "로그인" if t["min_level"] <= 0 else f"레벨 {t['min_level']}+"
            h = (f'<div class="tile locked"><span class="em">{em}</span><span class="nm">{nm}</span>'
                 f'<span class="lk">🔒 {need}</span></div>')
        (content_tiles if t["kind"] == "content" else inst_tiles).append(h)

    sections = ""
    if content_tiles:
        sections += '<h2 class="sec">소식·자료</h2><div class="tiles">' + "".join(content_tiles) + "</div>"
    if inst_tiles:
        sections += '<h2 class="sec">계기</h2><div class="tiles">' + "".join(inst_tiles) + "</div>"
    if not sections:
        sections = '<p class="empty">아직 진열된 것이 없어요 — 곧 채워집니다.</p>'

    auth_html = ""
    if not viewer:
        auth_html = """
<h2 class="sec" style="margin-top:0">로그인 · 가입</h2>
<div class="card">
 <div class="authtabs">
  <button id="tabLogin" class="on" onclick="authTab('login')">로그인</button>
  <button id="tabJoin" onclick="authTab('join')">가입</button>
 </div>
 <form id="fLogin" onsubmit="return doLogin(event)">
  <input class="f" id="li" name="username" autocomplete="username" placeholder="아이디" autocapitalize="none">
  <input class="f" id="lp" name="password" type="password" autocomplete="current-password" placeholder="비밀번호">
  <label class="chk"><input type="checkbox" id="lauto" checked> 자동 로그인</label>
  <button class="go" id="lb" type="submit">로그인</button>
  <p style="text-align:center;margin-top:10px"><a href="#" onclick="return authTab('reset')" style="color:#a2937a;font-size:13px">비밀번호를 잊으셨나요?</a></p>
 </form>
 <form id="fJoin" style="display:none" onsubmit="return doJoin(event)">
  <p class="m" style="margin-bottom:10px">이름·아이디·이메일만 있으면 바로 등록돼요.
  이메일은 비밀번호를 잊었을 때 찾는 데 씁니다. 운영자가 등급을 올려주면 더 많은 것이 열립니다.</p>
  <input class="f" id="jn" maxlength="24" placeholder="이름 (닉네임)">
  <input class="f" id="ji" name="username" autocomplete="username" placeholder="아이디 (영문 소문자·숫자 3~20자)" autocapitalize="none">
  <input class="f" id="je" name="email" type="email" autocomplete="email" placeholder="이메일 (비밀번호 찾기용)" autocapitalize="none">
  <input class="f" id="jp" name="new-password" type="password" autocomplete="new-password" placeholder="비밀번호 (4자 이상)">
  <label class="chk"><input type="checkbox" id="jauto" checked> 자동 로그인</label>
  <button class="go" id="jb" type="submit">가입하고 시작하기</button>
 </form>
 <form id="fReset" style="display:none" onsubmit="return doReset(event)">
  <p class="m" style="margin-bottom:10px">가입할 때 쓴 이메일을 넣으면, 임시 비밀번호를 그 이메일로 보내드려요.
  받은 비밀번호로 로그인한 뒤 바꾸시면 됩니다.</p>
  <input class="f" id="re" name="email" type="email" autocomplete="email" placeholder="가입 이메일" autocapitalize="none">
  <button class="go" id="rb" type="submit">임시 비밀번호 메일로 받기</button>
  <p style="text-align:center;margin-top:10px"><a href="#" onclick="return authTab('login')" style="color:#a2937a;font-size:13px">← 로그인으로</a></p>
 </form>
 <div class="err" id="ae"></div>
</div>
<script>
function authTab(t){
  var show={login:'none',join:'none',reset:'none'}; show[t]='block';
  document.getElementById('fLogin').style.display=show.login;
  document.getElementById('fJoin').style.display=show.join;
  document.getElementById('fReset').style.display=show.reset;
  document.getElementById('tabLogin').className=(t==='login')?'on':'';
  document.getElementById('tabJoin').className=(t==='join')?'on':'';
  document.getElementById('ae').textContent='';
  return false;
}
async function _auth(url,body,btn,onOk){
  var e=document.getElementById('ae'); e.textContent=''; btn.disabled=true;
  try{
    var r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    var d=await r.json().catch(function(){return {};});
    if(!r.ok||!d.ok){ e.textContent=d.detail||d.error||'실패했어요 — 다시 시도해 주세요'; btn.disabled=false; return; }
    if(onOk){ onOk(d); btn.disabled=false; } else { location.reload(); }
  }catch(x){ e.textContent='연결 실패 — 잠시 후 다시'; btn.disabled=false; }
}
function doLogin(ev){ ev.preventDefault();
  var u=document.getElementById('li').value.trim(), p=document.getElementById('lp').value;
  if(!u||!p){ document.getElementById('ae').textContent='아이디와 비밀번호를 입력해 주세요'; return false; }
  _auth('login',{user_id:u,password:p,auto:document.getElementById('lauto').checked},document.getElementById('lb'));
  return false; }
function doJoin(ev){ ev.preventDefault();
  var n=document.getElementById('jn').value.trim(), u=document.getElementById('ji').value.trim(),
      em=document.getElementById('je').value.trim(), p=document.getElementById('jp').value;
  if(!n||!u||!em||!p){ document.getElementById('ae').textContent='이름·아이디·이메일·비밀번호를 입력해 주세요'; return false; }
  _auth('join',{name:n,user_id:u,email:em,password:p,auto:document.getElementById('jauto').checked},document.getElementById('jb'));
  return false; }
function doReset(ev){ ev.preventDefault();
  var em=document.getElementById('re').value.trim();
  if(!em){ document.getElementById('ae').textContent='가입 이메일을 입력해 주세요'; return false; }
  _auth('reset',{email:em},document.getElementById('rb'),function(d){
    var e=document.getElementById('ae'); e.style.color='#2e7d32';
    e.textContent=d.message||'임시 비밀번호를 이메일로 보냈어요'; });
  return false; }
</script>"""

    logout_js = """
<script>
async function doLogout(){
  try{ await fetch('logout',{method:'POST'}); }catch(e){}
  location.reload();
}
function togglePw(){ var c=document.getElementById('pwcard');
  c.style.display=(c.style.display==='none')?'block':'none'; }
async function doChangePw(ev){ ev.preventDefault();
  var e=document.getElementById('pwe'); e.style.color='#a33'; e.textContent='';
  var p=document.getElementById('npw').value, b=document.getElementById('npb');
  if(!p||p.length<4){ e.textContent='새 비밀번호는 4자 이상이어야 해요'; return false; }
  b.disabled=true;
  try{
    var r=await fetch('password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({new_password:p})});
    var d=await r.json().catch(function(){return {};});
    if(!r.ok||!d.ok){ e.textContent=d.detail||'실패했어요'; b.disabled=false; return false; }
    e.style.color='#2e7d32'; e.textContent=d.message||'바꿨어요'; document.getElementById('npw').value=''; b.disabled=false;
  }catch(x){ e.textContent='연결 실패'; b.disabled=false; }
  return false; }
</script>""" if viewer else ""

    # PC(≥900px): 손님이면 본문+로그인 사이드바 2단(.cols), 회원이면 넓은 1단. 폰은 늘 1단.
    aside = f"<aside>{auth_html}</aside>" if auth_html else ""
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex">
<title>{_esc(title)}</title><style>{_CSS}</style></head>
<body><div class="wrap{' cols' if aside else ''}">
<header><h1>🏘️ {_esc(title)}</h1>
{('<p class="intro">' + _esc(intro) + '</p>') if intro else ''}
{hello}
</header>
{pwcard}
<main>
{sections}
</main>
{aside}
{logout_js}
<footer>비밀번호를 잊으면 로그인 화면의 '비밀번호를 잊으셨나요?'에서 이메일로 임시 비밀번호를 받으세요<br>powered by IndieBiz OS</footer>
</div></body></html>"""


def render_notice(title: str, msg: str, home: str = "") -> str:
    """잠금·무효 링크 등 안내 페이지."""
    back = f'<p style="margin-top:14px"><a href="{_esc(home)}" style="color:#8a5a2b">← 홈으로</a></p>' if home else ""
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex">
<title>{_esc(title)}</title><style>{_CSS}</style></head>
<body><div class="wrap"><div class="card" style="margin-top:40px;text-align:center">
<h3>{_esc(title)}</h3><p class="m">{_esc(msg)}</p>{back}
</div></div></body></html>"""
