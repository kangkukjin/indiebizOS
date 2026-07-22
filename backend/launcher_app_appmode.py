"""원격 런처 웹앱 JS — 앱 표면 탭(제네릭 계기: 매니페스트 해석·클라이언트 미디어·템플릿).

LAUNCHER_APPHOME_JS(홈 그리드 — 검색브라우저 타일 포함)는 표면 정체라 별도 상수 —
폰 표면은 포식 없는 자기 변형으로 갈아끼운다.
2026-07-22 표면 분리 1단계(launcher_web_app.py 에서 verbatim 분해)."""

LAUNCHER_APPMODE_HEAD_JS = """/* ================= 앱 (제네릭 렌더러 — /launcher/instruments 매니페스트 해석) ================= */
let appHomeRendered=false;
let INSTRUMENTS=[];
let CUR={inst:null, mode:null, optCache:{}};
let VIEW_CTX=null; /* 마지막 렌더의 {view,data} — 행 버튼/드릴 디스패치용 */
let SPLIT=false, LIST=null; /* master-detail: SPLIT=2분할 모드, LIST={view,data}=리스트 컨텍스트 */
const CUSTOM_RENDERERS={}; /* escape hatch: manifest renderer:"custom:이름" → 전용 렌더 함수 (지도·플레이어 등) */

async function loadInstruments(force){
  if(INSTRUMENTS.length && !force) return;  /* force=true 면 매니페스트 재fetch (계기/어휘 변경 반영) */
  try{ const r=await jfetch('/launcher/instruments'); if(r.ok){ const d=await r.json(); INSTRUMENTS=d.instruments||[]; } }catch(e){}
}
"""

LAUNCHER_APPHOME_JS = """async function renderAppHome(force){
  const home=document.getElementById('appHome');
  home.innerHTML='<div class="center"><div class="spin"></div></div>';
  await loadInstruments(force);
  if(!INSTRUMENTS.length){ home.innerHTML='<p class="muted">계기 매니페스트를 불러오지 못했습니다</p>'; return; }
  home.innerHTML=
    '<p class="muted" style="margin-bottom:12px">직접 조작 — 아이콘을 눌러 바로 실행 (0 토큰)</p>'+
    '<div class="grid">'+INSTRUMENTS.map((inst,ix)=>
      '<button class="tile" onclick="openInstrument('+ix+')"><span class="em">'+esc(inst.icon||'🔧')+'</span><span class="nm">'+esc(inst.name)+'</span></button>'
    ).join('')+
    /* 내장 앱(매니페스트 밖): 포식(검색) 브라우저 — 구 표면 탭에서 앱으로 이사 */
    '<button class="tile" onclick="openForage()"><span class="em">🔍</span><span class="nm">검색브라우저</span></button>'+
    '</div>';
  appHomeRendered=true;
}
function openForage(){
  setSurface('forage');
  try{ history.pushState({forage:1}, ''); }catch(e){}  /* 안드로이드 뒤로가기 → 앱 그리드 복귀 */
}
"""

