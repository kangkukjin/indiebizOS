"""
api_nas.py - 원격 Finder (NAS) API
IndieBiz OS - Remote File Access System

외부에서 Cloudflare Tunnel을 통해 파일에 접근할 수 있는 API
"""

import os
import sys
import platform
import stat as stat_module
import json
import hashlib
import secrets
import mimetypes
import subprocess
import shutil
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List
from functools import wraps

from fastapi import APIRouter, HTTPException, Request, Response, Query
from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse
from pydantic import BaseModel

from runtime_utils import get_data_path as _get_data_path
from nas_subtitle import (
    detect_subtitles, srt_to_vtt, ass_to_vtt, smi_to_vtt,
    SUBTITLE_EXTENSIONS, LANG_NAMES, api_get_subtitles, api_get_subtitle_file,
)
from nas_music import api_music_search, api_music_stream
from nas_webapp import get_default_webapp_html

router = APIRouter(prefix="/nas", tags=["nas"])

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

# ============ 설정 ============

DATA_PATH = _get_data_path()
NAS_CONFIG_PATH = DATA_PATH / "nas_config.json"

# 스트리밍 청크 크기 (64KB - 8KB에서 8배 증가, Cloudflare Tunnel 호환성 유지)
STREAM_CHUNK_SIZE = 64 * 1024

# 기본 설정
DEFAULT_CONFIG = {
    "enabled": False,
    "password_hash": None,  # SHA256 해시
    "allowed_paths": [],  # 허용된 경로 목록 (비어있으면 홈 디렉토리)
    "session_timeout_hours": 24,
    "created_at": None,
}

# 세션 저장소 (메모리)
sessions = {}

# 설정 캐시 (디스크 I/O 감소)
_config_cache = None
_config_cache_mtime = 0

# ============ 트랜스코딩 설정 ============

from common.platform_utils import find_binary  # 전 OS 바이너리 탐색 (윈도우 .exe·표준 경로 폴백)
FFMPEG_PATH = find_binary("ffmpeg") or "ffmpeg"
FFPROBE_PATH = find_binary("ffprobe") or "ffprobe"

# 프로브 결과 캐시: {(file_path, mtime): probe_result}
_probe_cache: dict = {}
_PROBE_CACHE_MAX = 200

# 활성 트랜스코딩 프로세스 추적
_active_transcodes: dict = {}

# 플랫폼별 H.264 인코더 자동 감지 (한 번만 실행)
_hw_encoder: str | None = None

def _detect_h264_encoder() -> str:
    """사용 가능한 H.264 인코더를 감지하여 반환. HW 가속 우선, 실패 시 libx264 폴백."""
    global _hw_encoder
    if _hw_encoder is not None:
        return _hw_encoder

    # 플랫폼별 HW 인코더 후보 (우선순위 순)
    candidates = []
    if sys.platform == "darwin":
        candidates = ["h264_videotoolbox"]
    elif sys.platform == "win32":
        candidates = ["h264_nvenc", "h264_qsv", "h264_amf"]
    else:  # Linux
        candidates = ["h264_nvenc", "h264_vaapi", "h264_qsv"]

    for enc in candidates:
        try:
            r = subprocess.run(
                [FFMPEG_PATH, "-hide_banner", "-f", "lavfi", "-i", "nullsrc=s=64x64:d=0.1",
                 "-c:v", enc, "-f", "null", "-"],
                capture_output=True, timeout=10
            )
            if r.returncode == 0:
                _hw_encoder = enc
                return _hw_encoder
        except Exception:
            continue

    # 모든 HW 인코더 실패 → 소프트웨어 폴백
    _hw_encoder = "libx264"
    return _hw_encoder

# 브라우저 호환 코덱/컨테이너
BROWSER_COMPATIBLE_VIDEO = {"h264", "av1", "vp8", "vp9"}
BROWSER_COMPATIBLE_AUDIO = {"aac", "mp3", "opus", "vorbis", "flac"}
BROWSER_COMPATIBLE_CONTAINERS = {"mp4", "webm", "ogg", "mov"}


# ============ 유틸리티 ============

