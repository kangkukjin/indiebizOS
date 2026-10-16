async function renderAppHome(force){
  const home=document.getElementById('appHome');
  home.innerHTML='<div class="center"><div class="spin"></div></div>';
  await loadInstruments(force);
  if(!INSTRUMENTS.length){ home.innerHTML='<p class="muted">계기 매니페스트를 불러오지 못했습니다</p>'; return; }
  home.innerHTML=
    '<p class="muted" style="margin-bottom:12px">직접 조작 — 아이콘을 눌러 바로 실행 (0 토큰)</p>'+
    '<div class="grid">'+INSTRUMENTS.map((inst,ix)=>
      '<button class="tile" onclick="openInstrument('+ix+')"><span class="em">'+esc(inst.icon||'🔧')+'</span><span class="nm">'+esc(window.__ui ? window.__ui.instrument(inst).name : inst.name)+'</span></button>'
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
