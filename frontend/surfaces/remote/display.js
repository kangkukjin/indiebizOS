function renderView(view,data){
  if(data&&data.error) return '<p class="muted">'+esc(data.error)+'</p>';
  if(data&&data.success===false) return '<p class="muted">'+esc(data.message||'실패')+'</p>';
  return (view||[]).map((p,vi)=>renderPrim(p,vi,data)).join('');
}
function dynFilterOf(mode){ return (mode&&mode.filter&&mode.filter.from_field)?mode.filter:null; }
function applyCatFilter(mode,data){  /* CUR.catFilter 적용된 데이터(map 마커·card_list 동시 거름) */
  const f=dynFilterOf(mode); if(!f||CUR.catFilter==null||!data) return data;
  return applyDynFilter(data,f.from,f.from_field,CUR.catFilter);
}
function renderDynFilter(mode,data){
  const f=dynFilterOf(mode); if(!f||!data) return '';
  const cats=dynFilterCats(data,f.from,f.from_field);
  if(!cats.length) return '';
  // 칩 값은 data-c 속성에 담고(esc), 클릭은 그 속성을 읽는다 — onclick 인라인 따옴표 이스케이프 회피.
  let h='<div class="filters" style="margin-bottom:10px">';
  h+='<button class="fchip'+(CUR.catFilter==null?' on':'')+'" onclick="setCatFilter(null)">전체</button>';
  h+=cats.slice(0,12).map(c=>'<button class="fchip'+(String(CUR.catFilter)===String(c)?' on':'')
    +'" data-c="'+esc(c)+'" onclick="setCatFilter(this.getAttribute(\'data-c\'))">'+esc(c)+'</button>').join('');
  return h+'</div>';
}
function renderModeBody(mode,data){
  return renderDynFilter(mode,data)+renderView(mode.view,applyCatFilter(mode,data))+renderComposeBar(mode.compose);
}
function trendColor(p,data){ const up=trendUp(p,data); return up==null?null:(up?'var(--up)':'var(--down)'); }
function emptyMsg(p,data){
  return '<p class="muted" style="margin-top:10px">'+esc(emptyText(p,data))+'</p>';
}
function renderPrim(p,vi,data){
  if(p.type==='calendar'){ _calSetup(p,data); setTimeout(_calDraw,0); return '<div id="calHost"></div>'; }
  if(p.type==='map'){
    const md=p.from?jget(data,p.from):data;
    let mk=p.markers?viewList(data,p.markers):[];
    if(p.max&&mk.length>p.max) mk=mk.slice(0,p.max);  // 마커 폭주 방지(상권 등 수천건)
    const id='lmap_'+(_mapSeq++);
    _MAP_QUEUE[id]={md:md,markers:mk,on:p.on||null};
    // search_here: "이 지역에서 검색" 버튼 — 현재 뷰포트 중심·반경으로 재조회(nearby 등). 데스크탑 GenericInstrument 와 파리티.
    const searchBtn=(p.on&&p.on.search_here)?'<button class="lmapsearch" onclick="mapSearchHere(\''+id+'\')">📍 이 지역에서 검색</button>':'';
    return '<div style="position:relative;margin-bottom:10px">'
      +'<div id="'+id+'" class="lmap" style="height:320px;border-radius:12px;overflow:hidden;background:var(--bg3)"></div>'
      +'<button class="lmaptoggle" onclick="toggleMapDrag(\''+id+'\',this)">🔓 지도 이동</button>'+searchBtn+'</div>';
  }
  if(p.type==='group'){
    // 파티션 콤비네이터(데스크탑 ViewPrim group 의 원격 쌍). from 리스트를 by 키로 나눠(입력순 보존)
    // 그룹마다 헤더 + 내부 view 재귀 렌더(data={items:멤버}=단일통화). table:groupby(집계)와 달리 멤버 유지.
    // ★내부 view 의 item_click 은 검증기가 금지(원격 rowDrill 이 최상위 view[vi] 로만 찾음) — 링크/버튼만.
    const arr=viewList(data,p.from);
    if(!arr.length) return emptyMsg(p,data);
    // 파티션은 공용 코어(groupPartition). ★키는 esc 안 한 원문으로 나눈다 — 아래서 헤더를
    //   esc() 하므로 여기서 또 tpl(=esc 포함)을 쓰면 '&' 가 두 번 이스케이프된다(옛 버그).
    const inner=p.view||[];
    return groupPartition(arr,it=>tplWith(p.by,it),p.max_groups).map((g,gi)=>{
      const members=g.members;
      const header=p.label?tplWith(p.label,members[0]):g.key;
      const gdata={items:members};
      return '<div style="margin-bottom:22px"><h3 style="font-size:17px;font-weight:700;color:var(--fg);'
        +'border-bottom:2px solid var(--bd);padding-bottom:6px;margin:0 0 12px">'+esc(header)+'</h3>'
        +inner.map((ip,j)=>renderPrim(ip,vi*100+gi*10+j,gdata)).join('')+'</div>';
    }).join('');
  }
  if(p.type==='metric'){
    const col=trendColor(p,data);
    return '<div class="card">'+(p.label?'<div class="muted">'+tpl(p.label,data)+'</div>':'')+
      '<div class="big"'+(col?' style="color:'+col+'"':'')+'>'+tpl(p.big,data)+(p.unit?' <span style="font-size:14px">'+tpl(p.unit,data)+'</span>':'')+'</div>'+
      (p.sub?'<div'+(col?' style="color:'+col+'; font-weight:600"':' class="muted"')+'>'+tpl(p.sub,data)+'</div>':'')+'</div>';
  }
  /* ★kv 값은 tplWith(=이스케이프 없는 원문)로 만들어 kvVal 에 넘긴다 — kvVal 이 esc 를 하므로
     tpl(esc 포함)을 넘기면 이중 이스케이프('<'가 &lt; 로 보임)가 되고, URL 판정도 &amp; 로
     망가진 주소를 href 에 넣는다. 키(k)는 kvVal 을 안 거치므로 tpl 그대로. */
  if(p.type==='kv')
    return '<div class="card">'+(p.title?'<div class="step-label">'+esc(p.title)+'</div>':'')+
      (p.rows||[]).map(r=>'<div class="kv"><span class="k">'+tpl(r.k,data)+'</span>'+kvVal(tplWith(r.v,data))+'</div>').join('')+'</div>';
  if(p.type==='kv_list'){
    const arr=viewList(data,p.from);
    if(!arr.length) return emptyMsg(p,data);
    return '<div class="card">'+(p.title?'<div class="step-label">'+esc(p.title)+'</div>':'')+
      arr.map(it=>'<div class="kv"><span class="k">'+tpl(p.k,it)+'</span>'+kvVal(tplWith(p.v,it))+'</div>').join('')+'</div>';
  }
  if(p.type==='card_list'){
    const arr=viewList(data,p.from);
    if(!arr.length) return emptyMsg(p,data);
    const c=p.card||{};
    // wide 카드=화면 폭 반응형 그리드(폰 1열·넓으면 2~4열, 유튜브 홈) — 전폭 1열 고정이면 데스크탑서 썸네일 과대
    const wideOpen=c.wide?'<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px;align-items:start">':'';
    return wideOpen+arr.map((it,ri)=>{
      const click=p.item_click?' onclick="rowDrill('+vi+','+ri+','+(SPLIT&&VIEW_CTX&&data===VIEW_CTX.data?'true':'false')+')" style="cursor:pointer"':'';
      let body='<div class="t">'+tpl(c.title,it)+'</div><div class="m">'+(c.lines||[]).map(l=>tpl(l,it)).join('<br>')+'</div>';
      const callTarget=mediaCallTarget(p,it);
      if(callTarget){
        body+='<div style="display:flex;gap:8px;margin-top:8px">'+
          '<button class="btn2" data-call-target="'+callTarget+'" data-call-purpose="voice_call" onclick="event.stopPropagation();messengerCall(this)">음성 통화</button>'+
          '<button class="btn2" data-call-target="'+callTarget+'" data-call-purpose="video_call" onclick="event.stopPropagation();messengerCall(this)">영상 통화</button></div>';
      }
      if(c.link&&c.link.href){
        const href=tpl(c.link.href,it);
        // 인앱 뷰어로 — href 는 남긴다(길게 누르기/가운데 클릭으로 새 탭도 그대로).
        // 제목은 this.href 에서 파생(속성 이스케이프 회피 — esc() 는 따옴표를 안 막는다).
        if(href) body+='<a href="'+href+'" target="_blank" style="font-size:12px" onclick="event.stopPropagation();return openWebOverlay(this.href)">'+esc(c.link.label||'상세 →')+'</a>';
      }
      if(c.image){
        const img=tpl(c.image,it);
        // wide: 16:9 가로 썸네일을 위에 크게(유튜브 모바일 홈 카드) — 데스크탑 파리티
        if(c.wide) return '<div class="card" style="margin:0"'+click+'>'+(img?'<img src="'+img+'" loading="lazy" style="width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:10px;background:var(--bg3)">':'<div style="width:100%;aspect-ratio:16/9;border-radius:10px;background:var(--bg3)"></div>')+'<div style="margin-top:8px">'+body+'</div></div>';
        return '<div class="card bookcard"'+click+'>'+(img?'<img src="'+img+'" loading="lazy">':'<img>')+'<div>'+body+'</div></div>';
      }
      return '<div class="card"'+click+'>'+body+'</div>';
    }).join('')+(c.wide?'</div>':'');
  }
  if(p.type==='image_grid'){
    const arr=viewList(data,p.from);
    if(!arr.length) return emptyMsg(p,data);
    return '<div class="posters">'+arr.map((it,ri)=>{
      const img=p.image?tpl(p.image,it):'';
      // 클릭=원본/동영상 라이트박스. URL 은 클릭 시 <img src>에서 파생(따옴표 이스케이프 회피, CCTV playStream 선례).
      const click=img?' onclick="openMediaFromEl(this)" style="cursor:pointer"':'';
      // 행 버튼(사진 빼기 등) — list_action button 과 같은 어휘(rowBtn 공유), 라이트박스 클릭과 분리.
      const btn=(p.button&&p.button.action)?'<button class="btn2" style="margin-top:4px" onclick="event.stopPropagation();rowBtn('+vi+','+ri+',this)">'+esc(p.button.label||'실행')+'</button>':'';
      return '<div class="poster"'+click+'>'+(img?'<img src="'+img+'" loading="lazy">':'<div style="aspect-ratio:3/4;background:var(--bg3);border-radius:8px"></div>')+
        '<div class="t">'+tpl(p.title,it)+'</div><div class="m">'+(p.lines||[]).map(l=>tpl(l,it)).join('<br>')+'</div>'+btn+'</div>';
    }).join('')+'</div>';
  }
  if(p.type==='media_player'){
    const arr=viewList(data,p.from);
    if(!arr.length) return emptyMsg(p,data);
    // continuous: 한 곡이 끝나면 다음 곡 자동 재생(앨범·플레이리스트 연속 듣기) — 데스크탑 파리티
    const cont=p.continuous?' data-mp="1" onended="mpNext(this)"':'';
    // lazy: preload="none" — 항목마다 스트림을 미리 물지 않는다(유튜브 릴레이처럼 요청이
    // 곧 서버 작업(해소+ffmpeg)인 src 는 재생을 눌러야만 받게). video: '{is_video}'(또는
    // true) 참이면 <audio> 대신 <video>(poster 지원) — 데스크탑 파리티.
    // ★목록 길이를 함께 넘긴다 — 긴 목록(음악앱 한 폴더 최대 500곡)은 lazy 선언이 없어도
    //   'none' 이어야 한다(판정은 공용 코어 preloadOf 가 정본).
    const pre=preloadOf(p,arr.length);
    // src_low: 느린 회선(테슬라 실측 1.4Mbps — 원본 1080p 는 소리만 나오고 화면 정지)이면
    // 저대역 판 자동 선택. 판정·소스 선택은 공용 코어(isSlowNet/mediaModel)가 정본.
    const slowNet=isSlowNet(navigator.connection);
    // 적응형(HLS) 하이드레이션 — innerHTML 로 붙는 video[data-hls] 를 관찰해 hls.js 를
    // 문다(조각마다 화질 자동 전환). autoStartLoad:false + play 시 startLoad = lazy 유지.
    if(!window.__mpHlsObs&&window.Hls&&Hls.isSupported()){
      const arm=()=>{document.querySelectorAll('video[data-hls]:not([data-hls-on])').forEach(v=>{
        v.setAttribute('data-hls-on','1');
        const h=new Hls({autoStartLoad:false});
        h.loadSource(v.getAttribute('data-hls')); h.attachMedia(v);
        v.addEventListener('play',()=>h.startLoad(),{once:true});
      });};
      window.__mpHlsObs=new MutationObserver(arm);
      window.__mpHlsObs.observe(document.body,{childList:true,subtree:true});
      arm();
    }
    // 🔀 랜덤 — 연속 재생(continuous) 자리에만 붙는다. 묶음 div 가 셔플 상태·자루를 들고,
    // 다음 곡 결정은 공용 코어(shuffleNext)가 한다 — 데스크탑과 같은 규칙.
    const shBtn=(p.continuous&&arr.length>1)?'<button class="btn2" style="margin-bottom:8px" onclick="mpShuffle(this)">🔀 랜덤</button>':'';
    return '<div'+(p.continuous?' data-mp-group="1"':'')+'>'+shBtn+arr.map(it=>{
      const mm=mediaModel(p,it,tpl,slowNet);   // tpl=원격판(값 esc) — 속성 안에 들어가므로 그대로
      // 소스 해소(절대 URL / 백엔드 라우트 / 파일경로)는 공용 코어가 정본 — 원격은 동일오리진이라 base=''.
      // ★'/' 로 시작한다고 site-relative 가 아니다: 파일시스템 절대경로도 '/' 로 시작한다(isBackendRoute).
      const src=resolveMediaUrl(mm.src,'');
      const title=mm.title, isVid=mm.isVideo, poster=resolveMediaUrl(mm.poster,'');
      // 소스 우선순위: HLS(hls.js — 적응형) > 네이티브 HLS(사파리) > 프로그레시브(+저대역 자동)
      const hlsRaw=resolveMediaUrl(mm.hls,'');
      const canHlsJs=isVid&&hlsRaw&&window.Hls&&Hls.isSupported();
      const canNative=isVid&&hlsRaw&&!canHlsJs&&document.createElement('video').canPlayType('application/vnd.apple.mpegurl');
      const vSrc=canHlsJs?'':(canNative?hlsRaw:src);
      const vAttr=canHlsJs?' data-hls="'+hlsRaw+'"':(vSrc?' src="'+vSrc+'"':'');
      // max-width 캡 — 넓은 화면에서 전폭 확대는 과하다(유튜브 데스크탑 플레이어 상한)
      const media=isVid
        ?'<video controls playsinline preload="'+pre+'"'+vAttr+(poster?' poster="'+poster+'"':'')+' style="width:100%;max-width:880px;display:block;margin:0 auto;border-radius:10px;background:#000;aspect-ratio:16/9"></video>'
        :'<audio controls preload="'+pre+'" src="'+src+'" style="width:100%"'+cont+'></audio>';
      return '<div class="card">'+(title?'<div class="step-label">'+esc(title)+'</div>':'')+((src||canHlsJs)?media:'<div class="m">재생할 오디오가 없습니다.</div>')+'</div>';
    }).join('')+'</div>';
  }
  if(p.type==='thread'){
    const rows=viewList(data,p.from);
    const arr=p.reverse===true?[...rows].reverse():rows;
    if(!arr.length) return emptyMsg(p,data);
    // 항목 버튼(item_button) — 본문이 match(정규식, i)와 일치하는 항목에만 붙는 선언형 버튼
    // (2026-08-31 뷰 어휘 개정). 계약(정규식·라벨·액션)은 매니페스트 데이터 — 렌더러는 내용어를 모른다.
    let ibRe=null;
    if(p.item_button&&p.item_button.action&&p.item_button.match){ try{ ibRe=new RegExp(p.item_button.match,'i'); }catch(e){} }
    return '<div class="thread">'+arr.map((it,ri)=>{
      const sourceIndex=p.reverse===true?arr.length-1-ri:ri;
      const mine=p.mine?!!jget(it,p.mine):false;
      const st=p.status?statusGlyph(jget(it,p.status)||''):'';
      const foot=[p.meta?tpl(p.meta,it):'', p.time?tpl(p.time,it):'', st].filter(Boolean).join(' · ');
      const txt=tpl(p.text,it);
      const ibtn=(ibRe&&ibRe.test(txt))?'<div><button class="btn2" style="margin-top:4px" onclick="threadIbBtn('+vi+','+sourceIndex+',this)">'+esc(p.item_button.label||'실행')+'</button></div>':'';
      return '<div class="tmsg'+(mine?' me':'')+'"><div class="tbub">'+txt+'</div>'+ibtn+(foot?'<div class="tfoot">'+foot+'</div>':'')+'</div>';
    }).join('')+'</div>';
  }
  if(p.type==='engine'){
    // engine(2026-10-05) — 편집 엔진 표면은 데스크탑 계기가 연다. 원격/폰은 열람 강등: 원문이 있으면 보여주고 안내만.
    const text=jget(data,'text');
    return '<div class="card muted" style="font-size:13px">편집 엔진 표면은 데스크탑 앱에서 열립니다 · 여기서는 열람만</div>'
      +(text?'<pre class="result">'+esc(String(text))+'</pre>':'');
  }
  if(p.type==='blocks'){
    // 문서 IR 렌더 — from 배열의 각 원소 = 블록 {type,...} (self:read blocks:true / table:structure 출력)
    const arr=viewList(data,p.from);
    if(!arr.length) return emptyMsg(p,data);
    return '<div class="card docv">'+arr.map(docBlockHtml).join('')+'</div>';
  }
  if(p.type==='form'){
    let h='<div class="card">'+(p.title?'<div class="step-label">'+esc(tpl(p.title,data))+'</div>':'');
    (p.fields||[]).forEach((f,fi)=>{
      const val=tpl(f.value||'',data); const id='ff_'+vi+'_'+f.key;
      h+='<div style="margin-bottom:8px"><label class="muted" style="display:block;font-size:11px;margin-bottom:3px">'+esc(f.label||'')+'</label>';
      if(f.type==='select') h+='<select class="field" id="'+id+'">'+(f.options||[]).map(o=>'<option value="'+esc(String(o.value))+'"'+(String(o.value)===String(val)?' selected':'')+'>'+esc(o.label)+'</option>').join('')+'</select>';
      else if(f.type==='textarea'){ h+='<textarea class="field" id="'+id+'" rows="'+(f.rows||3)+'">'+esc(val)+'</textarea>';
        if(f.ai_dock){ h+='<div id="aid_sug_'+vi+'_'+fi+'"></div>'
          +'<div class="row" style="margin-top:6px;align-items:flex-end">'
          +'<textarea class="field" id="aid_in_'+vi+'_'+fi+'" rows="1" style="flex:1" placeholder="'+esc(f.ai_dock.placeholder||'AI에게 시키기 — 예: 더 간결하게')+'"></textarea>'
          +'<button class="go" onclick="aiDockAsk('+vi+','+fi+',this)">✨ AI</button></div>'; }
      }
      else if(f.type==='toggle') h+='<select class="field" id="'+id+'"><option value="0"'+(String(val)!=='1'?' selected':'')+'>꺼짐</option><option value="1"'+(String(val)==='1'?' selected':'')+'>켜짐</option></select>';
      else if(f.type==='images'){
        // 썸네일(전 표면 /image?path=) + 제거. 추가(파일선택)는 데스크탑 전용이라 원격엔 없음.
        const arr=parseImagePaths(val);   // 공용 코어 — attachment_path(JSON 배열 또는 레거시 단일)
        h+='<div style="display:flex;flex-wrap:wrap;gap:8px">';
        arr.forEach(pth=>{ h+='<div style="position:relative">'
          +'<img src="'+API+'/image?path='+encodeURIComponent(pth)+'" style="width:64px;height:64px;object-fit:cover;border-radius:8px;border:1px solid var(--line)">'
          +(f.remove_action?'<button onclick="imgRemove('+vi+','+fi+',\''+encodeURIComponent(pth)+'\')" style="position:absolute;top:-6px;right:-6px;width:20px;height:20px;border-radius:50%;background:#333;color:#fff;border:none;font-size:12px;line-height:1;cursor:pointer">×</button>':'')
          +'</div>'; });
        if(!arr.length) h+='<span class="muted" style="font-size:12px">이미지 없음 (사진 추가는 데스크탑에서)</span>';
        h+='</div>';
      }
      else if(f.type==='recurrence') h+=_recurSelect(id,val);
      else if(f.type==='date'||f.type==='time'||f.type==='datetime') h+='<input type="'+dateInputType(f.type)+'" class="field" id="'+id+'" value="'+esc(val)+'">';
      else if(f.type==='folder') h+='<input class="field" id="'+id+'" value="'+esc(val)+'" placeholder="'+esc(f.placeholder||'폴더 경로 (선택은 데스크탑에서)')+'">';
      // files: 네이티브 다중 파일 선택은 데스크탑 전용(window.electron.selectFiles) — 원격은 안내만.
      // 입력을 그리지 않으므로 formSave 의 값 수집(if(el))에서 조용히 빠진다(images 와 같은 강등).
      else if(f.type==='files') h+='<span class="muted" style="font-size:12px">파일 선택은 데스크탑에서</span>';
      else h+='<input class="field" id="'+id+'" value="'+esc(val)+'" placeholder="'+esc(f.placeholder||'')+'">';
      h+='</div>';
    });
    h+='<div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:4px">'
      +'<button class="go" onclick="formSave('+vi+',this)">'+esc(p.button||'저장')+'</button>';
    // 보조 액션(즐겨찾기 토글·삭제 등) — 드릴 데이터 컨텍스트로 실행
    (p.actions||[]).forEach((a,ai)=>{
      const dz=a.style==='danger'?';color:#c0392b;border-color:#e8b9b3':'';
      h+='<button class="linkbtn" style="padding:9px 13px;border:1px solid var(--line);border-radius:10px'+dz+'" onclick="formAct('+vi+','+ai+',this)">'+esc(tpl(a.label,data))+'</button>';
    });
    h+='</div></div>';
    return h;
  }
  if(p.type==='editable_list'){
    const arr=viewList(data,p.from);
    let h='<div class="card">'+(p.title?'<div class="step-label">'+esc(p.title)+'</div>':'');
    if(!arr.length) h+='<p class="muted">'+esc(p.empty||'없음')+'</p>';
    arr.forEach((it,ri)=>{ h+='<div class="kv"><span class="k">'+tpl(p.display,it)+'</span>'+(p.delete_action?'<button class="linkbtn" onclick="elDelete('+vi+','+ri+')">삭제</button>':'')+'</div>'; });
    if(p.add){
      h+='<div class="row" style="flex-wrap:wrap;margin-top:8px">'+(p.add.fields||[]).map(f=>{ const eid='ea_'+vi+'_'+f.key;
          if(f.type==='select') return '<select class="field" id="'+eid+'" style="flex:0 1 110px"><option value="">'+esc(f.placeholder||'')+'</option>'+(f.options||[]).map(o=>'<option value="'+esc(String(o.value))+'">'+esc(o.label)+'</option>').join('')+'</select>';
          if(f.type==='recurrence') return _recurSelect(eid,'');
          if(f.type==='date'||f.type==='time'||f.type==='datetime') return '<input type="'+dateInputType(f.type)+'" class="field" style="min-width:0" id="'+eid+'">';
          return '<input class="field" style="min-width:0" id="'+eid+'" placeholder="'+esc(f.placeholder||'')+'">'; }).join('')
        +'<button class="go" onclick="elAdd('+vi+',this)">'+esc((p.add.button)||'추가')+'</button></div>';
    }
    h+='</div>'; return h;
  }
  if(p.type==='sparkline'){
    // 좌표·스케일·라벨 포맷은 공용 코어(sparkModel/fmtSpark) — 여기선 SVG 마크업만
    const sm=sparkModel(p,data);
    if(!sm) return '';
    const rows=sm.rows, w=sm.w, hh=sm.h, pts=sm.pts, fmt=fmtSpark;
    const col=trendColor(p,data)||'var(--acc)';
    const lbl='position:absolute;right:0;font-size:10px;color:var(--dim);background:var(--bg2);padding:0 2px;border-radius:3px';
    return '<div class="card"><div style="position:relative">'
      +'<div style="position:relative;height:64px">'
      +'<svg viewBox="0 0 '+w+' '+hh+'" style="width:100%;height:100%" preserveAspectRatio="none"><polyline points="'+pts+'" fill="none" stroke="'+col+'" stroke-width="1.5" vector-effect="non-scaling-stroke"/></svg>'
      +'<span style="'+lbl+';top:0">'+esc(fmt(sm.mx))+'</span>'
      +'<span style="'+lbl+';bottom:0">'+esc(fmt(sm.mn))+'</span>'
      +'</div>'
      +'<div style="display:flex;justify-content:space-between;font-size:10px;color:var(--dim);margin-top:4px"><span>'+esc(rows[0].x)+'</span><span>'+esc(rows[rows.length-1].x)+'</span></div>'
      +'</div></div>';
  }
  if(p.type==='list_action'){
    const arr=viewList(data,p.from);
    if(!arr.length) return emptyMsg(p,data);
    const click=p.item_click?' style="cursor:pointer"':'';
    return arr.map((it,ri)=>
      '<div class="card sw-item"'+(p.item_click?' onclick="rowDrill('+vi+','+ri+','+(SPLIT&&VIEW_CTX&&data===VIEW_CTX.data?'true':'false')+')"':'')+click+'>'+(p.icon?'<span>'+esc(p.icon)+'</span>':'')+
      '<div style="flex:1"><div class="nm">'+tpl(p.title,it)+'</div><div class="pr">'+tpl(p.sub,it)+'</div></div>'+
      (p.select&&p.select.action?'<select class="btn2" onclick="event.stopPropagation()" onchange="event.stopPropagation();rowSel('+vi+','+ri+',this)">'+(p.select.options||[]).map(function(o){var sv=String(o.value);return '<option value="'+esc(sv)+'"'+(String(tpl(p.select.value,it))===sv?' selected':'')+'>'+esc(o.label)+'</option>';}).join('')+'</select>':'')+
      (p.button?'<button class="btn2" onclick="event.stopPropagation();rowBtn('+vi+','+ri+',this)">'+esc(p.button.label||'▶')+'</button>':'')+
      (p.button2?'<button class="btn2" onclick="event.stopPropagation();rowBtn('+vi+','+ri+',this,\'button2\')">'+esc(p.button2.label||'⬇')+'</button>':'')+'</div>'
    ).join('');
  }
  return '';
}
function renderComposeBar(cmp){
  if(!cmp) return '';
  const opts=composeChannelOptions(cmp, VIEW_CTX&&VIEW_CTX.data);
  let sel='';
  /* 어디로 보내는지는 항상 보인다 — 후보가 하나뿐이어도 칩으로 표시(고를 게 없을 뿐 숨길 이유는 없음) */
  if(opts.length>=2) sel='<select id="composeChannel" class="field chan" style="border-radius:22px">'
    +opts.map(o=>'<option value="'+esc(o.key)+'">'+esc(o.label)+'</option>').join('')+'</select>';
  else if(opts.length===1) sel='<span class="muted chan" title="발신 채널" style="font-size:12px">'
    +esc(opts[0].label)+'</span>';
  /* 발신 채널(어디로 보내나)은 제 줄에 — 입력+전송과 한 줄로 묶으면 좁은 드릴 패널에서 넘친다 */
  return '<div class="composebar">'+(sel?'<div class="chanrow">'+sel+'</div>':'')+'<div class="sendrow">'+'<input id="composeInput" class="field" placeholder="'+esc(cmp.placeholder||'메시지 입력…')+'" '
    +'onkeydown="if(event.key===\'Enter\')composeSend(document.getElementById(\'composeSendBtn\'))">'
    +'<button id="composeSendBtn" class="go" onclick="composeSend(this)">'+esc(cmp.button||'전송')+'</button></div></div>';
}
function renderDrill(){
  const out = SPLIT ? document.getElementById('mdDetail') : document.getElementById('instOut');
  if(!out||!VIEW_CTX) return;
  let h = SPLIT ? '<button class="linkbtn mdback" onclick="mdBack()">‹ 목록</button>'
                : '<button class="linkbtn" onclick="runMode()">‹ 목록으로</button>';
  let av, ac;
  if(VIEW_CTX.tabs&&VIEW_CTX.tabs.length){
    const ai=Math.min(VIEW_CTX.activeTab||0,VIEW_CTX.tabs.length-1);
    h+='<div class="tabs">'+VIEW_CTX.tabs.map((t,i)=>'<button class="tab'+(i===ai?' on':'')+'" onclick="drillTab('+i+')">'+esc(t.name)+'</button>').join('')+'</div>';
    av=VIEW_CTX.tabs[ai].view; ac=VIEW_CTX.tabs[ai].compose;
  } else { av=VIEW_CTX.view; ac=VIEW_CTX.compose; }
  VIEW_CTX._activeView=av; VIEW_CTX._activeCompose=ac;
  out.innerHTML=h+renderView(av,VIEW_CTX.data)+renderComposeBar(ac);
  initMaps(); scheduleDetailPoll();
}