def load_config() -> dict:
    """NAS 설정 로드 (mtime 기반 캐시 — 파일 변경 시에만 디스크 읽기)"""
    global _config_cache, _config_cache_mtime
    if NAS_CONFIG_PATH.exists():
        current_mtime = NAS_CONFIG_PATH.stat().st_mtime
        if _config_cache is not None and current_mtime == _config_cache_mtime:
            return _config_cache
        with open(NAS_CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
            merged = {**DEFAULT_CONFIG, **config}
            _config_cache = merged
            _config_cache_mtime = current_mtime
            return merged
    return DEFAULT_CONFIG.copy()


def save_config(config: dict):
    """NAS 설정 저장 (캐시 무효화 포함)"""
    global _config_cache, _config_cache_mtime
    config['updated_at'] = datetime.now().isoformat()
    with open(NAS_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    # 저장 후 캐시 즉시 갱신
    _config_cache = {**DEFAULT_CONFIG, **config}
    _config_cache_mtime = NAS_CONFIG_PATH.stat().st_mtime


def hash_password(password: str) -> str:
    """비밀번호 SHA256 해시"""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_session(session_token: str) -> bool:
    """세션 유효성 검증"""
    if session_token not in sessions:
        return False

    session = sessions[session_token]
    if datetime.now() > session['expires_at']:
        del sessions[session_token]
        return False

    return True


def _remote_unauthenticated(request: Request) -> bool:
    """터널을 통해 들어온 원격 요청인데 NAS 세션이 없으면 True(차단 대상).

    /config·/status 는 데스크탑(localhost)이 NAS 로그인 없이 호출하므로
    무조건 막을 수 없다. 외부(터널) 요청에 대해서만 세션을 강제한다.
    """
    try:
        from api_launcher_web import is_external_request
        if is_external_request(request):
            token = request.cookies.get('nas_session') or request.headers.get('X-NAS-Session')
            if not token or not verify_session(token):
                return True
    except Exception:
        pass
    return False


def get_safe_path(base_paths: List[str], requested_path: str) -> Optional[Path]:
    """
    경로 조작 공격 방지
    요청된 경로가 허용된 기본 경로 내에 있는지 확인
    """
    if not base_paths:
        # 기본값: 홈 디렉토리
        base_paths = [os.path.expanduser("~")]

    # 요청 경로 정규화
    if not requested_path or requested_path in ("/", ""):
        # 첫 번째 허용 경로 반환
        return Path(base_paths[0])

    # 절대 경로로 변환 (Windows: C:\... / D:\... , Unix: /...)
    req_path = Path(requested_path)
    if req_path.is_absolute():
        target = req_path
    else:
        target = Path(base_paths[0]) / requested_path

    # realpath로 심볼릭 링크 해석
    try:
        real_target = target.resolve()
    except (OSError, ValueError):
        return None

    # 허용된 경로 내에 있는지 확인
    for base in base_paths:
        try:
            real_base = Path(base).resolve()
            if str(real_target).startswith(str(real_base)):
                return real_target
        except (OSError, ValueError):
            continue

    return None


def get_file_info(path: Path) -> dict:
    """파일/폴더 정보 반환 (stat 1회만 호출)"""
    st = path.stat()
    is_dir = stat_module.S_ISDIR(st.st_mode)

    info = {
        "name": path.name,
        "path": str(path),
        "is_dir": is_dir,
        "size": st.st_size if not is_dir else None,
        "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
        "created": datetime.fromtimestamp(st.st_ctime).isoformat(),
    }

    if not is_dir:
        # 파일 타입 추정
        mime_type, _ = mimetypes.guess_type(path.name)
        info["mime_type"] = mime_type

        # 파일 카테고리
        if mime_type:
            if mime_type.startswith("video/"):
                info["category"] = "video"
            elif mime_type.startswith("audio/"):
                info["category"] = "audio"
            elif mime_type.startswith("image/"):
                info["category"] = "image"
            elif mime_type.startswith("text/") or mime_type in ["application/json", "application/xml"]:
                info["category"] = "text"
            elif mime_type == "application/pdf":
                info["category"] = "pdf"
            else:
                info["category"] = "other"
        else:
            info["category"] = "other"

    return info


def format_size(size: int) -> str:
    """파일 크기를 읽기 쉬운 형태로 변환"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def probe_video(file_path: Path) -> dict:
    """ffprobe로 동영상 코덱/컨테이너/내장자막 분석 (mtime 기반 캐시)"""
    path_str = str(file_path)
    mtime = file_path.stat().st_mtime
    cache_key = (path_str, mtime)

    if cache_key in _probe_cache:
        return _probe_cache[cache_key]

    try:
        result = subprocess.run(
            [FFPROBE_PATH, "-v", "quiet", "-print_format", "json",
             "-show_streams", "-show_format", path_str],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return {"error": "ffprobe failed", "needs_transcode": True}
        info = json.loads(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        return {"error": str(e), "needs_transcode": True}

    streams = info.get("streams", [])
    fmt = info.get("format", {})

    video_codec = None
    audio_codec = None
    subtitle_tracks = []
    duration = float(fmt.get("duration", 0))

    for s in streams:
        codec_type = s.get("codec_type")
        codec_name = s.get("codec_name", "").lower()
        if codec_type == "video" and video_codec is None:
            video_codec = codec_name
        elif codec_type == "audio" and audio_codec is None:
            audio_codec = codec_name
        elif codec_type == "subtitle":
            track_index = len(subtitle_tracks)
            lang = s.get("tags", {}).get("language", "")
            title = s.get("tags", {}).get("title", "")
            subtitle_tracks.append({
                "index": track_index,
                "codec": codec_name,
                "language": lang,
                "title": title or LANG_NAMES.get(lang, lang) or f"Track {track_index}",
            })

    container = file_path.suffix.lower().lstrip(".")

    video_ok = video_codec in BROWSER_COMPATIBLE_VIDEO
    audio_ok = audio_codec in BROWSER_COMPATIBLE_AUDIO or audio_codec is None
    container_ok = container in BROWSER_COMPATIBLE_CONTAINERS
    needs_transcode = not (video_ok and audio_ok and container_ok)

    probe_result = {
        "video_codec": video_codec,
        "audio_codec": audio_codec,
        "container": container,
        "duration": duration,
        "needs_transcode": needs_transcode,
        "video_compatible": video_ok,
        "audio_compatible": audio_ok,
        "container_compatible": container_ok,
        "subtitle_tracks": subtitle_tracks,
    }

    # 캐시 저장 (최대치 초과 시 절반 삭제)
    if len(_probe_cache) >= _PROBE_CACHE_MAX:
        keys = list(_probe_cache.keys())
        for k in keys[:len(keys) // 2]:
            del _probe_cache[k]
    _probe_cache[cache_key] = probe_result

    return probe_result


def _kill_transcode(process: subprocess.Popen):
    """트랜스코딩 FFmpeg 프로세스를 안전하게 종료"""
    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
    except Exception:
        pass


# ============ 인증 데코레이터 ============

def require_auth(func):
    """인증 필요 데코레이터"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        request: Request = kwargs.get('request') or args[0]

        # 설정 확인
        config = load_config()
        if not config.get('enabled'):
            raise HTTPException(status_code=503, detail="NAS 서비스가 비활성화되어 있습니다")

        # 세션 토큰 확인
        session_token = request.cookies.get('nas_session') or request.headers.get('X-NAS-Session')

        if not session_token or not verify_session(session_token):
            raise HTTPException(status_code=401, detail="인증이 필요합니다")

        return await func(*args, **kwargs)

    return wrapper


# ============ 설정 API ============

class NASConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    password: Optional[str] = None  # 새 비밀번호 설정 시
    allowed_paths: Optional[List[str]] = None


@router.get("/config")
async def get_nas_config(request: Request):
    """NAS 설정 조회 (비밀번호 제외)"""
    if _remote_unauthenticated(request):
        raise HTTPException(status_code=401, detail="인증이 필요합니다")
    config = load_config()
    return {
        "enabled": config.get("enabled", False),
        "has_password": config.get("password_hash") is not None,
        "allowed_paths": config.get("allowed_paths", []),
        "session_timeout_hours": config.get("session_timeout_hours", 24),
    }


@router.put("/config")
async def update_nas_config(update: NASConfigUpdate, request: Request):
    """NAS 설정 업데이트"""
    # 원격(터널)에서 무인증으로 비밀번호·허용경로를 덮어쓰지 못하게 차단.
    # (데스크탑 localhost는 통과 — 최초 설정은 로컬에서 이뤄진다)
    if _remote_unauthenticated(request):
        raise HTTPException(status_code=401, detail="인증이 필요합니다")
    config = load_config()

    if update.enabled is not None:
        config["enabled"] = update.enabled

    if update.password is not None:
        if len(update.password) < 4:
            raise HTTPException(status_code=400, detail="비밀번호는 4자 이상이어야 합니다")
        config["password_hash"] = hash_password(update.password)

    if update.allowed_paths is not None:
        # 경로 유효성 검증
        valid_paths = []
        for p in update.allowed_paths:
            path = Path(p).expanduser()
            if path.exists() and path.is_dir():
                valid_paths.append(str(path.resolve()))
        config["allowed_paths"] = valid_paths

    if config.get("created_at") is None:
        config["created_at"] = datetime.now().isoformat()

    save_config(config)

    return {"status": "success", "message": "설정이 업데이트되었습니다"}


# ============ 인증 API ============

class LoginRequest(BaseModel):
    password: str


@router.post("/auth/login")
async def nas_login(request: Request, login: LoginRequest, response: Response):
    """NAS 로그인"""
    config = load_config()

    if not config.get("enabled"):
        raise HTTPException(status_code=503, detail="NAS 서비스가 비활성화되어 있습니다")

    if not config.get("password_hash"):
        raise HTTPException(status_code=400, detail="비밀번호가 설정되지 않았습니다")

    # 비밀번호 확인
    if hash_password(login.password) != config["password_hash"]:
        raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다")

    # 세션 생성
    session_token = secrets.token_urlsafe(32)
    timeout_hours = config.get("session_timeout_hours", 24)

    sessions[session_token] = {
        "created_at": datetime.now(),
        "expires_at": datetime.now() + timedelta(hours=timeout_hours),
        "ip": request.client.host if request.client else "unknown",
    }

    # 쿠키 설정
    # ★secure 는 조건부다: 파인더는 런처와 달리 로컬(http://localhost:8765/nas/app)에서도
    # 쓰이므로 무조건 secure=True 면 로컬 로그인이 깨진다. HTTPS 로 들어온 요청(터널·funnel
    # 경유 = 원격)일 때만 붙여, 공개망 구간에서 세션이 평문으로 새지 않게 한다.
    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    is_https = forwarded_proto == "https" or request.url.scheme == "https"
    response.set_cookie(
        key="nas_session",
        value=session_token,
        max_age=timeout_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=is_https,
    )

    return {"status": "success", "message": "로그인 성공", "session_token": session_token}


@router.post("/auth/logout")
async def nas_logout(request: Request, response: Response):
    """NAS 로그아웃"""
    session_token = request.cookies.get('nas_session')

    if session_token and session_token in sessions:
        del sessions[session_token]

    response.delete_cookie("nas_session")

    return {"status": "success", "message": "로그아웃되었습니다"}


@router.get("/auth/check")
async def check_auth(request: Request):
    """인증 상태 확인"""
    config = load_config()

    if not config.get("enabled"):
        return {"authenticated": False, "enabled": False}

    session_token = request.cookies.get('nas_session') or request.headers.get('X-NAS-Session')
    authenticated = session_token and verify_session(session_token)

    return {"authenticated": authenticated, "enabled": True}


# ============ 파일 API ============

@router.get("/files")
async def list_files(
    request: Request,
    path: str = Query(default="", description="디렉토리 경로"),
    show_hidden: bool = Query(default=False, description="숨김 파일 표시"),
):
    """파일 목록 조회"""
    # 인증 확인
    config = load_config()
    if not config.get("enabled"):
        raise HTTPException(status_code=503, detail="NAS 서비스가 비활성화되어 있습니다")

    session_token = request.cookies.get('nas_session') or request.headers.get('X-NAS-Session')
    if not session_token or not verify_session(session_token):
        raise HTTPException(status_code=401, detail="인증이 필요합니다")

    # 경로 검증
    allowed_paths = config.get("allowed_paths", [])
    safe_path = get_safe_path(allowed_paths, path)

    if not safe_path or not safe_path.exists():
        raise HTTPException(status_code=404, detail="경로를 찾을 수 없습니다")

    if not safe_path.is_dir():
        raise HTTPException(status_code=400, detail="디렉토리가 아닙니다")

    # 파일 목록 생성
    items = []
    try:
        for item in safe_path.iterdir():
            # 숨김 파일 필터링
            if not show_hidden and item.name.startswith('.'):
                continue

            try:
                items.append(get_file_info(item))
            except (PermissionError, OSError):
                # 접근 불가 파일 무시
                continue
    except PermissionError:
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다")

    # 정렬: 폴더 먼저, 그 다음 이름순
    items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))

    # 상위 경로 계산
    parent_path = None
    for base in (allowed_paths or [os.path.expanduser("~")]):
        base_resolved = Path(base).resolve()
        if safe_path != base_resolved and str(safe_path).startswith(str(base_resolved)):
            parent_path = str(safe_path.parent)
            break

    return {
        "path": str(safe_path),
        "parent": parent_path,
        "items": items,
        "total": len(items),
    }


