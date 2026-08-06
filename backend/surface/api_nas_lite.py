"""
api_nas_lite.py — 구형 기기용 경량 Finder 페이지 HTML (api_nas.py 에서 분리, 2026-08-06 1500줄 규칙)

/nas/lite(iOS 10.3+ 구형 Safari) · /nas/lite2(iOS 5.1.1 아이패드 1세대) 가 서빙하는
자족 HTML 두 벌. 순수 데이터 — 로직 금지(서빙 라우터는 api_nas.py 에 잔류).
launcher_lite.py(런처판)의 NAS 형제.
"""

# 구형 Safari(iOS 10.3+) 호환 경량 Finder 페이지. 최신 런처가 못 뜨는 낡은 WebKit 용.
# ES6 이하(arrow/?. 회피), 문자열 결합만. /nas/lite 가 서빙. 쿠키(nas_session)로 인증 →
# img/iframe/file 직링크도 자동 인증. 텍스트=주력, EPUB=서버 추출, PDF=네이티브 새 탭.
_NAS_LITE_HTML = r'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black">
<title>NAS Finder</title>
<style>
  * { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
  body { margin:0; font-family:-apple-system,Helvetica,Arial,sans-serif; background:#111; color:#eee; font-size:17px; }
  .hide { display:none !important; }
  .bar { position:-webkit-sticky; position:sticky; top:0; background:#1c1c1e; border-bottom:1px solid #333; padding:8px 10px; display:-webkit-flex; display:flex; -webkit-align-items:center; align-items:center; }
  .bar .path { -webkit-flex:1; flex:1; font-size:12px; color:#9a9a9e; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; padding:0 8px; }
  button { background:#2c2c2e; color:#eee; border:1px solid #444; border-radius:8px; padding:9px 13px; font-size:15px; }
  button:active { background:#3a3a3c; }
  .list { padding:2px 0 50px; }
  .row { display:-webkit-flex; display:flex; -webkit-align-items:center; align-items:center; padding:13px 14px; border-bottom:1px solid #222; }
  .row .ic { font-size:20px; width:26px; text-align:center; }
  .row .nm { -webkit-flex:1; flex:1; word-break:break-all; padding:0 10px; }
  .row .sz { font-size:12px; color:#888; white-space:nowrap; }
  .row .dl { margin-left:10px; padding:6px 11px; font-size:13px; color:#fff; background:#196127; border-color:#196127; }
  .login { padding:64px 24px; text-align:center; }
  .login input { width:100%; max-width:280px; padding:13px; font-size:17px; border-radius:8px; border:1px solid #444; background:#222; color:#eee; margin:12px 0; }
  .err { color:#ff6b6b; font-size:14px; min-height:18px; }
  .viewer { position:fixed; top:0; left:0; right:0; bottom:0; background:#111; display:-webkit-flex; display:flex; -webkit-flex-direction:column; flex-direction:column; z-index:10; }
  .vbar { background:#1c1c1e; border-bottom:1px solid #333; padding:8px 10px; display:-webkit-flex; display:flex; -webkit-align-items:center; align-items:center; }
  .vtitle { -webkit-flex:1; flex:1; font-size:12px; color:#9a9a9e; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; padding:0 8px; }
  .vbody { -webkit-flex:1; flex:1; overflow:auto; }  /* -webkit-overflow-scrolling:touch 제거 — 긴 텍스트 검은화면(합성레이어 한계) 방지 */
  pre.txt { white-space:pre-wrap; word-wrap:break-word; padding:16px; margin:0; font-size:16px; line-height:1.6; font-family:Menlo,monospace; }
  /* 빠른 점프 스크롤바 — 썸을 잡아끌어 파일 임의 위치로 즉시 이동(탭 페이징 보완) */
  .jbar { position:absolute; top:46px; right:2px; bottom:4px; width:28px; z-index:20; cursor:pointer; touch-action:none; display:none; }
  .jbar:before { content:''; position:absolute; left:12px; right:12px; top:0; bottom:0; background:#2c2c2e; border-radius:2px; }
  .jthumb { position:absolute; left:4px; right:4px; min-height:46px; background:#0a84ff; border-radius:9px; opacity:0.85; }
  .jthumb:active { opacity:1; background:#3a9bff; }
  .epub { padding:18px 20px; line-height:1.8; font-size:18px; }
  .epub img { max-width:100%; }
  img.imgv { max-width:100%; display:block; margin:0 auto; }
</style>
</head>
<body>
<div id="login" class="login">
  <h2>NAS Finder</h2>
  <input id="pw" type="password" placeholder="비밀번호" autocomplete="current-password">
  <div><button id="loginBtn">로그인</button></div>
  <p class="err" id="err"></p>
</div>
<div id="app" class="hide">
  <div class="bar"><button id="up">↑</button><span class="path" id="curpath"></span><button id="logout">나가기</button></div>
  <div class="list" id="list"></div>
</div>
<div id="viewer" class="viewer hide">
  <div class="vbar"><button id="vclose">← 닫기</button><span class="vtitle" id="vtitle"></span><button id="vminus">A-</button><button id="vplus">A+</button></div>
  <div class="vbody" id="vbody"></div>
  <div class="jbar" id="jbar"><div class="jthumb" id="jthumb"></div></div>
</div>
<script>
(function(){
  var parentPath = null, fontSize = 17;
  function $(id){ return document.getElementById(id); }
  function esc(s){ return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }
  function fmtSize(n){ if(n==null) return ""; if(n<1024) return n+"B"; if(n<1048576) return Math.round(n/1024)+"KB"; return (n/1048576).toFixed(1)+"MB"; }
  function api(url, opts){ opts = opts || {}; opts.credentials = "same-origin"; return fetch(url, opts); }

  $("loginBtn").addEventListener("click", doLogin);
  $("pw").addEventListener("keyup", function(e){ if(e.keyCode===13) doLogin(); });
  function doLogin(){
    $("err").textContent = "";
    api("/nas/auth/login", { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({password: $("pw").value}) })
      .then(function(r){ if(!r.ok) throw 0; return r.json(); })
      .then(function(){ $("login").className="login hide"; $("app").className=""; loadDir(""); })
      .catch(function(){ $("err").textContent="비밀번호가 올바르지 않습니다"; });
  }
  $("logout").addEventListener("click", function(){ api("/nas/auth/logout",{method:"POST"}).then(function(){ location.reload(); }); });
  $("up").addEventListener("click", function(){ if(parentPath!=null) loadDir(parentPath); });

  function loadDir(path){
    api("/nas/files?path="+encodeURIComponent(path)).then(function(r){
      if(r.status===401){ showLogin(); throw 0; }
      if(!r.ok) throw 0; return r.json();
    }).then(function(d){
      parentPath = d.parent;
      $("curpath").textContent = d.path;
      $("up").style.opacity = (d.parent==null)?"0.3":"1";
      renderList(d.items||[]);
      window.scrollTo(0,0);
    }).catch(function(){});
  }
  function iconFor(it){
    var n=(it.name||"").toLowerCase();
    if(it.is_dir) return "[D]";
    if(n.indexOf(".epub")>=0) return "EP";
    if(it.category==="pdf") return "PD";
    if(it.category==="image") return "IM";
    if(it.category==="video") return "VD";
    if(it.category==="audio") return "AU";
    return "TX";
  }
  function renderList(items){
    var h="", i;
    for(i=0;i<items.length;i++){
      var it=items[i];
      var dl = it.is_dir? "" : '<button class="dl" id="d'+i+'">저장</button>';
      h+='<div class="row"><span class="ic">'+iconFor(it)+'</span><span class="nm">'+esc(it.name)+'</span><span class="sz">'+(it.is_dir?"":fmtSize(it.size))+'</span>'+dl+'</div>';
    }
    var list=$("list"); list.innerHTML=h;
    var rows=list.getElementsByClassName("row");
    for(i=0;i<rows.length;i++){
      (function(it, idx){
        rows[idx].addEventListener("click", function(){ if(it.is_dir) loadDir(it.path); else openFile(it); });
        if(!it.is_dir){ var b=document.getElementById("d"+idx); if(b){ b.addEventListener("click", function(e){ e.stopPropagation(); exportFile(it); }); } }
      })(items[i], i);
    }
  }
  function exportFile(it){ var url="/nas/file?path="+encodeURIComponent(it.path); var w=window.open(url,"_blank"); if(!w) window.location.href=url; }

  $("vclose").addEventListener("click", function(){ $("viewer").className="viewer hide"; $("vbody").innerHTML=""; jShow(false); });
  $("vplus").addEventListener("click", function(){ fontSize+=2; applyFont(); });
  $("vminus").addEventListener("click", function(){ if(fontSize>10){ fontSize-=2; applyFont(); } });
  // 탭 페이징 — 위쪽 40% 탭=이전, 아래쪽 40% 탭=다음(가운데 무시). 드래그는 수동 스크롤 유지.
  $("vbody").addEventListener("click", function(e){
    var vb=$("vbody"); if(vb.scrollHeight<=vb.clientHeight+4) return;
    var r=vb.getBoundingClientRect(); var rel=((e.clientY||0)-r.top)/(r.height||vb.clientHeight);
    var step=vb.clientHeight-48;
    if(rel<0.4){ vb.scrollTop-=step; } else if(rel>0.6){ vb.scrollTop+=step; }
  });
  function applyFont(){ var t=$("vbody").querySelector("pre.txt, .epub"); if(t) t.style.fontSize=fontSize+"px"; jUpd(); }
  function openViewer(title){ $("vtitle").textContent=title; $("viewer").className="viewer"; }

  // 빠른 점프 스크롤바 — 썸 위치 = vbody 스크롤 비율. 드래그로 파일 임의 위치 즉시 이동.
  var jbar=$("jbar"), jthumb=$("jthumb"), jdrag=false;
  function jShow(on){ jbar.style.display=on?"block":"none"; if(on) jUpd(); }
  function jUpd(){
    if(jbar.style.display!=="block") return;
    var vb=$("vbody"), sh=vb.scrollHeight, ch=vb.clientHeight;
    if(sh<=ch+4){ jthumb.style.display="none"; return; }  // 짧은 파일이면 썸 숨김
    jthumb.style.display="block";
    var trackH=jbar.clientHeight, thumbH=Math.max(46, trackH*ch/sh), maxTop=trackH-thumbH;
    jthumb.style.height=thumbH+"px";
    jthumb.style.top=(maxTop*(vb.scrollTop/(sh-ch)))+"px";
  }
  function jJump(cy){
    var vb=$("vbody"), rect=jbar.getBoundingClientRect(), thumbH=jthumb.offsetHeight, maxTop=rect.height-thumbH;
    var y=Math.max(0, Math.min(maxTop, cy-rect.top-thumbH/2)), sh=vb.scrollHeight, ch=vb.clientHeight;
    vb.scrollTop=(sh-ch)*(maxTop? y/maxTop : 0);
    jUpd();
  }
  function jY(e){ return (e.touches&&e.touches[0])? e.touches[0].clientY : e.clientY; }
  jbar.addEventListener("mousedown", function(e){ jdrag=true; e.preventDefault(); jJump(jY(e)); });
  document.addEventListener("mousemove", function(e){ if(jdrag){ e.preventDefault(); jJump(jY(e)); } });
  document.addEventListener("mouseup", function(){ jdrag=false; });
  jbar.addEventListener("touchstart", function(e){ jdrag=true; e.preventDefault(); jJump(jY(e)); }, {passive:false});
  document.addEventListener("touchmove", function(e){ if(jdrag){ e.preventDefault(); jJump(jY(e)); } }, {passive:false});
  document.addEventListener("touchend", function(){ jdrag=false; });
  $("vbody").addEventListener("scroll", jUpd);
  window.addEventListener("resize", jUpd);

  function isTextName(n){ return /\.(txt|md|markdown|log|csv|json|xml|html?|css|js|py|sh|ini|conf|yaml|yml|srt|vtt|tsv|rtf)$/.test(n); }

  function openFile(it){
    var name=(it.name||"").toLowerCase();
    var url="/nas/file?path="+encodeURIComponent(it.path);
    if(name.indexOf(".epub")>=0){ openEpub(it); return; }
    if(it.category==="pdf"){ var w=window.open(url,"_blank"); if(!w) window.location.href=url; return; }
    if(it.category==="image"){ openViewer(it.name); jShow(false); $("vbody").innerHTML='<img class="imgv" src="'+url+'">'; return; }
    if(it.category==="text" || isTextName(name)){
      openViewer(it.name); jShow(false);
      $("vbody").innerHTML='<pre class="txt">불러오는 중...</pre>';
      api("/nas/text?path="+encodeURIComponent(it.path)).then(function(r){ if(!r.ok) throw 0; return r.json(); })
        .then(function(d){ var pre=$("vbody").querySelector("pre.txt"); pre.textContent=d.content; pre.style.fontSize=fontSize+"px"; jShow(true); })
        .catch(function(){ $("vbody").innerHTML='<pre class="txt">텍스트로 열 수 없습니다.</pre>'; });
      return;
    }
    var w2=window.open(url,"_blank"); if(!w2) window.location.href=url;
  }
  function openEpub(it){
    openViewer(it.name); jShow(false);
    $("vbody").innerHTML='<div class="epub">불러오는 중...</div>';
    api("/nas/epub?path="+encodeURIComponent(it.path)).then(function(r){ if(!r.ok) throw 0; return r.json(); })
      .then(function(d){ var div=$("vbody").querySelector(".epub"); div.innerHTML=d.html||"(내용 없음)"; div.style.fontSize=fontSize+"px"; if(d.title) $("vtitle").textContent=d.title; jShow(true); })
      .catch(function(){ $("vbody").innerHTML='<div class="epub">EPUB을 열 수 없습니다.</div>'; });
  }
  function showLogin(){ $("app").className="hide"; $("login").className="login"; }

  api("/nas/auth/check").then(function(r){ return r.json(); }).then(function(d){
    if(d && d.authenticated){ $("login").className="login hide"; $("app").className=""; loadDir(""); }
  }).catch(function(){});
})();
</script>
</body>
</html>'''


# 초-구형 기기(iOS 5.1.1 아이패드 1세대 등) 호환 — 순수 ES5 + XMLHttpRequest + 구식 레이아웃.
# fetch/Promise/현대 flexbox 전혀 안 씀. /nas/lite2 가 서빙. (단 터널 HTTPS는 iPad1 TLS/인증서
# 한계로 안 될 수 있음 → LAN 평문 HTTP 권장.) 기능은 lite 와 동일(텍스트/EPUB/PDF/이미지).
_NAS_LITE2_HTML = r'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>NAS Finder (old)</title>
<style>
  * { -webkit-box-sizing:border-box; box-sizing:border-box; }
  body { margin:0; font-family:Helvetica,Arial,sans-serif; background:#111; color:#eee; font-size:17px; -webkit-text-size-adjust:none; }
  .hide { display:none; }
  #bar { background:#1c1c1e; border-bottom:1px solid #333; padding:8px; overflow:hidden; }
  #bar #up { float:left; }
  #bar #logout { float:right; }
  #curpath { display:block; padding:8px 2px 0; clear:both; font-size:12px; color:#9a9a9e; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }
  button { background:#2c2c2e; color:#eee; border:1px solid #444; border-radius:6px; padding:9px 13px; font-size:15px; }
  .row { padding:13px 12px; border-bottom:1px solid #222; overflow:hidden; }
  .row .ic { display:inline-block; width:30px; color:#8a8a8e; }
  .row .sz { float:right; font-size:12px; color:#888; padding-top:2px; }
  .row .dl { float:right; margin-left:10px; padding:6px 11px; font-size:13px; color:#fff; background:#196127; border-color:#196127; }
  .login { padding:50px 20px; text-align:center; }
  .login input { width:240px; padding:12px; font-size:17px; border:1px solid #444; border-radius:6px; background:#222; color:#eee; margin:10px 0; }
  .err { color:#ff6b6b; min-height:18px; }
  #viewer { position:fixed; top:0; left:0; right:0; bottom:0; background:#111; }
  #vbar { background:#1c1c1e; border-bottom:1px solid #333; padding:8px; overflow:hidden; }
  #vbar #vclose { float:left; }
  #vbar .vctrl { float:right; }
  /* -webkit-overflow-scrolling:touch 제거 — GPU 합성 스크롤 레이어는 최대 크기 한계가 있어
     긴 텍스트(1.8MB 등)는 그 한계 넘는 부분이 검게 칠해진다(스크롤 높이는 살아있음). 일반
     스크롤은 타일링 페인팅이라 전체가 칠해진다(모멘텀만 빠짐 — 리더엔 렌더링이 우선). */
  #vbody { position:absolute; top:53px; left:0; right:0; bottom:0; overflow:auto; }
  pre.txt { white-space:pre-wrap; word-wrap:break-word; padding:14px; margin:0; font-size:16px; line-height:1.6; }
  /* 빠른 점프 스크롤바 — 썸을 잡아끌어 파일 임의 위치로 즉시 이동(탭 페이징 보완) */
  .jbar { position:absolute; top:55px; right:0; bottom:2px; width:30px; z-index:20; display:none; background:#1c1c1e; border-left:1px solid #333; }
  .jthumb { position:absolute; left:5px; right:5px; min-height:48px; background:#0a84ff; border-radius:8px; }
  .epub { padding:16px; line-height:1.75; font-size:18px; }
  .epub img { max-width:100%; }
  img.imgv { max-width:100%; }
</style>
</head>
<body>
<div id="login" class="login">
  <h3>NAS Finder</h3>
  <input id="pw" type="password" placeholder="비밀번호">
  <div><button id="loginBtn">로그인</button></div>
  <p class="err" id="err"></p>
</div>
<div id="app" class="hide">
  <div id="bar"><button id="up">위로</button><button id="logout">나가기</button><span id="curpath"></span></div>
  <div id="list"></div>
</div>
<div id="viewer" class="hide">
  <div id="vbar"><button id="vclose">닫기</button><span class="vctrl"><button id="vminus">A-</button> <button id="vplus">A+</button></span></div>
  <div id="vbody"></div>
  <div class="jbar" id="jbar"><div class="jthumb" id="jthumb"></div></div>
</div>
<script>
(function(){
  var parentPath=null, fontSize=17;
  function $(id){ return document.getElementById(id); }
  function esc(s){ s=(s==null?'':''+s); return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
  function fmtSize(n){ if(n==null) return ''; if(n<1024) return n+'B'; if(n<1048576) return Math.round(n/1024)+'KB'; return Math.round(n/104857.6)/10+'MB'; }
  function xhr(method,url,jsonBody,cb,errcb){
    var x=new XMLHttpRequest();
    x.open(method,url,true);
    if(jsonBody!=null) x.setRequestHeader('Content-Type','application/json');
    x.onreadystatechange=function(){
      if(x.readyState!==4) return;
      if(x.status>=200 && x.status<300){ cb(x); } else if(errcb){ errcb(x); }
    };
    x.send(jsonBody!=null? JSON.stringify(jsonBody): null);
  }
  function parse(x){ try{ return JSON.parse(x.responseText); }catch(e){ return null; } }

  $('loginBtn').onclick=doLogin;
  $('pw').onkeyup=function(e){ if(e.keyCode===13) doLogin(); };
  function doLogin(){
    $('err').innerHTML='';
    xhr('POST','/nas/auth/login',{password:$('pw').value},function(){
      $('login').className='login hide'; $('app').className=''; loadDir('');
    },function(){ $('err').innerHTML='비밀번호가 올바르지 않습니다'; });
  }
  $('logout').onclick=function(){ xhr('POST','/nas/auth/logout',null,function(){ location.reload(); },function(){ location.reload(); }); };
  $('up').onclick=function(){ if(parentPath!=null) loadDir(parentPath); };

  function loadDir(path){
    xhr('GET','/nas/files?path='+encodeURIComponent(path),null,function(x){
      var d=parse(x); if(!d) return;
      parentPath=d.parent;
      $('curpath').innerHTML=esc(d.path);
      $('up').style.opacity=(d.parent==null)?'0.3':'1';
      render(d.items||[]);
      window.scrollTo(0,0);
    },function(x){ if(x.status===401){ $('app').className='hide'; $('login').className='login'; } });
  }
  function iconFor(it){
    var n=(it.name||'').toLowerCase();
    if(it.is_dir) return '[D]';
    if(n.indexOf('.epub')>=0) return 'EP';
    if(it.category==='pdf') return 'PD';
    if(it.category==='image') return 'IM';
    if(it.category==='video') return 'VD';
    if(it.category==='audio') return 'AU';
    return 'TX';
  }
  function render(items){
    var h='',i;
    for(i=0;i<items.length;i++){
      var it=items[i];
      var dl=it.is_dir?'':'<button class="dl" id="d'+i+'">저장</button>';
      h+='<div class="row" id="r'+i+'">'+dl+'<span class="ic">'+iconFor(it)+'</span>'+esc(it.name)+'<span class="sz">'+(it.is_dir?'':fmtSize(it.size))+'</span></div>';
    }
    $('list').innerHTML=h;
    for(i=0;i<items.length;i++){ bindRow(i, items[i]); }
  }
  function bindRow(idx, it){
    $('r'+idx).onclick=function(){ if(it.is_dir) loadDir(it.path); else openFile(it); };
    if(!it.is_dir){ var b=$('d'+idx); if(b){ b.onclick=function(e){ if(e&&e.stopPropagation) e.stopPropagation(); exportFile(it); return false; }; } }
  }
  function exportFile(it){ var url='/nas/file?path='+encodeURIComponent(it.path); var w=window.open(url,'_blank'); if(!w) window.location.href=url; }

  $('vclose').onclick=function(){ $('viewer').className='hide'; $('vbody').innerHTML=''; jShow(false); };
  $('vplus').onclick=function(){ fontSize+=2; applyFont(); };
  $('vminus').onclick=function(){ if(fontSize>10){ fontSize-=2; applyFont(); } };
  // 탭 페이징 — 모멘텀 스크롤이 없어(긴 텍스트 검은화면 방지로 제거) 긴 파일 넘기기가 힘들다.
  // 위쪽(40%) 탭=이전 페이지, 아래쪽(40%) 탭=다음 페이지, 가운데는 무시. 드래그는 수동 스크롤 그대로.
  $('vbody').onclick=function(e){
    var vb=$('vbody'); if(vb.scrollHeight<=vb.clientHeight+4) return;  // 스크롤 불필요(이미지 등)면 무시
    var y=(e&&e.clientY!=null)?e.clientY:0;
    var r=vb.getBoundingClientRect?vb.getBoundingClientRect():{top:53,height:vb.clientHeight};
    var rel=(y-r.top)/(r.height||vb.clientHeight);
    var step=vb.clientHeight-48;  // 한 화면 - 겹침(맥락 유지)
    if(rel<0.4){ vb.scrollTop-=step; } else if(rel>0.6){ vb.scrollTop+=step; }
  };
  function applyFont(){ var t=$('vbody').firstChild; if(t&&t.style) t.style.fontSize=fontSize+'px'; jUpd(); }
  function openViewer(){ $('viewer').className=''; }

  // 빠른 점프 스크롤바 — 썸 위치 = vbody 스크롤 비율. 드래그로 파일 임의 위치 즉시 이동.
  // iOS5 호환: addEventListener 3번째 인자는 불리언만, onscroll/onresize 프로퍼티 사용.
  var jbar=$('jbar'), jthumb=$('jthumb'), jdrag=false;
  function jShow(on){ jbar.style.display=on?'block':'none'; if(on) jUpd(); }
  function jUpd(){
    if(jbar.style.display!=='block') return;
    var vb=$('vbody'), sh=vb.scrollHeight, ch=vb.clientHeight;
    if(sh<=ch+4){ jthumb.style.display='none'; return; }  // 짧은 파일이면 썸 숨김
    jthumb.style.display='block';
    var trackH=jbar.clientHeight, thumbH=Math.max(48, trackH*ch/sh), maxTop=trackH-thumbH;
    jthumb.style.height=thumbH+'px';
    jthumb.style.top=(maxTop*(vb.scrollTop/(sh-ch)))+'px';
  }
  function jJump(cy){
    var vb=$('vbody'), rect=jbar.getBoundingClientRect(), thumbH=jthumb.offsetHeight, maxTop=rect.height-thumbH;
    var y=Math.max(0, Math.min(maxTop, cy-rect.top-thumbH/2)), sh=vb.scrollHeight, ch=vb.clientHeight;
    vb.scrollTop=(sh-ch)*(maxTop? y/maxTop : 0);
    jUpd();
  }
  function jY(e){ return (e.touches&&e.touches[0])? e.touches[0].clientY : (e.clientY||0); }
  jbar.addEventListener('mousedown', function(e){ jdrag=true; if(e.preventDefault) e.preventDefault(); jJump(jY(e)); }, false);
  document.addEventListener('mousemove', function(e){ if(jdrag){ if(e.preventDefault) e.preventDefault(); jJump(jY(e)); } }, false);
  document.addEventListener('mouseup', function(){ jdrag=false; }, false);
  jbar.addEventListener('touchstart', function(e){ jdrag=true; if(e.preventDefault) e.preventDefault(); jJump(jY(e)); }, false);
  document.addEventListener('touchmove', function(e){ if(jdrag){ if(e.preventDefault) e.preventDefault(); jJump(jY(e)); } }, false);
  document.addEventListener('touchend', function(){ jdrag=false; }, false);
  $('vbody').onscroll=jUpd;
  window.onresize=jUpd;

  function isText(n){ return /\.(txt|md|markdown|log|csv|tsv|json|xml|html?|css|js|py|sh|ini|conf|yaml|yml|srt|vtt|rtf)$/.test(n); }
  function openFile(it){
    var name=(it.name||'').toLowerCase();
    var url='/nas/file?path='+encodeURIComponent(it.path);
    if(name.indexOf('.epub')>=0){ openEpub(it); return; }
    if(it.category==='pdf'){ var w=window.open(url,'_blank'); if(!w) window.location.href=url; return; }
    if(it.category==='image'){ openViewer(); jShow(false); $('vbody').innerHTML='<img class="imgv" src="'+url+'">'; return; }
    if(it.category==='text'||isText(name)){
      openViewer(); jShow(false); $('vbody').innerHTML='<pre class="txt">불러오는 중...</pre>';
      xhr('GET','/nas/text?path='+encodeURIComponent(it.path),null,function(x){
        var d=parse(x); var pre=$('vbody').firstChild;
        if(d&&pre){ pre.innerHTML=''; pre.appendChild(document.createTextNode(d.content)); pre.style.fontSize=fontSize+'px'; jShow(true); }
      },function(){ $('vbody').innerHTML='<pre class="txt">텍스트로 열 수 없습니다.</pre>'; });
      return;
    }
    var w2=window.open(url,'_blank'); if(!w2) window.location.href=url;
  }
  function openEpub(it){
    openViewer(); jShow(false); $('vbody').innerHTML='<div class="epub">불러오는 중...</div>';
    xhr('GET','/nas/epub?path='+encodeURIComponent(it.path),null,function(x){
      var d=parse(x); var div=$('vbody').firstChild;
      if(d&&div){ div.innerHTML=d.html||'(내용 없음)'; div.style.fontSize=fontSize+'px'; jShow(true); }
    },function(){ $('vbody').innerHTML='<div class="epub">EPUB을 열 수 없습니다.</div>'; });
  }

  xhr('GET','/nas/auth/check',null,function(x){
    var d=parse(x); if(d&&d.authenticated){ $('login').className='login hide'; $('app').className=''; loadDir(''); }
  });
})();
</script>
</body>
</html>'''
