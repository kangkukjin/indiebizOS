"""원격 런처 웹앱 JS — 조종실(수동) 표면 탭(m*: 번역→dry-run 검수→실행→증류 + IBL 사전).

2026-07-22 표면 분리 1단계(launcher_web_app.py 에서 verbatim 분해)."""

LAUNCHER_MANUAL_JS = """/* ================= 수동 ================= */
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

/* ================= 주행기록계 =================
   PC 조종실(EpisodeJournal.tsx)과 같은 화면을 이 표면에도 둔다 — 지난 주행 목록,
   행을 누르면 그 주행의 실행기억(전체 로그), 분석 스위치.
   API 도 데스크탑과 같은 것을 쓴다: /world-pulse/episodes · /xray/episodes/{id} ·
   /world-pulse/episodes/{id}/analysis-prompt. 이 셋은 is_public_remote_path 목록에
   없으므로 외부(터널)에서는 런처 세션 쿠키가 있어야 통과한다 — 주행기록이 무인가
   접근에 열리지 않는다는 뜻이고, 새 인증 경계를 만들지 않았다는 뜻이기도 하다.
   데스크탑은 Electron 창을 열어 분석하지만 여기엔 창이 없으므로, 같은 프롬프트를
   자율주행 탭의 시스템 AI 입력칸에 실어 준다(보내기는 사용자가 누른다). */
let jOpen=false, jRows=null, jExpanded=null, jLogs={};
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
  if(ep.agent) m.push(String(ep.agent));
  if(ep.hippocampus_score!=null) m.push('확신 '+Math.round(ep.hippocampus_score*100)+'%');
  if(ep.execution_rounds!=null&&ep.execution_rounds>1) m.push(ep.execution_rounds+'라운드');
  if(ep.total_ms!=null) m.push((ep.total_ms/1000).toFixed(1)+'초');
  const d=ep.unconscious_decision;
  if(d) m.push(d==='THINK'?'숙고':(d==='EXECUTE'?'실행':String(d)));
  const r=ep.evaluation_result;
  if(r) m.push(r==='ACHIEVED'?'달성':'미달');
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
    h+='<div style="font-size:11px;color:var(--dim);margin-top:4px">'+esc(jMeta(ep))+'</div>';
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
async function jLoad(){
  jRows=null; jRender();
  try{
    const r=await jfetch('/world-pulse/episodes?limit=20');
    if(!r.ok) throw new Error('HTTP '+r.status);
    const d=await r.json();
    jRows=d.episodes||[];
  }catch(e){
    jRows=[];
    const b=document.getElementById('jBody');
    if(b) b.innerHTML='<p class="muted">주행기록을 불러오지 못했습니다 — '+esc(e.message)+'</p>';
    return;
  }
  jRender();
}
function jToggle(){
  jOpen=!jOpen;
  const b=document.getElementById('jBody'); if(b) b.style.display=jOpen?'block':'none';
  const rb=document.getElementById('jReloadBtn'); if(rb) rb.style.display=jOpen?'block':'none';
  if(jOpen&&jRows===null) jLoad();
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
    setTimeout(function(){
      const inp=document.getElementById('apInput');
      if(inp){ inp.value=d.prompt||''; inp.focus(); }
    },80);
  }catch(e){ alert('분석 준비 실패: '+e.message); }
}

"""
