/* ----- 뷰 렌더 (순수 함수: view+data → HTML 문자열) ----- */

/* ----- 동적 필터(filter.from_field): 결과-필드 distinct 칩 + 클라이언트 측 거르기(재조회 없음).
       distinct 수집·거르기 자체는 공용 렌더 코어(dynFilterCats/applyDynFilter)가 정본. ----- */



/* 비분할 모드 본문 = 동적필터 칩 + (필터 적용된) 뷰 + 작성바. runMode/mapViewEvent/setCatFilter 공유. */

function setCatFilter(v){
  CUR.catFilter=v;
  if(!VIEW_CTX||VIEW_CTX.refresh!=='mode') return;
  // 인터랙티브 지도 viewport 보존 — 재렌더가 지도를 재생성하므로(데스크탑은 map 유지라 불필요)
  for(const k in _LMAPS){ const m=_LMAPS[k];
    try{ if(m&&m.getContainer&&document.body.contains(m.getContainer())) _mapKeepView={c:m.getCenter(),z:m.getZoom()}; }catch(e){} }
  const out=document.getElementById('instOut'); if(!out) return;
  out.innerHTML=renderModeBody(CUR.mode,VIEW_CTX.data); initMaps();
}
/* 추세 방향(trendUp)·빈 결과 문구(emptyText)는 공용 렌더 코어가 정본 — 여기선 색·마크업만 */


/* media_player continuous — 끝난 곡의 다음 audio(data-mp)를 자동 재생 (데스크탑 onEnded 파리티).
   곡은 그 플레이어 묶음(data-mp-group) 안에서만 찾는다 — 문서 전체를 뒤지면 한 화면에
   플레이어가 둘일 때 옆 묶음으로 넘어간다(데스크탑은 이미 group 단위). */
function mpGroup(el){ return (el&&el.closest&&el.closest('[data-mp-group]'))||null; }
function mpList(g){ return Array.prototype.slice.call((g||document).querySelectorAll('audio[data-mp]')); }
function mpPlay(a){ if(!a) return; a.play().catch(function(){}); a.scrollIntoView({block:'nearest'}); }
function mpNext(el){
  const g=mpGroup(el), all=mpList(g), cur=all.indexOf(el);
  /* 🔀 랜덤이 켜져 있으면 다음 순서 대신 섞은 자루가 고른 곡 — 규칙은 공용 코어(shuffleNext)가 정본. */
  if(g&&g.dataset.mpShuffle==='1'){
    const r=shuffleNext(all.length,cur,g.__mpPlayed||[]);
    g.__mpPlayed=r.played;
    if(r.index>=0) mpPlay(all[r.index]);
    return;
  }
  mpPlay(all[cur+1]);
}
/* 🔀 랜덤 토글 — 켜면 그 자리에서 무작위 한 곡으로 재생을 옮긴다. 끄는 순간엔 재생 중인 곡을
   건드리지 않고 다음 곡부터 순서로 돌아간다(듣던 곡이 끊기는 것이 더 놓란다). */
function mpShuffle(btn){
  const g=mpGroup(btn); if(!g) return;
  const on=g.dataset.mpShuffle!=='1';
  g.dataset.mpShuffle=on?'1':'0';
  btn.textContent=on?'🔀 랜덤 켜짐':'🔀 랜덤';
  if(!on) return;
  const all=mpList(g);
  let cur=-1; for(let i=0;i<all.length;i++) if(!all[i].paused) cur=i;
  const r=shuffleNext(all.length,cur,[]);
  g.__mpPlayed=r.played;
  if(r.index>=0) mpPlay(all[r.index]);
}
/* 지도 render 프리미티브 — leaflet. innerHTML 후 initMaps()로 지연 초기화.
   봉투: route_map{origin,destination,path:[[lat,lng]],summary} | location_map{center,markers:[{name,lat,lng}]}.
   spec: {type:'map', from:'map_data'(봉투 위치), markers:'cctvs'(추가 마커, 옵션)} */
var _MAP_QUEUE={}, _mapSeq=0, _LMAPS={};
/* 뷰-이벤트 페이로드 잔류($변수) — 데스크탑 ModePane.values 와 같은 뜻(selection 등 keep 규약). */
var VIEW_VARS={};
// 인터랙티브 지도(on:) — _mapProg=프로그래매틱 이동(fitBounds/setView) 가드(재조회 피드백 루프 차단),
// _mapKeepView=재조회 재렌더 너머 viewport 보존(데스크탑 didFit 가드의 원격판).
var _mapProg=false, _mapKeepView=null;
/* 뷰-이벤트(map moveend/marker_click) → 액션 재조회 후 현재 모드 view 재렌더. viewport 는 _mapKeepView 로 보존. */
async function mapViewEvent(tpl,payload){
  Object.assign(VIEW_VARS,payload||{});
  if(!tpl||tpl==='keep'||!VIEW_CTX) return;
  const vals=Object.assign({},gatherInputs(),payload);
  let d; try{ d=await ibl(actionRequest(CUR.mode,tpl,vals)); }catch(e){ return; }
  if(!d||d.error||d.success===false) return;
  VIEW_CTX.data=d;
  const out=document.getElementById('instOut'); if(!out) return;
  // 모드 뷰면 동적필터 재적용(새 결과 → catFilter 초기화), 드릴 뷰면 그대로.
  if(VIEW_CTX.refresh==='mode'){ CUR.catFilter=null; out.innerHTML=renderModeBody(CUR.mode,d); }
  else out.innerHTML=renderView(VIEW_CTX.view,d)+renderComposeBar(VIEW_CTX.compose);
  initMaps();
}
/* "이 지역에서 검색" — 현재 지도 뷰포트(중심·반경)로 search_here 템플릿 재조회. viewport 는 _mapKeepView 로 보존. */
function mapSearchHere(id){
  const map=_LMAPS[id]; if(!map||!map._searchHere) return;
  const c=map.getCenter(); _mapKeepView={c:c,z:map.getZoom()};
  const r=Math.round(map.distance(c,map.getBounds().getNorthEast()));
  mapViewEvent(map._searchHere,{lat:Number(c.lat.toFixed(6)),lng:Number(c.lng.toFixed(6)),radius:r,radius_km:Number((r/1000).toFixed(2))});
}
/* 지도가 세로 스와이프를 먹어 페이지 스크롤을 막는 문제 해결:
   기본은 dragging(한 손가락 패닝) 끔 → 한 손가락 스와이프는 페이지 스크롤로 통과.
   핀치 줌(touchZoom)은 그대로(두 손가락이라 스크롤과 충돌 없음). 패닝이 필요하면 토글로 켠다. */
