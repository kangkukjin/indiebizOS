# 구형 기기 호환 경량 런처 — /launcher/lite 가 서빙 (NAS /nas/lite·lite2 의 런처판).
#
# 대상: 구형 Safari 전 구간을 한 페이지로 — iOS 10.3(lite급)은 물론 iOS 5.1.1
# 아이패드 1세대(lite2급)까지. 그래서 fetch/Promise/화살표/템플릿리터럴/현대 flexbox 를
# 전혀 안 쓰고 순수 ES5 + XMLHttpRequest + 구식 블록 레이아웃만 쓴다.
#
# 기능 3탭 (본판 5탭의 핵심만):
#   자율주행 — 시스템 AI 대화. POST /system-ai/chat {background:true} 로 즉시 반환받고
#              (터널 524 타임아웃 회피, 본판 자율주행 탭과 동일 경로) 대화 로그를
#              폴링해 응답을 받는다.
#   조종실   — 자연어 → /ibl/translate 번역 → /ibl/validate dry-run 검수 → /ibl/execute
#              실행 (project_id='수동모드', 본판 조종실과 동일 계약).
#   창고     — ★읽기 전용. 내 창고 = /portal/warehouse-admin/list?level=N 목록 + /file 로 열기,
#              이웃 = /warehouse-feed/feed 변화 타임라인. 본판 창고 탭의 쓰기 기능
#              (업로드·리트윗·좋아요·이웃 편집·소개발행)은 의도적으로 뺐다 — 구형 기기에서
#              필요한 건 '보는 것'이고, 쓰기를 넣으면 ES5 로 옮길 코드가 몇 배가 된다.
#              파일 열기는 <a href> 앵커라 XHR 헤더가 안 붙는다: LAN(사설망)은 인증 게이트가
#              통과시키고(is_external_request ③), 터널은 secure 쿠키가 붙어 양쪽 다 열린다.
#
# 인증: 기존 /launcher/auth/login 재사용. 쿠키(launcher_session)는 secure 전용이라
# LAN 평문 HTTP(아이패드 1세대는 터널 TLS 가 막힐 수 있어 http://<맥IP>:8765 권장)에선
# 안 붙는다 → 로그인 응답의 session_id 를 localStorage 에 들고 X-Launcher-Session
# 헤더로 보낸다(verify_session 이 쿠키/헤더 둘 다 받는 기존 계약).
#
# ★Python-내-JS 백슬래시 함정 회피: r''' 원시 문자열 (하우스 규약).