/* 원격 조종실의 표시만 소유한다. 조회·타이머·선택 상태는 launcher_manual_js에 둔다. */
function cpAttr(value){ return esc(value).replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
function cpSystemText(value){
  return '<span data-ui-system="'+cpAttr(value||'')+'">'+esc(value||'')+'</span>';
}
function cpHealthLabel(health){
  return health.healthy==null?'IBL 미점검':!health.healthy?'IBL 주의':health.stale?'IBL 점검 오래됨':'IBL 건강';
}
function cpPursuitStatus(status){
  return ({active:'진행 중',parked:'보류',done:'완료',abandoned:'보관'})[status]||status;
}
function cpRender(kind,data){
  if(kind==='active') return (data.items||[]).map(it=>
    '<div class="cp-entry"><button class="btn2" data-kind="'+cpAttr(it.kind)+'" data-project="'+cpAttr(it.project_id)+'" onclick="cpOpenActive(this)">'+esc(it.project_name)+'</button> '+
    (it.busy?'작업 중 · '+esc(it.elapsed_sec)+'초째':'대기 중')+
    '<div class="muted">'+esc((it.agents||[]).join(' · '))+'</div></div>').join('')||'<p class="muted">없음</p>';
  if(kind==='structure') return mdChat(data.content||'');
  if(kind==='status'){
    const h=data.ibl_health||{};
    return '<p>'+esc(cpHealthLabel(h))+' · 마지막 점검 '+esc(h.checked_at||'미점검')+'</p>'+
      (h.items||[]).map(it=>'<div class="cp-entry">'+(it.ok==null?'○':it.ok?'✓':'⚠')+' '+cpSystemText(it.label)+
        (it.detail?'<div class="muted">'+cpSystemText(it.detail)+'</div>':'')+'</div>').join('')+
      '<p>액션 '+esc(h.action_count??'—')+'개 · 디스크 '+esc(data.disk_free_gb??'—')+'GB</p>'+
      Object.entries(data.services||{}).map(([name,alive])=>'<p>'+cpSystemText(({scheduler:'스케줄러',channel_poller:'채널 폴러',system_ai_runner:'시스템 AI'})[name]||name)+
        ' · '+(alive?'실행 중':'중지')+'</p>').join('');
  }
  if(kind==='logs') return (data.note?'<p class="muted">'+esc(data.note)+'</p>':'')+
    '<pre class="cp-scroll">'+esc((data.lines||[]).join('\n')||'(비어 있음)')+'</pre>';
  if(kind==='limbs') return cpRenderLimbs(data);
  if(kind==='body') return cpRenderBody(data);
  if(kind==='pursuits'){
    const rows=data.items||[];
    return (rows.map(p=>'<div class="cp-entry"><button class="btn2" data-id="'+cpAttr(p.id)+'" onclick="cpPursuitDetail(this.dataset.id,this)">'+esc(p.title)+'</button><article hidden></article>'+
      '<p class="muted">'+esc(cpPursuitStatus(p.status))+' · '+esc(p.agent_key)+'</p>'+
      (p.next?'<p>다음: '+esc(p.next)+'</p>':'')+'</div>').join('')||'<p class="muted">아직 기록된 과제가 없습니다.</p>')+
      '<div class="cp-tools"><button class="btn2" onclick="cpPursuitPage(-20)"'+(cpPursuitOffset===0?' disabled':'')+'>이전</button>'+
      '<span>'+esc(rows.length?cpPursuitOffset+1:0)+'–'+esc(cpPursuitOffset+rows.length)+' / '+esc(data.total||0)+'</span>'+
      '<button class="btn2" onclick="cpPursuitPage(20)"'+(cpPursuitOffset+20>=(data.total||0)?' disabled':'')+'>다음</button></div>';
  }
  return '';
}
function cpRenderLimbs(data){
  const rows=(data.items||[]).filter(pc=>!pc.revoked&&pc.registration?.state!=='removed');
  const phoneLabels={bootstrap:'업데이트 지원 APK 최초 설치 필요',unpublished:'중앙 APK 미발행',current:'앱 최신',available:'새 앱 있음',updating:'APK 전송 중',staged:'설치 준비 중',installing:'설치·재접속 확인 중',awaiting_permission:'폰에서 앱 설치 권한 허용 필요',awaiting_confirmation:'폰에서 Android 설치 확인 필요',failed:'업데이트 실패',incompatible:'APK 호환 확인 필요'};
  const helperLabels={unknown:'헬퍼 상태 미확인',current:'헬퍼 최신',manual:'새 헬퍼 있음(직접 교체)',available:'새 헬퍼 있음',updating:'헬퍼 교체 중'};
  return '<p>USB에 복사할 공용 헬퍼 폴더</p><pre>'+esc(data.usb?.folder||'—')+'</pre><p class="muted">'+(data.usb?.ready?'준비됨':'폴더 준비 필요')+'</p>'+
    (rows.map(pc=>{
      const reg=pc.registration||{}, phone=reg.kind==='phone', update=pc.phone_update;
      const status=reg.state==='removal_pending'?'해제 요청됨':reg.paused?'작업 중지됨':pc.connected?'연결됨':'오프라인';
      return '<div class="cp-entry"><b>'+esc(pc.alias)+'</b><p>'+esc(status)+' · '+(phone?'폰 (IndieBiz OS)':'PC')+' · '+esc(reg.capabilities?.os||'')+'</p>'+
        '<p class="muted">'+esc(phone?(phoneLabels[update?.state]||update?.state||''):(helperLabels[pc.helper?.state]||''))+
        (pc.helper?.rolled_back?' · 지난 교체가 되돌려짐':'')+
        (update?.current_version?' · v'+esc(update.current_version):'')+(update?.latest_version?' → v'+esc(update.latest_version):'')+
        (update?.message?' · '+esc(update.message):'')+'</p></div>';
    }).join('')||'<p class="muted">아직 등록된 기기가 없습니다.</p>');
}
function cpRenderBody(data){
  const rows=data.items||[], keys=[...new Set(rows.flatMap(row=>Object.keys(row)))];
  return (data.path?'<p>'+esc(data.path)+'</p>':'')+'<p class="muted">'+esc(data.text)+'</p>'+
    (rows.length?'<div class="cp-scroll"><table><thead><tr>'+keys.map(k=>'<th>'+esc(k)+'</th>').join('')+'</tr></thead><tbody>'+
      rows.map(row=>'<tr>'+keys.map(k=>'<td>'+(k==='파일'&&row[k]?'<button class="linkbtn" data-path="'+cpAttr(row[k])+'" onclick="cpBodyFile(this.dataset.path)">'+esc(row[k])+'</button>':
        esc(typeof row[k]==='object'?JSON.stringify(row[k]):row[k]))+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>':'<p class="muted">이 기간엔 기록이 없습니다.</p>');
}
function cpRenderPursuit(data){
  const p=data.pursuit||{};
  return '<h4>'+esc(p.title)+' · '+esc(cpPursuitStatus(p.status))+'</h4>'+
    (data.pending_turns?.length?'<p>요약 대기 또는 중단된 턴 '+esc(data.pending_turns.length)+'건이 있습니다.</p>':'')+
    [['전체 완료 기준',p.goal_criteria],['현재 규정',p.framing],['확보한 결과',p.progress],['다음 할 일',p.next]].map(([label,value])=>
      value?'<p><b>'+esc(label)+'</b></p><pre>'+esc(value)+'</pre>':'').join('')+
    (p.assumptions||[]).filter(a=>a.status==='broken').map(a=>'<p>깨진 전제: '+esc(a.text)+' — '+esc(a.evidence)+'</p>').join('')+
    '<details><summary>사건 기록</summary>'+((data.events||[]).map(e=>'<div class="cp-entry"><b>'+esc(e.kind)+'</b><pre class="cp-scroll">'+esc(JSON.stringify(e.payload,null,2))+'</pre></div>').join('')||'<p class="muted">기록 없음</p>')+'</details>';
}
function cpRenderRecall(data){
  return '<p>해마 최고점수 '+esc(((data.top_score||0)*100).toFixed(1))+'%'+(data.top_score>=0.85?' — 반사(Reflex) 경로':'')+
    ' · 주입 '+esc(data.total_chars??0)+'자</p><pre>'+esc(data.top_code||'')+'</pre>'+
    (data.sections||[]).map(sec=>sec.present?'<details open><summary>'+esc(sec.label)+' ('+esc((sec.content||'').length)+'자)</summary><pre class="cp-scroll">'+esc(sec.content)+'</pre></details>':
      '<p class="muted">'+esc(sec.label)+' — 회상 없음</p>').join('');
}

function cpRenderHistory(){
  return cpHistory.map((entry,index)=>'<div class="cp-entry"><button class="btn2" onclick="cpRestoreHistory('+index+')">'+(entry.ok?'✓ ':'⚠ ')+esc(entry.intent||entry.code)+'</button><pre>'+esc(entry.code)+'</pre></div>').join('');
}
