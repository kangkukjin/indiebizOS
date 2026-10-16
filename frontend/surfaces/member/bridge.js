
let seq=0;const pending=new Map();
function memberBoot(){parent.postMessage({memberFrame:'ready'},'*')}
window.addEventListener('message',e=>{if(e.source!==parent)return;const m=e.data||{};if(m.memberFrame==='apps'){INSTRUMENTS=m.instruments||[];renderAppHome()}if(m.memberFrame==='result'){const p=pending.get(m.id);if(p){pending.delete(m.id);m.error?p.reject(Error(m.error)):p.resolve(memberAppResult(m.result))}}});
function memberAppResult(value){let v=unwrapFinalResult(value);if(typeof v==='string')v={text:v};if(v?.message&&!v.text)v={...v,text:v.message};if(v?.blocks)v={...v,items:v.blocks};else if(v?.text&&!v.items)v={...v,items:[{type:'paragraph',text:v.text}]};return v}
function ibl(code){return new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});parent.postMessage({memberFrame:'execute',id,code},'*')})}
// 자연어 제작 버튼도 시스템 AI 위임 없이 같은 회원 작업으로 보낸다.
function memberAppRequest(spec){
 const args=gatherInputs();
 return new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});parent.postMessage({memberFrame:'request',id,action_id:spec.client_action_id,args,title:spec.name||CUR.inst.name},'*')});
}
const memberIblRunMode=runMode,memberIblFireButton=fireButton;
runMode=async function(){
 if(!CUR.mode.client_action_id)return memberIblRunMode();
 const mode=CUR.mode,box=document.getElementById('instOut');box.textContent='요청을 처리하고 있습니다…';
 try{const r=await memberAppRequest(mode);if(CUR.mode!==mode||!box.isConnected)return;box.innerHTML=mode.request?mdChat(r.input_required||r.response||r.error||'작업이 끝났습니다'):(VIEW_CTX={view:mode.view,data:r,compose:mode.compose,refresh:'mode'},renderModeBody(mode,r))}catch(e){box.textContent=e.message}
};
fireButton=async function(i,button){
 const spec=(CUR.mode.buttons||[])[i];if(!spec?.client_action_id)return memberIblFireButton(i,button);
 const mode=CUR.mode;button.disabled=true;const box=document.getElementById('instOut');box.textContent='클라이언트 담당 에이전트가 처리 중입니다…';
 try{const r=await memberAppRequest(spec);if(CUR.mode!==mode||!box.isConnected)return;if(spec.refresh)await runMode();else box.innerHTML=(mode.view||[]).some(v=>v.type==='kv')?renderModeBody(mode,r):mdChat(r.input_required||r.response||r.error||r.message||'요청한 동작을 마쳤습니다')}catch(e){box.textContent=e.message}finally{button.disabled=false}
};
function jfetch(){return Promise.reject(Error('회원 앱에서 이 네트워크 경로는 사용할 수 없습니다'))}
async function loadInstruments(){}
function renderAppHome(){document.getElementById('appInst').style.display='none';const h=document.getElementById('appHome');h.style.display='block';h.innerHTML='<div class="grid">'+INSTRUMENTS.map((i,n)=>'<button class="tile" onclick="openInstrument('+n+')"><span class="em">'+esc(i.icon||'◻')+'</span><span>'+esc(i.name)+'</span></button>').join('')+'</div>'}
function _upFileObj(){alert('앱의 내 파일에서 파일을 가져오고 그 경로를 입력하세요')}
window.addEventListener('popstate',appBackHome);