function toggleMapDrag(id,btn){
  const map=_LMAPS[id]; if(!map) return;
  if(map.dragging.enabled()){ map.dragging.disable(); btn.textContent='🔓 지도 이동'; btn.classList.remove('on'); }
  else { map.dragging.enable(); btn.textContent='🔒 스크롤'; btn.classList.add('on'); }
}
function initMaps(){
  if(typeof L==='undefined') return;
  // 재렌더로 DOM 에서 분리된 옛 지도 정리 — 누수 + 분리된 지도의 moveend 핸들러가 전역 가드 간섭하는 것 방지.
  for(const k in _LMAPS){ const mp=_LMAPS[k];
    try{ if(!mp||!mp.getContainer||!document.body.contains(mp.getContainer())){ if(mp&&mp.remove) mp.remove(); delete _LMAPS[k]; } }
    catch(e){ delete _LMAPS[k]; } }
  for(const id in _MAP_QUEUE){
    const el=document.getElementById(id); if(!el||el._inited) continue;
    el._inited=true; const spec=_MAP_QUEUE[id]; delete _MAP_QUEUE[id];
    try{
      const map=L.map(id,{attributionControl:false,dragging:false});  // 한 손가락 패닝 끔(페이지 스크롤 통과). 토글로 켬.
      _LMAPS[id]=map;
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19}).addTo(map);
      const B=[]; const md=spec.md||{};
      if(md.path&&md.path.length){
        L.polyline(md.path,{color:'#e11d48',weight:5,opacity:0.85}).addTo(map);
        md.path.forEach(ll=>B.push(ll));
        if(md.origin){ L.marker([md.origin.lat,md.origin.lng]).addTo(map).bindPopup('출발 · '+esc(md.origin.name||'')); B.push([md.origin.lat,md.origin.lng]); }
        if(md.destination){ L.marker([md.destination.lat,md.destination.lng]).addTo(map).bindPopup('도착 · '+esc(md.destination.name||'')); B.push([md.destination.lat,md.destination.lng]); }
      }
      (md.markers||[]).forEach(m=>{ if(m.lat==null||m.lng==null) return; L.marker([m.lat,m.lng]).addTo(map).bindPopup(esc(m.name||'')); B.push([m.lat,m.lng]); });
      // marker_click: IBL 템플릿(문자열·재조회) | {stream:true}(마커 url 영상 재생, IBL 없음·_mapKeepView 안 건드림) | 없음(팝업+▶영상버튼).
      const clickSpec=spec.on&&spec.on.marker_click;
      const clickStream=clickSpec&&typeof clickSpec==='object'&&clickSpec.stream;
      const clickTpl=(typeof clickSpec==='string')?clickSpec:null;
      (spec.markers||[]).forEach(m=>{ if(m.lat==null||m.lng==null) return;
        const mk=L.marker([m.lat,m.lng]).addTo(map); const nm=m.name||m.title||'마커';
        if(clickStream){
          if(m.url){ const i=_streamUrls.push(m.url)-1; mk.on('click',()=>playStream(i)); }
          else mk.bindPopup('<b>'+esc(nm)+'</b>');
        } else if(clickTpl){
          mk.on('click',()=>{ _mapKeepView={c:map.getCenter(),z:map.getZoom()};
            mapViewEvent(clickTpl,{id:m.id==null?'':m.id,name:String(nm),lat:m.lat,lng:m.lng,url:m.url==null?'':String(m.url)}); });
        } else {
          let btn='';
          if(m.url){ const i=_streamUrls.push(m.url)-1; btn='<br><button class="go" style="margin-top:6px;padding:4px 12px" onclick="playStream('+i+')">▶ 영상</button>'; }
          mk.bindPopup('<b>'+esc(nm)+'</b>'+btn);
        }
        B.push([m.lat,m.lng]); });
      // 인터랙티브(on:)면 viewport 보존(첫 로드만 fit)·재조회 피드백 가드. 정적이면 매번 fit(기존 동작).
      if(spec.on&&_mapKeepView){ _mapProg=true; map.setView(_mapKeepView.c,_mapKeepView.z); _mapKeepView=null; }
      else if(B.length){ if(spec.on) _mapProg=true; map.fitBounds(B,{padding:[28,28],maxZoom:15}); }
      else if(md.center&&md.center.lat!=null){ if(spec.on) _mapProg=true; map.setView([md.center.lat,md.center.lng],13); }
      else map.setView([37.4979,127.0276],11);
      if(spec.on){
        map._searchHere=spec.on.search_here||null;  // "이 지역에서 검색" 버튼(mapSearchHere)이 읽는다
        const moveTpl=spec.on.moveend||spec.on.center_drag;
        if(moveTpl) map.on('moveend',()=>{ if(_mapProg){ _mapProg=false; return; } // 프로그래매틱 이동 무시
          if(map._reqT) clearTimeout(map._reqT);
          map._reqT=setTimeout(()=>{ const c=map.getCenter(); _mapKeepView={c:c,z:map.getZoom()};
            const r=Math.round(map.distance(c,map.getBounds().getNorthEast()));
            mapViewEvent(moveTpl,{lat:Number(c.lat.toFixed(6)),lng:Number(c.lng.toFixed(6)),radius:r,radius_km:Number((r/1000).toFixed(2))}); },600); });
        setTimeout(()=>{ _mapProg=false; },500); // fit 이 moveend 안 내도 가드 해제(백업)
      }
      setTimeout(()=>map.invalidateSize(),60);
    }catch(e){ el.innerHTML='<p class="muted">지도 로드 실패</p>'; }
  }
}
/* 달력 render 프리미티브 — 월 그리드 + 선택일 상세(시간·반복·삭제) + 정기목록 + add.fields 폼.
   그리드=none(연월)·monthly(항상)·yearly(월-일); daily/weekly/interval=정기목록. 타입색=color_field.
   add.fields=form 필드 어휘(date 자동 주입). 데스크탑 CalendarPrim 과 동일 어휘. 전역 _calCur 로 단순화. */
var _calCur=null, _calState={y:null,m:null,sel:null};
var _CAL_COLOR={birthday:'#f472b6',anniversary:'#fb7185',holiday:'#f87171',meeting:'#60a5fa',task:'#fbbf24',report:'#a78bfa',schedule:'#2dd4bf'};
var _CAL_REPEAT={daily:'매일',weekly:'매주',monthly:'매월',yearly:'매년',interval:'주기'};
function _calColor(e,field){ return _CAL_COLOR[String((e||{})[field||'type']||'')]||'#a8a29e'; }
function _calAddField(f){ const id='calAdd_'+f.key;
  if(f.type==='select') return '<select class="field" id="'+id+'" style="min-width:0"><option value="">'+esc(f.placeholder||'')+'</option>'+(f.options||[]).map(o=>'<option value="'+esc(String(o.value))+'">'+esc(o.label)+'</option>').join('')+'</select>';
  if(f.type==='recurrence') return _recurSelect(id,'');
  if(f.type==='date'||f.type==='time'||f.type==='datetime') return '<input type="'+dateInputType(f.type)+'" class="field" style="min-width:0" id="'+id+'">';
  return '<input class="field" style="min-width:0" id="'+id+'" placeholder="'+esc(f.placeholder||'')+'">';
}
function _calSetup(p,data){
  const evs=viewList(data,p.from||'items');  // 전 이벤트(정기=날짜없음 포함). 필터는 draw 에서.
  const now=new Date();
  _calCur={prim:p, events:evs,
    y:(_calState.y!=null?_calState.y:now.getFullYear()),
    m:(_calState.m!=null?_calState.m:now.getMonth()),
    sel:_calState.sel};
}
function _calDraw(){
  const host=document.getElementById('calHost'); if(!host||!_calCur) return;
  const c=_calCur, y=c.y, m=c.m, cf=c.prim.color_field||'type';
  // 월 산식(일자 매핑·정기 분리·말일)은 공용 렌더 코어가 정본. 코어는 month 를 1-12 로 센다.
  const _cm=calendarModel(c.events,y,m+1);
  const byDay=_cm.byDay, first=_cm.firstWeekday, days=_cm.daysInMonth;
  let h='<div class="card"><div class="row" style="align-items:center;justify-content:space-between">'
    +'<button class="iconbtn" onclick="_calNav(-1)">◀</button><b>'+y+'년 '+(m+1)+'월</b>'
    +'<button class="iconbtn" onclick="_calNav(1)">▶</button></div><div class="calgrid">';
  ['일','월','화','수','목','금','토'].forEach(w=>{ h+='<div class="calwd">'+w+'</div>'; });
  for(let i=0;i<first;i++) h+='<div></div>';
  for(let d=1;d<=days;d++){ const hs=byDay[d]?' calhas':'', sl=(c.sel===d)?' calsel':'';
    h+='<div class="calday'+hs+sl+'" onclick="_calPick('+d+')">'+d+(byDay[d]?'<span class="caldot" style="background:'+_calColor(byDay[d][0],cf)+'"></span>':'')+'</div>'; }
  h+='</div>';
  if(c.sel){ const list=byDay[c.sel]||[]; c._dayList=list;
    h+='<div class="calpanel"><div class="step-label">'+y+'-'+pad2(m+1)+'-'+pad2(c.sel)+'</div>';
    if(list.length) list.forEach((e,i)=>{ const tm=e.time?' <span class="muted" style="font-size:11px">'+esc(e.time)+'</span>':'';
      const rl=(e.repeat&&e.repeat!=='none')?' <span class="muted" style="font-size:11px">'+(_CAL_REPEAT[e.repeat]||e.repeat)+'</span>':'';
      h+='<div class="kv"><span class="k"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;background:'+_calColor(e,cf)+'"></span>'+esc(e.title||'')+tm+rl+'</span>'
      +(c.prim.delete_action?'<button class="linkbtn" onclick="_calDel('+i+')">삭제</button>':'')+'</div>'; });
    else h+='<p class="muted">일정 없음</p>';
    if(c.prim.add){ const fields=c.prim.add.fields||[{key:'title',type:'text',placeholder:'일정 제목'}];
      h+='<div class="row" style="flex-wrap:wrap;margin-top:8px">'+fields.map(_calAddField).join('')+'<button class="go" onclick="_calAdd()">'+esc(c.prim.add.button||'추가')+'</button></div>'; }
    h+='</div>'; }
  const periodic=_cm.recurring;
  if(periodic.length){ h+='<div style="margin-top:12px"><div class="muted" style="font-size:11px;margin-bottom:6px">정기 일정</div><div style="display:flex;flex-wrap:wrap;gap:6px">';
    periodic.forEach(e=>{ h+='<span style="padding:4px 10px;border-radius:999px;border:1px solid var(--line);font-size:12px"><span style="display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:6px;background:'+_calColor(e,cf)+'"></span>'+esc(e.title||'')+' <span class="muted">'+(_CAL_REPEAT[e.repeat]||e.repeat)+(e.time?' '+esc(e.time):'')+'</span></span>'; });
    h+='</div></div>'; }
  h+='</div>'; host.innerHTML=h;
}
function _calNav(delta){ if(!_calCur) return;
  // 월 이동은 공용 코어(calShift, 1-12) — 여기 상태는 0-11 이라 앞뒤로 환산
  const nx=calShift(_calCur.y,_calCur.m+1,delta), y=nx.year, m=nx.month-1;
  _calCur.m=m; _calCur.y=y; _calCur.sel=null;
  _calState.y=y; _calState.m=m; _calState.sel=null; _calDraw(); }
