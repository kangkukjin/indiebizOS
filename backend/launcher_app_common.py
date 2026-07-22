"""원격 런처 웹앱 JS — 공통부(유틸·ibl()·로그인/부트·클립보드·피어·모델 기어) + 표면 토글.

launcher_web_app.LAUNCHER_APP_JS 가 조각들을 원래 순서로 이어붙인다(바이트 동일 조립).
LAUNCHER_SETSURFACE_JS(어떤 탭이 존재하는가)는 표면 정체라 별도 상수 — 폰 표면은
자기 변형으로 갈아끼운다. 2026-07-22 표면 분리 1단계(launcher_web_app.py 에서 verbatim 분해)."""

LAUNCHER_COMMON_JS = """<script>
const API='';
let surface='autopilot';
let apChat={ type:'system', projectId:null, agentId:null, agentName:null };
let apProjects=[];
let apSwitches=[];

/* ===== 공통 ===== */
function esc(s){ const d=document.createElement('div'); d.textContent=(s==null?'':String(s)); return d.innerHTML; }
/* 채팅 버블용 경량 마크다운 — AI 응답의 **·`·##·리스트·링크가 생짜로 보이던 것을 얇게 해석.
   버블은 white-space:pre-wrap 이라 블록 요소를 만들지 않고 인라인 치환만 한다(줄바꿈은 원문 그대로). */
function mdChat(t){
  let s=String(t==null?'':t);
  s=s.replace(/\\s*\\[MAP:\\{[\\s\\S]*?\\}\\]\\s*/g,'\\n');  /* 지도 봉투(데스크탑 렌더 전용)는 원격 표시서 제거 */
  s=esc(s);
  const fences=[];
  s=s.replace(/```[a-zA-Z0-9_-]*\\n?([\\s\\S]*?)```/g,function(_m,c){ fences.push(c.replace(/\\n+$/,'')); return '\\u0000F'+(fences.length-1)+'\\u0000'; });
  s=s.replace(/`([^`\\n]+)`/g,'<code>$1</code>');
  s=s.replace(/\\*\\*([^*\\n]+)\\*\\*/g,'<b>$1</b>');
  s=s.replace(/^#{1,6}\\s+(.+)$/gm,'<span class="mdh">$1</span>');
  s=s.replace(/^&gt; ?(.+)$/gm,'<span class="mdq">▏ $1</span>');
  s=s.replace(/^(\\s*)[-*]\\s+/gm,'$1• ');
  s=s.replace(/\\[([^\\]]+)\\]\\((https?:[^)\\s]+)\\)/g,'<a href="$2" target="_blank" rel="noopener">$1</a>');
  s=s.replace(/(^|[^"'>=\\]])(https?:\\/\\/[^\\s<>"']+)/g,'$1<a href="$2" target="_blank" rel="noopener">$2</a>');
  s=s.replace(/\\u0000F(\\d+)\\u0000/g,function(_m,i){ return '<pre>'+fences[+i]+'</pre>'; });
  return s;
}
// kv 값 렌더 — http(s) URL 이면 새 탭으로 여는 링크(공개 사이트 주소 등), 아니면 텍스트.
function kvVal(v){ const t=String(v==null?'':v).trim();
  const isUrl=(t.startsWith('http://')||t.startsWith('https://'))&&t.indexOf(' ')<0;
  return isUrl
    ? '<a href="'+esc(t)+'" target="_blank" rel="noopener" style="color:var(--info);word-break:break-all">'+esc(t)+'</a>'
    : '<span>'+esc(v)+'</span>'; }
function jfetch(url,opt){ return fetch(API+url, Object.assign({headers:{'Content-Type':'application/json'}}, opt||{})); }
async function ibl(code){
  /* 포털(회원 원격 계기): 범용 /ibl/execute 대신 회원 실행 게이트로 보낸다 — 렌더러 포크 금지·매개변수화 */
  /* surface:'web' = 보고 있는 곳이 브라우저라는 표식 — 소리·저장이 맥이 아니라 여기서 나게 한다
     (포털은 게이트가 서버측에서 같은 표식을 붙인다). */
  const r=window.__PORTAL
    ? await jfetch(window.__PORTAL.exec,{method:'POST',body:JSON.stringify({code:code})})
    : await jfetch('/ibl/execute',{method:'POST',body:JSON.stringify({code,project_id:'앱모드',project_path:'.',surface:'web'})});
  if(!r.ok){ let m='[HTTP '+r.status+']'; try{ const e=await r.json(); if(e&&(e.error||e.detail)) m=e.error||e.detail; }catch(_e){} throw new Error(m); }
  const data=await r.json();
  /* 합성(>>) 액션은 final_result(마지막 단계)를 펼쳐 단일 액션처럼 노출 — view의 from/{필드}가 풀리도록 */
  if(data && typeof data==='object' && 'final_result' in data){
    const fr=data.final_result;
    if(typeof fr==='string'){ try{ return JSON.parse(fr); }catch(e){ return {message:fr}; } }
    if(fr && typeof fr==='object') return fr;
  }
  return data;
}

/* ===== 로그인 ===== */
document.addEventListener('DOMContentLoaded',()=>{
  if(window.__PORTAL){ portalBoot(); return; }
  document.getElementById('pw').addEventListener('keydown',e=>{ if(e.key==='Enter')doLogin(); });
  checkSession();
});
/* 포털(개인 커뮤니티 홈) 부트 — 이 셸을 회원용 단일 계기 페이지로 재사용(포크 금지·매개변수화).
   로그인/표면 토글/계기판을 전부 건너뛰고 서버가 주입한 계기 하나(__PORTAL.instrument)를 바로
   연다. 실행은 ibl() 이 __PORTAL.exec(회원 실행 게이트)로 보낸다. appHome 을 미리 숨겨
   openInstrument 의 history push 를 막는다 → 뒤로가기 = 포털 홈. */
function portalBoot(){
  document.getElementById('login').style.display='none';
  document.getElementById('app').classList.add('on');
  const top=document.querySelector('.top'); if(top) top.style.display='none';
  const sf=document.querySelector('.surfaces'); if(sf) sf.style.display='none';
  const ap=document.getElementById('p-autopilot'); if(ap) ap.classList.remove('on');
  document.getElementById('p-app').classList.add('on');
  document.getElementById('appHome').style.display='none';
  INSTRUMENTS=[window.__PORTAL.instrument];
  openInstrument(0);
}
async function checkSession(){
  // 비번 없는 표면(폰 자급·로컬)은 게이트 자체가 무의미 → config로 즉시 진입(맥 프록시 의존 제거).
  // 폰은 has_password=false 라 /projects(맥 터널 왕복) 결과와 무관히 바로 런처가 뜬다 = 로그인 화면 없음.
  try{ const c=await(await jfetch('/launcher/config')).json(); if(c && c.has_password===false){ showApp(); return; } }catch(e){}
  try{ const r=await jfetch('/projects'); if(r.ok){ showApp(); } }catch(e){}
}
async function doLogin(){
  const pw=document.getElementById('pw').value;
  const el=document.getElementById('loginErr'); el.textContent='';
  try{
    const r=await jfetch('/launcher/auth/login',{method:'POST',body:JSON.stringify({password:pw})});
    if(r.ok){ showApp(); } else { const d=await r.json().catch(()=>({})); el.textContent=d.detail||'로그인 실패'; }
  }catch(e){ el.textContent='서버 연결 실패'; }
}
let IS_PHONE=false;
async function showApp(){
  document.getElementById('login').style.display='none';
  document.getElementById('app').classList.add('on');
  // 자급 컴패니언(폰-로컬)인지 판별 — REMOTE 배지는 원격 시나리오 전용이라 폰에선 숨긴다.
  // (2026-07-21 헤더의 ↻ 새로고침·⏻ 로그아웃 제거 — 새로고침은 브라우저와 겹치고,
  //  로그아웃은 표면에 상주할 만큼 자주 쓰지 않는다. 세션 해제는 브라우저 데이터 삭제.)
  try{ const r=await jfetch('/launcher/config'); if(r.ok){ const c=await r.json();
    IS_PHONE=(c.host==='phone-local');
    /* 허브 OS — 붙여넣기 안내 키에만 쓴다. 폰 네이티브가 받는 config 는 폰 자신의 것이라
       허브 OS 를 모른다 → 그때는 두 키를 다 보여준다(라벨은 어차피 OS 중립). */
    if(c.platform==='mac') PASTE_KEY='⌘V';
    else if(c.platform==='windows'||c.platform==='linux') PASTE_KEY='Ctrl+V';
    if(IS_PHONE){ const b=document.getElementById('surfBadge'); if(b) b.style.display='none'; }
  } }catch(e){}
  /* 클립보드 'PC로'는 두 표면 공통 — 방향은 표면이 정한다(보고 있는 기계 → 허브 PC).
     읽는 방법만 갈린다: 폰 네이티브=Java ClipboardManager, 원격런처=브라우저 clipboard API. */
  const cm=document.getElementById('clipToMacBtn'); if(cm) cm.style.display='block';
  apLoad();
  loadPeer(); setInterval(loadPeer, 20000);  /* 다른 몸 연결상태 폴링(계기판) */
  loadGear();  /* 모델 기어 레버(계기판) */
}

/* ===== 여기→허브PC 클립보드 (헤더 버튼) — 데스크탑 '폰으로'의 역방향 =====
   방향은 *표면*이 정한다: 보고 있는 기계의 클립보드를 허브 PC 로 민다. 데스크탑 런처는
   '폰으로'(PC→폰), 이 표면은 'PC로'. 사용자가 방향을 고를 일이 없다(당기기 없음).
   ★라벨은 OS 중립 — 허브는 맥일 수도 윈도우일 수도 있다(둘 다 indiebizOS 설치 대상).
   내부 라우트 이름(/launcher/clip-to-mac)은 폰 번들에 박혀 있어 그대로 둔다.
   읽는 방법만 표면별로 갈린다:
     - 폰 네이티브: /launcher/clip-to-mac (Java ClipboardManager — WebView 의 readText 는 불가)
     - 원격런처(브라우저): navigator.clipboard.readText → 실패하면 붙여넣기 칸 폴백
   놓는 쪽은 둘 다 기존 어휘 [self:output]{op:"clipboard"} — 허브 백엔드가 실행하니 거기 박힌다. */
let clipMacBusy=false;
let PASTE_KEY='⌘V / Ctrl+V';   /* 허브 OS 를 알기 전 기본값 — showApp 에서 확정 */
function clipMacFlash(msg){
  const b=document.getElementById('clipToMacBtn'); if(!b) return;
  b.textContent=msg;
  setTimeout(()=>{ b.textContent='📋 PC로 보내기'; clipMacBusy=false; }, 3500);
}
async function clipToMac(){
  if(clipMacBusy) return;
  const b=document.getElementById('clipToMacBtn'); if(!b) return;
  clipMacBusy=true;
  b.textContent='보내는 중…';
  if(IS_PHONE){
    let msg='실패';
    try{
      const r=await jfetch('/launcher/clip-to-mac',{method:'POST'});
      const d=await r.json().catch(()=>({}));
      if(d && d.success) msg='PC 도착 ✓ ('+(d.chars||0)+'자) — '+PASTE_KEY+' 로 붙여넣으세요';
      else msg=(d && d.error) ? d.error : '실패';
    }catch(e){ msg='연결 실패'; }
    clipMacFlash(msg);
    return;
  }
  /* 브라우저 표면: 읽기는 권한·제스처에 걸린다(iOS 는 확인 UI, 일부 브라우저는 아예 불가)
     → 실패·빈값이면 붙여넣기 칸으로 떨어뜨린다. 어디서든 되는 최후 경로. */
  let text='';
  try{ text=await navigator.clipboard.readText(); }catch(e){ text=''; }
  if(!(text||'').trim()){ clipMacBusy=false; b.textContent='📋 PC로 보내기'; clipPasteBox(); return; }
  clipSendToMac(text);
}
async function clipSendToMac(text){
  /* JSON.stringify = IBL 문자열 이스케이프 (따옴표·줄바꿈·중괄호·백슬래시 왕복 검증됨) */
  try{
    const d=await ibl('[self:output]{op: "clipboard", content: '+JSON.stringify(String(text))+'}');
    if(d && (d.copied_length || d.ok)) clipMacFlash('PC 도착 ✓ ('+(d.copied_length||String(text).length)+'자) — '+PASTE_KEY+' 로 붙여넣으세요');
    else clipMacFlash((d && d.error) ? d.error : '실패');
  }catch(e){ clipMacFlash('전송 실패: '+e.message); }
}
/* 붙여넣기 칸 폴백 — 셸 마크업을 늘리지 않도록 필요할 때만 만든다 */
function clipPasteBox(){
  let ov=document.getElementById('clipPasteOv');
  if(!ov){
    ov=document.createElement('div'); ov.id='clipPasteOv';
    ov.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:9999;display:none;align-items:flex-start;justify-content:center;padding:56px 16px';
    ov.innerHTML='<div style="background:var(--bg2);border:1px solid var(--line);border-radius:16px;padding:16px;width:100%;max-width:420px;box-shadow:0 20px 60px rgba(74,64,53,.25)">'
      +'<div style="font-size:15px;font-weight:600;margin-bottom:6px">📋 PC로 보내기</div>'
      +'<div style="font-size:12px;color:var(--dim);margin-bottom:10px;line-height:1.5">브라우저가 클립보드를 직접 읽지 못했어요.<br>아래 칸을 길게 눌러 <b>붙여넣기</b> 한 뒤 보내세요.</div>'
      +'<textarea id="clipPasteTa" rows="5" placeholder="여기에 붙여넣기" style="width:100%;padding:10px;border:1px solid var(--line);border-radius:10px;background:var(--bg);color:var(--txt);font-size:14px;resize:vertical"></textarea>'
      +'<div style="display:flex;gap:8px;margin-top:12px;justify-content:flex-end">'
      +'<button onclick="clipPasteClose()" style="background:var(--bg3);border:1px solid var(--line);color:var(--dim);border-radius:999px;padding:8px 16px;font-size:14px">취소</button>'
      +'<button onclick="clipPasteSend()" style="background:var(--acc);border:none;color:#fff;border-radius:999px;padding:8px 18px;font-size:14px;font-weight:600">PC로 보내기</button>'
      +'</div></div>';
    document.body.appendChild(ov);
  }
  ov.style.display='flex';
  const ta=document.getElementById('clipPasteTa'); if(ta){ ta.value=''; setTimeout(()=>{ try{ta.focus();}catch(e){} }, 60); }
}
function clipPasteClose(){ const ov=document.getElementById('clipPasteOv'); if(ov) ov.style.display='none'; }
function clipPasteSend(){
  const ta=document.getElementById('clipPasteTa'); const t=ta?ta.value:'';
  if(!(t||'').trim()){ if(ta) ta.focus(); return; }
  clipPasteClose(); clipMacBusy=true;
  const b=document.getElementById('clipToMacBtn'); if(b) b.textContent='보내는 중…';
  clipSendToMac(t);
}

/* ===== 다른 몸(피어) 연결상태 — 계기판 안에 표기 ===== */
function renderPeer(d){
  const el=document.getElementById('peerStatus'); if(!el) return;
  if(!d){ el.style.display='none'; return; }
  const online = !!(d.has_peer && d.online);
  const name = d.peer_name || '다른 몸';
  const status = !d.has_peer ? '미연동' : (online ? '연결됨' : '오프라인');
  const dot = online ? '#10b981' : '#d6d3d1';
  el.innerHTML =
    '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:'+dot+'"></span>'+
    '<span style="color:'+(online?'#44403c':'#a8a29e')+';margin-left:8px">'+((d.peer_icon||'📱'))+' '+esc(name)+'</span>'+
    '<span style="color:'+(online?'#059669':'#a8a29e')+';margin-left:6px">· '+status+'</span>';
  el.style.cssText='display:flex;align-items:center;font-size:12px;padding:8px 2px;margin-bottom:8px';
}
async function loadPeer(){
  try{ const r=await jfetch('/nodes/peer-status'); if(r.ok){ renderPeer(await r.json()); return; } }catch(e){}
  renderPeer(null);
}

/* ===== 모델 기어 — 계기판 변속 레버 + 설정(프리셋·핀). data-속성 위임으로 따옴표 함정 회피 ===== */
let gearState=null, gearOpen=false, gearAgents=[], gearOverrides={}, gearPresetDraft={};
const GEAR_DESC={'절약':'전부 경량 — 빠르고 저렴','균형':'실행·의식 중급 — 기본','최대':'실행·의식 고급 — 최고 품질'};
async function loadGear(){
  try{ const r=await jfetch('/model-gear'); if(r.ok){ gearState=await r.json(); renderGear(); return; } }catch(e){}
  const el=document.getElementById('gearLever'); if(el) el.style.display='none';
}
function renderGear(){
  const el=document.getElementById('gearLever'); if(!el||!gearState) return;
  el.style.display='block'; const g=gearState; let h='';
  h+='<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">';
  h+='<span style="font-weight:700;font-size:14px">⚙️ 모델 기어</span>';
  h+='<button data-act="toggle" style="font-size:11px;padding:4px 10px;border-radius:8px;border:1px solid var(--line);background:'+(gearOpen?'var(--acc)':'var(--bg3)')+';color:var(--txt)">설정</button></div>';
  h+='<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px">';
  (g.gears||[]).forEach(function(name){
    const on=g.current_gear===name;
    h+='<button data-act="gear" data-g="'+esc(name)+'" style="padding:10px 6px;border-radius:10px;border:1px solid '+(on?'var(--acc)':'var(--line)')+';background:'+(on?'var(--acc)':'var(--bg)')+';color:'+(on?'#fff':'var(--txt)')+';text-align:center">';
    h+='<div style="font-weight:700;font-size:13px">'+esc(name)+'</div>';
    h+='<div style="font-size:10px;margin-top:2px;color:'+(on?'rgba(255,255,255,.85)':'var(--dim)')+'">'+esc(GEAR_DESC[name]||'')+'</div></button>';
  });
  h+='</div>';
  if(g.axes){
    h+='<div style="display:flex;flex-wrap:wrap;gap:10px;margin-top:10px;padding-top:8px;border-top:1px solid var(--line);font-size:11px;color:var(--dim)">';
    Object.keys(g.axes).forEach(function(ax){ h+='<span>'+esc(ax)+' <b style="color:var(--txt)">'+esc(g.axes[ax].tier)+'</b></span>'; });
    h+='<span style="color:var(--dim)">· 티어별 모델은 설정 ▸ 모델 설정</span></div>';
  }
  if(typeof g.consciousness_enabled!=='undefined'){
    const on=g.consciousness_enabled!==false;
    h+='<div style="display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:10px;padding-top:8px;border-top:1px solid var(--line)">';
    h+='<span style="font-size:11px;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"><b style="color:'+(on?'var(--txt)':'var(--dim)')+'">🧠 의식 '+(on?'켜짐':'꺼짐')+'</b> <span style="color:var(--dim)">'+(on?'— 복잡한 일은 숙고(THINK)':'— 반사+바로 실행, 빠름·저렴')+'</span></span>';
    h+='<button data-act="mind" role="switch" aria-checked="'+on+'" title="끄면 THINK(의식) 경로를 차단합니다. 반사(고확신)는 유지." style="position:relative;flex-shrink:0;width:40px;height:20px;border-radius:9999px;border:none;cursor:pointer;background:'+(on?'var(--acc)':'var(--line)')+'">';
    h+='<span style="position:absolute;top:2px;left:'+(on?'22px':'2px')+';width:16px;height:16px;border-radius:9999px;background:#fff;transition:left .15s"></span></button></div>';
  }
  if(gearOpen) h+=renderGearSettings();
  el.innerHTML=h;
}
function renderGearSettings(){
  const g=gearState, tiers=g.tiers||['경량','중급','고급'], axes=g.axis_names||['분류','평가','실행','의식'];
  let h='<div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--line)">';
  h+='<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px"><span style="font-size:12px;font-weight:600">기어 프리셋</span><button data-act="savePresets" style="font-size:11px;padding:3px 10px;border-radius:8px;border:1px solid var(--line);background:var(--bg3);color:var(--txt)">저장</button></div>';
  h+='<table style="width:100%;font-size:11px;border-collapse:collapse"><tr style="color:var(--dim)"><td style="padding:2px 4px">기어</td>';
  axes.forEach(function(ax){ h+='<td style="padding:2px;text-align:center">'+esc(ax)+'</td>'; });
  h+='</tr>';
  Object.keys(gearPresetDraft).forEach(function(gn){
    h+='<tr><td style="padding:3px 4px;font-weight:600">'+esc(gn)+'</td>';
    axes.forEach(function(ax){
      h+='<td style="padding:2px"><select data-act="cell" data-gn="'+esc(gn)+'" data-ax="'+esc(ax)+'" style="width:100%;font-size:11px;padding:2px;background:var(--bg);color:var(--txt);border:1px solid var(--line);border-radius:5px">';
      tiers.forEach(function(t){ h+='<option'+((gearPresetDraft[gn]||{})[ax]===t?' selected':'')+'>'+esc(t)+'</option>'; });
      h+='</select></td>';
    });
    h+='</tr>';
  });
  h+='</table>';
  h+='<div style="font-size:12px;font-weight:600;margin:12px 0 6px">에이전트 핀 — 특정 에이전트만 고정</div><div style="max-height:200px;overflow-y:auto">';
  gearAgents.forEach(function(a){
    const cur=gearOverrides[a.id]||'';
    h+='<div style="display:flex;align-items:center;justify-content:space-between;gap:8px;padding:3px 0">';
    h+='<span style="font-size:12px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+esc(a.name)+' <span style="color:var(--dim);font-size:10px">'+esc(a.project)+'</span></span>';
    h+='<select data-act="pin" data-id="'+esc(a.id)+'" style="font-size:11px;padding:2px 4px;border-radius:5px;background:'+(cur?'var(--acc)':'var(--bg)')+';color:'+(cur?'#fff':'var(--dim)')+';border:1px solid var(--line)"><option value="">기어 따름</option>';
    tiers.forEach(function(t){ h+='<option'+(cur===t?' selected':'')+' value="'+esc(t)+'">📌 '+esc(t)+'</option>'; });
    h+='</select></div>';
  });
  h+='</div></div>';
  return h;
}
async function setGearTo(name){
  try{ const r=await jfetch('/model-gear',{method:'PUT',body:JSON.stringify({gear:name})}); if(r.ok){ gearState=await r.json(); renderGear(); } }catch(e){}
}
async function gearToggle(){
  gearOpen=!gearOpen;
  if(gearOpen){
    if(gearState&&gearState.presets) gearPresetDraft=JSON.parse(JSON.stringify(gearState.presets));
    try{ const r=await jfetch('/model-gear/overrides'); if(r.ok){ const d=await r.json(); gearAgents=d.agents||[]; gearOverrides=d.overrides||{}; } }catch(e){}
  }
  renderGear();
}
async function saveGearPresets(){
  try{ const r=await jfetch('/model-gear/presets',{method:'PUT',body:JSON.stringify({presets:gearPresetDraft})}); if(r.ok){ gearState=await r.json(); renderGear(); } }catch(e){}
}
async function setGearPin(id,tier){
  const next=Object.assign({},gearOverrides); if(tier) next[id]=tier; else delete next[id];
  try{ const r=await jfetch('/model-gear/overrides',{method:'PUT',body:JSON.stringify({overrides:next})}); if(r.ok){ const d=await r.json(); gearOverrides=d.overrides||{}; renderGear(); } }catch(e){}
}
async function setConsciousness(enabled){
  try{ const r=await jfetch('/model-gear/consciousness',{method:'PUT',body:JSON.stringify({enabled:enabled})}); if(r.ok){ gearState=await r.json(); renderGear(); } }catch(e){}
}
/* 위임 핸들러 — 인라인 onclick 없이 data-속성으로(따옴표 함정 회피) */
document.addEventListener('click',function(ev){
  const t=ev.target.closest('[data-act]'); if(!t||!document.getElementById('gearLever').contains(t)) return;
  const act=t.getAttribute('data-act');
  if(act==='toggle') gearToggle();
  else if(act==='gear') setGearTo(t.getAttribute('data-g'));
  else if(act==='savePresets') saveGearPresets();
  else if(act==='mind') setConsciousness(!(gearState&&gearState.consciousness_enabled!==false));
});
document.addEventListener('change',function(ev){
  const t=ev.target; if(!t.getAttribute||!document.getElementById('gearLever').contains(t)) return;
  const act=t.getAttribute('data-act');
  if(act==='cell'){ const gn=t.getAttribute('data-gn'),ax=t.getAttribute('data-ax'); if(!gearPresetDraft[gn])gearPresetDraft[gn]={}; gearPresetDraft[gn][ax]=t.value; }
  else if(act==='pin') setGearPin(t.getAttribute('data-id'),t.value);
});

"""

LAUNCHER_SETSURFACE_JS = """/* ===== 표면 토글 ===== */
function setSurface(s){
  surface=s;
  /* 포식은 표면 탭이 아니라 앱모드의 앱 — 탭 하이라이트는 '앱'에 매핑, 탭 없는 표면은 건너뜀 */
  const hl=(s==='forage')?'app':s;
  ['autopilot','manual','app','forage','warehouse'].forEach(k=>{
    const t=document.getElementById('t-'+k); if(t) t.classList.toggle('on',k===hl);
    document.getElementById('p-'+k).classList.toggle('on',k===s);
  });
  if(s==='app' && !appHomeRendered) renderAppHome();
  if(s==='forage' && !fgInit){ fgInit=true; fgNav('board'); }
  if(s==='warehouse') whLoad(WH_LEVEL);
}
"""