@router.get("/file")
async def get_file(
    request: Request,
    path: str = Query(..., description="파일 경로"),
):
    """파일 다운로드/스트리밍"""
    # 인증 확인
    config = load_config()
    if not config.get("enabled"):
        raise HTTPException(status_code=503, detail="NAS 서비스가 비활성화되어 있습니다")

    session_token = request.cookies.get('nas_session') or request.headers.get('X-NAS-Session')
    if not session_token or not verify_session(session_token):
        raise HTTPException(status_code=401, detail="인증이 필요합니다")

    # 경로 검증
    allowed_paths = config.get("allowed_paths", [])
    safe_path = get_safe_path(allowed_paths, path)

    if not safe_path or not safe_path.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    if safe_path.is_dir():
        raise HTTPException(status_code=400, detail="디렉토리는 다운로드할 수 없습니다")

    # MIME 타입 결정
    mime_type, _ = mimetypes.guess_type(safe_path.name)
    if not mime_type:
        mime_type = "application/octet-stream"

    # 텍스트 파일은 감지된 charset 을 Content-Type 에 명시 — 구형 iOS Safari(lite2 대상)는
    # 다운로드/공유시트가 없어 브라우저 인라인 보기가 최선인데, charset 이 없으면 cp949/euc-kr
    # 한글이 utf-8 로 렌더돼 글자가 다 깨졌다. 인코딩만 맞추면 어떤 한글 텍스트도 읽힌다.
    if mime_type.startswith("text/") and safe_path.stat().st_size <= 10 * 1024 * 1024:
        for enc in ("utf-8", "utf-8-sig", "cp949", "euc-kr"):
            try:
                safe_path.read_text(encoding=enc)
                mime_type = f"text/plain; charset={'utf-8' if enc == 'utf-8-sig' else enc}"
                break
            except (UnicodeDecodeError, LookupError):
                continue

    # Range 요청 처리 (동영상 스트리밍용)
    range_header = request.headers.get("range")
    file_size = safe_path.stat().st_size

    if range_header:
        # Range 헤더 파싱
        range_match = range_header.replace("bytes=", "").split("-")
        start = int(range_match[0]) if range_match[0] else 0
        end = int(range_match[1]) if range_match[1] else file_size - 1

        if start >= file_size:
            raise HTTPException(status_code=416, detail="Range Not Satisfiable")

        end = min(end, file_size - 1)
        content_length = end - start + 1

        def iter_file():
            with open(safe_path, "rb") as f:
                f.seek(start)
                remaining = content_length
                while remaining > 0:
                    chunk_size = min(STREAM_CHUNK_SIZE, remaining)
                    data = f.read(chunk_size)
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        return StreamingResponse(
            iter_file(),
            status_code=206,
            media_type=mime_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
            },
        )

    # 전체 파일 반환
    return FileResponse(
        safe_path,
        media_type=mime_type,
        filename=safe_path.name,
        headers={"Accept-Ranges": "bytes"},
    )


