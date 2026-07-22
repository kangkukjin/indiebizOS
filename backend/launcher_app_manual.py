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

"""
