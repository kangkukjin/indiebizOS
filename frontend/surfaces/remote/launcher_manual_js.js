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
        '<label class="warnbox"><input type="checkbox" id="mConfirm" onchange="document.getElementById(\'mExecBtn\').disabled=!this.checked"><span><b>부작용(쓰기/외부 전송)이 있는 액션</b>입니다. 실행하면 되돌릴 수 없을 수 있습니다. 확인 후 체크하세요.</span></label>';
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
async function apOpenDictionary(){
  closeAbout();
  const dialog=document.getElementById('apDictionaryDialog'),palette=document.getElementById('palette');
  dialog.append(palette);palette.style.display='block';dialog.showModal();
  if(!paletteLoaded)await loadPalette();
}
function apRestoreDictionary(){
  document.getElementById('paletteHome').append(document.getElementById('palette'));closePalette();
}
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
        const meta=acts[a]||{}, search=[node,a,meta.description,...(meta.keywords||[])].join(' ').toLowerCase();
        html+='<div class="act-chip" data-key="'+cpAttr(search)+'"><button class="btn2" data-seed="'+cpAttr(seed)+'" onclick="seedAction(this.dataset.seed)">'+esc(a)+'</button>'+
          '<p>'+cpSystemText(meta.description)+'</p>'+(meta.target_key?'<p><code>'+esc(meta.target_key)+'</code> — '+cpSystemText(meta.target_description)+'</p>':'')+
          Object.entries(meta.ops?.values||{}).map(([op,description])=>'<p><code>'+esc(op)+'</code> — '+cpSystemText(String(description))+'</p>').join('')+'</div>';
      }
      html+='</div>';
    }
    html+='</div>'; p.innerHTML=html; paletteLoaded=true;
  }catch(e){ p.innerHTML='<p class="muted">카탈로그 로드 실패</p>'; }
}
function filterPalette(q){
  q=(q||'').toLowerCase().trim();
  document.querySelectorAll('#palette-list .act-chip').forEach(c=>{
    c.style.display=getConversation().matchesWord(c.dataset.key,q)?'inline-block':'none';
  });
}
function seedAction(seed){
  const dialog=document.getElementById('apDictionaryDialog');
  if(dialog?.open){
    const input=document.getElementById('apInput');input.value+=(input.value?String.fromCharCode(10):'')+seed+' ';dialog.close();input.focus();return;
  }
  document.getElementById('mCode').value=seed;
  document.getElementById('mAfterTranslate').style.display='block';
  document.getElementById('mCode').focus();
  document.getElementById('palette').scrollIntoView({behavior:'smooth',block:'nearest'});
}

/* ================= 주행기록계 =================
   PC 조종실(EpisodeJournal.tsx)과 같은 화면을 이 표면에도 둔다 — 지난 주행 목록,
   행을 누르면 그 주행의 실행기억(전체 로그), 분석 스위치.
   API 도 데스크탑과 같은 것을 쓴다: /world-pulse/episodes · /xray/episodes/{id} ·
   /world-pulse/episodes/{id}/analysis-prompt. 이 셋은 is_public_remote_path 목록에
   없으므로 외부(터널)에서는 런처 세션 쿠키가 있어야 통과한다 — 주행기록이 무인가
   접근에 열리지 않는다는 뜻이고, 새 인증 경계를 만들지 않았다는 뜻이기도 하다.
   데스크탑은 Electron 창을 열어 분석하지만 여기엔 창이 없으므로, 같은 프롬프트를
   자율주행 탭의 시스템 AI 입력칸에 실어 준다(보내기는 사용자가 누른다). */