@router.get("/text")
async def get_text_file(
    request: Request,
    path: str = Query(..., description="파일 경로"),
    encoding: str = Query(default="utf-8", description="인코딩"),
):
    """텍스트 파일 내용 조회"""
    # 인증 확인
    config = load_config()
    if not config.get("enabled"):
        raise HTTPException(status_code=503, detail="NAS 서비스가 비활성화되어 있습니다")

    session_token = request.cookies.get('nas_session') or request.headers.get('X-NAS-Session')
    if not session_token or not verify_session(session_token):
        raise HTTPException(status_code=401, detail="인증이 필요합니다")

    # 경로 검증
    allowed_paths = config.get("allowed_paths", [])
    safe_path = get_safe_path(allowed_paths, path)

    if not safe_path or not safe_path.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    if safe_path.is_dir():
        raise HTTPException(status_code=400, detail="디렉토리입니다")

    # 파일 크기 제한 (10MB)
    if safe_path.stat().st_size > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="파일이 너무 큽니다 (최대 10MB)")

    # 인코딩 폴백 — utf-8만 시도하던 게 한글 파일(cp949/euc-kr)·BOM·기타에서 깨졌다.
    # 호출자가 encoding을 명시하면 그것만, 기본이면 흔한 인코딩을 차례로 시도.
    candidates = [encoding] if encoding != "utf-8" else ["utf-8", "utf-8-sig", "cp949", "euc-kr", "latin-1"]
    for enc in candidates:
        try:
            content = safe_path.read_text(encoding=enc)
            return {"path": str(safe_path), "content": content, "size": len(content), "encoding": enc}
        except (UnicodeDecodeError, LookupError):
            continue
    raise HTTPException(status_code=400, detail="텍스트 인코딩을 인식할 수 없습니다(utf-8/cp949/euc-kr 등 모두 실패)")