function _calPick(d){ if(!_calCur) return; _calCur.sel=(_calCur.sel===d?null:d); _calState.sel=_calCur.sel; _calDraw(); }
async function _calAdd(){ if(!_calCur||!_calCur.prim.add||!_calCur.sel) return;
  const add=_calCur.prim.add, fields=add.fields||[{key:'title',type:'text'}];
  const vals={}; fields.forEach(f=>{ const el=document.getElementById('calAdd_'+f.key); if(el) vals[f.key]=el.value; });
  if(!String(vals.title||'').trim()){ alert('일정 제목을 입력하세요'); return; }
  vals.date=_calCur.y+'-'+pad2(_calCur.m+1)+'-'+pad2(_calCur.sel);  // 선택일 자동 주입
  try{ await dispatchAction(add.action,vals); }catch(e){ alert('추가 실패: '+e.message); } }
async function _calDel(i){ if(!_calCur||!_calCur._dayList) return; const item=_calCur._dayList[i]; if(!item) return;
  try{ await dispatchAction(_calCur.prim.delete_action,{},item); }catch(e){ alert('삭제 실패: '+e.message); } }


/* ----- 실행/디스패치 ----- */
/* 계기 입력값 영속화(localStorage) — 데스크탑 bespoke 계기가 쓰던 결정화를 제네릭 렌더러에도.
   키=계기id+모드id+입력key 별. 바꾼 키워드 등이 리로드 후에도 유지(이전엔 매번 default로 리셋). */
function _inpLS(instId,modeId,key){ return 'lz.inp.'+instId+'.'+modeId+'.'+key; }
function loadInpVal(instId,modeId,key,def){
  try{ const v=localStorage.getItem(_inpLS(instId,modeId,key)); return (v!=null)?v:(def||''); }catch(e){ return def||''; }
}
function saveInpVals(){
  const m=CUR.mode, inst=CUR.inst; if(!m||!inst) return;
  (m.inputs||[]).forEach(inp=>{ const el=document.getElementById('in_'+inp.key);
    if(el){ try{ localStorage.setItem(_inpLS(inst.id,m.id,inp.key), el.value); }catch(e){} } });
}
function gatherInputs(){
  const vals={};
  (CUR.mode.inputs||[]).forEach(inp=>{ const el=document.getElementById('in_'+inp.key); vals[inp.key]=el?el.value.trim():''; });
  if(CUR.mode.filter&&CUR.filterVal!=null) vals[CUR.mode.filter.key||'filter']=CUR.filterVal;
  if(CUR.inst&&CUR.inst.principal) vals.principal=CUR.inst.principal;  /* $principal — 보고 있는 주체(읽기 전용) */
  saveInpVals();  // 조회 시점에도 현재 값 영속화(onchange 못 탄 경우 안전망)
  return vals;
}
function setFilter(v){
  CUR.filterVal=v;
  document.querySelectorAll('#modeBody .fchip').forEach(b=>b.classList.toggle('on', b.getAttribute('data-v')===String(v)));
  runMode();
}
async function runMode(){
  const mode=CUR.mode; if(!mode||!mode.action||CUR.scopeBusy) return;
  const out=document.getElementById('instOut'); if(!out) return;
  const vals=gatherInputs();
  const missing=requiredInputMessage(mode,mode.action,vals);
  if(missing){ out.innerHTML='<p role="status" class="muted">'+esc(missing)+'</p>'; return; }
  const unlock=lockInstrumentSelection(), owner=CUR;
  out.innerHTML='<div class="center"><div class="spin"></div></div>';
  try{
    const d=await ibl(actionRequest(mode,mode.action,vals));
    if(CUR!==owner || CUR.mode!==mode || document.getElementById('instOut')!==out) return;
    SPLIT=hasMasterDetail(mode.view);   // 공용 코어 — 데스크탑 isSplit 과 같은 판정
    if(SPLIT){
      LIST={view:mode.view,data:d}; VIEW_CTX=null;
      out.innerHTML='<div class="mdsplit" id="mdSplit"><div class="mdlist" id="mdList">'+renderView(mode.view,d)+'</div>'
        +'<div class="mddetail" id="mdDetail"><div class="mdph">← 목록에서 대화를 선택하세요</div></div></div>';
      initMaps();
    } else {
      LIST=null; VIEW_CTX={view:mode.view,data:d,compose:mode.compose,refresh:'mode'}; CUR.catFilter=null;
      out.innerHTML=renderModeBody(mode,d);
      initMaps();
    }
    // 폰: 생성된 HTML(신문 등)을 조회 직후 자동으로 띄운다(별도 '띄우기' 탭 불필요).
    if(IS_PHONE && d && typeof d==='object' && typeof d.file==='string' && /\.html?$/i.test(d.file)) openFileOverlay(d.file, d.html);
  }catch(e){ if(CUR===owner) out.innerHTML='<p class="muted">오류: '+esc(e.message)+'</p>'; }
  finally{ unlock(); }
}
/* 작성바(compose) — $text=작성 내용, 드릴이면 {field}=대화 상대 행 필드. 전송 후 현재 뷰 새로고침. */
/* compose 발신 채널 후보 — 선택 규칙은 공용 렌더 코어(composeChannelOptions)가 정본.
   원격은 현재 렌더 컨텍스트(VIEW_CTX.data)가 곧 드릴 데이터라 그것만 넘긴다. */

/* 현재 렌더 중인 view(탭이면 활성 탭 view, 아니면 모드/드릴 view) */
function activeView(){ return (VIEW_CTX&&(VIEW_CTX._activeView||VIEW_CTX.view))||[]; }