LAUNCHER_LITE_HTML = r'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black">
<title>IndieBiz 런처</title>
<style>
  * { -webkit-tap-highlight-color:transparent; }
  html, body { margin:0; padding:0; }
  body { font-family:-apple-system,Helvetica,Arial,sans-serif; background:#111; color:#eee; font-size:16px; }
  .hide { display:none !important; }
  button { background:#2c2c2e; color:#eee; border:1px solid #444; border-radius:8px; padding:9px 13px; font-size:15px; }
  button:active { background:#3a3a3c; }
  button.pri { background:#0a5fbd; border-color:#0a5fbd; color:#fff; }
  input, textarea { -webkit-appearance:none; border:1px solid #444; border-radius:8px; background:#222; color:#eee; font-size:16px; padding:10px; }
  /* 상단 바 — 구식 블록 레이아웃(float 없이 inline-block) */
  .bar { position:fixed; top:0; left:0; right:0; background:#1c1c1e; border-bottom:1px solid #333; padding:7px 8px; z-index:5; }
  .bar button { margin-right:6px; }
  .bar .tab.on { background:#0a5fbd; border-color:#0a5fbd; color:#fff; }
  .bar .right { position:absolute; right:8px; top:7px; }
  .page { padding:58px 0 0; }
  /* 로그인 */
  .login { padding:80px 24px 0; text-align:center; }
  .login input { width:80%; max-width:280px; margin:12px 0; }
  .err { color:#ff6b6b; font-size:14px; min-height:18px; }
  /* 자율주행(채팅) */
  #chatlog { padding:6px 10px 120px; }
  .msg { margin:7px 0; }
  .msg .bub { display:inline-block; max-width:86%; padding:9px 12px; border-radius:14px; white-space:pre-wrap; word-wrap:break-word; text-align:left; line-height:1.5; }
  .msg.user { text-align:right; }
  .msg.user .bub { background:#0a5fbd; color:#fff; }
  .msg.ai .bub { background:#2c2c2e; }
  .msg .who { font-size:11px; color:#888; margin:0 4px 2px; }
  .wait { color:#9a9a9e; font-size:14px; padding:6px 12px; }
  .composer { position:fixed; left:0; right:0; bottom:0; background:#1c1c1e; border-top:1px solid #333; padding:8px; z-index:5; }
  .composer textarea { width:70%; height:44px; vertical-align:bottom; margin:0; }
  .composer button { height:46px; vertical-align:bottom; margin-left:6px; }
  /* 조종실 */
  #cockpit { padding:10px; padding-bottom:80px; }
  #cockpit .lbl { font-size:12px; color:#9a9a9e; margin:14px 2px 5px; }
  #cockpit input.intent { width:96%; }
  #cockpit textarea.code { width:96%; height:74px; font-family:Menlo,monospace; font-size:14px; }
  #cockpit .btns { margin-top:8px; }
  .step { border:1px solid #333; border-radius:8px; padding:8px 10px; margin:6px 0; font-size:14px; }
  .step .co { font-family:Menlo,monospace; font-size:13px; color:#8ec6ff; word-wrap:break-word; }
  .step .ef { color:#ccc; margin-top:3px; }
  .step .warn { color:#ffb454; margin-top:3px; }
  .step .bad { color:#ff6b6b; margin-top:3px; }
  pre.result { background:#1a1a1c; border:1px solid #333; border-radius:8px; padding:10px; font-size:13px; white-space:pre-wrap; word-wrap:break-word; margin:8px 0; max-height:340px; overflow:auto; }
  .item { border-bottom:1px solid #262628; padding:9px 4px; font-size:15px; }
  .item .m { font-size:12px; color:#888; margin-top:2px; }
  /* 창고 (읽기 전용) */
  #wh { padding-bottom:40px; }
  #wh .sub, #wh .lv { padding:8px 8px 4px; }
  #wh .sub button, #wh .lv button { margin-right:6px; }
  #wh .lv button { padding:6px 10px; font-size:14px; }
  #wh .sub .tab.on, #wh .lv .tab.on { background:#0a5fbd; border-color:#0a5fbd; color:#fff; }
  #wh .item { padding:9px 10px; }
  #wh .item a { color:#8ec6ff; text-decoration:none; word-wrap:break-word; }
</style>
</head>
<body>

<div id="login" class="login">
  <h2>IndieBiz 런처</h2>
  <p style="color:#9a9a9e;font-size:13px;">경량판 (구형 기기용)</p>
  <input id="pw" type="password" placeholder="비밀번호" autocomplete="current-password">
  <div><button id="loginBtn" class="pri">로그인</button></div>
  <p class="err" id="lerr"></p>
</div>

<div id="app" class="hide">
  <div class="bar">
    <button id="tabChat" class="tab on">자율주행</button>
    <button id="tabCp" class="tab">조종실</button>
    <button id="tabWh" class="tab">창고</button>
    <span class="right"><button id="refresh">&#8635;</button><button id="logout">나가기</button></span>
  </div>

  <div id="chat" class="page">
    <div id="chatlog"></div>
    <div class="composer">
      <textarea id="cmsg" placeholder="시스템 AI에게 말하기"></textarea><button id="csend" class="pri">보내기</button>
    </div>
  </div>

  <div id="cockpit" class="page hide">
    <div class="lbl">1. 자연어 명령</div>
    <input id="intent" class="intent" type="text" placeholder="예: 오늘 청주 날씨 알려줘">
    <div class="btns"><button id="btnTr" class="pri">IBL로 번역</button></div>
    <div class="lbl">2. IBL 코드 (직접 수정 가능)</div>
    <textarea id="code" class="code"></textarea>
    <div class="btns"><button id="btnVal">검수 (dry-run)</button> <button id="btnRun" class="pri">실행</button></div>
    <div id="steps"></div>
    <div class="lbl" id="resLbl" style="display:none;">결과</div>
    <div id="result"></div>
  </div>

  <div id="wh" class="page hide">
    <div class="sub"><button id="whMine" class="tab on">내 창고</button><button id="whNb" class="tab">이웃</button></div>
    <div id="whBody"></div>
  </div>
</div>

<script>
(function(){
  function $(id){ return document.getElementById(id); }
  function esc(s){ return String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

  var SID = null;
  try { SID = window.localStorage.getItem("launcher_lite_sid"); } catch(e) {}

  // XHR 래퍼 — fetch 없는 초구형 Safari까지. 쿠키는 same-origin 자동 동반,
  // LAN 평문 HTTP(secure 쿠키 불가)는 X-Launcher-Session 헤더가 인증을 진다.
  function api(method, url, body, cb){
    var x = new XMLHttpRequest();
    x.open(method, url, true);
    x.setRequestHeader("Content-Type", "application/json");
    if (SID) x.setRequestHeader("X-Launcher-Session", SID);
    x.onreadystatechange = function(){
      if (x.readyState !== 4) return;
      var d = null;
      try { d = JSON.parse(x.responseText); } catch(e) {}
      cb(x.status, d);
    };
    x.send(body ? JSON.stringify(body) : null);
  }

  // ── 로그인 ─────────────────────────────────────────────
  function showLogin(){ $("login").className = "login"; $("app").className = "hide"; }
  function showApp(){ $("login").className = "login hide"; $("app").className = ""; loadChat(); }

  $("loginBtn").addEventListener("click", doLogin);
  $("pw").addEventListener("keyup", function(e){ if (e.keyCode === 13) doLogin(); });
  function doLogin(){
    $("lerr").textContent = "";
    api("POST", "/launcher/auth/login", { password: $("pw").value }, function(st, d){
      if (st === 200 && d && d.session_id){
        SID = d.session_id;
        try { window.localStorage.setItem("launcher_lite_sid", SID); } catch(e) {}
        showApp();
      } else {
        $("lerr").textContent = (d && d.detail) ? d.detail : "비밀번호가 올바르지 않습니다";
      }
    });
  }
  $("logout").addEventListener("click", function(){
    api("POST", "/launcher/auth/logout", null, function(){});
    SID = null;
    try { window.localStorage.removeItem("launcher_lite_sid"); } catch(e) {}
    window.location.reload();
  });

  // ── 탭 ────────────────────────────────────────────────
  var TAB = "chat";
  $("tabChat").addEventListener("click", function(){ setTab("chat"); });
  $("tabCp").addEventListener("click", function(){ setTab("cp"); });
  $("tabWh").addEventListener("click", function(){ setTab("wh"); });
  function setTab(t){
    TAB = t;
    $("chat").className    = (t === "chat") ? "page" : "page hide";
    $("cockpit").className = (t === "cp")   ? "page" : "page hide";
    $("wh").className      = (t === "wh")   ? "page" : "page hide";
    $("tabChat").className = (t === "chat") ? "tab on" : "tab";
    $("tabCp").className   = (t === "cp")   ? "tab on" : "tab";
    $("tabWh").className   = (t === "wh")   ? "tab on" : "tab";
    if (t === "wh") whEnter();
  }
  $("refresh").addEventListener("click", function(){
    if (TAB === "wh") whRefresh();
    else if (TAB === "chat") loadChat();
  });

  // ── 자율주행 (시스템 AI 대화) ──────────────────────────
  var lastId = 0, pollTimer = null, pollUntil = 0;

  function renderRows(rows, append){
    var log = $("chatlog");
    if (!append) log.innerHTML = "";
    for (var i = 0; i < rows.length; i++){
      var r = rows[i];
      if (r.id && r.id <= lastId) continue;
      if (r.id && r.id > lastId) lastId = r.id;
      if (r.role !== "user" && r.role !== "assistant") continue;
      var div = document.createElement("div");
      div.className = "msg " + (r.role === "user" ? "user" : "ai");
      var who = (r.role === "user" ? "나" : "시스템 AI") + (r.timestamp ? " · " + String(r.timestamp).slice(5, 16) : "");
      div.innerHTML = '<div class="who">' + esc(who) + '</div><div class="bub">' + esc(r.content) + '</div>';
      log.appendChild(div);
    }
    window.scrollTo(0, document.body.scrollHeight);
  }

  function loadChat(){
    api("GET", "/system-ai/conversations?limit=30", null, function(st, d){
      if (st === 401){ showLogin(); return; }
      if (st !== 200 || !d) return;
      lastId = 0;
      renderRows(d.conversations || [], false);
    });
  }

  function setWait(on){
    var w = $("waitline");
    if (on && !w){
      w = document.createElement("div");
      w.id = "waitline"; w.className = "wait";
      w.textContent = "시스템 AI가 생각하는 중…";
      $("chatlog").appendChild(w);
      window.scrollTo(0, document.body.scrollHeight);
    } else if (!on && w){
      w.parentNode.removeChild(w);
    }
  }

  function pollOnce(){
    api("GET", "/system-ai/conversations?limit=10", null, function(st, d){
      if (st !== 200 || !d) return;
      var rows = d.conversations || [], gotAi = false;
      for (var i = 0; i < rows.length; i++){
        if (rows[i].id > lastId && rows[i].role === "assistant") gotAi = true;
      }
      renderRows(rows, true);
      if (gotAi || new Date().getTime() > pollUntil){
        clearInterval(pollTimer); pollTimer = null; setWait(false);
        if (!gotAi) loadChat();
      }
    });
  }

  $("csend").addEventListener("click", sendChat);
  function sendChat(){
    var msg = $("cmsg").value;
    if (!msg || !msg.replace(/\s/g, "").length) return;
    $("cmsg").value = "";
    // 본판 자율주행과 동일: background:true 즉시 반환 → 대화 로그 폴링으로 응답 수신
    api("POST", "/system-ai/chat", { message: msg, background: true }, function(st, d){
      if (st === 401){ showLogin(); return; }
    });
    var div = document.createElement("div");
    div.className = "msg user";
    div.innerHTML = '<div class="who">나</div><div class="bub">' + esc(msg) + '</div>';
    $("chatlog").appendChild(div);
    setWait(true);
    pollUntil = new Date().getTime() + 10 * 60 * 1000;  // 최대 10분 대기
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollOnce, 4000);
  }

  // ── 조종실 (번역 → 검수 → 실행) ────────────────────────
  $("btnTr").addEventListener("click", function(){
    var it = $("intent").value;
    if (!it || !it.replace(/\s/g, "").length) return;
    $("steps").innerHTML = '<div class="wait">번역 중…</div>';
    api("POST", "/ibl/translate", { intent: it }, function(st, d){
      if (st === 401){ showLogin(); return; }
      if (st === 200 && d && d.ibl_code){
        $("code").value = d.ibl_code;
        $("steps").innerHTML = '<div class="wait">번역 완료 — 검수하거나 바로 실행하세요.</div>';
      } else {
        $("steps").innerHTML = '<div class="step"><div class="bad">' + esc((d && d.detail) || "번역 실패") + '</div></div>';
      }
    });
  });

  $("btnVal").addEventListener("click", function(){
    var code = $("code").value;
    if (!code) return;
    $("steps").innerHTML = '<div class="wait">검수 중…</div>';
    api("POST", "/ibl/validate", { code: code }, function(st, d){
      if (st === 401){ showLogin(); return; }
      if (st !== 200 || !d){ $("steps").innerHTML = '<div class="step"><div class="bad">검수 실패</div></div>'; return; }
      if (d.syntax_error){ $("steps").innerHTML = '<div class="step"><div class="bad">문법 오류: ' + esc(d.syntax_error) + '</div></div>'; return; }
      var h = "";
      var steps = d.steps || [];
      for (var i = 0; i < steps.length; i++){
        var s = steps[i];
        var mark = s.valid ? (s.safety === "write" ? "&#9888;" : "&#10003;") : "&#10007;";
        h += '<div class="step"><div class="co">' + mark + ' [' + esc(s.node) + ':' + esc(s.action) + ']</div>';
        h += '<div class="ef">' + esc(s.effect || "") + '</div>';
        if (s.param_warning) h += '<div class="warn">' + esc(s.param_warning) + '</div>';
        if (s.error) h += '<div class="bad">' + esc(s.error) + '</div>';
        h += '</div>';
      }
      if (d.has_side_effect) h += '<div class="step"><div class="warn">&#9888; 부작용(쓰기) 단계가 있습니다 — 실행 전 확인하세요.</div></div>';
      $("steps").innerHTML = h || '<div class="wait">단계 없음</div>';
    });
  });

  $("btnRun").addEventListener("click", function(){
    var code = $("code").value;
    if (!code) return;
    $("resLbl").style.display = "";
    $("result").innerHTML = '<div class="wait">실행 중…</div>';
    // 본판 조종실과 동일 계약: project_id='수동모드', surface='web'
    api("POST", "/ibl/execute", { code: code, project_id: "수동모드", project_path: ".", surface: "web" }, function(st, d){
      if (st === 401){ showLogin(); return; }
      if (st !== 200){
        $("result").innerHTML = '<pre class="result">' + esc((d && d.detail) || ("실행 실패 (" + st + ")")) + '</pre>';
        return;
      }
      // 단일 통화 items 는 목록으로, 그 외는 JSON 원문으로
      if (d && d.items && d.items.length){
        var h = "";
        for (var i = 0; i < d.items.length && i < 50; i++){
          var it = d.items[i];
          var title = it.title || it.name || it.summary || "";
          if (!title){ try { title = JSON.stringify(it).slice(0, 120); } catch(e) { title = "(항목)"; } }
          h += '<div class="item">' + esc(title);
          var meta = it.meta || it.desc || it.description || "";
          if (meta) h += '<div class="m">' + esc(String(meta).slice(0, 200)) + '</div>';
          h += '</div>';
        }
        if (d.items.length > 50) h += '<div class="wait">외 ' + (d.items.length - 50) + '건</div>';
        $("result").innerHTML = h;
      } else {
        var txt = "";
        try { txt = JSON.stringify(d, null, 2); } catch(e) { txt = String(d); }
        if (txt.length > 8000) txt = txt.slice(0, 8000) + "\n…(잘림)";
        $("result").innerHTML = '<pre class="result">' + esc(txt) + '</pre>';
      }
    });
  });

  // ── 창고 (읽기 전용) ──────────────────────────────────
  // 내 창고 = /portal/warehouse-admin/list?level=N, 이웃 = /warehouse-feed/feed.
  // 쓰기(업로드·리트윗·좋아요·이웃 편집)는 본판 몫 — 여기는 보기만 한다.
  var WH_SUB = "mine", WH_LV = 0, WH_LOADED = false;

  function whBytes(n){
    if (n == null) return "";
    if (n < 1024) return n + "B";
    if (n < 1048576) return (n / 1024).toFixed(1) + "KB";
    if (n < 1073741824) return (n / 1048576).toFixed(1) + "MB";
    return (n / 1073741824).toFixed(2) + "GB";
  }
  function whWhen(t){ return t ? String(t).replace("T", " ").slice(0, 16) : ""; }
  function whMsg(m){ $("whBody").innerHTML = '<div class="wait">' + esc(m) + '</div>'; }

  $("whMine").addEventListener("click", function(){ whSub("mine"); });
  $("whNb").addEventListener("click", function(){ whSub("nb"); });
  function whSub(t){
    WH_SUB = t;
    $("whMine").className = (t === "mine") ? "tab on" : "tab";
    $("whNb").className   = (t === "nb")   ? "tab on" : "tab";
    whRefresh();
  }
  function whEnter(){ if (!WH_LOADED){ WH_LOADED = true; whRefresh(); } }
  function whRefresh(){ if (WH_SUB === "mine") whLoadMine(); else whLoadFeed(); }

  // 내 창고 — 레벨 0~4 칩 + 파일 목록(최근 수정순). 클릭 = 소유자 열람 URL 로 새 창.
  function whLoadMine(){
    whMsg("불러오는 중…");
    api("GET", "/portal/warehouse-admin/list?level=" + WH_LV, null, function(st, d){
      if (st === 401){ showLogin(); return; }
      if (st !== 200 || !d){ whMsg("불러오기 실패 (" + st + ")"); return; }
      // ★응답 키는 counts 가 아니라 levels/level_labels 다 (2026-08-02 실측)
      var lv = d.levels || {}, lab = d.level_labels || {}, h = "", l, c, nm;
      if (d.title) h += '<div class="lv" style="color:#9a9a9e;font-size:13px;">' + esc(d.title) + '</div>';
      h += '<div class="lv">';
      for (l = 0; l <= 4; l++){
        c = (lv[String(l)] == null) ? 0 : lv[String(l)];
        nm = lab[String(l)] || String(l);
        h += '<button class="tab' + (l === WH_LV ? " on" : "") + '" data-lv="' + l + '">'
           + esc(nm) + ' <span style="color:#9a9a9e">' + c + '</span></button>';
      }
      h += '</div>';
      var files = d.files || [], i, f, href, cap = 300;
      if (!files.length){
        h += '<div class="wait">이 레벨 창고는 비어 있습니다.</div>';
      } else {
        for (i = 0; i < files.length && i < cap; i++){
          f = files[i];
          // .url 리트윗 포인터는 목적지로, 일반 파일은 소유자 열람 엔드포인트로
          href = f.link ? f.link
               : ("/portal/warehouse-admin/file?level=" + WH_LV + "&name=" + encodeURIComponent(f.name));
          h += '<div class="item"><a href="' + esc(href) + '" target="_blank">' + esc(f.name) + '</a>'
             + '<div class="m">' + esc(whWhen(f.mtime))
             + (f.bytes == null ? "" : " · " + whBytes(f.bytes))
             + (f.link ? " · 리트윗" : "") + '</div></div>';
        }
        if (files.length > cap) h += '<div class="wait">외 ' + (files.length - cap) + '건 (본판에서 보세요)</div>';
      }
      $("whBody").innerHTML = h;
      var btns = $("whBody").getElementsByTagName("button"), k;
      for (k = 0; k < btns.length; k++){
        btns[k].onclick = function(){
          WH_LV = parseInt(this.getAttribute("data-lv"), 10) || 0;
          whLoadMine();
        };
      }
    });
  }

  // 이웃 — 창고 폴러가 쌓은 변화 타임라인(seed/new/changed). 클릭 = 그 파일·글로 새 창.
  function whLoadFeed(){
    whMsg("불러오는 중…");
    api("GET", "/warehouse-feed/feed?limit=60", null, function(st, d){
      if (st === 401){ showLogin(); return; }
      if (st !== 200 || !d){ whMsg("불러오기 실패 (" + st + ")"); return; }
      var items = d.items || [];
      if (!items.length){ whMsg("아직 이웃 창고 소식이 없습니다."); return; }
      var h = "", i, it, who, kind, href, title;
      for (i = 0; i < items.length; i++){
        it = items[i];
        who = it.neighbor_title || it.neighbor_name || it.wh_url || "";
        kind = (it.kind === "new") ? "새 파일" : ((it.kind === "changed") ? "바뀜" : "기존");
        href = it.url || it.neighbor_home || "";
        title = it.path || "(제목 없음)";
        h += '<div class="item">'
           + (href ? ('<a href="' + esc(href) + '" target="_blank">' + esc(title) + '</a>') : esc(title))
           + '<div class="m">' + esc(who) + ' · ' + kind
           + (it.mtime ? " · " + esc(whWhen(it.mtime)) : "") + '</div></div>';
      }
      $("whBody").innerHTML = h;
    });
  }

  // ── 부팅: 기존 세션(쿠키 또는 저장된 SID)이 살아 있으면 바로 앱 ──
  api("GET", "/system-ai/conversations?limit=1", null, function(st){
    if (st === 200) showApp(); else showLogin();
  });
})();
</script>
</body>
</html>'''