@router.get("/epub")
async def get_epub_file(request: Request, path: str = Query(..., description="EPUB 파일 경로")):
    """EPUB → 읽기용 HTML. 구형 Safari(iOS 10)가 epub.js 없이 텍스트로 읽도록
    스파인(읽기 순서)대로 각 XHTML 의 <body> 본문만 추출해 이어 붙인다(stdlib only)."""
    config = load_config()
    if not config.get("enabled"):
        raise HTTPException(status_code=503, detail="NAS 서비스가 비활성화되어 있습니다")
    session_token = request.cookies.get('nas_session') or request.headers.get('X-NAS-Session')
    if not session_token or not verify_session(session_token):
        raise HTTPException(status_code=401, detail="인증이 필요합니다")
    allowed_paths = config.get("allowed_paths", [])
    safe_path = get_safe_path(allowed_paths, path)
    if not safe_path or not safe_path.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    if safe_path.is_dir():
        raise HTTPException(status_code=400, detail="디렉토리입니다")
    try:
        import zipfile, posixpath
        import re as _re
        from urllib.parse import unquote as _unquote
        with zipfile.ZipFile(str(safe_path)) as z:
            # 1) container.xml → OPF 경로
            opf_path = None
            try:
                cont = z.read("META-INF/container.xml").decode("utf-8", "ignore")
                m = _re.search(r'full-path="([^"]+)"', cont)
                if m:
                    opf_path = m.group(1)
            except Exception:
                pass
            if not opf_path:
                for n in z.namelist():
                    if n.lower().endswith(".opf"):
                        opf_path = n
                        break
            if not opf_path:
                raise HTTPException(status_code=400, detail="EPUB 구조를 읽을 수 없습니다 (OPF 없음)")
            opf_dir = posixpath.dirname(opf_path)
            opf = z.read(opf_path).decode("utf-8", "ignore")
            # 2) manifest: id→href (속성 순서 무관)
            manifest = {}
            for tag in _re.findall(r'<item\b[^>]*>', opf):
                idm = _re.search(r'\bid="([^"]+)"', tag)
                hm = _re.search(r'\bhref="([^"]+)"', tag)
                if idm and hm:
                    manifest[idm.group(1)] = _unquote(hm.group(1))
            # 3) spine 순서
            spine = _re.findall(r'<itemref\b[^>]*\bidref="([^"]+)"', opf)
            tm = _re.search(r'<dc:title[^>]*>([^<]+)</dc:title>', opf)
            title = tm.group(1).strip() if tm else safe_path.name
            parts, total = [], 0
            for sid in spine:
                href = manifest.get(sid)
                if not href:
                    continue
                full = posixpath.normpath(posixpath.join(opf_dir, href)) if opf_dir else href
                try:
                    raw = z.read(full).decode("utf-8", "ignore")
                except Exception:
                    continue
                bm = _re.search(r'(?is)<body[^>]*>(.*?)</body>', raw)
                body = bm.group(1) if bm else raw
                body = _re.sub(r'(?is)<script.*?</script>', '', body)
                body = _re.sub(r'(?is)<style.*?</style>', '', body)
                body = _re.sub(r'(?is)<img[^>]*>', '', body)  # zip 내부 이미지라 안 뜸 → 제거
                parts.append(body)
                total += len(body)
                if total > 8 * 1024 * 1024:  # 8MB 상한(읽기용)
                    break
            return {"path": str(safe_path), "title": title,
                    "html": "\n<hr/>\n".join(parts), "chapters": len(parts)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"EPUB 파싱 실패: {str(e)}")


