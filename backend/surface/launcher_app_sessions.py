"""원격 런처의 영속 세션 표면. 데스크톱과 같은 /chat-sessions 저장·실행 API."""

LAUNCHER_SESSIONS_JS = r'''
let apSessionContext=null;
async function apResearchHistory(){
 const d=document.getElementById('apSessionHistory'),box=document.getElementById('apSessionList');
 document.getElementById('apSessionSearch').hidden=true;box.replaceChildren();
 for(const [i,t] of apThreads.entries()){
  const button=document.createElement('button');button.className='ap-session-row';button.textContent=t.title+' · '+(t.updated_label||'');
  button.onclick=()=>{d.close();apPickThread(i)};box.append(button);
 }d.showModal();
}
function apSessionsEnabled(){return ['system','agent'].includes(apChat.type)}
function apOpenSessionHistory(){if(apChat.type==='research'){apResearchHistory();return}const d=document.getElementById('apSessionHistory');d.showModal();document.getElementById('apSessionSearch').focus()}
function apCloseSessionHistory(){document.getElementById('apSessionHistory').close()}
function apStopSessions(){apCloseSessionHistory();if(apSessionContext)clearTimeout(apSessionContext.timer);apSessionContext=null}
function apSessionLive(s,id){return apSessionContext===s&&(id===undefined||s.id===id)}
function apSessionDay(value){const d=new Date(value||'');return isNaN(d)?'':d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0')}
async function apSessionRequest(s,path='',method='GET',body={}){
 const query=new URLSearchParams({...s.target,...(method==='GET'?body:{})});
 const r=await jfetch('/chat-sessions'+path+(method==='GET'?'?'+query:''),{method,...(method==='GET'?{}:{body:JSON.stringify({...s.target,...body})})});
 const d=await r.json();if(!r.ok)throw Error(d.detail||d.error||('HTTP '+r.status));return d;
}
function apSessionError(s,error){if(apSessionLive(s))document.getElementById('apSessionError').textContent=error?error.message:''}
function apSessionControls(s){
 if(!apSessionLive(s))return;
 const item=s.items.find(x=>x.id===s.id),pending=s.pending.has(s.id);
 document.getElementById('apSend').disabled=!s.id||!s.loaded||Boolean(item?.archived)||s.running||pending;
 document.getElementById('apSessionStop').hidden=!s.running;
 document.getElementById('apSessionOlder').hidden=!s.older;
 document.getElementById('apSessionOlder').disabled=s.reading;
 document.getElementById('apSessionNew').disabled=s.creating;
 document.getElementById('apSessionTitle').textContent=item?.title||'새 세션을 시작하세요';
 document.getElementById('apSessionArchived').hidden=!item?.archived;
}
function apRenderSessionList(){
 const s=apSessionContext;if(!s)return;
 const search=document.getElementById('apSessionSearch').value.trim().toLocaleLowerCase();
 const rows=s.items.filter(x=>(x.title+' '+apSessionDay(x.updated_at||x.created_at)).toLocaleLowerCase().includes(search));
 const signature=JSON.stringify([rows,s.id]);if(signature===s.listSignature)return;s.listSignature=signature;
 const box=document.getElementById('apSessionList');box.replaceChildren();let day=null;
 for(const row of rows){
  const next=apSessionDay(row.updated_at||row.created_at);
  if(next!==day){day=next;const heading=document.createElement('h3');heading.textContent=day||'날짜 미상';box.append(heading)}
  const button=document.createElement('button');button.type='button';button.className='ap-session-row';button.setAttribute('aria-current',String(row.id===s.id));
  const title=document.createElement('span');title.textContent=row.title;button.append(title);
  if(row.running||row.archived){const status=document.createElement('small');status.textContent=row.running?'진행 중':'보관됨';button.append(status)}
  button.onclick=()=>apSelectSession(row.id);box.append(button);
 }
 if(!rows.length){const empty=document.createElement('p');empty.textContent='표시할 세션이 없습니다.';box.append(empty)}
 apSessionControls(s);
}
async function apSessionList(s){
 const data=await apSessionRequest(s);if(!apSessionLive(s))return;
 s.items=data.sessions||[];apRenderSessionList();
}
function apRenderSessionMessages(s,prepend=false){
 const box=document.getElementById('apMsgs'),top=box.scrollTop,height=box.scrollHeight;
 const follow=!s.rendered||height-top-box.clientHeight<100;
 const signature=JSON.stringify([s.messages,s.snapshot?.turn,s.snapshot?.events]);if(signature===s.signature)return;s.signature=signature;
 box.replaceChildren();let day=null;
 for(const row of s.messages){
  const next=apSessionDay(row.timestamp);
  if(next!==day){day=next;const sep=document.createElement('div');sep.className='ap-hist-sep';sep.textContent=day||'날짜 미상';box.append(sep)}
  apAddMsg(row.role,row.content,apImgObjs(row.images));
 }
 const turn=s.snapshot?.turn;
 if(s.running)apAddMsg('assistant',turn.stream_content||'작업 중…');
 else if(turn&&['failed','interrupted','cancelled'].includes(turn.state)){
  const notice=document.createElement('p');notice.className='ap-hist-sep';notice.textContent=turn.error||'작업이 중단됐습니다. 기록을 확인하고 이어서 요청하세요.';box.append(notice);
 }
 if(!box.childElementCount){const empty=document.createElement('div');empty.className='empty';empty.textContent='메시지를 입력해 시작하세요.';box.append(empty)}
 box.scrollTop=prepend?top+box.scrollHeight-height:follow?box.scrollHeight:top;s.rendered=true;
}
async function apSessionSnapshot(s,id,before){
 const generation=s.generation;
 const d=await apSessionRequest(s,'/'+encodeURIComponent(id),'GET',before?{before}:{});
 if(!apSessionLive(s,id)||s.generation!==generation)return;
 const rows=new Map(s.messages.map(m=>[m.id,m]));for(const row of d.messages||[])rows.set(row.id,row);
 s.messages=[...rows.values()].sort((a,b)=>Number(a.id)-Number(b.id));
 if(before||!s.loaded)s.older=Boolean(d.has_older);
 if(!before){s.snapshot=d;s.running=d.turn?.state==='running'}
 s.loaded=true;apRenderSessionMessages(s,Boolean(before));apSessionControls(s);
}
async function apSelectSession(id,preserveDraft=false){
 const s=apSessionContext;if(!s)return;
 apCloseSessionHistory();s.generation=(s.generation||0)+1;s.id=id;s.messages=[];s.loaded=false;s.running=false;s.older=false;s.reading=false;s.snapshot=null;s.signature='';s.rendered=false;
 try{localStorage.setItem(s.key,id)}catch(e){}
 if(!preserveDraft){document.getElementById('apInput').value='';apImages=[];apRenderChips();}document.getElementById('apMsgs').replaceChildren();
 apRenderSessionList();apSessionControls(s);apSessionError(s,null);
 try{await apSessionSnapshot(s,id)}catch(e){if(apSessionLive(s,id))apSessionError(s,e)}
}
async function apNewSession(){
 if(apChat.type==='research'){await apThreadCreate();return}
 const s=apSessionContext;if(!s||s.creating)return;s.creating=true;apSessionControls(s);
 const previous=s.id,generation=s.generation;
 try{const row=await apSessionRequest(s,'','POST');if(!apSessionLive(s))return;s.items.unshift(row);apRenderSessionList();if(s.id===previous&&s.generation===generation)await apSelectSession(row.id)}
 catch(e){apSessionError(s,e)}finally{s.creating=false;apSessionControls(s)}
}
async function apSessionOlder(){
 const s=apSessionContext;if(!s||s.reading||!s.messages.length)return;
 const id=s.id;s.reading=true;apSessionControls(s);
 try{await apSessionSnapshot(s,id,s.messages[0].id)}catch(e){if(apSessionLive(s,id))apSessionError(s,e)}
 finally{if(apSessionLive(s,id)){s.reading=false;apSessionControls(s)}}
}
async function apSessionSend(){
 const s=apSessionContext;if(!s||!s.id||!s.loaded||s.running||s.pending.has(s.id)||s.items.find(x=>x.id===s.id)?.archived)return;
 const generation=s.generation,id=s.id,input=document.getElementById('apInput'),text=input.value,photos=apImages.slice();if(!text.trim()&&!photos.length)return;
 s.pending.add(id);apSessionControls(s);apSessionError(s,null);
 try{
  await apSessionRequest(s,'/'+encodeURIComponent(id)+'/messages','POST',{message:text.trim()||'첨부한 사진을 봐줘.',images:photos.map(im=>({base64:im.b64,media_type:im.media_type}))});
  if(!apSessionLive(s,id)||s.generation!==generation)return;
  if(input.value===text)input.value='';apImages=apImages.filter(im=>!photos.includes(im));apRenderChips();
  await apSessionSnapshot(s,id);await apSessionList(s);
 }catch(e){if(apSessionLive(s,id))apSessionError(s,e)}finally{s.pending.delete(id);apSessionControls(s)}
}
async function apSessionCancel(){
 const s=apSessionContext;if(!s||!s.running)return;const id=s.id;
 try{await apSessionRequest(s,'/'+encodeURIComponent(id)+'/cancel','POST');if(apSessionLive(s,id))await apSessionSnapshot(s,id)}catch(e){if(apSessionLive(s,id))apSessionError(s,e)}
}
async function apStartSessions(){
 apStopSessions();
 const target=apChat.type==='agent'?{target:'agent',project_id:apChat.projectId,agent_id:String(apChat.agentId)}:{target:'system_ai'};
 const s={target,key:'remote-conversation:'+JSON.stringify(target),id:'',items:[],messages:[],pending:new Set(),loaded:false,running:false,older:false};apSessionContext=s;
 document.getElementById('apSessionSearch').hidden=false;document.getElementById('apSessionSearch').value='';
 apSessionError(s,null);apSessionControls(s);apRenderSessionList();
 try{await apSessionList(s);if(!apSessionLive(s))return;
  let saved='';try{saved=localStorage.getItem(s.key)||''}catch(e){}
  const row=s.items.find(x=>x.id===saved)||s.items.find(x=>!x.archived);
  if(row&&!s.id&&!s.creating)await apSelectSession(row.id,true);
 }catch(e){apSessionError(s,e)}
 const poll=async()=>{if(!apSessionLive(s))return;
  try{await apSessionList(s);if(s.id)await apSessionSnapshot(s,s.id)}catch(e){apSessionError(s,e)}
  if(apSessionLive(s))s.timer=setTimeout(poll,1500);
 };if(apSessionLive(s))s.timer=setTimeout(poll,1500);
}
'''
