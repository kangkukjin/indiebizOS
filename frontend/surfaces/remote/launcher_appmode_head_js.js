/* ================= 앱 (제네릭 렌더러 — /launcher/instruments 매니페스트 해석) ================= */
let appHomeRendered=false;
let INSTRUMENTS=[];
let CUR={inst:null, mode:null, optCache:{}};
let VIEW_CTX=null; /* 마지막 렌더의 {view,data} — 행 버튼/드릴 디스패치용 */
let SPLIT=false, LIST=null; /* master-detail: SPLIT=2분할 모드, LIST={view,data}=리스트 컨텍스트 */
const CUSTOM_RENDERERS={}; /* escape hatch: manifest renderer:"custom:이름" → 전용 렌더 함수 (지도·플레이어 등) */

document.addEventListener('DOMContentLoaded',()=>{
  if(!window.__ui) return;
  window.__ui.subscribe(()=>{
    const home=document.getElementById('appHome'), box=document.getElementById('appInst');
    if(appHomeRendered && home && home.style.display!=='none') renderAppHome();
    if(!box || box.style.display==='none' || !CUR.inst) return;
    const ix=INSTRUMENTS.findIndex(i=>i.id===CUR.inst.id); if(ix<0) return;
    const previous=CUR, context=VIEW_CTX, list=LIST;
    const modeIndex=Math.max(0,(previous.inst.modes||[previous.inst]).indexOf(previous.mode));
    const controls=[...box.querySelectorAll('input,textarea,select')].map(el=>({el,id:el.id,value:el.value,checked:el.checked}));
    const out=document.getElementById('instOut');
    openInstrument(ix,true); if(modeIndex) setMode(modeIndex,true);
    CUR.optCache=previous.optCache; CUR.filterVal=previous.filterVal; CUR.catFilter=previous.catFilter;
    if(context && context.refresh==='mode'){
      VIEW_CTX={...context,view:CUR.mode.view,compose:CUR.mode.compose};
      document.getElementById('instOut').innerHTML=renderModeBody(CUR.mode,context.data);
    }else if(out && document.getElementById('instOut')){
      document.getElementById('instOut').replaceWith(out); VIEW_CTX=context; LIST=list;
    }
    for(const saved of controls){
      const el=saved.id && document.getElementById(saved.id); if(!el) continue;
      if(saved.el.type==='file'){el.replaceWith(saved.el);continue;}
      if(el.tagName==='SELECT' && el.options.length<=1) el.innerHTML=saved.el.innerHTML;
      el.value=saved.value; if('checked' in el) el.checked=saved.checked;
    }
  });
});
let _revalidating=false;
async function loadInstruments(force){
  if(INSTRUMENTS.length && !force){ _revalidateInstruments(); return; }  /* 캐시로 즉시 그림 — 재확인은 배경에서(아래) */
  try{ const r=await jfetch('/launcher/instruments'); if(r.ok){ const d=await r.json(); INSTRUMENTS=d.instruments||[]; } }catch(e){}
}

/* 매니페스트 배경 재확인 — 계기가 은퇴하면(어휘 app: 블록·instruments yaml 삭제) 서버 목록은
   즉시 바뀌는데, 세션이 오래 사는 폰 WebView·원격 탭은 첫 fetch 목록을 영원히 들고 있어
   죽은 아이콘을 계속 광고했다(2026-09-05). 목록이 달라졌고 홈을 보고 있을 때만 조용히 다시 그린다. */
async function _revalidateInstruments(){
  if(_revalidating) return;
  _revalidating=true;
  try{
    const r=await jfetch('/launcher/instruments'); if(!r.ok) return;
    const fresh=((await r.json()).instruments)||[];
    /* 내용 전체를 비교한다 — id·이름만 보면 버튼 action 이 바뀐 개정(2026-10-05 판본 2 이행)을 놓쳐
       오래 열린 탭이 옛 code 를 계속 보냈다. */
    const key=l=>JSON.stringify(l);
    if(!fresh.length || key(fresh)===key(INSTRUMENTS)) return;
    INSTRUMENTS=fresh;
    const home=document.getElementById('appHome');
    if(appHomeRendered && home && home.style.display!=='none') await renderAppHome();
  }catch(e){}
  finally{ _revalidating=false; }
}