LAUNCHER_APPMODE_REST_JS = """function appBackHome(){
  document.getElementById('appInst').style.display='none';
  document.getElementById('appHome').style.display='block';
}
function openInstrument(ix){
  const inst=INSTRUMENTS[ix]; if(!inst) return;
  CUR={inst:inst, mode:null, optCache:{}}; VIEW_CTX=null;
  // 홈에서 계기로 들어갈 때만 history 항목 push(뒤로가기로 그리드 복귀). 중복 push 방지.
  const _fromHome=document.getElementById('appHome').style.display!=='none';
  document.getElementById('appHome').style.display='none';
  const box=document.getElementById('appInst'); box.style.display='block';
  if(_fromHome){ try{ history.pushState({inst:1}, ''); }catch(e){} }
  let h='<div class="inst-head"><button class="back" onclick="history.back()">←</button><h2>'+esc(inst.icon||'')+' '+esc(inst.name)+'</h2></div>';
  if(inst.renderer&&inst.renderer.indexOf('custom:')===0){
    box.innerHTML=h+'<div id="modeBody"></div>';
    const fn=CUSTOM_RENDERERS[inst.renderer.slice(7)];
    if(fn) fn(inst,document.getElementById('modeBody'));
    else document.getElementById('modeBody').innerHTML='<p class="muted">렌더러 없음: '+esc(inst.renderer)+'</p>';
    return;
  }
  // 탭 + 최상단 고정 버튼(소개발행 등)을 같은 줄에 — 버튼은 오른쪽 끝(margin-left:auto)
  const _tabsHtml=(inst.modes && inst.modes.length>1)?inst.modes.map((m,i)=>'<button class="tab" id="modeTab'+i+'" onclick="setMode('+i+')">'+esc(m.name)+'</button>').join(''):'';
  const _topHtml=(inst.top_buttons||[]).map((b,i)=>'<button class="btn2" style="'+(i===0?'margin-left:auto':'')+'" onclick="fireTop('+i+')">'+esc(b.label)+'</button>').join('');
  if(_tabsHtml||_topHtml){ h+='<div class="tabs" style="align-items:center">'+_tabsHtml+_topHtml+'</div>'; }
  h+='<div id="modeBody"></div>';
  box.innerHTML=h;
  setMode(0);
}
function setMode(i){
  const inst=CUR.inst; const modes=inst.modes||[inst]; const mode=modes[i];
  CUR.mode=mode; VIEW_CTX=null; SPLIT=false; LIST=null;
  if(inst.modes) modes.forEach((m,j)=>{ const t=document.getElementById('modeTab'+j); if(t)t.classList.toggle('on',j===i); });
  CUR.optCache={};
  CUR.catFilter=null;  // 동적 필터(from_field) 선택값 — 모드 진입 시 초기화
  CUR.filterVal=(mode.filter&&mode.filter.items)?((mode.filter.items.find(x=>x.default)||mode.filter.items[0]||{}).value):null;
  let h='';
  if(mode.note) h+='<div class="note">'+esc(mode.note)+'</div>';
  const inputs=mode.inputs||[];
  if(inputs.length){
    h+='<div class="row" style="flex-wrap:wrap">'+inputs.map(inp=>{
      if(inp.type==='select')
        return '<select class="field" id="in_'+esc(inp.key)+'" style="flex:0 1 130px" onchange="selChanged(\\''+esc(inp.key)+'\\')"><option value="">'+esc(inp.label||'전체')+'</option></select>';
      return '<input class="field" style="min-width:0" id="in_'+esc(inp.key)+'" value="'+esc(loadInpVal(inst.id,mode.id,inp.key,inp.default))+'" placeholder="'+esc(inp.placeholder||'')+'" onchange="saveInpVals()" onkeydown="if(event.key===\\'Enter\\')runMode()">';
    }).join('')+'<button class="go" onclick="runMode()">조회</button></div>';
  }
  inputs.forEach(inp=>{
    if(inp.chips&&inp.chips.length)
      h+='<div class="chips" style="margin-top:10px">'+inp.chips.map(c=>
        '<span class="chip" onclick="chipRun(\\''+esc(inp.key)+'\\',\\''+esc(c)+'\\')">'+esc(c)+'</span>').join('')+'</div>';
  });
  // 기간 토글(차트 범위) — 클릭 즉시 그 기간으로 재조회
  if(mode.filter&&mode.filter.items){
    h+='<div class="filters" style="margin-top:10px">'+mode.filter.items.map(x=>
      '<button class="fchip'+(String(x.value)===String(CUR.filterVal)?' on':'')+'" data-v="'+esc(String(x.value))+'" onclick="setFilter(\\''+esc(String(x.value))+'\\')">'+esc(x.label)+'</button>').join('')+'</div>';
  }
  const btns=mode.buttons||[];
  if(btns.length)
    h+='<div class="btnrow" style="margin-top:10px">'+btns.map((b,bi)=>
      '<button class="btn2" onclick="fireButton('+bi+',this)">'+esc(b.label)+'</button>').join('')+'</div>';
  h+='<div id="instOut"></div>';
  document.getElementById('modeBody').innerHTML=h;
  // select 채우기는 선언 순서대로 — 정적 옵션(동기)이 먼저 값을 잡아야 종속 옵션이 그 값을 읽는다
  (async()=>{ for(const inp of inputs){ if(inp.type==='select') await fillOptions(inp); } if(mode.auto_run) runMode(); })();
}
/* options_action 의 $key 를 형제 입력값으로 치환 — 비어 있으면 missing 표시(종속 대기) */
function resolveOptionsAction(template){
  let missing=false;
  const code=String(template).replace(/\\$(\\w+)/g,(m,k)=>{ const el=document.getElementById('in_'+k); const v=el?String(el.value):''; if(!v) missing=true; return v.replace(/"/g,''); });
  return {code, missing};
}
/* 배열은 option_value/option_label로, 딕셔너리({이름:코드})는 entries로 정규화 → [{value,label}] */
function normalizeOptions(raw,inp){
  if(Array.isArray(raw)) return raw.map(o=>({value:o[inp.option_value||'value'], label:o[inp.option_label||'label']}));
  if(raw&&typeof raw==='object') return Object.entries(raw).map(([k,v])=>({value:v, label:k}));
  return [];
}
function setOptions(sel,opts,def){
  while(sel.options.length>1) sel.remove(1);  /* placeholder 1개 유지 */
  opts.forEach(o=>{ const el=document.createElement('option'); el.value=o.value; el.textContent=o.label; sel.appendChild(el); });
  if(def!=null && opts.some(o=>String(o.value)===String(def))) sel.value=def;
}
async function fillOptions(inp){
  const sel=document.getElementById('in_'+inp.key); if(!sel) return;
  if(Array.isArray(inp.options)){ setOptions(sel, inp.options.map(o=>({value:o.value,label:o.label})), inp.default); return; }
  if(!inp.options_action) return;
  const {code,missing}=resolveOptionsAction(inp.options_action);
  if(missing){ setOptions(sel, [], null); return; }   /* 종속 부모 미선택 — 비워두고 대기 */
  let opts=CUR.optCache[code];
  if(!opts){ try{ const d=await ibl(code); opts=normalizeOptions(jget(d,inp.options_from),inp); CUR.optCache[code]=opts; }catch(e){ opts=[]; } }
  if(document.getElementById('in_'+inp.key)!==sel) return;
  setOptions(sel, opts, inp.default);
}
/* select 변경 시, 그 키에 의존하는 종속 select 들을 비우고 다시 채운다 (cascade) */
function selChanged(key){
  const mode=CUR.mode; if(!mode) return;
  (mode.inputs||[]).forEach(inp=>{
    if(inp.type==='select' && inp.options_action && new RegExp('\\\\$'+key+'\\\\b').test(inp.options_action)) fillOptions(inp);
  });
}
function chipRun(key,val){ const el=document.getElementById('in_'+key); if(el) el.value=val; runMode(); }
/* 폰 라디오: 백엔드가 play_in_client+stream_url 반환 → WebView 가 직접 재생(소리=폰 스피커).
   한국 방송=HLS(.m3u8)라 hls.js, ICY/mp3 등은 네이티브 <audio>. */
let _radioHls=null;
function _radioAudioEl(){ let a=document.getElementById('radioAudio'); if(!a){ a=document.createElement('audio'); a.id='radioAudio'; a.autoplay=true; a.addEventListener('ended',_npHide); document.body.appendChild(a); } return a; }
/* 전역 미니플레이어: 클라이언트 오디오(라디오·유튜브뮤직)는 #radioAudio 전역 엘리먼트라
   계기를 벗어나도 계속 재생된다. 재생 중이면 어디서든 보이는 정지 바를 띄워(클라이언트 관심사=
   IBL 왕복 없이 stopRadioStream 직접) "멈출 방법 없음" 해소. 곡이 끝나면(ended) 자동 숨김. */
function _npBar(){
  let b=document.getElementById('nowPlaying');
  if(!b){
    b=document.createElement('div'); b.id='nowPlaying';
    b.style.cssText='position:fixed;left:0;right:0;bottom:0;z-index:9998;display:none;align-items:stretch;gap:10px;padding:10px 14px;background:var(--bg2);border-top:1px solid var(--line);box-shadow:0 -2px 10px rgba(74,64,53,.12)';
    // 컬럼: (1) 제목+정지 (2) 진행바 — 유한 길이(유튜브뮤직)일 때만 timeupdate 가 표시, 라이브(라디오)엔 숨김
    b.innerHTML='<div style="flex:1;display:flex;flex-direction:column;gap:6px;min-width:0">'
      +'<div style="display:flex;align-items:center;gap:10px">'
      +'<span style="font-size:18px">\\u266a</span>'
      +'<span id="npTitle" style="flex:1;color:var(--txt);font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"></span>'
      +'<button onclick="stopRadioStream()" style="background:var(--acc);color:#fff;border:none;border-radius:18px;padding:8px 18px;font-size:15px;font-weight:bold">\\u25a0 \\uc815\\uc9c0</button>'
      +'</div>'
      +'<div id="npSeekRow" style="display:none;align-items:center;gap:8px">'
      +'<span id="npCur" style="color:var(--dim);font-size:11px;font-variant-numeric:tabular-nums;min-width:34px;text-align:right">0:00</span>'
      +'<input id="npSeek" type="range" min="0" max="100" value="0" step="1" style="flex:1;accent-color:var(--acc);cursor:pointer">'
      +'<span id="npDur" style="color:var(--dim);font-size:11px;font-variant-numeric:tabular-nums;min-width:34px">0:00</span>'
      +'</div>'
      +'</div>';
    document.body.appendChild(b);
  }
  return b;
}
function _npShow(label){ const b=_npBar(); const t=document.getElementById('npTitle'); if(t) t.textContent=label||'\\uc7ac\\uc0dd \\uc911'; b.style.display='flex'; }
function _npHide(){ const b=document.getElementById('nowPlaying'); if(b) b.style.display='none'; }
/* 진행바(중간 점프): #radioAudio 는 실제 브라우저 <audio> 라 native seek 가 공짜.
   유한 길이(유튜브뮤직)면 스크러버를 띄우고, 라이브 스트림(라디오, duration=Infinity)이면 숨긴다. */
function _npFmtT(s){ if(!isFinite(s)||s<0) return '0:00'; s=Math.floor(s); var m=Math.floor(s/60), x=s%60, h=Math.floor(m/60); if(h>0){ m=m%60; return h+':'+String(m).padStart(2,'0')+':'+String(x).padStart(2,'0'); } return m+':'+String(x).padStart(2,'0'); }
var _npSeeking=false;
function npSeekTo(v){ var a=document.getElementById('radioAudio'); if(a && isFinite(a.duration)){ try{ a.currentTime=Number(v); }catch(e){} } }
function _npWireSeek(a){
  if(a._npWired) return; a._npWired=true;
  a.addEventListener('timeupdate',function(){
    if(_npSeeking) return;
    var row=document.getElementById('npSeekRow'), sk=document.getElementById('npSeek');
    var cur=document.getElementById('npCur'), du=document.getElementById('npDur');
    if(isFinite(a.duration) && a.duration>0){
      if(row) row.style.display='flex';
      if(sk){ sk.max=Math.floor(a.duration); sk.value=Math.floor(a.currentTime); }
      if(cur) cur.textContent=_npFmtT(a.currentTime);
      if(du) du.textContent=_npFmtT(a.duration);
    } else if(row){ row.style.display='none'; }  // 라이브(라디오)=무한 → 숨김
  });
  var sk=document.getElementById('npSeek');
  if(sk){
    sk.addEventListener('input',function(){ _npSeeking=true; var cur=document.getElementById('npCur'); if(cur) cur.textContent=_npFmtT(Number(sk.value)); });
    sk.addEventListener('change',function(){ npSeekTo(sk.value); _npSeeking=false; });
  }
}
function playRadioStream(url,vol,label){
  const a=_radioAudioEl();
  if(_radioHls){ try{_radioHls.destroy();}catch(e){} _radioHls=null; }
  if(typeof vol==='number') a.volume=Math.max(0,Math.min(1,vol/100));
  if(/\\.m3u8/i.test(url) && window.Hls && Hls.isSupported()){
    _radioHls=new Hls(); _radioHls.loadSource(url); _radioHls.attachMedia(a);
    _radioHls.on(Hls.Events.MANIFEST_PARSED,()=>a.play().catch(()=>{}));
  } else { a.src=url; a.play().catch(()=>{}); }
  _npShow(label);
  _npSeeking=false;
  var row=document.getElementById('npSeekRow'); if(row) row.style.display='none';  // 새 곡=일단 숨김(메타 로드되면 timeupdate가 판단)
  var sk=document.getElementById('npSeek'); if(sk) sk.value=0;
  _npWireSeek(a);
}
function stopRadioStream(){
  if(_radioHls){ try{_radioHls.destroy();}catch(e){} _radioHls=null; }
  const a=document.getElementById('radioAudio'); if(a){ a.pause(); a.removeAttribute('src'); a.load(); }
  var row=document.getElementById('npSeekRow'); if(row) row.style.display='none';
  _npHide();
}
/* CCTV 영상(item2): 지도 마커 클릭 → 전체화면 <video> 오버레이로 HLS 재생.
   onclick 은 URL 대신 _streamUrls 정수 인덱스를 넘겨 따옴표 이스케이프 함정을 원천 회피. */
var _streamUrls=[], _cctvHls=null;
function playStream(idx){
  const url=_streamUrls[idx]; if(!url) return;
  let ov=document.getElementById('streamOverlay');
  if(!ov){
    ov=document.createElement('div'); ov.id='streamOverlay';
    ov.style.cssText='position:fixed;inset:0;background:#000;z-index:9999;display:flex';
    ov.innerHTML='<button onclick="closeStream()" style="position:absolute;top:12px;right:12px;z-index:2;background:rgba(0,0,0,.6);color:#fff;border:none;border-radius:20px;padding:8px 16px;font-size:16px">✕ 닫기</button><video id="streamVideo" controls autoplay playsinline muted style="width:100%;height:100%;object-fit:contain"></video>';
    document.body.appendChild(ov);
  }
  ov.style.display='flex';
  const v=document.getElementById('streamVideo');
  if(_cctvHls){ try{_cctvHls.destroy();}catch(e){} _cctvHls=null; }
  if(/\\.m3u8/i.test(url) && window.Hls && Hls.isSupported()){
    _cctvHls=new Hls(); _cctvHls.loadSource(url); _cctvHls.attachMedia(v);
    _cctvHls.on(Hls.Events.MANIFEST_PARSED,()=>v.play().catch(()=>{}));
  } else { v.src=url; v.play().catch(()=>{}); }
}
function closeStream(){
  if(_cctvHls){ try{_cctvHls.destroy();}catch(e){} _cctvHls=null; }
  const v=document.getElementById('streamVideo'); if(v){ v.pause(); v.removeAttribute('src'); v.load(); }
  const ov=document.getElementById('streamOverlay'); if(ov) ov.style.display='none';
}
/* 사진 라이트박스(image_grid): 썸네일 클릭 → 원본 이미지/동영상을 전체화면 오버레이로.
   full URL 은 클릭된 엘리먼트의 <img src>(이미 URL 인코딩됨)에서 파생 — 썸네일→원본 엔드포인트
   치환(thumbnail→image, video-thumbnail→video)+size 파라미터 제거. 따옴표 이스케이프 무필요. */
function openMediaFromEl(el){
  const im=el.querySelector('img'); if(!im) return;
  const src=im.getAttribute('src')||''; if(!src) return;
  const isVid=src.indexOf('video-thumbnail')>=0;
  const full=src.replace('/photo/video-thumbnail','/photo/video').replace('/photo/thumbnail','/photo/image').replace(/[?&]size=\\d+/,'');
  let ov=document.getElementById('mediaOverlay');
  if(!ov){
    ov=document.createElement('div'); ov.id='mediaOverlay';
    ov.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.93);z-index:9999;display:flex;align-items:center;justify-content:center';
    ov.onclick=function(e){ if(e.target===ov||e.target.id==='mediaClose') closeMedia(); };
    ov.innerHTML='<button id="mediaClose" style="position:absolute;top:12px;right:12px;background:rgba(0,0,0,.6);color:#fff;border:none;border-radius:20px;padding:8px 16px;font-size:16px">✕ 닫기</button><div id="mediaBody" style="max-width:100%;max-height:100%;display:flex;align-items:center;justify-content:center"></div>';
    document.body.appendChild(ov);
  }
  document.getElementById('mediaBody').innerHTML = isVid
    ? '<video src="'+full+'" controls autoplay playsinline style="max-width:100%;max-height:92vh"></video>'
    : '<img src="'+full+'" style="max-width:100%;max-height:92vh;object-fit:contain">';
  ov.style.display='flex';
}
function closeMedia(){
  const b=document.getElementById('mediaBody'); if(b) b.innerHTML='';
  const ov=document.getElementById('mediaOverlay'); if(ov) ov.style.display='none';
}
async function fireButton(bi,btn){
  const b=(CUR.mode.buttons||[])[bi]; if(!b) return;
  btn.disabled=true;
  /* $key=모드 입력값 치환(팔로우 $npub·보드 만들기 $name/$tag 등) — 데스크탑 fireButton 과 동일 의미 */
  try{ let d=await ibl(buildAction(b.action,gatherInputs()));
    /* 합성(>>) 결과는 final_result(마지막 단계)를 펼쳐 본다 — 발행 링크 등 */
    if(d&&typeof d==='object'&&'final_result' in d){ let fr=d.final_result; if(typeof fr==='string'){try{fr=JSON.parse(fr)}catch(e){}} if(fr&&typeof fr==='object') d=fr; }
    if(d&&d.stop_in_client){ stopRadioStream(); }
    else if(d&&d.error){ alert(d.error); }
    else if(d&&d.url){ try{await navigator.clipboard.writeText(d.url);}catch(e){} alert((d.message||'발행 완료')+'\\n\\n링크가 복사되었습니다 — 친구에게 붙여넣으세요:\\n'+d.url); }  // 발행 등 링크 반환 액션
    else if(b.refresh){ runMode(); }  // 실행 후 현재 모드 재조회(토글/재생성 즉시 반영)
  }
  catch(e){ alert('실행 실패: '+e.message); }
  finally{ btn.disabled=false; }
}
/* 최상단 고정 버튼(소개발행 등) — 탭 무관, CUR.inst.top_buttons 에서 실행 */
async function fireTop(i){
  const b=(CUR.inst.top_buttons||[])[i]; if(!b||!b.action) return;
  if(b.confirm && !confirm(b.confirm)) return;
  try{ let d=await ibl(b.action);
    if(d&&typeof d==='object'&&'final_result' in d){ let fr=d.final_result; if(typeof fr==='string'){try{fr=JSON.parse(fr)}catch(e){}} if(fr&&typeof fr==='object') d=fr; }
    if(d&&d.error){ alert(d.error); } else{ alert((d&&d.message)||'완료'); }
  }
  catch(e){ alert('실행 실패: '+e.message); }
}

/* ----- 액션 템플릿: $key=사용자 입력, {path}=데이터 행 필드 ----- */
function jget(o,path){ if(!path) return o; return String(path).split('.').reduce((a,k)=>(a==null?undefined:a[k]),o); }
function buildAction(template,values){
  let code=template.replace(/\\$(\\w+)/g,(m,k)=>{
    const v=values[k]; return v==null?'':String(v).replace(/\\\\/g,'\\\\\\\\').replace(/"/g,'\\\\"');
  });
  code=code.replace(/\\w+:\\s*"",?\\s*/g,'');  /* 빈 입력 파라미터 제거 */
  code=code.replace(/,\\s*\\}/g,'}').replace(/\\{\\s*,/g,'{');
  return code;
}
function viewList(data,from){ if(from==='.') return [data]; const a=jget(data,from); return Array.isArray(a)?a:[]; }
function rowAction(template,item){
  return template.replace(/\\{([\\w.]+)\\}/g,(m,path)=>{ const v=jget(item,path); return v==null?'':String(v).replace(/"/g,''); });
}

/* ----- 표시 템플릿: "{path|filter|...}" → 문자열 (HTML 이스케이프 포함) ----- */
function applyFilter(v,f){
  if(f==='round') return v==null?v:Math.round(Number(v));
  if(f==='num') return v==null?null:Number(v).toLocaleString();
  if(f==='abs') return v==null?v:Math.abs(Number(v));
  if(f==='arrow') return (Number(v)||0)>=0?'▲':'▼';
  if(f.indexOf('opt:')===0){ const a=f.slice(4).split(','); return (v==null||v===''||Number(v)===0)?'':(a[0]||'')+v+(a[1]||''); }
  if(f.indexOf('trunc:')===0){ const n=parseInt(f.slice(6))||40; const s=String(v==null?'':v); return s.length>n?s.slice(0,n)+'…':s; }
  return v;
}
function tpl(t,data){
  if(t==null) return '';
  return String(t).replace(/\\{([^{}]+)\\}/g,(m,expr)=>{
    const parts=expr.split('|'); let v=jget(data,parts[0].trim());
    for(let i=1;i<parts.length;i++) v=applyFilter(v,parts[i].trim());
    return v==null?'':esc(v);
  });
}

function statusGlyph(s){ return s==='sent'?'✓':s==='pending'?'⏳':s==='failed'?'⚠':''; }
// blocks — 문서 IR 렌더. 블록 구조는 IR이 정본, 여기선 인라인 마크다운(**·`·[링크](url))만 얇게 해석.
function mdInline(t){
  return esc(t==null?'':String(t))
    .replace(/\\*\\*([^*]+)\\*\\*/g,'<strong>$1</strong>')
    .replace(/`([^`]+)`/g,'<code>$1</code>')
    .replace(/\\[([^\\]]+)\\]\\((https?:[^)\\s]+)\\)/g,'<a href="$2" target="_blank" rel="noopener">$1</a>');
}
function docBlockHtml(b){
  if(!b||typeof b!=='object') return '';
  const t=String(b.type||'paragraph');
  if(t==='heading'){ const l=Math.min(6,Math.max(1,parseInt(b.level)||2)); return '<div class="dh dh'+l+'">'+mdInline(b.text)+'</div>'; }
  if(t==='list'){
    const tag=b.ordered?'ol':'ul';
    return '<'+tag+'>'+(b.items||[]).map(it=>{
      const o=(it&&typeof it==='object')?it:null;
      const tx=o?String(o.text==null?'':o.text):String(it==null?'':it);
      const u=o&&o.url?String(o.url):'';
      return '<li>'+(u?'<a href="'+esc(u)+'" target="_blank" rel="noopener">'+esc(tx)+'</a>':mdInline(tx))+'</li>';
    }).join('')+'</'+tag+'>';
  }
  if(t==='table'){
    const cols=b.columns||[], rows=(b.rows||[]).filter(r=>Array.isArray(r));
    return '<div style="overflow-x:auto"><table class="dtab">'
      +(cols.length?'<thead><tr>'+cols.map(c=>'<th>'+esc(c==null?'':String(c))+'</th>').join('')+'</tr></thead>':'')
      +'<tbody>'+rows.map(r=>'<tr>'+r.map(c=>'<td>'+esc(c==null?'':String(c))+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>';
  }
  if(t==='quote') return '<blockquote class="dq">'+mdInline(b.text)+(b.cite?'<cite>— '+esc(String(b.cite))+'</cite>':'')+'</blockquote>';
  if(t==='code') return '<pre class="dcode"><code>'+esc(b.text==null?'':String(b.text))+'</code></pre>';
  if(t==='divider') return '<hr class="dhr">';
  if(t==='image'){
    const s=String(b.src||b.path||'');
    return s?'<figure class="dfig"><img src="'+esc(s)+'" loading="lazy">'+(b.caption?'<figcaption>'+esc(String(b.caption))+'</figcaption>':'')+'</figure>':'';
  }
  return '<p class="dp">'+mdInline(b.text)+'</p>';
}

// 반복 주기 표준 어휘 — recurrence 필드 타입 baked 옵션(manage_events repeat 값과 일치, 데스크탑 RECURRENCE_OPTS 쌍).
var _RECUR_OPTS=[['none','한 번'],['daily','매일'],['weekly','매주'],['monthly','매월'],['yearly','매년']];
function _recurSelect(id,val){ const v=val||'none'; return '<select class="field" id="'+id+'">'+_RECUR_OPTS.map(o=>'<option value="'+o[0]+'"'+(o[0]===v?' selected':'')+'>'+o[1]+'</option>').join('')+'</select>'; }
function _dateInputType(t){ return t==='datetime'?'datetime-local':t; } // date/time 그대로, datetime→datetime-local

"""