@router.get("/lite", response_class=HTMLResponse)
async def serve_nas_lite(request: Request):
    """구형 기기(iOS 10.3 Safari 등) 호환 경량 Finder — 텍스트/EPUB/PDF/이미지 읽기.
    최신 런처가 못 뜨는 낡은 WebKit 용. /nas API(files/text/epub/file)를 ES6 이하로 호출."""
    return HTMLResponse(content=_NAS_LITE_HTML)


@router.get("/lite2", response_class=HTMLResponse)
async def serve_nas_lite2(request: Request):
    """초-구형 기기(iOS 5.1.1 아이패드 1세대 등) 호환 — 순수 ES5 + XMLHttpRequest.
    fetch/Promise/현대 flex 안 씀. 같은 /nas API 사용. 터널 HTTPS는 그 기기의 TLS/인증서
    한계로 막힐 수 있어 LAN 평문 HTTP(http://<맥IP>:8765/nas/lite2) 사용을 권장."""
    return HTMLResponse(content=_NAS_LITE2_HTML)


# ============ 자막 API (nas_subtitle.py에서 로직 처리) ============

@router.get("/subtitles")
async def get_subtitles(
    request: Request,
    path: str = Query(..., description="동영상 파일 경로"),
):
    """동영상에 연결된 자막 파일 목록 반환"""
    return await api_get_subtitles(request, path, load_config, verify_session, get_safe_path)


@router.get("/subtitle")
async def get_subtitle_file(
    request: Request,
    path: str = Query(..., description="자막 파일 경로"),
    smi_class: str = Query(default="KRCC", description="SMI 언어 클래스"),
):
    """자막 파일을 WebVTT 형식으로 반환"""
    return await api_get_subtitle_file(request, path, smi_class, load_config, verify_session, get_safe_path)


# ============ 트랜스코딩 API ============

@router.get("/probe")
async def probe_file(
    request: Request,
    path: str = Query(..., description="동영상 파일 경로"),
):
    """동영상 코덱/컨테이너 분석 (트랜스코딩 필요 여부 판단)"""
    config = load_config()
    if not config.get("enabled"):
        raise HTTPException(status_code=503, detail="NAS 서비스가 비활성화되어 있습니다")

    session_token = request.cookies.get('nas_session') or request.headers.get('X-NAS-Session')
    if not session_token or not verify_session(session_token):
        raise HTTPException(status_code=401, detail="인증이 필요합니다")

    allowed_paths = config.get("allowed_paths", [])
    safe_path = get_safe_path(allowed_paths, path)

    if not safe_path or not safe_path.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    result = probe_video(safe_path)
    result["path"] = str(safe_path)
    return result