/* 드릴 새로고침 — 드릴이면 드릴 액션 재실행 후 재렌더, 아니면 모드 재실행 */
async function refreshCurrent(){
  if(VIEW_CTX&&VIEW_CTX.refresh==='drill'){
    const target=VIEW_CTX; const nd=await ibl(target.action); if(VIEW_CTX!==target) return;
    if(nd&&typeof nd==='object') nd._item=target.item;
    VIEW_CTX.data=nd; renderDrill();
    /* ★SPLIT(master_detail)이면 왼쪽 목록도 조용히 갱신 — 드릴 폼 저장이 바꾼 값(비즈니스 레벨 등)이
       목록에 바로 반영되게. runMode()는 드릴을 닫으므로 데이터만 다시 당겨 mdList 만 재렌더. */
    if(SPLIT&&LIST&&CUR.mode&&CUR.mode.action){
      try{
        const vals=gatherInputs(); let ok=true;
        for(const inp of (CUR.mode.inputs||[])) if(inp.required&&!vals[inp.key]) ok=false;
        if(ok){
          const md=await ibl(actionRequest(CUR.mode,CUR.mode.action,vals));
          LIST.data=md;
          const ml=document.getElementById('mdList');
          if(ml){ ml.innerHTML=renderView(CUR.mode.view,md); initMaps(); }
        }
      }catch(e){ /* 목록은 다음 조회가 진실 */ }
    }
  } else { runMode(); }
}

/* 액션 실행기: $field 치환 + {path}(rowContext, 기본 현재 데이터) 치환 → 실행 → 새로고침.
   opts.back=true 면 성공 후 새로고침 대신 목록으로 복귀(삭제 등 — 현재 상세가 사라지는 경우). */
async function dispatchAction(template,fieldValues,rowContext,opts){
  /* 모드 입력값(gatherInputs)도 $key 치환에 합류 — form/행 액션이 상단 셀렉터(포털 선택 등)를
     참조할 수 있게. 필드값이 우선이라 키 충돌 시 기존 동작 그대로. (데스크탑 dispatch 와 파리티) */
  const ctx=rowContext||(VIEW_CTX&&VIEW_CTX.data);
  const code=actionRequest(CUR.mode,template,Object.assign(gatherInputs(),fieldValues||{}),ctx||undefined);
  const d=await ibl(code);
  if(d&&(d.error||d.success===false)){ alert(d.error||d.message||'실패'); return false; }
  if(opts&&opts.back) runMode(); else await refreshCurrent();
  return true;
}

/* 드릴 렌더 — 탭(대화/정보) + 활성 view + 활성 compose */
let detailPollTimer=null;
function scheduleDetailPoll(){
  clearTimeout(detailPollTimer);
  const target=VIEW_CTX;
  if(!target||!target.poll||!jget(target.data,target.poll.while)||activeView().some(v=>v.type==='form')) return;
  detailPollTimer=setTimeout(async()=>{
    if(VIEW_CTX!==target) return;
    try {
      const nd=await ibl(target.action);
      if(VIEW_CTX!==target) return;
      const input=document.getElementById('composeInput'); const draft=input?input.value:'';
      const focus=document.activeElement===input;
      nd._item=target.item; target.data=nd; renderDrill();
      const next=document.getElementById('composeInput'); if(next){next.value=draft;if(focus)next.focus();}
    }catch(e){ if(VIEW_CTX===target) scheduleDetailPoll(); }
  },Math.max(1000,target.poll.interval_ms||2000));
}
let composeRequest={key:'',id:''};

function drillTab(i){ if(VIEW_CTX){ VIEW_CTX.activeTab=i; renderDrill(); } }
function mdBack(){ const s=document.getElementById('mdSplit'); if(s) s.classList.remove('has-detail'); }

async function composeSend(btn){
  const cmp=VIEW_CTX&&(VIEW_CTX._activeCompose||VIEW_CTX.compose); if(!cmp) return;
  const inp=document.getElementById('composeInput'); const text=inp?inp.value.trim():''; if(!text) return;
  const key=JSON.stringify([VIEW_CTX.action,text]);
  if(composeRequest.key!==key) composeRequest={key,id:crypto.randomUUID()};
  const fields={text,request_id:composeRequest.id};
  const opts=composeChannelOptions(cmp, VIEW_CTX&&VIEW_CTX.data);
  if(opts.length){ const selEl=document.getElementById('composeChannel'); const key=selEl?selEl.value:opts[0].key; const sel=opts.filter(o=>o.key===key)[0]||opts[0]; fields.channel_type=sel.channel_type; fields.to=sel.to; }
  btn.disabled=true;
  try{ if(await dispatchAction(cmp.action,fields)) composeRequest={key:'',id:''}; }
  catch(e){ alert('전송 실패: '+e.message); }
  finally{ btn.disabled=false; }
}
async function formSave(vi,btn){
  const p=activeView()[vi]; if(!p) return;
  const vals={}; (p.fields||[]).forEach(f=>{ const el=document.getElementById('ff_'+vi+'_'+f.key); if(el) vals[f.key]=el.value; });
  btn.disabled=true; try{ await dispatchAction(p.action,vals); }catch(e){ alert('저장 실패: '+e.message); } finally{ btn.disabled=false; }
}
/* images 필드 — 첨부 이미지 제거(드릴 데이터 컨텍스트로 remove_image). 추가는 데스크탑 전용. */
async function imgRemove(vi,fi,encPath){
  const p=activeView()[vi]; if(!p) return;
  const f=(p.fields||[])[fi]; if(!f||!f.remove_action) return;
  try{ await dispatchAction(f.remove_action,{path:decodeURIComponent(encPath)}); }
  catch(e){ alert('이미지 제거 실패: '+e.message); }
}
/* form 보조 액션(즐겨찾기 토글·삭제 등) — 드릴 데이터 컨텍스트로 실행. back=true면 목록 복귀. */
async function formAct(vi,ai,btn){
  const p=activeView()[vi]; if(!p||!p.actions||!p.actions[ai]) return;
  const a=p.actions[ai];
  if(a.confirm && !confirm(a.confirm)) return;
  btn.disabled=true;
  try{ await dispatchAction(a.action,{},null,{back:a.back}); }
  catch(e){ alert('실패: '+e.message); }
  finally{ btn.disabled=false; }
}
/* ai_dock — textarea 위 ephemeral AI 제안(요청→제안→반영/첨부/닫기). dispatchAction 과 달리
   새로고침 없이 ibl() 결과 텍스트만 받아 제안으로 띄우고, 적용 시 textarea 값을 바꾼다. */