let jOpen=false, jRows=null, jExpanded=null, jLogs={}, jTimer=null;
function jRel(iso){
  if(!iso) return '';
  const t=Date.parse(iso); if(isNaN(t)) return '';
  const s=Math.max(0,Math.floor((Date.now()-t)/1000));
  if(s<60) return s+'초 전';
  if(s<3600) return Math.floor(s/60)+'분 전';
  if(s<86400) return Math.floor(s/3600)+'시간 전';
  return Math.floor(s/86400)+'일 전';
}
function jMeta(ep){
  const m=[];
  const rel=jRel(ep.started_at); if(rel) m.push(rel);
  if(ep.is_running) m.push('진행 중');
  if(ep.agent) m.push(String(ep.agent));
  if(ep.hippocampus_score!=null) m.push('확신 '+Math.round(ep.hippocampus_score*100)+'%');
  m.push(ep.execution_rounds!=null?ep.execution_rounds+'라운드':ep.is_running?'라운드 집계 대기':'라운드 미측정');
  m.push(ep.ibl_calls!=null?'IBL '+ep.ibl_calls+'회'+(ep.ibl_actions!=null?' · 액션 '+ep.ibl_actions:''):'IBL 미측정');
  if(ep.total_ms!=null) m.push((ep.total_ms/1000).toFixed(1)+'초');
  const d=ep.unconscious_decision;
  if(d) m.push(d==='THINK'?'숙고':(d==='EXECUTE'?'실행':String(d)));
  const r=ep.review_status==='APPROVED'?'ACHIEVED':ep.review_status==='REWORK'?'NOT_ACHIEVED':ep.review_status||ep.evaluation_result;
  if(r) m.push(r==='ACHIEVED'?'검수 승인':r==='NOT_ACHIEVED'?'기준 미충족':r==='UNKNOWN'?'검수 미완료':r==='NOT_RUN'?'미검수':String(r));
  if(r) m.push(ep.goal_status==='ACHIEVED'?'목표 달성':ep.goal_status==='NOT_ACHIEVED'?'목표 미달':'목표 미확정');
  return m.join(' · ');
}
function jRender(){
  const b=document.getElementById('jBody'); if(!b) return;
  if(jRows===null){ b.innerHTML='<p class="muted">기록 불러오는 중…</p>'; return; }
  if(!jRows.length){ b.innerHTML='<p class="muted">아직 기록된 주행이 없습니다.</p>'; return; }
  let h='';
  jRows.forEach(function(ep){
    const open=(jExpanded===ep.id), st=jLogs[ep.id];
    h+='<div style="padding:8px 0;border-bottom:1px solid var(--line)">';
    h+='<div style="display:flex;align-items:flex-start;gap:8px">';
    h+='<button onclick="jToggleLog('+ep.id+')" title="이 주행의 실행기억(전체 로그)을 펼칩니다" style="flex:1;min-width:0;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:left;background:none;border:none;padding:0;font-size:13px;color:var(--txt)">';
    h+=(open?'▾ ':'▸ ')+esc(ep.user_message||'(요청 없음)')+'</button>';
    h+='<button onclick="jAnalyze('+ep.id+')" title="이 주행을 시스템 AI로 분석 — 잘된 점·문제점·고칠 것" style="flex-shrink:0;font-size:11px;padding:4px 10px;border-radius:8px;border:1px solid var(--line);background:var(--bg3);color:var(--txt)">🔬 분석</button>';
    h+='</div>';
    h+='<div title="이번 응답의 검수 결과입니다. 중단 사유 보고가 승인된 경우에도 원래 작업은 미완료일 수 있습니다. 실제 결과는 상세 기록에서 확인하세요." style="font-size:11px;color:var(--dim);margin-top:4px">'+esc(jMeta(ep))+'</div>';
    if(open){
      h+='<div style="margin-top:8px;border:1px solid var(--line);border-radius:8px;background:var(--bg3);max-height:320px;overflow:auto">';
      if(!st||st.s==='loading') h+='<p class="muted" style="padding:8px 10px;margin:0">실행기억 불러오는 중…</p>';
      else if(st.s==='error') h+='<p class="muted" style="padding:8px 10px;margin:0">기록을 불러오지 못했습니다 (로그가 만료됐을 수 있습니다).</p>';
      else h+='<pre style="margin:0;padding:8px 10px;font-size:11px;line-height:1.5;white-space:pre-wrap;word-break:break-word">'+esc(st.t||'(로그가 비어 있습니다)')+'</pre>';
      h+='</div>';
    }
    h+='</div>';
  });
  b.innerHTML=h;
}
async function jLoad(background=false){
  clearTimeout(jTimer);
  if(!background){ jRows=null; jRender(); }
  try{
    const r=await jfetch('/world-pulse/episodes?limit=20');
    if(!r.ok) throw new Error('HTTP '+r.status);
    const d=await r.json();
    jRows=d.episodes||[];
  }catch(e){
    if(background){ if(jOpen) jTimer=setTimeout(()=>jLoad(true),5000); return; }
    jRows=[];
    const b=document.getElementById('jBody');
    if(b) b.innerHTML='<p class="muted">주행기록을 불러오지 못했습니다 — '+esc(e.message)+'</p>';
    return;
  }
  jRender();
  if(jOpen&&jRows.some(ep=>ep.is_running)) jTimer=setTimeout(()=>jLoad(true),5000);
}
function jToggle(){
  jOpen=!jOpen;
  if(!jOpen) clearTimeout(jTimer);
  const b=document.getElementById('jBody'); if(b) b.style.display=jOpen?'block':'none';
  const rb=document.getElementById('jReloadBtn'); if(rb) rb.style.display=jOpen?'block':'none';
  if(jOpen) jLoad(jRows!==null);
}
async function jToggleLog(id){
  const willOpen=(jExpanded!==id);
  jExpanded=willOpen?id:null;
  jRender();
  if(!willOpen) return;
  if(jLogs[id]&&jLogs[id].s==='ok') return;
  try{
    const r=await jfetch('/xray/episodes/'+id);
    if(!r.ok) throw new Error('HTTP '+r.status);
    const d=await r.json();
    jLogs[id]={s:'ok',t:d.log||''};
  }catch(e){ jLogs[id]={s:'error'}; }
  jRender();
}
async function jAnalyze(id){
  try{
    const r=await jfetch('/world-pulse/episodes/'+id+'/analysis-prompt');
    if(!r.ok) throw new Error('HTTP '+r.status);
    const d=await r.json();
    if(typeof setSurface!=='function'||typeof apPickSystem!=='function'){
      alert('이 표면에는 시스템 AI 채팅이 없습니다.'); return;
    }
    setSurface('autopilot'); apPickSystem();
    // 채팅 열기는 동기 처리다. 지연 콜백은 그 사이 열린 다른 상대의 초안을 덮어쓴다.
    const inp=document.getElementById('apInput');
    if(inp){ inp.value=d.prompt||''; inp.focus(); }
  }catch(e){ alert('분석 준비 실패: '+e.message); }
}

