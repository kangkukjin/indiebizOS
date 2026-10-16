
let apSessionContext=null;
async function apResearchHistory(){
 const d=document.getElementById('apSessionHistory'),box=document.getElementById('apSessionList');
 box.replaceChildren();
 for(const [i,t] of apThreads.entries()){
  const button=document.createElement('button');button.className='ap-session-row';button.textContent=t.title+' · '+(t.updated_label||'');
  button.onclick=()=>{d.close();apPickThread(i)};box.append(button);
 }d.showModal();
}
function apSessionsEnabled(){return ['system','agent'].includes(apChat.type)}
function apOpenSessionHistory(){if(apChat.type==='research'){apResearchHistory();return}const d=document.getElementById('apSessionHistory');d.showModal()}
function apCloseSessionHistory(){document.getElementById('apSessionHistory').close()}
function apStopSessions(){apCloseSessionHistory();if(apSessionContext)clearTimeout(apSessionContext.timer);apSessionContext=null}
function apSessionLive(s,id){return apSessionContext===s&&(id===undefined||s.id===id)}

async function apSessionRequest(s,path='',method='GET',body={}){
 const query=new URLSearchParams({...s.target,...(method==='GET'?body:{})});
 const r=await jfetch('/chat-sessions'+path+(method==='GET'?'?'+query:''),{method,...(method==='GET'?{}:{body:JSON.stringify({...s.target,...body})})});
 const d=await r.json();if(!r.ok)throw Error(d.detail||d.error||('HTTP '+r.status));return d;
}
function apSessionError(s,error){if(apSessionLive(s))document.getElementById('apSessionError').textContent=error?error.message:''}


async function apSessionList(s){
 const data=await apSessionRequest(s);if(!apSessionLive(s))return;
 s.items=data.sessions||[];apRenderSessionList();
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
 const s=apSessionContext;if(!s||!s.id||!s.loaded||s.running||s.pending.has(s.id))return;
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
 getConversation().arrange(document.getElementById('apSessions'),{older:'apSessionOlder',history:'apHistory',new:'apSessionNew',dictionary:'apDictionary'});
 apStopSessions();
 const target=apChat.type==='agent'?{target:'agent',project_id:apChat.projectId,agent_id:String(apChat.agentId)}:{target:'system_ai'};
 const s={target,key:'remote-conversation:'+JSON.stringify(target),id:'',items:[],messages:[],pending:new Set(),loaded:false,running:false,older:false};apSessionContext=s;
 apSessionError(s,null);apSessionControls(s);apRenderSessionList();
 try{await apSessionList(s);if(!apSessionLive(s))return;
  let saved='';try{saved=localStorage.getItem(s.key)||''}catch(e){}
  const row=s.items.find(x=>x.id===saved)||s.items[0];
  if(row&&!s.id&&!s.creating)await apSelectSession(row.id,true);
 }catch(e){apSessionError(s,e)}
 const poll=async()=>{if(!apSessionLive(s))return;
  try{await apSessionList(s);if(s.id)await apSessionSnapshot(s,s.id)}catch(e){apSessionError(s,e)}
  if(apSessionLive(s))s.timer=setTimeout(poll,1500);
 };if(apSessionLive(s))s.timer=setTimeout(poll,1500);
}
