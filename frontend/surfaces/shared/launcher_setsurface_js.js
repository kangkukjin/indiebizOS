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
  if(typeof _npSync==='function') _npSync();  /* 미니플레이어=앱모드 전용 — 표면이 바뀌면 다시 판단 */
}