@router.get("/transcode")
async def transcode_video(
    request: Request,
    path: str = Query(..., description="동영상 파일 경로"),
    start: float = Query(default=0, description="시작 시간 (초)"),
):
    """동영상 실시간 트랜스코딩 (H.264+AAC fMP4 스트림)"""
    config = load_config()
    if not config.get("enabled"):
        raise HTTPException(status_code=503, detail="NAS 서비스가 비활성화되어 있습니다")

    session_token = request.cookies.get('nas_session') or request.headers.get('X-NAS-Session')
    if not session_token or not verify_session(session_token):
        raise HTTPException(status_code=401, detail="인증이 필요합니다")

    allowed_paths = config.get("allowed_paths", [])
    safe_path = get_safe_path(allowed_paths, path)

    if not safe_path or not safe_path.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    # 코덱 분석 → 스트림별로 copy 가능 여부 판단
    probe = probe_video(safe_path)
    v_ok = probe.get("video_compatible")
    a_ok = probe.get("audio_compatible")

    if v_ok:
        video_codec_args = ["-c:v", "copy"]
    else:
        encoder = _detect_h264_encoder()
        video_codec_args = ["-c:v", encoder, "-b:v", "4M"]
        # libx264는 preset 설정으로 속도/품질 균형
        if encoder == "libx264":
            video_codec_args.extend(["-preset", "fast"])

    if a_ok:
        audio_codec_args = ["-c:a", "copy"]
    else:
        audio_codec_args = ["-c:a", "aac", "-b:a", "128k", "-ac", "2"]

    # FFmpeg 명령 구성
    cmd = [FFMPEG_PATH]
    if start > 0:
        cmd.extend(["-ss", str(start)])
    cmd.extend([
        "-i", str(safe_path),
        *video_codec_args,
        *audio_codec_args,
        "-f", "mp4",
        "-movflags", "frag_keyframe+empty_moov+default_base_moof",
        "-v", "quiet",
        "pipe:1"
    ])

    try:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="FFmpeg를 찾을 수 없습니다")

    request_id = f"{id(request)}_{time.time()}"
    _active_transcodes[request_id] = process

    def stream_ffmpeg():
        try:
            while True:
                chunk = process.stdout.read(STREAM_CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk
        except GeneratorExit:
            pass
        finally:
            _kill_transcode(process)
            _active_transcodes.pop(request_id, None)

    return StreamingResponse(
        stream_ffmpeg(),
        media_type="video/mp4",
        headers={
            "Content-Type": "video/mp4",
            "Cache-Control": "no-cache",
            "X-Transcode-Start": str(start),
        },
    )


@router.get("/embedded-subtitle")
async def get_embedded_subtitle(
    request: Request,
    path: str = Query(..., description="동영상 파일 경로"),
    track: int = Query(default=0, description="자막 트랙 인덱스"),
):
    """내장 자막 추출 (MKV/MP4 → WebVTT 변환)"""
    config = load_config()
    if not config.get("enabled"):
        raise HTTPException(status_code=503, detail="NAS 서비스가 비활성화되어 있습니다")

    session_token = request.cookies.get('nas_session') or request.headers.get('X-NAS-Session')
    if not session_token or not verify_session(session_token):
        raise HTTPException(status_code=401, detail="인증이 필요합니다")

    allowed_paths = config.get("allowed_paths", [])
    safe_path = get_safe_path(allowed_paths, path)

    if not safe_path or not safe_path.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    try:
        result = subprocess.run(
            [FFMPEG_PATH, "-i", str(safe_path),
             "-map", f"0:s:{track}", "-f", "webvtt", "-v", "quiet", "pipe:1"],
            capture_output=True, timeout=30
        )
        if result.returncode != 0 or not result.stdout:
            raise HTTPException(status_code=404, detail="자막 트랙을 추출할 수 없습니다")

        return Response(
            content=result.stdout,
            media_type="text/vtt; charset=utf-8",
            headers={"Content-Type": "text/vtt; charset=utf-8"},
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="자막 추출 시간 초과")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="FFmpeg를 찾을 수 없습니다")


# ============ 상태 API ============

@router.get("/status")
async def get_nas_status(request: Request):
    """NAS 서비스 상태"""
    if _remote_unauthenticated(request):
        raise HTTPException(status_code=401, detail="인증이 필요합니다")
    config = load_config()

    return {
        "enabled": config.get("enabled", False),
        "has_password": config.get("password_hash") is not None,
        "active_sessions": len(sessions),
        "allowed_paths_count": len(config.get("allowed_paths", [])),
    }


# ============ 음악 스트리밍 (nas_music.py에서 로직 처리) ============

