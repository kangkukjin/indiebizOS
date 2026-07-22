"""원격 런처 웹앱 JS — 공유창고 표면 탭(내 창고 wh* · 이웃 피드 wf* · 이웃찾기 wd*).

창고는 숙주(맥) 몸의 살림 — 폰네이티브 표면 조립에는 이 조각이 들어가지 않는다.
2026-07-22 표면 분리 1단계(launcher_web_app.py 에서 verbatim 분해)."""

LAUNCHER_WAREHOUSE_JS = """/* ================= 공유창고 (레벨별 폴더 — 소유자 리모컨) =================
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
   발견 채널은 #indienet 고정([others:feed]{hashtag:"indienet"}) — publish_intro 가 항상
   #IndieNet 으로 발신하므로 수신도 같은 주파수. hashtag 를 안 넘기면 활성 보드(active_board)로
   폴백해, 보드를 전환한 기기(윈도우 사례)에선 조용히 다른 방을 읽는다. 소개 본문의
   "공유창고 : <url>" 라벨(indienet_publish.publish_intro 계약)을 파싱해 창고이웃 등록으로 잇는다. */
let wdItems=[]; let wdAdded={};
async function wdLoad(){
  const l=document.getElementById('wdList'); if(!l) return;
  if(!wdItems.length) l.innerHTML='<div class="wh-empty">📡 릴레이에서 소개를 모으는 중…</div>';
  try{
    const r=await ibl('[others:feed]{op: "read", hashtag: "indienet", limit: 50}');
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
/* 게시판처럼 한마디 — 커뮤니티 계기와 같은 [others:feed]{op:"post"} 경로. 내용=JSON.stringify 이스케이프.
   ★hashtag 고정 필수: 없으면 post_to_board 활성 보드 폴백 — 보드 전환 기기에선 다른 방에 발행. */
async function wdPost(){
  const inp=document.getElementById('wdDraft'); const btn=document.getElementById('wdPostBtn');
  const t=(inp&&inp.value||'').trim(); if(!t) return;
  if(btn){ btn.disabled=true; btn.textContent='게시 중…'; }
  try{
    const r=await ibl('[others:feed]{op: "post", hashtag: "indienet", content: '+JSON.stringify(t)+'}');
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

"""