/* 조종실 정보는 데스크톱과 같은 API의 관측값을 읽는다. 세션/표면이 보일 때만 폴링한다. */
let cpTimer=null, cpTick=0;
const cpGenerations={}, cpInFlight=new Set();
const cpTargets={status:'cpStatusBody',limbs:'cpLimbsBody'};
function cpVisible(){
  return !document.hidden && document.getElementById('app')?.classList.contains('on') &&
    document.getElementById('p-manual')?.classList.contains('on');
}
async function cpRequest(path,options){
  const r=await jfetch(path,options);
  const data=await r.json();
  if(!r.ok) throw new Error(typeof data.detail==='string'?data.detail:'HTTP '+r.status);
  if(data.error || data.success===false) throw new Error(String(data.error||data.message||'조회 실패'));
  return data;
}
async function cpRead(kind){
  if(kind==='status') return cpRequest('/world-pulse/dashboard');
  if(kind==='limbs') return cpRequest('/remote-pcs');
}
async function cpLoad(kind,background=false){
  if(!cpVisible()) return;
  if(background&&cpInFlight.has(kind)) return;
  const box=document.getElementById(cpTargets[kind]); if(!box) return;
  const generation=(cpGenerations[kind]||0)+1; cpGenerations[kind]=generation;
  cpInFlight.add(kind);
  if(!background) box.innerHTML='<p class="muted">불러오는 중…</p>';
  try{
    const data=await cpRead(kind);
    if(generation!==cpGenerations[kind]||!cpVisible()) return;
    box.innerHTML=cpRender(kind,data);
    if(kind==='status') document.getElementById('cpHealthSummary').textContent=cpHealthLabel(data.ibl_health||{});
  }catch(e){
    if(generation!==cpGenerations[kind]||!cpVisible()) return;
    box.innerHTML='<p role="alert" class="cp-error">불러오지 못했습니다 — '+esc(e.message)+'</p>'+
      '<button class="btn2" data-kind="'+kind+'" onclick="cpLoad(this.dataset.kind)">다시 시도</button>';
    if(kind==='status') document.getElementById('cpHealthSummary').textContent='조회 실패';
  }finally{ if(generation===cpGenerations[kind]) cpInFlight.delete(kind); }
}
function cpToggle(kind,open){ if(open) cpLoad(kind); }
function cpSync(){
  clearTimeout(cpTimer); cpTimer=null;
  if(!cpVisible()){
    // 화면을 떠난 뒤 도착한 응답은 다시 로그인한 화면을 덮어쓰지 않는다.
    for(const key of Object.keys(cpGenerations)) cpGenerations[key]++;
    cpInFlight.clear();
    return;
  }
  if(cpTick++%2===0) cpLoad('status',true);
  if(document.getElementById('cpLimbs')?.open) cpLoad('limbs',true);
  cpTimer=setTimeout(cpSync,15000);
}
function cpEnter(){ cpTick=0; cpSync(); }
// 공통/폰 셸의 탭 계약을 바꾸지 않고 이 계기의 표시 수명만 관측한다.
const cpPanel=document.getElementById('p-manual'), cpApp=document.getElementById('app');
if(cpPanel && cpApp){
  const cpObserver=new MutationObserver(cpEnter);
  cpObserver.observe(cpPanel,{attributes:true,attributeFilter:['class']});
  cpObserver.observe(cpApp,{attributes:true,attributeFilter:['class']});
  document.addEventListener('visibilitychange',cpEnter);
  window.addEventListener('pagehide',()=>clearTimeout(cpTimer));
}
async function cpCheckHealth(){
  const button=document.getElementById('cpCheck'), message=document.getElementById('cpCheckMessage');
  if(button.disabled) return;
  button.disabled=true; message.textContent='점검 중… 약 5분 걸릴 수 있습니다 (AI 0).';
  try{ await cpRequest('/world-pulse/ibl-health-check',{method:'POST'}); message.textContent='점검 완료'; await cpLoad('status'); }
  catch(e){ message.textContent='점검 실패: '+e.message; }
  finally{ button.disabled=false; }
}
