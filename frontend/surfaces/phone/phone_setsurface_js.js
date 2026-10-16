/* ===== 표면 토글 (폰: 3탭 — 창고·포식 없음, launcher_surface_phone 조립) ===== */
function setSurface(s){
  surface=s;
  ['autopilot','manual','app'].forEach(k=>{
    const t=document.getElementById('t-'+k); if(t) t.classList.toggle('on',k===s);
    document.getElementById('p-'+k).classList.toggle('on',k===s);
  });
  if(s==='app' && !appHomeRendered) renderAppHome();
  if(typeof _npSync==='function') _npSync();  /* 미니플레이어=앱모드 전용 — 표면이 바뀌면 다시 판단 */
}

