"""원격 런처 웹앱 — 앱 셸 JS(로그인·표면 토글·계기 로직·portalBoot). <script> 시작을 포함.

api_launcher_web.get_launcher_webapp_html() 이 세 조각을 그대로 이어붙인다(바이트 동일 조립).
2026-07-18 모듈화(1500줄 규칙) — api_launcher_web.py 의 단일 문자열에서 verbatim 이동.
"""

LAUNCHER_APP_JS = """<script>
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
  const r=window.__PORTAL
    ? await jfetch(window.__PORTAL.exec,{method:'POST',body:JSON.stringify({code:code})})
    : await jfetch('/ibl/execute',{method:'POST',body:JSON.stringify({code,project_id:'앱모드',project_path:'.'})});
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
async function doLogout(){ try{ await jfetch('/launcher/auth/logout',{method:'POST'}); }catch(e){} location.reload(); }
let IS_PHONE=false;
async function showApp(){
  document.getElementById('login').style.display='none';
  document.getElementById('app').classList.add('on');
  // 자급 컴패니언(폰-로컬)인지 판별 — REMOTE 배지·로그아웃(⏻)·새로고침(↻)은 원격 시나리오
  // 전용이라 폰에선 숨긴다(폰=자기 몸, 로그아웃/원격 새로고침 의미 없음).
  try{ const r=await jfetch('/launcher/config'); if(r.ok){ const c=await r.json();
    IS_PHONE=(c.host==='phone-local');
    if(IS_PHONE){ const b=document.getElementById('surfBadge'); if(b) b.style.display='none';
      const ha=document.getElementById('headerActions'); if(ha) ha.style.display='none'; }
  } }catch(e){}
  apLoad();
  loadPeer(); setInterval(loadPeer, 20000);  /* 다른 몸 연결상태 폴링(계기판) */
  loadGear();  /* 모델 기어 레버(계기판) */
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

/* ===== 표면 토글 ===== */
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
function refreshSurface(){
  if(surface==='autopilot') apLoad();
  else if(surface==='app'){ appBackHome(); appHomeRendered=false; renderAppHome(true); }  /* 매니페스트 강제 재fetch */
  else if(surface==='forage') fgNav('board');
  else if(surface==='warehouse') whLoad(WH_LEVEL);
}

/* ================= 공유창고 (레벨별 폴더 — 소유자 리모컨) =================
   list/remove 는 로그인 세션으로 warehouse-admin 에 그대로 도달. 넣기는 데스크탑처럼
   로컬 경로가 없으므로 파일 바이트를 upload 엔드포인트로 직접 올린다(한 파일 = 한 요청). */
let WH_LEVEL = Number(localStorage.getItem('indiebiz_wh_level')) || 0;
if(!(WH_LEVEL>=0 && WH_LEVEL<=4)) WH_LEVEL = 0;
let whData = null;
function whBytes(n){ if(n<1024)return n+'B'; if(n<1048576)return (n/1024).toFixed(1)+'KB'; if(n<1073741824)return (n/1048576).toFixed(1)+'MB'; return (n/1073741824).toFixed(2)+'GB'; }
function whIcon(name){ const e=(name.split('.').pop()||'').toLowerCase();
  if(/^(mp4|mov|avi|mkv|webm)$/.test(e))return '🎬'; if(/^(mp3|m4a|wav|flac|ogg)$/.test(e))return '🎵';
  if(/^(zip|tar|gz|7z|rar)$/.test(e))return '🗜️'; if(/^(md|txt|pdf|docx?|hwp|xlsx|csv|pptx?)$/.test(e))return '📄'; return '📁'; }
/* 소유자 열람 URL — 세션 쿠키로 도달. 사진 표시·동영상 재생(비호환 코덱은 서버가 H.264 변환)·텍스트 열람. */
function whFileUrl(name){ return API+'/portal/warehouse-admin/file?level='+WH_LEVEL+'&name='+encodeURIComponent(name); }
function whErr(m){ const e=document.getElementById('whErr'); if(!e)return;
  if(m){ e.textContent=m; e.style.display=''; } else e.style.display='none'; }
async function whLoad(lv){
  WH_LEVEL = lv; localStorage.setItem('indiebiz_wh_level', String(lv));
  whErr('');
  try{
    const r=await jfetch('/portal/warehouse-admin/list?level='+lv);
    if(!r.ok){
      /* 폰은 맥 프록시라 집 PC 가 꺼져 있으면 503 — 서버가 준 안내를 그대로 보여준다 */
      let m='HTTP '+r.status;
      try{ const e=await r.json(); if(e&&(e.error||e.detail)) m=e.error||e.detail; }catch(_e){}
      throw new Error(m);
    }
    whData=await r.json(); whRender();
  }catch(e){ whErr('불러오기 실패: '+e.message); }
}
function whRender(){
  const d=whData; if(!d) return;
  document.getElementById('whTitle').textContent=d.title||'공유창고';
  const url=document.getElementById('whUrl');
  if(d.public_url){ url.href=d.public_url; url.textContent=d.public_url.replace(/^https?:\\/\\//,''); url.style.display=''; }
  else url.style.display='none';
  /* 레벨 탭 */
  const lv=document.getElementById('whLevels'); let h='';
  /* 레벨=0~4 숫자일 뿐 — 의미(누가 몇인지)는 사용자가 정한다. 이름표 붙이지 않음 */
  for(let i=0;i<=4;i++){ const cnt=(d.levels&&d.levels[String(i)])||0;
    h+='<button class="wh-lv'+(i===WH_LEVEL?' on':'')+'" onclick="whLoad('+i+')">'
      +'<span>레벨 '+i+'</span><span class="cnt">'+cnt+'</span></button>'; }
  lv.innerHTML=h;
  /* 파일 목록 */
  const list=document.getElementById('whList'); const files=d.files||[];
  if(!files.length){ list.innerHTML='<div class="wh-empty">📦 비어 있어요<br>＋ 파일 올리기 · ＋ 폴더 올리기로 이 레벨 창고에 넣으세요</div>'; return; }
  list.innerHTML=whRenderNode(whTree(files));
}
/* 창고 안 상대경로("매매/망의 시대.txt")를 폴더 트리로 되접는다. 임의 깊이.
   표시만 파일명으로 짧아지고, 열기·내려받기·빼기의 키는 전체 경로 f.name 그대로. */
function whTree(files){
  const root={dirs:{}, files:[]};
  for(const f of files){
    const parts=f.name.split('/'); let node=root;
    for(const seg of parts.slice(0,-1)){
      if(!node.dirs[seg]) node.dirs[seg]={dirs:{}, files:[]};
      node=node.dirs[seg];
    }
    node.files.push({f:f, label:parts[parts.length-1]});
  }
  return root;
}
/* 폴더 요약 = 하위 전체 개수·크기 + 가장 최근 mtime(폴더 정렬 키 — 목록이 최신순이므로) */
function whAgg(node){
  let count=node.files.length;
  let bytes=node.files.reduce((s,x)=>s+(x.f.bytes||0),0);
  let mtime=node.files.reduce((m,x)=>(x.f.mtime>m?x.f.mtime:m),'');
  for(const k in node.dirs){ const a=whAgg(node.dirs[k]);
    count+=a.count; bytes+=a.bytes; if(a.mtime>mtime) mtime=a.mtime; }
  return {count:count, bytes:bytes, mtime:mtime};
}
/* 파일 먼저(최신순 — 백엔드 정렬 유지), 폴더 나중(안에서 가장 최근 것 순) */
function whRenderNode(node){
  let h=node.files.map(x=>whFileRow(x.f, x.label)).join('');
  const names=Object.keys(node.dirs).sort((a,b)=>
    whAgg(node.dirs[b]).mtime>whAgg(node.dirs[a]).mtime?1:-1);
  for(const name of names){
    const sub=node.dirs[name]; const a=whAgg(sub);
    h+='<details class="wh-fd"><summary>'
      +'<span class="tw">▶</span><span class="ic">📁</span>'
      +'<span class="tx"><div class="nm">'+esc(name)+'</div>'
      +'<div class="mt">'+a.count+'개 · '+whBytes(a.bytes)+'</div></span></summary>'
      +'<div class="kids">'+whRenderNode(sub)+'</div></details>';
  }
  return h;
}
function whFileRow(f, label){
  const enc=encodeURIComponent(f.name);
  const url=whFileUrl(f.name);           /* 열기 = 사진 표시·동영상 재생·텍스트 열람 */
  const isImg=/\\.(jpe?g|png|gif|webp)$/i.test(f.name);
  const thumb=isImg
    ? '<img src="'+url+'" onerror="this.style.display=\\'none\\'">'
    : '<span class="ic">'+whIcon(f.name)+'</span>';
  return '<div class="wh-item">'
    +'<a class="op" href="'+url+'" target="_blank" rel="noopener">'+thumb+'</a>'
    +'<a class="tx op" href="'+url+'" target="_blank" rel="noopener" title="'+esc(f.name)+'">'
    +'<div class="nm">'+esc(label!==undefined?label:f.name)+'</div>'
    +'<div class="mt">'+whBytes(f.bytes)+' · '+esc((f.mtime||'').replace('T',' '))+'</div></a>'
    +'<a class="dl" href="'+url+'&download=1" download title="내려받기">⬇</a>'
    +'<button class="rm" title="빼기 (휴지통으로 이동 — 복구 가능)" onclick="whRemove(\\''+enc+'\\')">🗑</button></div>';
}
async function whUpload(files){
  if(!files||!files.length) return;
  const arr=Array.from(files); const busy=document.getElementById('whBusy');
  whErr('');
  let ok=0, fail=0;
  for(let i=0;i<arr.length;i++){
    const f=arr[i]; busy.textContent='올리는 중… '+(i+1)+'/'+arr.length;
    /* 폴더 올리기면 webkitRelativePath 가 "사진/2024/a.jpg" — 그 구조 그대로 창고에 만든다.
       (f.path 는 drop 으로 걸어 들어온 항목이 채워 넣는 같은 뜻의 필드) */
    const rel=f.webkitRelativePath||f._relPath||f.name;
    try{
      const r=await fetch(API+'/portal/warehouse-admin/upload?level='+WH_LEVEL+'&filename='+encodeURIComponent(rel),
        {method:'POST', headers:{'Content-Type':f.type||'application/octet-stream'}, body:f});
      if(!r.ok){ let m='HTTP '+r.status; try{ const e=await r.json(); if(e&&e.detail) m=e.detail; }catch(_e){} throw new Error(m); }
      ok++;
    }catch(e){ fail++; whErr(esc(rel)+' 실패: '+e.message); }
  }
  busy.textContent='';
  document.getElementById('whFile').value='';
  const dirIn=document.getElementById('whDir'); if(dirIn) dirIn.value='';
  await whLoad(WH_LEVEL);
  if(fail && !ok) whErr(fail+'건 업로드 실패');
}
async function whRemove(nameEnc){
  const name=decodeURIComponent(nameEnc);
  try{
    await jfetch('/portal/warehouse-admin/remove',{method:'POST',body:JSON.stringify({level:WH_LEVEL,name:name})});
  }catch(e){ /* 재조회가 진실 */ }
  whLoad(WH_LEVEL);
}

/* ===== 공유창고 — 이웃 탭 (창고 피드: 등기부 + 타임라인 + 전수 파일명 검색) =====
   백엔드 /warehouse-feed/* — 폴러(30분 주기, AI·토큰 0)가 쌓은 걸 읽는다.
   클릭 = 이웃의 공개 창고(/·/f?path=)가 새 탭으로 — 이웃 쪽 표면 재사용, 신규 0. */
let WH_TAB='mine'; let wfNb=[]; let wfCands=[]; let wfItems=[]; let wfResults=null; let wfShown=[];
/* 피드 필터 — 두 독립 축: 내가 이웃에게 준 레벨(접근 계약) + 내가 창고에 준 즐겨찾기
   점수(평가 — 레벨 비대칭과 무관하게 내가 정함). 레벨·점수=숫자, 의미 라벨 없음. */
let wfMinLv=0; let wfMinScore=0;
function wfSetLv(v){ wfMinLv=parseInt(v,10)||0; wfLoad(); }
function wfSetSc(v){ wfMinScore=parseInt(v,10)||0; wfLoad(); }
/* 즐겨찾기 점수(0~3) — 칩의 별을 누르면 순환. 키=창고 url(창고=주소가 정체). */
async function wfScore(i){
  const n=wfNb[i]; if(!n) return;
  try{ await jfetch('/warehouse-feed/score',{method:'POST',
    body:JSON.stringify({url:n.warehouse_url,score:((n.score||0)+1)%4})}); }
  catch(e){ /* 재조회가 진실 */ }
  wfLoad();
}
function whTab(t){ WH_TAB=t;
  document.getElementById('whTabMine').classList.toggle('on', t==='mine');
  document.getElementById('whTabNb').classList.toggle('on', t==='nb');
  document.getElementById('whTabDs').classList.toggle('on', t==='ds');
  document.getElementById('whMine').style.display = (t==='mine'?'':'none');
  document.getElementById('whNb').style.display = (t==='nb'?'':'none');
  document.getElementById('whDs').style.display = (t==='ds'?'':'none');
  document.getElementById('whAddBtn').style.display = (t==='mine'?'':'none');
  if(t==='nb') wfLoad();
  if(t==='ds') wdLoad();
}
function whRefresh(){ if(WH_TAB==='mine') whLoad(WH_LEVEL); else if(WH_TAB==='ds') wdLoad(); else wfPoll(); }
/* 소개발행 — 비즈니스 계기에서 이동(2026-07-19): "나를 알리기"는 창고의 일. 소유자 셸 전용. */
async function whIntro(){
  if(!confirm('공개 인사 프로필과 공개 창고 주소를 #IndieNet 에 발행할까요? (명함 kind:0 + 발견 노트 kind:1)')) return;
  const b=document.getElementById('whIntroBtn'); if(b){ b.disabled=true; b.textContent='발행 중…'; }
  try{
    const r=await ibl('[self:business_document]{op: "publish"}');
    alert((r&&r.message)||'소개를 발행했어요.');
  }catch(e){ alert('소개발행 실패: '+e); }
  if(b){ b.disabled=false; b.textContent='🌐 소개발행'; }
}
/* ===== 이웃찾기 — #IndieNet 발견 노트(소개발행의 수신면) =====
   데이터=[others:feed]{op:"read"} (활성 보드 #indienet, IndieNet 창과 동일). 소개 본문의
   "공유창고 : <url>" 라벨(indienet_publish.publish_intro 계약)을 파싱해 창고이웃 등록으로 잇는다. */
let wdItems=[]; let wdAdded={};
async function wdLoad(){
  const l=document.getElementById('wdList'); if(!l) return;
  if(!wdItems.length) l.innerHTML='<div class="wh-empty">📡 릴레이에서 소개를 모으는 중…</div>';
  try{
    const r=await ibl('[others:feed]{op: "read", limit: 50}');
    if(r&&r.error) throw new Error(r.error);
    /* 보드 통화는 채팅방 관례(과거→최신) — 게시판형 목록은 최신 글이 맨 위 */
    wdItems=((r&&r.items)||[]).slice().reverse();
    wdRender();
  }catch(e){ l.innerHTML='<div class="wh-empty">불러오기 실패: '+esc(String(e))+'</div>'; }
}
function wdLinkify(h){ return String(h||'').replace(/https?:\\/\\/[^\\s<]+/g,
  u=>'<a href="'+u+'" target="_blank" rel="noopener" style="color:var(--acc);word-break:break-all">'+u+'</a>'); }
function wdWh(c){
  const t=String(c||'');
  /* 계약: "공유창고 Warehouse : <url>" (한/영 병기). 키워드 게이트 — 공유창고와 warehouse
     **둘 다** 있어야 창고 글(정식 발행=항상 병기, 잡담에 한쪽만 나오면 무시). 라벨 형식 아니면 마지막 URL 폴백. */
  if(!(/공유창고/.test(t) && /warehouse/i.test(t))) return null;
  const m=t.match(/(?:공유창고|warehouse)[^\\n]*?:\\s*(https?:\\/\\/\\S+)/i); if(m) return m[1];
  const urls=t.match(/https?:\\/\\/\\S+/g);
  return (urls&&urls.length)?urls[urls.length-1]:null;
}
function wdRender(){
  const l=document.getElementById('wdList'); if(!l) return;
  if(!wdItems.length){ l.innerHTML='<div class="wh-empty">아직 소개가 없어요 — 🌐 소개발행으로 나를 알려보세요</div>'; return; }
  l.innerHTML='<div class="wf-more">#IndieNet 게시판 — 소개도 대화도 여기서. 공유창고 Warehouse 병기 표시가 있는 글은 그 자리에서 창고이웃 등록 (정식 소개는 🌐 소개발행)</div>'
    +wdItems.map((it,i)=>{
    const wh=wdWh(it.content);
    const btns=wh?('<div style="margin-top:6px;display:flex;gap:8px">'
      +'<a class="wf-go" style="text-decoration:none" target="_blank" rel="noopener" href="'+esc(wh)+'">📦 창고 열기</a>'
      +(wdAdded[wh]?'<button class="wf-go" disabled>등록됨</button>'
                   :'<button class="wf-go" onclick="wdAdd('+i+')">＋ 창고이웃 등록</button>')
      +'</div>'):'';
    return '<div class="wh-item" style="display:block">'
      +'<div class="mt">'+esc(it.author||'')+' · '+esc(it.time||'')+'</div>'
      +'<div style="white-space:pre-wrap;word-break:break-word;margin-top:4px">'+wdLinkify(esc(it.content||''))+'</div>'
      +btns+'</div>';
  }).join('');
}
async function wdAdd(i){
  const it=wdItems[i]; const wh=it&&wdWh(it.content); if(!wh) return;
  try{
    /* npub 동봉 — 서버가 창고+nostr 두 접점을 한 이웃에 모으고 신원 기준 중복을 막는다 */
    await jfetch('/warehouse-feed/neighbors/add',{method:'POST',body:JSON.stringify({url:wh, npub:(it.author_full||'')})});
    wdAdded[wh]=true; wdRender();
    alert('창고이웃으로 등록했어요 — 이웃 탭 피드에 이 창고의 소식이 흐릅니다.');
  }catch(e){ alert('등록 실패: '+e); }
}
/* 게시판처럼 한마디 — 커뮤니티 계기와 같은 [others:feed]{op:"post"} 경로. 내용=JSON.stringify 이스케이프. */
async function wdPost(){
  const inp=document.getElementById('wdDraft'); const btn=document.getElementById('wdPostBtn');
  const t=(inp&&inp.value||'').trim(); if(!t) return;
  if(btn){ btn.disabled=true; btn.textContent='게시 중…'; }
  try{
    const r=await ibl('[others:feed]{op: "post", content: '+JSON.stringify(t)+'}');
    if(r&&(r.error||r.success===false)) throw new Error(r.error||r.message||'게시 실패');
    if(inp) inp.value='';
    await wdLoad();
  }catch(e){ alert('게시 실패: '+e); }
  if(btn){ btn.disabled=false; btn.textContent='게시'; }
}
function wfErr(m){ const e=document.getElementById('wfErr'); if(!e)return;
  if(m){ e.textContent=m; e.style.display=''; } else e.style.display='none'; }
async function wfLoad(){
  wfErr('');
  try{
    const [rn,rf]=await Promise.all([jfetch('/warehouse-feed/neighbors'),
      jfetch('/warehouse-feed/feed?limit=100&min_level='+wfMinLv+'&min_score='+wfMinScore)]);
    if(!rn.ok||!rf.ok) throw new Error('HTTP '+rn.status+'/'+rf.status);
    const dn=await rn.json(), df=await rf.json();
    wfNb=dn.neighbors||[]; wfCands=dn.candidates||[]; wfItems=df.items||[]; wfResults=null;
    const qi=document.getElementById('wfQ'); if(qi) qi.value='';
    wfRender();
  }catch(e){ wfErr('불러오기 실패: '+e.message); }
}
function wfRender(){
  const bar=document.getElementById('wfNeighbors'); let h='';
  wfNb.forEach((n,i)=>{
    const st = n.ok===0 ? '<span class="err">연결 안 됨</span>'
                        : '<span class="cnt">'+(n.file_count==null?'?':n.file_count)+'개</span>';
    const ad = (n.adapter && n.adapter!=='native')
      ? '<span class="cnt" style="background:#e0f2fe;color:#0284c7" title="창고 방언 — indiebizOS 창고가 아닌 표면(색인·RSS·Nextcloud·페이지)을 어댑터가 읽어옵니다">'+esc(n.adapter_label||n.adapter)+'</span>' : '';
    /* 회원 로그인 — 계정으로 폴링하면 승급받은 레벨의 파일까지 피드에 들어온다 */
    const lg = (n.login_user && n.login_ok===1)
      ? '<span class="cnt" style="background:#d1fae5;color:#059669" title="'+esc(n.login_user)+' 계정으로 폴링 중 — 이 창고가 나에게 준 레벨">레벨 '+(n.viewer_level==null?'?':n.viewer_level)+'</span>'
      : ((n.login_user && n.login_ok===0)
      ? '<span class="err" title="'+esc(n.login_error||'')+'">로그인 실패</span>' : '');
    const kb = (!n.adapter || n.adapter==='native')
      ? '<button title="이 창고에 내가 가입한 계정 등록 — 폴러가 로그인해 승급받은 레벨로 읽어요" onclick="wfLogin('+i+')">🔑</button>' : '';
    /* 즐겨찾기 점수 별 — 누르면 0→1→2→3 순환. 내 평가라 상대에겐 안 보인다. */
    const sc=(n.score||0);
    h+='<span class="wh-chip">'
      +'<button title="즐겨찾기 점수 '+sc+' — 누르면 0→1→2→3 순환 (피드·검색 필터가 씁니다)"'
      +(sc>0?' style="color:#B45309"':'')+' onclick="wfScore('+i+')">'+(sc>0?'★'+sc:'☆')+'</button>'
      +'<a href="'+esc(n.warehouse_url)+'/" target="_blank" rel="noopener" title="'+esc(n.warehouse_memo||'창고 열기')+'">'+esc(n.name)+'</a>'
      +st+ad+lg+kb
      +'<button title="창고 메모" onclick="wfMemo('+n.neighbor_id+')">✎</button>'
      +'<button title="등기부에서 떼기 (이웃은 남고 창고 연락처만 지움)" onclick="wfRemove('+n.contact_id+')">✕</button></span>';
  });
  h+='<button class="wh-chip" style="border-style:dashed;background:none;color:var(--dim);cursor:pointer" onclick="wfToggleAdd()">＋ 창고이웃 등록</button>';
  h+='<span style="flex:1"></span>';
  h+='<select class="wf-go" title="이 레벨 이상의 이웃이 보낸 소식만" onchange="wfSetLv(this.value)">'
    +[0,1,2,3,4].map(l=>'<option value="'+l+'"'+(wfMinLv===l?' selected':'')+'>'+(l===0?'모든 레벨':'레벨 '+l+' 이상')+'</option>').join('')
    +'</select>';
  h+='<select class="wf-go" title="내가 준 즐겨찾기 점수(이상)의 창고만 — 점수는 이웃 칩의 별로 줍니다"'
    +(wfMinScore>0?' style="color:#B45309;border-color:#D97706"':'')+' onchange="wfSetSc(this.value)">'
    +[0,1,2,3].map(s=>'<option value="'+s+'"'+(wfMinScore===s?' selected':'')+'>'+(s===0?'즐겨찾기 무관':'★'+s+' 이상')+'</option>').join('')
    +'</select>';
  h+='<button class="wf-go" title="모든 이웃 창고를 지금 둘러보기 (평소엔 30분마다 자동)" onclick="wfPoll()">↻ 지금 둘러보기</button>';
  bar.innerHTML=h;
  const sel=document.getElementById('wfCand');
  sel.innerHTML='<option value="">새 이웃으로…</option>'+wfCands.map(c=>'<option value="'+c.id+'">기존 이웃: '+esc(c.name)+'</option>').join('');
  const list=document.getElementById('wfFeed'); const items=(wfResults!=null?wfResults:wfItems);
  wfShown=[];   /* 리트윗 대상(파일)만 렌더 순서대로 — 접힌 줄 안의 파일도 여기 들어간다 */
  if(!wfNb.length){ list.innerHTML='<div class="wh-empty">📡 창고이웃이 아직 없어요<br>＋ 창고이웃 등록으로 이웃의 창고 주소를 넣으면<br>창고의 변화가 여기로 흘러옵니다</div>'; return; }
  if(!items.length){ list.innerHTML='<div class="wh-empty">'+(wfResults!=null?'검색 결과가 없어요':'아직 새 소식이 없어요')+'</div>'; return; }
  list.innerHTML=items.map(f=>f.group?wfGroupRow(f):wfFileRow(f)).join('');
}
/* 폴더 단위로 접힌 줄 — 이웃이 폴더 하나 올린 걸 N 연속 소식이 아니라 한 줄로.
   원장은 파일 단위 그대로고 표현만 접힌다(warehouse_feed._group_feed). */
function wfGroupRow(g){
  const shown=g.items||[]; const rest=(g.count||shown.length)-shown.length;
  const kind=g.kind==='new'?'<span class="wf-kind">새 파일 '+g.count+'개</span>'
    :(g.kind==='changed'?'<span class="wf-kind" style="color:var(--dim)">갱신 '+g.count+'개</span>'
                        :'<span class="wf-kind" style="color:var(--dim)">'+g.count+'개</span>');
  return '<details class="wh-fd"><summary>'
    +'<span class="tw">▶</span><span class="ic">📁</span>'
    +'<span class="tx"><div class="nm">'+esc(g.folder)+'</div>'
    +'<div class="mt">'+kind+'<span style="color:var(--acc)">'+esc(g.neighbor_name)+'</span> · '
    +whBytes(g.bytes||0)+' · '+esc((g.mtime||'').replace('T',' '))+'</div></span>'
    +'<a class="dl" href="'+esc(g.neighbor_home||'#')+'" target="_blank" rel="noopener" title="'+esc(g.neighbor_name)+'의 창고 열기">📦</a>'
    +'</summary><div class="kids">'
    +shown.map(f=>wfFileRow(Object.assign({}, f,
        {neighbor_name:g.neighbor_name, neighbor_home:g.neighbor_home}), f.path.split('/').pop())).join('')
    +(rest>0?'<div class="wf-more">외 '+rest+'개 — 창고를 열어 전부 보기</div>':'')
    +'</div></details>';
}
function wfFileRow(f, label){
  const i=wfShown.push(f)-1;      /* 리트윗은 이 인덱스로 원본 항목을 찾는다 */
  const kind=f.kind==='new'?'<span class="wf-kind">새 파일</span>'
    :(f.kind==='changed'?'<span class="wf-kind" style="color:var(--dim)">갱신</span>':'');
  return '<div class="wh-item">'
    +'<span class="ic">'+whIcon(f.path)+'</span>'
    +'<div class="tx">'
    +'<a class="op" style="display:block" href="'+esc(f.url)+'" target="_blank" rel="noopener" title="'+esc(f.path)+'"><div class="nm">'+esc(label!==undefined?label:f.path)+'</div></a>'
    +'<div class="mt">'+kind+'<span style="color:var(--acc)">'+esc(f.neighbor_name)+'</span> · '+whBytes(f.bytes||0)+' · '+esc((f.mtime||'').replace('T',' '))+'</div>'
    +'</div>'
    +'<a class="dl" href="'+esc(f.url)+'" target="_blank" rel="noopener" title="파일 열기">↗</a>'
    +'<a class="dl" href="'+esc(f.neighbor_home||'#')+'" target="_blank" rel="noopener" title="'+esc(f.neighbor_name)+'의 창고 열기">📦</a>'
    +'<button class="rm" title="좋아요 — 카운트는 파일 주인에게 쌓입니다" onclick="wfLike('+i+',this)">♥'+((f.likes||0)>0?('<span class="lkn">'+f.likes+'</span>'):'<span class="lkn"></span>')+'</button>'
    +'<button class="rm" title="리트윗 — 내 창고 리트윗 폴더에 소개(복사=소장/링크=추천)" onclick="wfRetweet('+i+')">📣</button>'
    +'<a class="dl" href="'+esc(f.url)+(f.url&&f.url.indexOf('?')>=0?'&':'?')+'download=1" title="내려받기">⬇</a>'
    +'</div>';
}
async function wfLike(i,btn){
  const f=(wfShown||[])[i]; if(!f) return;
  try{
    const r=await jfetch('/warehouse-feed/like',{method:'POST',body:JSON.stringify({wh_url:f.wh_url,path:f.path})});
    if(!r.ok){ let m='HTTP '+r.status; try{ const e=await r.json(); if(e&&e.detail) m=e.detail; }catch(_e){} throw new Error(m); }
    const d=await r.json(); f.likes=d.count;
    const s=btn.querySelector('.lkn'); if(s) s.textContent=d.count>0?d.count:'';
    btn.style.color=d.liked?'#d63384':'';
  }catch(e){ wfErr('좋아요 실패: '+e.message); }
}
async function wfRetweet(i){
  const f=(wfShown||[])[i]; if(!f) return;
  /* 레벨=0~4 숫자일 뿐, 의미는 사용자가 정한다 */
  const lvRaw=prompt("'"+f.path+"' 을(를) 내 창고 어느 레벨(0~4)의 리트윗 폴더에 소개할까요?", '0');
  if(lvRaw===null) return;
  const lv=parseInt(lvRaw,10);
  if(!(lv>=0 && lv<=4)){ wfErr('레벨은 0~4 숫자여야 해요'); return; }
  /* 확인=복사(파일 소장, 내 창고가 재서빙) / 취소=링크(포인터, 원 창고 직행) */
  const doCopy=confirm('파일을 복사해 소장할까요?\\n확인=복사(내 창고가 서빙, 원본 꺼져도 생존)\\n취소=링크로만 소개(원 창고 직행)');
  const mode=doCopy?'copy':'link';
  document.getElementById('whBusy').textContent=doCopy?'파일을 내 창고로 복사하는 중…':'내 창고에 소개하는 중…';
  try{
    const r=await jfetch('/warehouse-feed/retweet',{method:'POST',body:JSON.stringify({url:f.url,name:f.path,level:lv,mode:mode,warehouse:f.wh_url||''})});
    if(!r.ok){ let m='HTTP '+r.status; try{ const e=await r.json(); if(e&&e.detail) m=e.detail; }catch(_e){} throw new Error(m); }
  }catch(e){ wfErr('리트윗 실패: '+e.message); }
  document.getElementById('whBusy').textContent='';
}
function wfToggleAdd(){ const r=document.getElementById('wfAddRow');
  r.style.display = (r.style.display==='none'?'':'none'); }
async function wfAdd(){
  const cand=document.getElementById('wfCand').value;
  const name=document.getElementById('wfName').value.trim();
  const url=document.getElementById('wfUrl').value.trim();
  if(!url){ wfErr('창고 주소가 필요해요 (이름은 비우면 창고 제목으로)'); return; }
  const body={url:url}; if(cand) body.neighbor_id=Number(cand); else if(name) body.name=name;
  document.getElementById('whBusy').textContent='창고 등록·첫 폴링 중…';
  try{
    const r=await jfetch('/warehouse-feed/neighbors/add',{method:'POST',body:JSON.stringify(body)});
    if(!r.ok){ let m='HTTP '+r.status; try{ const e=await r.json(); if(e&&e.detail) m=e.detail; }catch(_e){} throw new Error(m); }
    document.getElementById('wfName').value=''; document.getElementById('wfUrl').value='';
    document.getElementById('wfAddRow').style.display='none';
  }catch(e){ wfErr(e.message); }
  document.getElementById('whBusy').textContent='';
  wfLoad();
}
async function wfRemove(contactId){
  try{ await jfetch('/warehouse-feed/neighbors/remove',{method:'POST',body:JSON.stringify({contact_id:contactId})}); }
  catch(e){ /* 재조회가 진실 */ }
  wfLoad();
}
async function wfMemo(id){
  const n=wfNb.find(x=>x.neighbor_id===id);
  const memo=prompt('창고 메모 — 이 창고에 뭐가 사는지 적어두면 나중에 어느 이웃부터 볼지 압니다', (n&&n.warehouse_memo)||'');
  if(memo===null) return;
  try{ await jfetch('/warehouse-feed/neighbors/memo',{method:'POST',body:JSON.stringify({neighbor_id:id,memo:memo})}); }
  catch(e){ /* 재조회가 진실 */ }
  wfLoad();
}
async function wfLogin(i){
  const n=wfNb[i]; if(!n) return;
  const uid=prompt('내 계정 아이디 — 가입은 창고 홈에서 (비우고 확인=로그인 해제)', n.login_user||'');
  if(uid===null) return;
  let pw='';
  if(uid.trim()){ pw=prompt('비밀번호'); if(pw===null) return; }
  document.getElementById('whBusy').textContent='로그인 확인 중…';
  try{
    const r=await jfetch('/warehouse-feed/credentials',{method:'POST',
      body:JSON.stringify({url:n.warehouse_url,user_id:uid.trim(),password:pw})});
    const d=await r.json();
    if(uid.trim() && !(d&&d.ok)) alert('로그인 실패: '+((d&&d.error)||'원인 미상'));
  }catch(e){ alert('로그인 확인 실패: '+e); }
  document.getElementById('whBusy').textContent='';
  wfLoad();
}
async function wfPoll(){
  document.getElementById('whBusy').textContent='이웃 창고 둘러보는 중…';
  try{ await jfetch('/warehouse-feed/poll',{method:'POST',body:'{}'}); }catch(e){}
  document.getElementById('whBusy').textContent='';
  wfLoad();
}
async function wfSearch(v){
  const t=(v||'').trim();
  if(!t){ wfResults=null; wfRender(); return; }
  try{
    /* 필터(레벨·즐겨찾기)는 검색에도 같은 신뢰 축으로 적용 — 컨트롤이 같은 화면에 있다 */
    const r=await jfetch('/warehouse-feed/search?q='+encodeURIComponent(t)
      +'&min_level='+wfMinLv+'&min_score='+wfMinScore);
    const d=await r.json(); wfResults=d.items||[]; wfRender();
  }catch(e){ /* 검색 실패는 조용히 */ }
}

/* ================= 자율주행 (드릴다운) ================= */
let apAgents=[]; let apAgProject=null;
async function apLoad(){ await apLoadProjects(); await apLoadSwitches(); apBrowseRoot(); }
async function apLoadProjects(){
  try{ const r=await jfetch('/projects'); if(r.ok){ const d=await r.json(); apProjects=d.projects||[]; } }catch(e){}
}
async function apLoadSwitches(){
  try{ const r=await jfetch('/switches'); if(r.ok){ const d=await r.json(); apSwitches=d.switches||[]; } }catch(e){}
}
function apShowBrowse(){ document.getElementById('ap-browse').style.display=''; document.getElementById('ap-chat').style.display='none'; }
function apShowChat(){ document.getElementById('ap-browse').style.display='none'; document.getElementById('ap-chat').style.display='flex'; }
function apCard(ic,nm,ds,onclick,chev){
  return '<div class="ap-card" onclick="'+onclick+'"><span class="ic">'+ic+'</span>'+
    '<span class="tx"><span class="nm">'+esc(nm)+'</span>'+(ds?'<span class="ds">'+esc(ds)+'</span>':'')+'</span>'+
    (chev?'<span class="chev">›</span>':'')+'</div>';
}
/* ① 루트: 시스템 AI / 스위치 / 프로젝트 */
function apBrowseRoot(){
  apShowBrowse();
  document.getElementById('ap-bhead').style.display='none';
  let h='<h3>시스템</h3>';
  h+=apCard('🤖','시스템 AI','IndieBiz OS 전체를 관리','apPickSystem()',false);
  // 스위치는 폰-자아엔 불필요(사용자 결정) — 폰에선 숨기고 원격/맥에선 노출.
  if(!IS_PHONE) h+=apCard('⚡','스위치','원클릭 자동화 실행','apBrowseSwitches()',true);
  h+=apCard('⏰','스케줄','반복 작업 보기·삭제','apBrowseSchedules()',true);
  h+='<h3>프로젝트 '+apProjects.length+'</h3>';
  h+='<button class="ap-newbtn" onclick="apProjectCreate()">＋ 프로젝트 만들기</button>';
  h+=apProjects.map(p=>
    '<div class="ap-card" onclick="apBrowseProject(\\''+esc(p.id)+'\\')"><span class="ic">'+(p.icon||'📁')+'</span>'+
    '<span class="tx"><span class="nm">'+esc(p.name)+'</span><span class="ds">에이전트 선택</span></span>'+
    '<span class="chev">›</span>'+
    '<button class="btn2 danger" onclick="event.stopPropagation();apProjectDelete(\\''+esc(p.id)+'\\',\\''+esc(p.name)+'\\')">🗑</button></div>'
  ).join('');
  document.getElementById('apBrowse').innerHTML=h;
}
/* 프로젝트 생성/삭제 — POST/DELETE /projects 는 catch-all 로 맥 (패리티) */
async function apProjectCreate(){
  const name=(prompt('새 프로젝트 이름:')||'').trim(); if(!name) return;
  try{ const r=await jfetch('/projects',{method:'POST',body:JSON.stringify({name,template_name:'기본'})});
    if(r.ok){ await apLoadProjects(); apBrowseRoot(); }
    else{ const d=await r.json().catch(()=>({})); alert('생성 실패: '+(d.error||d.detail||r.status)); }
  }catch(e){ alert('오류: '+e.message); }
}
async function apProjectDelete(id,name){
  if(!confirm('"'+name+'" 프로젝트를 삭제할까요? (에이전트·대화 모두 삭제)')) return;
  try{ const r=await jfetch('/projects/'+encodeURIComponent(id),{method:'DELETE'});
    if(r.ok){ await apLoadProjects(); apBrowseRoot(); }
    else{ const d=await r.json().catch(()=>({})); alert('삭제 실패: '+(d.error||d.detail||r.status)); }
  }catch(e){ alert('오류: '+e.message); }
}
/* ①-b 프로젝트 드릴 → 에이전트 전체 목록 (옛 ags[0] 자동선택 버그 제거) */
async function apBrowseProject(pid){
  const p=apProjects.find(x=>x.id===pid); if(!p) return;
  try{
    const r=await jfetch('/projects/'+encodeURIComponent(pid)+'/agents');
    if(!r.ok){ alert('에이전트 로드 실패'); return; }
    const d=await r.json(); apAgents=d.agents||[]; apAgProject=p;
    if(!apAgents.length){ alert('이 프로젝트에 에이전트가 없습니다.'); return; }
    apShowBrowse();
    document.getElementById('ap-bhead').style.display='flex';
    document.getElementById('apBrowseTitle').textContent=p.name;
    document.getElementById('apBrowse').innerHTML='<h3>에이전트 '+apAgents.length+'</h3>'+
      '<button class="ap-newbtn" onclick="apAgentCreate(\\''+esc(pid)+'\\')">＋ 에이전트 추가</button>'+
      apAgents.map((a,i)=>
        '<div class="ap-card" onclick="apPickAgent('+i+')"><span class="ic">👤</span>'+
        '<span class="tx"><span class="nm">'+esc(a.name)+'</span><span class="ds">'+esc((a.role||'').substring(0,48)||'에이전트')+'</span></span>'+
        '<button class="btn2 danger" onclick="event.stopPropagation();apAgentDelete(\\''+esc(pid)+'\\',\\''+esc(a.id)+'\\',\\''+esc(a.name)+'\\')">🗑</button></div>'
      ).join('');
  }catch(e){ alert('에이전트 로드 실패'); }
}
/* 에이전트 생성/삭제 — POST/DELETE /projects/{id}/agents 는 catch-all 로 맥 (패리티) */
async function apAgentCreate(pid){
  const name=(prompt('새 에이전트 이름:')||'').trim(); if(!name) return;
  const role=(prompt('역할 설명 (선택):')||'').trim();
  try{ const r=await jfetch('/projects/'+encodeURIComponent(pid)+'/agents',{method:'POST',body:JSON.stringify({name,role})});
    if(r.ok){ apBrowseProject(pid); }
    else{ const d=await r.json().catch(()=>({})); alert('생성 실패: '+(d.error||d.detail||r.status)); }
  }catch(e){ alert('오류: '+e.message); }
}
async function apAgentDelete(pid,aid,name){
  if(!confirm('"'+name+'" 에이전트를 삭제할까요?')) return;
  try{ const r=await jfetch('/projects/'+encodeURIComponent(pid)+'/agents/'+encodeURIComponent(aid),{method:'DELETE'});
    if(r.ok){ apBrowseProject(pid); }
    else{ const d=await r.json().catch(()=>({})); alert('삭제 실패: '+(d.error||d.detail||r.status)); }
  }catch(e){ alert('오류: '+e.message); }
}
/* ①-c 스위치 목록 (+ 생성/삭제 — 맥 패리티) */
function apBrowseSwitches(){
  apShowBrowse();
  document.getElementById('ap-bhead').style.display='flex';
  document.getElementById('apBrowseTitle').textContent='스위치';
  const box=document.getElementById('apBrowse');
  let h='<button class="ap-newbtn" onclick="apSwitchForm()">＋ 스위치 만들기</button>';
  if(!apSwitches.length){ h+='<p class="muted" style="padding:24px;text-align:center">스위치가 없습니다</p>'; }
  else { h+='<h3>스위치 '+apSwitches.length+'</h3>'+apSwitches.map(s=>
    '<div class="ap-card"><span class="ic">⚡</span><span class="tx"><span class="nm">'+esc(s.name)+'</span><span class="ds">'+esc((s.prompt||s.command||'').substring(0,50))+'</span></span>'+
    '<button class="btn2" onclick="apRunSwitch(\\''+esc(s.id)+'\\',this)">실행</button>'+
    '<button class="btn2 danger" onclick="apSwitchDelete(\\''+esc(s.id)+'\\',\\''+esc(s.name)+'\\')">🗑</button></div>'
  ).join(''); }
  box.innerHTML=h;
}
/* 스위치 생성 폼 (이름+명령+프로젝트→에이전트). POST /switches 는 catch-all 로 맥. */
function apSwitchForm(){
  const box=document.getElementById('apBrowse');
  const projOpts=apProjects.map(p=>'<option value="'+esc(p.id)+'">'+esc(p.name)+'</option>').join('');
  box.innerHTML='<h3>새 스위치</h3><div class="ap-form">'+
    '<label>이름</label><input id="swName" placeholder="예: 아침 뉴스 브리핑">'+
    '<label>명령 (프롬프트)</label><textarea id="swCmd" rows="3" placeholder="이 스위치가 실행할 지시"></textarea>'+
    '<label>프로젝트</label><select id="swProj" onchange="apSwitchLoadAgents()">'+projOpts+'</select>'+
    '<label>에이전트</label><select id="swAgent"><option>로딩…</option></select>'+
    '<div class="ap-form-row"><button class="btn2" onclick="apBrowseSwitches()">취소</button>'+
    '<button class="go" onclick="apSwitchCreate()">만들기</button></div></div>';
  apSwitchLoadAgents();
}
async function apSwitchLoadAgents(){
  const ps=document.getElementById('swProj'); if(!ps) return;
  const sel=document.getElementById('swAgent'); sel.innerHTML='<option>로딩…</option>';
  try{ const r=await jfetch('/projects/'+encodeURIComponent(ps.value)+'/agents'); const d=await r.json();
    sel.innerHTML=(d.agents||[]).map(a=>'<option value="'+esc(a.name)+'">'+esc(a.name)+'</option>').join('')||'<option value="">(에이전트 없음)</option>';
  }catch(e){ sel.innerHTML='<option value="">(로드 실패)</option>'; }
}
async function apSwitchCreate(){
  const name=(document.getElementById('swName').value||'').trim();
  const command=(document.getElementById('swCmd').value||'').trim();
  const projectId=document.getElementById('swProj').value;
  const agentName=document.getElementById('swAgent').value;
  if(!name||!command){ alert('이름과 명령을 입력하세요'); return; }
  try{
    const r=await jfetch('/switches',{method:'POST',body:JSON.stringify({name,command,config:{projectId,agentName},icon:'⚡'})});
    if(r.ok){ await apLoadSwitches(); apBrowseSwitches(); }
    else{ const d=await r.json().catch(()=>({})); alert('생성 실패: '+(d.error||d.detail||r.status)); }
  }catch(e){ alert('오류: '+e.message); }
}
async function apSwitchDelete(id,name){
  if(!confirm('"'+name+'" 스위치를 삭제할까요?')) return;
  try{
    const r=await jfetch('/switches/'+encodeURIComponent(id),{method:'DELETE'});
    if(r.ok){ await apLoadSwitches(); apBrowseSwitches(); }
    else{ const d=await r.json().catch(()=>({})); alert('삭제 실패: '+(d.error||d.detail||r.status)); }
  }catch(e){ alert('오류: '+e.message); }
}
/* ①-d 스케줄 목록 (반복 트리거 보기·삭제 — self:trigger op:list/delete via /ibl/execute).
   trigger_engine 은 폰 로컬 번들이라 이 자아의 스케줄(대화처럼 자아별 사적)을 보여준다. */
function apScheduleWhen(cfg){
  cfg=cfg||{};
  if(cfg.interval_minutes) return cfg.interval_minutes+'분마다';
  const rep=cfg.repeat||cfg.frequency||''; const time=cfg.time||'';
  if(rep==='daily') return '매일 '+time;
  if(rep==='weekly') return '매주 '+time;
  if(rep) return rep+' '+time;
  if(time) return time;
  try{ return JSON.stringify(cfg); }catch(e){ return '예약'; }
}
async function apBrowseSchedules(){
  apShowBrowse();
  document.getElementById('ap-bhead').style.display='flex';
  document.getElementById('apBrowseTitle').textContent='스케줄';
  const box=document.getElementById('apBrowse');
  box.innerHTML='<p class="muted" style="padding:20px;text-align:center">불러오는 중…</p>';
  try{
    const r=await jfetch('/ibl/execute',{method:'POST',body:JSON.stringify({code:'[self:trigger]{op: "list", type: "schedule"}'})});
    const d=await r.json(); const trigs=d.triggers||[];
    if(!trigs.length){ box.innerHTML='<p class="muted" style="padding:24px;text-align:center;line-height:1.7">반복 스케줄이 없습니다.<br><span style="font-size:13px">시스템 AI에게 "매일 아침 9시에 뉴스 알려줘"처럼 말해 만들 수 있어요.</span></p>'; return; }
    box.innerHTML='<h3>반복 스케줄 '+trigs.length+'</h3>'+trigs.map(t=>{
      const en=t.enabled!==false;
      return '<div class="ap-card"><span class="ic">'+(en?'⏰':'⏸️')+'</span>'+
        '<span class="tx"><span class="nm">'+esc(t.name||t.id)+'</span><span class="ds">'+esc(apScheduleWhen(t.config))+' · '+esc((t.pipeline||'').substring(0,38))+'</span></span>'+
        '<button class="btn2 danger" onclick="apScheduleDelete(\\''+esc(t.id)+'\\',\\''+esc(t.name||t.id)+'\\')">🗑</button></div>';
    }).join('');
  }catch(e){ box.innerHTML='<p class="muted" style="padding:24px;text-align:center">불러오기 실패: '+esc(e.message)+'</p>'; }
}
async function apScheduleDelete(id,name){
  if(!confirm('"'+name+'" 스케줄을 삭제할까요?')) return;
  try{
    const r=await jfetch('/ibl/execute',{method:'POST',body:JSON.stringify({code:'[self:trigger]{op: "delete", id: "'+id+'"}'})});
    if(r.ok){ apBrowseSchedules(); } else { const d=await r.json().catch(()=>({})); alert('삭제 실패: '+(d.error||d.detail||r.status)); }
  }catch(e){ alert('오류: '+e.message); }
}
/* ② 대상 확정 → 대화/결과 (전체 폭) */
function apPickSystem(){
  apChat={ type:'system', projectId:null, agentId:null, agentName:null };
  apOpenChat('🤖 시스템 AI','IndieBiz OS 전체를 관리합니다');
}
function apPickAgent(i){
  const a=apAgents[i], p=apAgProject; if(!a||!p) return;
  apChat={ type:'agent', projectId:p.id, agentId:a.id, agentName:a.name };
  apOpenChat(p.name+' · '+a.name, (a.role||'').substring(0,80));
}
function apOpenChat(title,sub){
  document.getElementById('apTitle').textContent=title;
  document.getElementById('apSub').textContent=sub||'';
  document.getElementById('apMsgs').innerHTML='<div class="empty">메시지를 입력해 시작하세요.</div>';
  apShowChat();
  apLoadHistory();  // 시스템 AI·에이전트 모두 과거 대화 자동 로드(연속성)
  setTimeout(()=>{ try{ document.getElementById('apInput').focus(); }catch(e){} },50);
}
/* 과거 대화 로드 — 채팅 진입 시 이전 대화를 버블로 표시.
   시스템 AI=/system-ai/conversations / 에이전트=/conversations/{pid}/{aid}/messages (맥/폰 공통) */
async function apLoadHistory(){
  try{
    let convs=[];
    if(apChat.type==='system'){
      const r=await jfetch('/system-ai/conversations?limit=40'); if(!r.ok) return;
      convs=((await r.json()).conversations||[]).map(m=>({role:(m.role==='user')?'user':'assistant', content:m.content||''}));
    }else if(apChat.type==='agent'){
      const r=await jfetch('/conversations/'+encodeURIComponent(apChat.projectId)+'/'+encodeURIComponent(apChat.agentId)+'/messages?limit=40');
      if(!r.ok) return;
      const msgs=((await r.json()).messages||[]).slice().reverse();  // DESC → 시간순
      convs=msgs.map(m=>({role:(m.is_agent===true)?'assistant':'user', content:m.content||''}));
    }else return;
    if(!convs.length) return;  // 이력 없으면 안내문 유지
    const c=document.getElementById('apMsgs'); c.innerHTML='';
    convs.forEach(m=>{ apAddMsg(m.role, m.content); });
    const sep=document.createElement('div'); sep.className='ap-hist-sep'; sep.textContent='― 여기부터 새 대화 ―';
    c.appendChild(sep); c.scrollTop=c.scrollHeight;
  }catch(e){}
}
function apExitChat(){ apBrowseRoot(); }
async function apRunSwitch(id,btn){
  btn.disabled=true; btn.textContent='실행 중...';
  try{ const r=await jfetch('/switches/'+encodeURIComponent(id)+'/execute',{method:'POST'}); alert(r.ok?'스위치를 실행했습니다':'실행 실패'); }
  catch(e){ alert('오류: '+e.message); }
  finally{ btn.disabled=false; btn.textContent='실행'; }
}
function apAddMsg(role,text){
  const c=document.getElementById('apMsgs');
  const ph=c.querySelector('.empty'); if(ph) ph.remove();
  const el=document.createElement('div'); el.className='msg '+role;
  el.innerHTML='<div class="av">'+(role==='user'?'🧑':'🤖')+'</div><div class="bub">'+(role==='user'?esc(text):mdChat(text))+'</div>';
  c.appendChild(el); c.scrollTop=c.scrollHeight;
}
function apKey(e){ if(e.key==='Enter'&&!e.shiftKey){ e.preventDefault(); apSend(); } }
/* 어시스턴트(에이전트/시스템AI 발신) 메시지를 {id,content} 배열(시간순)로 — 폴링용.
   시스템 AI=/system-ai/conversations(role==assistant), 에이전트=/conversations/.../messages(from==agent).
   id 를 마커로 쓰는 이유: limit 윈도가 슬라이딩하면 개수 비교는 신규 메시지를 놓칠 수 있다. */
async function apAssistantMsgs(){
  if(apChat.type==='system'){
    const r=await jfetch('/system-ai/conversations?limit=40');
    if(!r.ok) return null;
    return ((await r.json()).conversations||[]).filter(m=>m.role==='assistant').map(m=>({id:m.id,content:m.content||''}));
  }else{
    const r=await jfetch('/conversations/'+encodeURIComponent(apChat.projectId)+'/'+encodeURIComponent(apChat.agentId)+'/messages?limit=40');
    if(!r.ok) return null;
    const msgs=((await r.json()).messages||[]).slice().reverse();  // DESC → 시간순
    return msgs.filter(m=>m.is_agent===true).map(m=>({id:m.id,content:m.content||''}));
  }
}
function apMaxId(arr){ let mx=0; (arr||[]).forEach(m=>{ if(m.id>mx) mx=m.id; }); return mx; }
function apSleep(ms){ return new Promise(res=>setTimeout(res,ms)); }
/* 백그라운드 명령의 답을 대화 DB 폴링으로 회수. baselineId 보다 큰 id의 어시스턴트 메시지가
   나타나면 그 내용 반환. 각 폴링은 짧은 요청이라 터널 100초 타임아웃에 안 걸린다. 최대 ~10분. */
async function apPollAssistant(baselineId,bub){
  const dots=['작업 중…','작업 중… ·','작업 중… · ·','작업 중… · · ·'];
  for(let i=0;i<200;i++){
    await apSleep(i<6?1500:3000);  // 짧은 답은 빨리, 긴 작업은 느슨하게
    if(bub) bub.textContent=dots[i%dots.length];
    let a; try{ a=await apAssistantMsgs(); }catch(e){ continue; }  // 일시 오류는 넘김
    if(a==null) continue;
    const fresh=a.filter(m=>m.id>baselineId);
    if(fresh.length) return fresh[fresh.length-1].content;
  }
  return '⏳ 아직 처리 중입니다. 잠시 후 대화를 다시 열어 확인해 주세요.';
}
async function apSend(){
  const inp=document.getElementById('apInput'); const msg=inp.value.trim(); if(!msg) return;
  apAddMsg('user',msg); inp.value='';
  const btn=document.getElementById('apSend'); btn.disabled=true;
  apAddMsg('assistant','…'); const last=document.getElementById('apMsgs').lastChild.querySelector('.bub');
  try{
    // 시스템 AI·에이전트 공통: 영상 생성처럼 수 분짜리 작업이 Cloudflare 터널 100초 타임아웃(524)에
    // 걸려 "실패"로 보이던 문제 해결 — 백그라운드로 보내고(즉시 반환) 대화 DB를 폴링해 답을 받는다.
    const baselineId=apMaxId(await apAssistantMsgs());
    let r;
    if(apChat.type==='system'){
      r=await jfetch('/system-ai/chat',{method:'POST',body:JSON.stringify({message:msg,background:true})});
    }else{
      await jfetch('/projects/'+encodeURIComponent(apChat.projectId)+'/agents/'+encodeURIComponent(apChat.agentId)+'/start',{method:'POST'});
      r=await jfetch('/projects/'+encodeURIComponent(apChat.projectId)+'/agents/'+encodeURIComponent(apChat.agentId)+'/command',{method:'POST',body:JSON.stringify({command:msg,background:true})});
    }
    if(!r.ok){ const d=await r.json().catch(()=>({})); last.textContent='['+r.status+'] '+(d.detail||'오류'); return; }
    last.textContent='작업 중…';
    last.innerHTML=mdChat(await apPollAssistant(baselineId,last));
  }catch(e){ last.textContent='연결 오류: '+e.message; }
  finally{ btn.disabled=false; }
}

/* ================= 수동 ================= */
let mLastIntent='', mLastScore=0;
function resetManualFrom(stage){
  if(stage<=3) document.getElementById('mAfterValidate').style.display='none';
  if(stage<=4) document.getElementById('mAfterExecute').style.display='none';
}
async function mTranslate(){
  const intent=document.getElementById('mIntent').value.trim(); if(!intent) return;
  mLastIntent=intent;
  const btn=document.getElementById('mTransBtn'); btn.disabled=true; btn.textContent='…';
  resetManualFrom(2); document.getElementById('mAfterTranslate').style.display='none';
  try{
    const r=await jfetch('/ibl/translate',{method:'POST',body:JSON.stringify({intent})});
    const d=await r.json();
    document.getElementById('mCode').value=d.ibl_code||d.raw||'';
    document.getElementById('mRefs').textContent=d.references||'(참고 용례 없음)';
    document.getElementById('mAfterTranslate').style.display='block';
  }catch(e){ alert('번역 실패: '+e.message); }
  finally{ btn.disabled=false; btn.textContent='번역'; }
}
function toggleRefs(){ const b=document.getElementById('mRefs'); b.style.display=b.style.display==='block'?'none':'block'; }
async function mValidate(){
  const code=document.getElementById('mCode').value.trim(); if(!code) return;
  const btn=document.getElementById('mValBtn'); btn.disabled=true; btn.textContent='검수 중…';
  resetManualFrom(4);
  try{
    const r=await jfetch('/ibl/validate',{method:'POST',body:JSON.stringify({code})});
    const d=await r.json();
    const box=document.getElementById('mSteps');
    if(!d.valid){
      box.innerHTML='<div class="eff write"><div class="h">⚠ 구문 오류</div><div class="e">'+esc(d.syntax_error||'알 수 없는 오류')+'</div></div>';
      document.getElementById('mSideWarn').innerHTML='';
      document.getElementById('mExecBtn').disabled=true;
      document.getElementById('mAfterValidate').style.display='block';
      return;
    }
    const steps=d.steps||[];
    box.innerHTML=steps.map(s=>{
      const sf=s.safety||'unknown';
      return '<div class="eff '+sf+'"><div class="h"><span class="pill s-'+sf+'">'+sf+'</span>['+esc(s.node)+':'+esc(s.action)+']</div>'+
        '<div class="e">'+esc(s.effect||'(설명 없음)')+'</div></div>';
    }).join('');
    if(d.has_side_effect){
      document.getElementById('mSideWarn').innerHTML=
        '<label class="warnbox"><input type="checkbox" id="mConfirm" onchange="document.getElementById(\\'mExecBtn\\').disabled=!this.checked"><span><b>부작용(쓰기/외부 전송)이 있는 액션</b>입니다. 실행하면 되돌릴 수 없을 수 있습니다. 확인 후 체크하세요.</span></label>';
      document.getElementById('mExecBtn').disabled=true;
    }else{
      document.getElementById('mSideWarn').innerHTML='';
      document.getElementById('mExecBtn').disabled=false;
    }
    document.getElementById('mAfterValidate').style.display='block';
  }catch(e){ alert('검수 실패: '+e.message); }
  finally{ btn.disabled=false; btn.textContent='검수 (dry-run)'; }
}
async function mExecute(){
  const code=document.getElementById('mCode').value.trim(); if(!code) return;
  const btn=document.getElementById('mExecBtn'); btn.disabled=true; btn.textContent='실행 중…';
  try{
    const r=await jfetch('/ibl/execute',{method:'POST',body:JSON.stringify({code,project_id:'수동모드',project_path:'.'})});
    const d=await r.json();
    document.getElementById('mResult').textContent=JSON.stringify(d,null,2);
    document.getElementById('mDistillMsg').textContent='';
    document.getElementById('mDistillBtn').disabled=false;
    document.getElementById('mAfterExecute').style.display='block';
    document.getElementById('mAfterExecute').scrollIntoView({behavior:'smooth',block:'nearest'});
  }catch(e){ alert('실행 실패: '+e.message); }
  finally{ btn.disabled=false; btn.textContent='실행'; }
}
async function mDistill(){
  const code=document.getElementById('mCode').value.trim();
  const btn=document.getElementById('mDistillBtn'); btn.disabled=true;
  try{
    const r=await jfetch('/ibl/distill',{method:'POST',body:JSON.stringify({intent:mLastIntent,code,top_score:mLastScore})});
    const d=await r.json();
    document.getElementById('mDistillMsg').textContent=d.distilled?'✓ 해마에 학습되었습니다':('학습 안 함'+(d.reason?' — '+d.reason:''));
  }catch(e){ document.getElementById('mDistillMsg').textContent='학습 실패: '+e.message; btn.disabled=false; }
}
/* 둘러보기 팔레트 */
let paletteLoaded=false;
function closeAbout(){ const a=document.getElementById('mAbout'); if(a) a.style.display='none'; const b=document.getElementById('btnAbout'); if(b) b.classList.remove('on'); }
function closePalette(){ const p=document.getElementById('palette'); if(p) p.style.display='none'; const b=document.getElementById('btnDict'); if(b) b.classList.remove('on'); }
async function togglePalette(){
  const p=document.getElementById('palette');
  const open = p.style.display==='none';
  closeAbout();
  if(open){ p.style.display='block'; document.getElementById('btnDict').classList.add('on'); if(!paletteLoaded) await loadPalette(); }
  else closePalette();
}
function toggleAbout(){
  const a=document.getElementById('mAbout');
  const open = a.style.display==='none';
  closePalette();
  a.style.display = open?'block':'none';
  document.getElementById('btnAbout').classList.toggle('on', open);
}
async function loadPalette(){
  const p=document.getElementById('palette'); p.innerHTML='<div class="center"><div class="spin"></div></div>';
  try{
    const r=await jfetch('/ibl/actions/catalog'); const d=await r.json();
    const nodes=d.nodes||{}; let html='<input class="field" placeholder="액션 검색..." oninput="filterPalette(this.value)" style="margin-bottom:10px">';
    html+='<div id="palette-list">';
    for(const node in nodes){
      const acts=nodes[node].actions||{};
      html+='<div class="cat-node" data-node="'+esc(node)+'"><h4>'+esc(node)+'</h4>';
      for(const a in acts){
        const seed='['+node+':'+a+']{}';
        html+='<span class="act-chip" data-key="'+esc((node+' '+a).toLowerCase())+'" onclick="seedAction(\\''+esc(seed)+'\\')">'+esc(a)+'</span>';
      }
      html+='</div>';
    }
    html+='</div>'; p.innerHTML=html; paletteLoaded=true;
  }catch(e){ p.innerHTML='<p class="muted">카탈로그 로드 실패</p>'; }
}
function filterPalette(q){
  q=(q||'').toLowerCase().trim();
  document.querySelectorAll('#palette-list .act-chip').forEach(c=>{
    c.style.display=(!q||c.dataset.key.indexOf(q)>=0)?'inline-block':'none';
  });
}
function seedAction(seed){
  document.getElementById('mCode').value=seed;
  document.getElementById('mAfterTranslate').style.display='block';
  document.getElementById('mCode').focus();
  document.getElementById('palette').scrollIntoView({behavior:'smooth',block:'nearest'});
}

/* ================= 앱 (제네릭 렌더러 — /launcher/instruments 매니페스트 해석) ================= */
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
async function renderAppHome(force){
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
function appBackHome(){
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
