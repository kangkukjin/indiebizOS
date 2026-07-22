"""원격 런처 웹앱 JS — 자율주행 표면 탭(ap*: 대상 드릴다운·대화·스위치·스케줄).

2026-07-22 표면 분리 1단계(launcher_web_app.py 에서 verbatim 분해)."""

LAUNCHER_AUTOPILOT_JS = """/* ================= 자율주행 (드릴다운) ================= */
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

"""