window.__aidock = window.__aidock || {};
async function aiDockAsk(vi,fi,btn){
  const p=activeView()[vi]; if(!p) return;
  const f=(p.fields||[])[fi]; if(!f||!f.ai_dock) return;
  const inEl=document.getElementById('aid_in_'+vi+'_'+fi);
  const instruction=((inEl&&inEl.value)||'').trim(); if(!instruction) return;
  const vals={}; (p.fields||[]).forEach(ff=>{ const el=document.getElementById('ff_'+vi+'_'+ff.key); if(el) vals[ff.key]=el.value; });
  vals.dock=instruction;
  const sug=document.getElementById('aid_sug_'+vi+'_'+fi);
  btn.disabled=true; if(sug) sug.innerHTML='<div class="card muted" style="font-size:12px;margin-top:6px">AI가 생각 중…</div>';
  try{
    const d=await ibl(actionRequest(CUR.mode,f.ai_dock.action,Object.assign({},gatherInputs(),VIEW_VARS||{},vals)));
    const text=(typeof d==='string')?d:String((d&&(d.result??d.text??d.answer??d.message??d.error))||'');
    window.__aidock[vi+'_'+fi]=text;
    const modes=(f.ai_dock.modes&&f.ai_dock.modes.length)?f.ai_dock.modes:['replace','append'];
    const isErr=!text||text.indexOf('⚠️')===0;
    let btns='';
    if(!isErr&&modes.indexOf('replace')>=0) btns+='<button class="go" onclick="aiDockApply('+vi+','+fi+',\'replace\')">반영 (대체)</button>';
    if(!isErr&&modes.indexOf('append')>=0) btns+='<button class="linkbtn" style="padding:9px 13px;border:1px solid var(--line);border-radius:10px" onclick="aiDockApply('+vi+','+fi+',\'append\')">첨부</button>';
    btns+='<button class="linkbtn" style="padding:9px 13px" onclick="aiDockClose('+vi+','+fi+')">닫기</button>';
    if(sug) sug.innerHTML='<div class="card" style="margin-top:6px"><div style="white-space:pre-wrap;font-size:13px;max-height:160px;overflow:auto">'+esc(text||'(빈 응답)')+'</div><div class="row" style="margin-top:6px">'+btns+'</div></div>';
    if(inEl) inEl.value='';
  }catch(e){ if(sug) sug.innerHTML='<div class="card muted" style="font-size:12px;margin-top:6px">⚠️ AI 응답 실패: '+esc(e.message)+'</div>'; }
  finally{ btn.disabled=false; }
}
function aiDockApply(vi,fi,mode){
  const p=activeView()[vi]; if(!p) return; const f=(p.fields||[])[fi]; if(!f) return;
  const text=window.__aidock[vi+'_'+fi]; if(text==null) return;
  const el=document.getElementById('ff_'+vi+'_'+f.key); if(!el) return;
  el.value=(mode==='append')?((el.value.trim()?el.value+'\n\n':'')+text):text;
  aiDockClose(vi,fi);
}
function aiDockClose(vi,fi){ const sug=document.getElementById('aid_sug_'+vi+'_'+fi); if(sug) sug.innerHTML=''; delete window.__aidock[vi+'_'+fi]; }
async function elAdd(vi,btn){
  const p=activeView()[vi]; if(!p||!p.add) return;
  const vals={}; (p.add.fields||[]).forEach(f=>{ const el=document.getElementById('ea_'+vi+'_'+f.key); if(el) vals[f.key]=el.value; });
  btn.disabled=true; try{ await dispatchAction(p.add.action,vals); }catch(e){ alert('추가 실패: '+e.message); } finally{ btn.disabled=false; }
}
async function elDelete(vi,ri){
  const p=activeView()[vi]; if(!p) return;
  const arr=viewList(VIEW_CTX.data,p.from); const item=arr[ri]; if(item==null) return;
  try{ await dispatchAction(p.delete_action,{},item); }catch(e){ alert('삭제 실패: '+e.message); }
}
async function messengerCall(btn){
  const target=btn.dataset.callTarget, purpose=btn.dataset.callPurpose;
  if(!target || !['voice_call','video_call'].includes(purpose)) return;
  if(typeof IS_PHONE!=='undefined' && IS_PHONE){
    location.href='/launcher/native-call?'+new URLSearchParams({target:target,purpose:purpose});
    return;
  }
  const buttons=btn.parentElement.querySelectorAll('button');
  buttons.forEach(b=>b.disabled=true);
  const tab=window.open('about:blank','_blank');
  if(tab) tab.opener=null;
  try{
    const response=await fetch('/media/sessions',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({kind:'call',purpose:purpose,target:target,request_id:crypto.randomUUID()})});
    const result=await response.json();
    if(!response.ok || !result.success || !result.session) throw new Error(result.error?.message || result.detail || '통화를 시작하지 못했습니다.');
    const url='/launcher/ui/#/media-call/'+encodeURIComponent(result.session.session_id);
    if(tab) tab.location.href=url; else location.href=url;
  }catch(e){ if(tab) tab.close(); alert(e.message); }
  finally{ buttons.forEach(b=>b.disabled=false); }
}
function rowItem(vi,ri){
  if(!VIEW_CTX) return null;
  const p=activeView()[vi]; if(!p) return null;
  const arr=viewList(VIEW_CTX.data,p.from);
  return arr[ri]==null?null:{prim:p,item:arr[ri]};
}
/* 잠깐 뜨는 토스트(저장 알림 등) — alert 대신 비차단. */
function toast(msg){
  let t=document.getElementById('toastMsg');
  if(!t){ t=document.createElement('div'); t.id='toastMsg';
    t.style.cssText='position:fixed;left:50%;bottom:80px;transform:translateX(-50%);z-index:9999;background:#222;color:#fff;padding:10px 18px;border-radius:20px;font-size:14px;max-width:80%;text-align:center;box-shadow:0 2px 10px rgba(0,0,0,.5)';
    document.body.appendChild(t); }
  t.textContent=msg; t.style.display='block';
  clearTimeout(t._h); t._h=setTimeout(()=>{t.style.display='none';},2600);
}
async function rowBtn(vi,ri,btn,key){
  key=key||'button';
  const r=rowItem(vi,ri); if(!r||!r.prim[key]) return;
  // stream:true 버튼 = 클라이언트 스트림 재생(CCTV '보기'). IBL 실행 없이 행 url 을 playStream(hls.js) 오버레이로.
  if(r.prim[key].stream){ if(r.item&&r.item.url){ const i=_streamUrls.push(r.item.url)-1; playStream(i); } return; }
  if(r.prim[key].confirm && !confirm(r.prim[key].confirm)) return;  // 파괴적 행 버튼(사진 빼기 등) 확인
  const action=actionRequest(CUR.mode,r.prim[key].action,null,r.item);
  btn.disabled=true; const old=btn.textContent; btn.textContent='…';
  try{
    const d=await ibl(action);
    if(d&&d.play_in_client&&d.stream_url){ playRadioStream(d.stream_url,d.volume,d.title||d.station||d.name); }  // 폰 라디오·유튜브뮤직: WebView 직접 재생 + 미니플레이어
    else if(d&&d.download_in_client){ toast(d.saved===false?('⚠ '+(d.message||'저장 실패')):('📥 '+(d.message||'저장됨'))); }  // mp3 폰 저장 결과
    else if(d&&(d.error||d.success===false)){
      // 폰: os_open(집 PC GUI)이 pc_only 로 막히면, 로컬 생성한 HTML 을 인앱 뷰어로 띄운다.
      const m=requestCode(action).match(/path:\s*"([^"]+\.html?)"/i);
      if(d.pc_only && m){ openFileOverlay(m[1]); }
      else alert(d.error||d.message||'실패');
    }
    else{  // 즐겨찾기 추가/삭제 등: 성공 메시지 토스트 + refresh 플래그면 현재 뷰 재조회
      if(d&&d.message) toast(d.message);
      if(r.prim[key].refresh) await refreshCurrent();
    }
  }
  catch(e){ alert('실행 실패: '+e.message); }
  finally{ btn.disabled=false; btn.textContent=old; }
}
/* thread 항목 버튼 — 본문 정규식 재실행으로 캡처 그룹({match1}..{matchN})을 행 필드에 합쳐
   액션 템플릿에 공급한다 (데스크탑 GenericInstrument thread item_button 과 동형). */
async function threadIbBtn(vi,ri,btn){
  const r=rowItem(vi,ri); const ib=r&&r.prim.item_button;
  if(!ib||!ib.action) return;
  let re=null; try{ re=new RegExp(ib.match||'','i'); }catch(e){ return; }
  const m=tpl(r.prim.text,r.item).match(re); if(!m) return;
  const item=Object.assign({},r.item);
  for(let gi=1;gi<m.length;gi++) item['match'+gi]=m[gi]==null?'':m[gi];
  const action=actionRequest(CUR.mode,ib.action,null,item);
  btn.disabled=true; const old=btn.textContent; btn.textContent='…';
  try{
    const d=await ibl(action);
    if(d&&(d.error||d.success===false)) alert(d.error||d.message||'실패');
    else{ if(d&&d.message) toast(d.message); if(ib.refresh) await refreshCurrent(); }
  }
  catch(e){ alert('실행 실패: '+e.message); }
  finally{ btn.disabled=false; btn.textContent=old; }
}
async function rowSel(vi,ri,sel){
  const r=rowItem(vi,ri); if(!r||!r.prim.select||!r.prim.select.action) return;
  const item=Object.assign({},r.item,{sel:sel.value});
  const action=actionRequest(CUR.mode,r.prim.select.action,null,item);
  sel.disabled=true;
  try{
    const d=await ibl(action);
    if(d&&(d.error||d.success===false)) alert(d.error||d.message||'실패');
    else{ if(d&&d.message) toast(d.message); if(r.prim.select.refresh) await refreshCurrent(); }
  }
  catch(e){ alert('실행 실패: '+e.message); }
  finally{ sel.disabled=false; }
}
/* ----- 인앱 웹 뷰어(내부 브라우저) -----
   외부 링크를 새 탭 대신 앱 안 오버레이로 띄운다 — 탭 전환이 비싼 화면(차 브라우저·
   태블릿)에서 런처를 잃지 않게. .fileov 오버레이 + popstate 뒤로가기 배관을 그대로 재사용
   (openFileOverlay 의 웹 판 — 저쪽은 로컬 산출물, 이쪽은 외부 URL).
   ★ 사이트 절반쯤은 X-Frame-Options / CSP frame-ancestors 로 삽입을 거부한다. 거부는
   브라우저가 강제하고 JS 로는 성공/거부를 구분할 수 없어(둘 다 교차출처) 서버
   (/launcher/framable)가 헤더를 대신 보고 알려준다 → 거부면 새 탭 폴백으로 바꾼다.
   프레임은 판정을 기다리지 않고 먼저 띄운다(느린 회선에서 체감 지연 0). */