@router.get("/music/search")
@require_auth
async def music_search(request: Request, q: str = Query(..., min_length=1), count: int = 5):
    """YouTube 음악 검색"""
    return await api_music_search(request, q, count, STREAM_CHUNK_SIZE)


@router.get("/music/stream/{video_id}")
@require_auth
async def music_stream(request: Request, video_id: str):
    """YouTube 오디오 스트리밍"""
    return await api_music_stream(request, video_id, STREAM_CHUNK_SIZE)


# ============ 홈 화면 설치 (IBFind) ============
# 원격런처(/launcher/*)와 같은 3종 세트 — 매니페스트·통과 전용 서비스워커·아이콘.
# 여기 라우트에는 @require_auth 를 걸지 않는다: 설치 판단은 로그인보다 먼저 일어나고,
# 정적 자산이라 새는 정보가 없다(아이콘·앱 이름뿐). /nas/* 는 이미 자체 세션 인증이라
# is_public_remote_path 가 통째로 위임하고 있어 추가 등록도 불필요하다.
# ★'매니페스트'는 웹 표준을 뜻한다 — 계기/창고 매니페스트와 다른 물건.

_FINDER_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "finder")


@router.get("/manifest.webmanifest")
async def finder_manifest():
    """웹 앱 매니페스트 — IBFind 아이콘·이름·창 모양 선언."""
    from fastapi.responses import JSONResponse
    return JSONResponse({
        "name": "IBFind — Remote Finder",
        "short_name": "IBFind",
        "description": "내 파일을 어디서나 — 원격 파인더",
        "start_url": "/nas/app",
        "scope": "/nas/",
        "display": "standalone",
        "background_color": "#1a1a2e",
        "theme_color": "#1a1a2e",
        "lang": "ko",
        "icons": [
            {"src": "/nas/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/nas/icon-512.png", "sizes": "512x512", "type": "image/png"},
            {"src": "/nas/icon-maskable-512.png", "sizes": "512x512", "type": "image/png",
             "purpose": "maskable"},
        ],
    }, media_type="application/manifest+json")


@router.get("/sw.js")
async def finder_service_worker():
    """서비스워커 — 캐시하지 않는다(설치 판정 조건만 충족).

    파인더는 세션 쿠키로 인증하고 파일 목록·미디어를 실시간으로 긁는 표면이라
    캐싱하면 남의 세션 결과나 낡은 목록이 남는다. 요청은 전부 네트워크로 흘린다.
    """
    js = (
        "self.addEventListener('install', function(e){ self.skipWaiting(); });\n"
        "self.addEventListener('activate', function(e){ e.waitUntil(self.clients.claim()); });\n"
        "// 통과만 한다 — 캐시 없음(세션 인증·실시간 목록)\n"
        "self.addEventListener('fetch', function(e){});\n"
    )
    return Response(content=js, media_type="application/javascript",
                    headers={"Cache-Control": "no-cache"})


@router.get("/icon-192.png")
async def finder_icon_192():
    return _finder_asset("icon-192.png")


@router.get("/icon-512.png")
async def finder_icon_512():
    return _finder_asset("icon-512.png")


@router.get("/icon-maskable-512.png")
async def finder_icon_maskable():
    return _finder_asset("icon-maskable-512.png")


@router.get("/apple-touch-icon.png")
async def finder_apple_icon():
    return _finder_asset("apple-touch-icon.png")


def _finder_asset(name: str):
    p = os.path.join(_FINDER_ASSETS, name)
    if not os.path.exists(p):
        return HTMLResponse(content="not found", status_code=404)
    return FileResponse(p, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=604800"})


# ============ 웹앱 서빙 ============

@router.get("/app", response_class=HTMLResponse)
async def serve_nas_webapp(request: Request):
    """NAS 웹앱 HTML 반환"""
    config = load_config()

    if not config.get("enabled"):
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head><title>NAS - 비활성화</title></head>
        <body style="font-family: sans-serif; padding: 50px; text-align: center;">
            <h1>🔒 NAS 서비스가 비활성화되어 있습니다</h1>
            <p>IndieBiz OS 설정에서 원격 Finder를 활성화해주세요.</p>
        </body>
        </html>
        """, status_code=503)

    # 웹앱 HTML 반환 (별도 파일 또는 인라인)
    # 1) static/nas/index.html 우선
    static_webapp = Path(__file__).parent / "static" / "nas" / "index.html"
    if static_webapp.exists():
        return HTMLResponse(content=static_webapp.read_text(encoding='utf-8'))
    # 2) nas_webapp.html 폴백
    webapp_path = Path(__file__).parent / "nas_webapp.html"
    if webapp_path.exists():
        return HTMLResponse(content=webapp_path.read_text(encoding='utf-8'))

    # 기본 웹앱 (인라인 — nas_webapp.py에서 제공)
    return HTMLResponse(content=get_default_webapp_html())