function _hostOf(u){ try{ return new URL(u).hostname.replace(/^www\./,''); }catch(e){ return u; } }
function openWebOverlay(url,title){
  if(!url) return false;
  /* 폰 네이티브는 shouldOverrideUrlLoading 으로 시스템 브라우저에 넘긴다(기존 동작 유지) */
  if(IS_PHONE){ window.location.href=url; return false; }
  const ov=document.createElement('div'); ov.className='fileov';
  const bar=document.createElement('div'); bar.className='fileov-bar';
  const nm=document.createElement('span'); nm.className='fileov-nm';
  nm.textContent=title||_hostOf(url);
  const acts=document.createElement('span'); acts.className='fileov-acts';
  const ext=document.createElement('button'); ext.className='iconbtn'; ext.textContent='↗';
  ext.title='새 탭에서 열기';
  ext.onclick=function(){ window.open(url,'_blank','noopener'); };
  const cls=document.createElement('button'); cls.className='iconbtn'; cls.textContent='✕';
  cls.onclick=function(){ history.back(); };
  acts.appendChild(ext); acts.appendChild(cls);
  bar.appendChild(nm); bar.appendChild(acts); ov.appendChild(bar);
  const ifr=document.createElement('iframe');
  /* allow-top-navigation 을 주지 않는다 = 프레임버스팅(top.location 탈취) 차단.
     교차출처라 allow-same-origin 을 줘도 우리 문서엔 손 못 댄다. */
  ifr.setAttribute('sandbox','allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox allow-downloads');
  ifr.src=url;
  ov.appendChild(ifr);
  document.body.appendChild(ov);
  /* 뒤로가기 한 단계로 닫히게 — popstate 핸들러가 .fileov 를 먼저 걷는다 */
  try{ history.pushState({fileov:1}, ''); }catch(e){}
  jfetch('/launcher/framable?url='+encodeURIComponent(url))
    .then(function(r){ return r.json(); })
    .then(function(d){
      if(!d || d.framable!==false || !document.body.contains(ov)) return;
      ifr.remove();
      const box=document.createElement('div'); box.className='fileov-blocked';
      const t=document.createElement('p');
      t.textContent=(title||_hostOf(url))+' 은(는) 다른 화면 안에 표시되는 것을 거부합니다.';
      const s=document.createElement('p'); s.className='muted'; s.textContent=d.reason||'';
      const b=document.createElement('button'); b.className='go';
      b.textContent='새 탭에서 열기 ↗';
      b.onclick=function(){ window.open(url,'_blank','noopener'); history.back(); };
      box.appendChild(t); box.appendChild(s); box.appendChild(b);
      ov.appendChild(box);
    })
    .catch(function(){});   /* 판정 실패 = 낙관(프레임 그대로, ↗ 버튼이 탈출구) */
  return false;
}
function openFileOverlay(path, html){
  const name=path.split('/').pop().split('\\').pop();
  const ov=document.createElement('div'); ov.className='fileov';
  ov.innerHTML='<div class="fileov-bar"><span>'+esc(name)+'</span>'
    +'<button class="iconbtn" onclick="history.back()">✕</button></div>';
  // iframe은 DOM으로 만들어 srcdoc/src를 *프로퍼티*로 설정(문자열 이스케이프 불필요).
  // html 콘텐츠가 동봉됐으면 srcdoc으로 직접 띄운다 — 파일이 다른 몸(맥)에 있어 /output 로
  // 못 찾는 경우(포워드 산출)에도 콘텐츠로 렌더. 없으면 기존대로 /output 파일 서빙.
  const ifr=document.createElement('iframe');
  // html 동봉이면 srcdoc, 아니면 로컬 경로를 /launcher/file 로 서빙(옛 /output 은 라우트 없음=404).
  // 빌림-완성으로 포워드 산출 파일도 폰 로컬에 있어 이 경로로 띄워진다.
  if(html){ ifr.srcdoc=html; } else { ifr.src=API+'/launcher/file?path='+encodeURIComponent(path); }
  ov.appendChild(ifr);
  document.body.appendChild(ov);
  // 안드로이드 뒤로가기로 닫히게 — SPA 라 WebView 백스택이 비면 뒤로가기가 앱을 종료(홈)시킨다.
  // history 항목을 push → canGoBack=true → 뒤로가기는 goBack→popstate 로 오버레이만 닫고
  // 앱모드 화면에 머문다(앱 종료 아님).
  try{ history.pushState({fileov:1}, ''); }catch(e){}
}
// 안드로이드 뒤로가기 일반 처리 — 가장 위(깊은) 것부터 한 단계만 닫는다. 각 "깊이 들어가기"
// (계기 열기·오버레이)가 history.pushState 로 항목을 쌓아 두면, 뒤로가기는 여기서 앱 안에서
// 한 단계 뒤로 가고, 더 닫을 게 없을 때만 네이티브가 앱을 종료한다. 모든 시각 ←/✕ 버튼도
// history.back() 으로 이 경로를 타 일관성 유지.
window.addEventListener('popstate', function(){
  const _ov=document.querySelector('.fileov');
  if(_ov){ _ov.remove(); return; }              // 1) 파일 오버레이(신문 등)
  const _fg=document.getElementById('p-forage');
  if(_fg && _fg.classList.contains('on')){ setSurface('app'); return; }  // 2) 검색브라우저(앱) → 앱 그리드
  const _inst=document.getElementById('appInst');
  if(_inst && _inst.style.display!=='none'){ appBackHome(); return; }  // 3) 계기 → 앱 그리드
});
async function rowDrill(vi,ri,inDetail=false){
  // split이면 리스트(LIST)에서 행을 찾아 상세 패널(#mdDetail)로, 아니면 현재 view(VIEW_CTX)에서 instOut으로.
  const src = SPLIT && !inDetail ? LIST : VIEW_CTX; if(!src) return;
  /* ★탭 드릴이면 활성 탭 view(_activeView)에서 찾는다 — 드릴이 tabs 로만 구성되면
     src.view 가 없어 행 클릭이 조용히 죽던 버그(음악 폴더 2단계에서 멈춤). vi 는
     renderDrill 이 renderView(av)에 넘긴 활성 view 배열 기준이라 activeView()와 정합. */
  const p=(SPLIT&&!inDetail?(src.view||[]):activeView())[vi]; if(!p||!p.item_click) return;
  // 동적 카테고리 필터가 활성이면 카드가 필터된 배열로 렌더되므로 ri 도 그 기준 → 같은 필터 적용 후 인덱싱(비분할만; split=master_detail 은 동적필터 없음).
  const drillData = SPLIT || inDetail ? src.data : applyCatFilter(CUR.mode, src.data);
  const item=viewList(drillData,p.from)[ri]; if(item==null) return;
  const dc=p.item_click;
  const detail = SPLIT ? document.getElementById('mdDetail') : document.getElementById('instOut');
  detail.innerHTML='<div class="center"><div class="spin"></div></div>';
  try{
    const code=actionRequest(CUR.mode,dc.action,gatherInputs(),item);  /* $입력(현재 다이얼)+$item(클릭 행) — 판본 2 는 치환 없이 inputs 로 */
    const d=await ibl(code);
    if(d&&typeof d==='object') d._item=item; /* 드릴 뷰에서 클릭한 행 참조용 */
    /* recursive: 지금 보고 있는 드릴 화면(뷰 또는 탭)을 그대로 재사용 — 깊이를 모르는
       트리(폴더 등)를 한 벌 선언으로 무제한 탐색(데스크탑 onDrill 과 같은 규칙).
       선언 view/tabs 가 이긴다. */
    const inh = (dc.recursive && (!SPLIT || inDetail) && VIEW_CTX) ? VIEW_CTX : null;
    const dview = dc.view || (inh ? inh.view : null);
    const dtabs = dc.tabs || (inh ? inh.tabs : null);
    VIEW_CTX={view:dview,tabs:dtabs,activeTab:0,data:d,action:code,item:item,compose:dc.compose,poll:dc.poll,refresh:'drill'};
    if(SPLIT){ const s=document.getElementById('mdSplit'); if(s) s.classList.add('has-detail'); }
    renderDrill();
  }catch(e){ detail.innerHTML='<p class="muted">오류: '+esc(e.message)+'</p>'; }
}

/* ================= 포식(검색) 브라우저 ================= */
/* 데스크탑 Electron ForageBrowser 의 핵심 루프(검색→후보판→진입→신호)를 폰/원격에서 재현.
   진입(브라우징)은 시스템 브라우저로 위임 — 런처 WebView 는 판을 든 채 뒤에 남고 뒤로가기로 복귀.
   그리드/썸네일·인앱 webview·번역주입은 데스크탑 전용(폰 스코프 밖). */
let fgInit=false, fgSub='board', fgBoard=null, fgSeq=0, fgSearching=false, fgHist=[], fgLib=[];
const FG_COUNT=10;

function fgNorm(u){ return String(u||'').replace(/\/+$/,'').toLowerCase(); }
function fgPick(i){ return {title:i.title, url:i.url, reason:i.reason}; }

function fgNav(which){
  fgSub=which;
  ['board','history','library'].forEach(k=>{
    const b=document.getElementById('fgnav-'+k); if(b) b.classList.toggle('on',k===which);
  });
  if(which==='board') fgRenderBoard();
  else if(which==='history') fgHistory();
  else if(which==='library') fgLibrary();
}

/* --- 응답 파싱 (데스크탑 parseCandidates + extractDestinations 이식) --- */
function fgParseCandidates(text){
  const items=[], intro=[], outro=[];
  const linkRe=/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/;
  for(const raw of String(text||'').split('\n')){
    const line=raw.trim(); if(!line) continue;
    const m=line.match(linkRe);
    if(m){
      const after=line.slice((m.index||0)+m[0].length);
      items.push({
        title:m[1].replace(/\*+/g,'').trim(),
        url:m[2],
        reason:after.replace(/^[\s—–:·,\-]+/,'').replace(/\*+/g,'').trim()
      });
    } else {
      (items.length===0?intro:outro).push(line.replace(/^[#>*\-]+\s*/,'').replace(/\*+/g,''));
    }
  }
  return {intro:intro.join(' ').trim(), outro:outro.join(' ').trim(), items};
}
function fgExtractDest(content){
  const dests=[]; let text=String(content||'');
  const MARK='[MAP:'; let start=text.indexOf(MARK);
  while(start!==-1){
    let depth=0,end=-1,inStr=false,esc2=false;
    for(let i=start+MARK.length;i<text.length;i++){
      const c=text[i];
      if(esc2){esc2=false;continue;}
      if(c==='\\'&&inStr){esc2=true;continue;}
      if(c==='"'){inStr=!inStr;continue;}
      if(inStr)continue;
      if(c==='{')depth++;
      else if(c==='}'){depth--; if(depth===0&&text[i+1]===']'){end=i+2;break;}}
    }
    if(end===-1)break;
    try{
      const data=JSON.parse(text.substring(start+MARK.length,end-1));
      for(const mk of (data.markers||[])){ if(mk&&mk.url) dests.push({title:mk.name||mk.url, reason:mk.meta||'', url:mk.url}); }
    }catch(e){}
    text=text.slice(0,start)+text.slice(end);
    start=text.indexOf(MARK);
  }
  return {text, dests};
}
function fgParseResp(content){
  const ed=fgExtractDest(content);
  const p=fgParseCandidates(ed.text);
  return {intro:p.intro, outro:p.outro, items:p.items.concat(ed.dests)};
}

/* --- 검색 → 후보판 --- */
async function fgSearch(){
  if(fgSearching) return;
  const inp=document.getElementById('fgQ'); const q=(inp?inp.value:'').trim();
  if(!q) return;
  fgSearching=true; const go=document.getElementById('fgGo'); if(go){go.disabled=true;go.textContent='…';}
  fgNav('board');
  const list=document.getElementById('fgList'); if(list) list.innerHTML='<div class="fg-empty">포식 중… 🔍</div>';
  try{
    const r=await jfetch('/forage/chat',{method:'POST',body:JSON.stringify({message:q,count:FG_COUNT})});
    if(!r.ok) throw new Error('검색 실패 ('+r.status+')');
    const d=await r.json();
    const parsed=fgParseResp(d.response||'');
    const seen=new Set(); const pool=[];
    for(const c of parsed.items){
      const k=fgNorm(c.url); if(!c.url||seen.has(k))continue; seen.add(k);
      pool.push({id:'c'+(++fgSeq),title:c.title,url:c.url,reason:c.reason||'',pinned:false,excluded:false,visited:false});
    }
    if(pool.length){
      fgBoard={id:'b'+Date.now()+'_'+fgSeq, query:q, intro:parsed.intro, outro:parsed.outro, round:1, saved:false, items:pool};
      if(inp) inp.value='';
    } else {
      fgBoard=null;
      if(list) list.innerHTML='<div class="fg-empty">'+esc(parsed.intro||parsed.outro||'후보를 찾지 못했어요. 다르게 물어봐 주세요.')+'</div>';
    }
  }catch(e){
    if(list) list.innerHTML='<div class="fg-empty">'+esc(e.message||'오류')+'</div>';
  }finally{
    fgSearching=false; const g2=document.getElementById('fgGo'); if(g2){g2.disabled=false;g2.textContent='포식';}
    if(fgBoard) fgRenderBoard();
  }
}

/* --- 후보판 렌더 --- */
function fgRenderBoard(){
  if(fgSub!=='board') return;
  const list=document.getElementById('fgList'); if(!list) return;
  if(!fgBoard){
    list.innerHTML='<div class="fg-empty">검색어를 넣고 포식하세요.<br>후보판이 깔리면 ✕로 치우고 📌로 담을 수 있어요.</div>';
    return;
  }
  let h='';
  if(fgBoard.intro) h+='<div class="fg-intro">'+esc(fgBoard.intro)+'</div>';
  const active=fgBoard.items.filter(i=>!i.excluded);
  const excluded=fgBoard.items.filter(i=>i.excluded);
  for(const it of active) h+=fgCardHtml(it);
  h+='<div class="fg-more" onclick="fgMore()">'+(fgSearching?'보충 중…':'＋ 더 채우기 ('+active.length+'/'+FG_COUNT+')')+'</div>';
  h+='<div class="fg-more" onclick="fgSave()">'+(fgBoard.saved?'✓ 도서관에 보존됨 (갱신)':'💾 이 판 보존하기')+'</div>';
  if(excluded.length){
    h+='<div class="fg-intro">치운 후보 '+excluded.length+'개</div>';
    for(const it of excluded) h+=fgCardHtml(it);
  }
  list.innerHTML=h;
}
function fgCardHtml(it){
  return '<div class="fg-card'+(it.pinned?' pinned':'')+(it.excluded?' excluded':'')+'">'+
    '<div class="t">'+(it.visited?'✓ ':'')+esc(it.title||it.url)+'</div>'+
    (it.reason?'<div class="r">'+esc(it.reason)+'</div>':'')+
    '<div class="u">'+esc(it.url)+'</div>'+
    '<div class="acts">'+
      '<button class="go" onclick="fgOpen(\''+it.id+'\')">열기 ↗</button>'+
      '<button class="pin'+(it.pinned?' on':'')+'" onclick="fgTogglePin(\''+it.id+'\')">📌'+(it.pinned?' 담음':'')+'</button>'+
      '<button onclick="fgToggleExclude(\''+it.id+'\')">'+(it.excluded?'되돌리기':'✕')+'</button>'+
    '</div>'+
  '</div>';
}

/* --- 진입 · 신호 --- */
async function fgOpen(id){
  if(!fgBoard) return;
  const it=fgBoard.items.find(x=>x.id===id); if(!it) return;
  it.visited=true;
  try{ await jfetch('/forage/history',{method:'POST',body:JSON.stringify({url:it.url,title:it.title||'',hunt_query:fgBoard.query||''})}); }catch(e){}
  fgRenderBoard();
  fgVisit(it.url, it.title||'');
}
function fgVisit(url,title){
  if(!url) return;
  if(IS_PHONE){ window.location.href=url; }   /* shouldOverrideUrlLoading → 시스템 브라우저, 런처는 판을 든 채 유지 */
  else { openWebOverlay(url,title); }  /* 원격 = 인앱 뷰어(판을 든 채 읽는다) — 거부 사이트면 새 탭 폴백 */
}
function fgTogglePin(id){ const it=fgBoard&&fgBoard.items.find(x=>x.id===id); if(!it)return; it.pinned=!it.pinned; if(it.pinned)it.excluded=false; fgRenderBoard(); }
function fgToggleExclude(id){ const it=fgBoard&&fgBoard.items.find(x=>x.id===id); if(!it)return; it.excluded=!it.excluded; if(it.excluded)it.pinned=false; fgRenderBoard(); }

/* --- 보충(합작 포식 라운드) --- */
async function fgMore(){
  if(!fgBoard||fgSearching) return;
  fgSearching=true; fgRenderBoard();
  const active=fgBoard.items.filter(i=>!i.excluded);
  const hunt={
    query:fgBoard.query, round:(fgBoard.round||1)+1, need:Math.max(1,FG_COUNT-active.length),
    pinned:fgBoard.items.filter(i=>i.pinned).map(fgPick),
    excluded:fgBoard.items.filter(i=>i.excluded).map(fgPick),
    kept:active.filter(i=>!i.pinned).map(fgPick),
    trail:fgBoard.items.filter(i=>i.visited).map(fgPick)
  };
  try{
    const r=await jfetch('/forage/chat',{method:'POST',body:JSON.stringify({message:fgBoard.query,count:FG_COUNT,hunt:hunt})});
    const d=await r.json();
    const parsed=fgParseResp(d.response||'');
    const seen=new Set(fgBoard.items.map(i=>fgNorm(i.url)));
    for(const c of parsed.items){
      const k=fgNorm(c.url); if(!c.url||seen.has(k))continue; seen.add(k);
      fgBoard.items.push({id:'c'+(++fgSeq),title:c.title,url:c.url,reason:c.reason||'',pinned:false,excluded:false,visited:false});
    }
    fgBoard.round=hunt.round;
  }catch(e){ toast('보충 실패'); }
  finally{ fgSearching=false; fgRenderBoard(); }
}

/* --- 판 보존 · 도서관 --- */
async function fgSave(){
  if(!fgBoard) return;
  fgBoard.saved=true;
  try{
    await jfetch('/forage/boards',{method:'POST',body:JSON.stringify({id:fgBoard.id, name:fgBoard.query||'',
      state:{query:fgBoard.query,intro:fgBoard.intro,round:fgBoard.round,
        items:fgBoard.items.map(i=>({title:i.title,url:i.url,reason:i.reason,pinned:i.pinned,removed:i.excluded,visited:i.visited}))}})});
    toast('도서관에 보존했어요');
  }catch(e){ toast('보존 실패'); }
  fgRenderBoard();
}
async function fgLibrary(){
  const list=document.getElementById('fgList'); if(!list) return;
  list.innerHTML='<div class="fg-empty">불러오는 중…</div>';
  try{
    const r=await jfetch('/forage/boards'); const d=await r.json(); fgLib=(d&&d.items)||[];
    if(!fgLib.length){ list.innerHTML='<div class="fg-empty">보존한 판이 없어요.<br>판에서 💾로 보존하면 여기 모입니다.</div>'; return; }
    let h='';
    fgLib.forEach((b,idx)=>{
      h+='<div class="fg-card"><div class="t" onclick="fgLoadBoard('+idx+')">'+esc(b.name||'(제목 없음)')+'</div>'+
        ((b.preview&&b.preview.length)?'<div class="r">'+esc(b.preview.join(' · '))+'</div>':'')+
        '<div class="acts"><button class="go" onclick="fgLoadBoard('+idx+')">판 열기 ('+(b.count||0)+')</button>'+
        '<button onclick="fgDeleteBoard('+idx+')">🗑 삭제</button></div></div>';
    });
    list.innerHTML=h;
  }catch(e){ list.innerHTML='<div class="fg-empty">오류: '+esc(e.message)+'</div>'; }
}
async function fgLoadBoard(idx){
  const b=fgLib[idx]; if(!b) return;
  try{
    const r=await jfetch('/forage/boards/'+encodeURIComponent(b.id)); const d=await r.json();
    if(!d||!d.ok){ toast('판을 불러오지 못했어요'); return; }
    const st=d.state||{};
    fgBoard={id:d.id, query:st.query||d.name||'', intro:st.intro||'', outro:st.outro||'', round:st.round||1, saved:true,
      items:(st.items||[]).map(i=>({id:'c'+(++fgSeq),title:i.title,url:i.url,reason:i.reason||'',pinned:!!i.pinned,excluded:!!i.removed,visited:!!i.visited}))};
    fgNav('board');
  }catch(e){ toast('오류'); }
}
async function fgDeleteBoard(idx){ const b=fgLib[idx]; if(!b)return; try{ await jfetch('/forage/boards/'+encodeURIComponent(b.id),{method:'DELETE'}); fgLibrary(); }catch(e){} }

/* --- 방문기록 --- */
async function fgHistory(){
  const list=document.getElementById('fgList'); if(!list) return;
  list.innerHTML='<div class="fg-empty">불러오는 중…</div>';
  try{
    const r=await jfetch('/forage/history?limit=300'); const d=await r.json(); fgHist=(d&&d.items)||[];
    if(!fgHist.length){ list.innerHTML='<div class="fg-empty">방문기록이 없어요.<br>후보를 열면 여기 쌓입니다.</div>'; return; }
    let h='<div class="fg-intro">방문기록 '+fgHist.length+'개</div>';
    fgHist.forEach((it,idx)=>{
      h+='<div class="fg-row"><div class="rx" onclick="fgHistOpen('+idx+')"><div class="rt">'+esc(it.title||it.url)+'</div><div class="ru">'+esc(it.url)+'</div></div>'+
        '<div class="rd" onclick="fgHistDelete('+it.id+')">🗑</div></div>';
    });
    list.innerHTML=h;
  }catch(e){ list.innerHTML='<div class="fg-empty">오류: '+esc(e.message)+'</div>'; }
}
function fgHistOpen(idx){ const it=fgHist[idx]; if(it) fgVisit(it.url, it.title||''); }
async function fgHistDelete(id){ try{ await jfetch('/forage/history/'+id,{method:'DELETE'}); fgHistory(); }catch(e){} }

/* ===== 홈 화면 설치: 서비스워커 등록 =====
   크롬이 '설치 가능'으로 보려면 fetch 핸들러를 가진 서비스워커가 있어야 한다. 우리 워커는
   캐시하지 않고 통과만 시킨다(개인화·실시간 표면이라 캐싱이 곧 버그). 보안 컨텍스트
   (https 또는 localhost)에서만 등록된다 — http://<집IP>:8765 직접 접속은 조용히 건너뛴다. */
if(!window.__MEMBER && 'serviceWorker' in navigator){
  window.addEventListener('load', function(){
    navigator.serviceWorker.register('/launcher/sw.js', {scope:'/launcher/'}).catch(function(e){});
  });
}
@@display_js@@
</script>
<!--INDIE_DISPLAY--></body>
</html>
