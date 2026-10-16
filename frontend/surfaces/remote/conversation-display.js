function apSessionDay(value){return getConversation().day(value)}
function apSessionControls(s){
 if(!apSessionLive(s))return;
 const item=s.items.find(x=>x.id===s.id),pending=s.pending.has(s.id);
 document.getElementById('apSend').disabled=!s.id||!s.loaded||s.running||pending;
 document.getElementById('apSessionStop').hidden=!s.running;
 document.getElementById('apSessionOlder').hidden=!s.older;
 document.getElementById('apSessionOlder').disabled=s.reading;
 document.getElementById('apSessionNew').disabled=s.creating;
 const title=item?.title||'새 세션을 시작하세요';
 document.getElementById('apSessionTitle').textContent=title;document.getElementById('apSessionTitle').title=title;
 document.getElementById('apSessionBar').hidden=!s.running;
}
function apRenderSessionList(){
 const s=apSessionContext;if(!s)return;
 const rows=s.items;
 const signature=JSON.stringify([rows,s.id]);if(signature===s.listSignature)return;s.listSignature=signature;
 const box=document.getElementById('apSessionList');box.replaceChildren();let day=null;
 for(const row of rows){
  const next=apSessionDay(row.updated_at||row.created_at);
  if(next!==day){day=next;const heading=document.createElement('h3');heading.textContent=day||'날짜 미상';box.append(heading)}
  const button=document.createElement('button');button.type='button';button.className='ap-session-row';button.setAttribute('aria-current',String(row.id===s.id));
  const title=document.createElement('span');title.textContent=row.title;button.append(title);
  if(row.running){const status=document.createElement('small');status.textContent='진행 중';button.append(status)}
  button.onclick=()=>apSelectSession(row.id);box.append(button);
 }
 if(!rows.length){const empty=document.createElement('p');empty.textContent='표시할 세션이 없습니다.';box.append(empty)}
 apSessionControls(s);
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
function apCard(ic,nm,ds,onclick,chev){
  return '<div class="ap-card" onclick="'+onclick+'"><span class="ic">'+ic+'</span>'+
    '<span class="tx"><span class="nm">'+esc(nm)+'</span>'+(ds?'<span class="ds">'+esc(ds)+'</span>':'')+'</span>'+
    (chev?'<span class="chev">›</span>':'')+'</div>';
}
function apRenderChips(){
  const box=document.getElementById('apChips'); if(!box) return;
  if(!apImages.length){ box.style.display='none'; box.innerHTML=''; return; }
  box.style.display='flex';
  box.innerHTML=apImages.map((im,i)=>
    '<div class="ap-chip"><img src="'+im.dataUrl+'"><button onclick="apRemoveChip('+i+')">✕</button></div>'
  ).join('');
}
function apImgObjs(paths){
  return (paths||[]).map(p=>{
    const endpoint=apChat.type==='agent'
      ? '/conversations/'+encodeURIComponent(apChat.projectId)+'/image'
      : '/system-ai/image';
    const u=endpoint+'?path='+encodeURIComponent(p);
    return {src:u, dl:u+'&dl=1'};
  });
}
function apAddMsg(role,text,imgs){
  const c=document.getElementById('apMsgs');
  const ph=c.querySelector('.empty'); if(ph) ph.remove();
  const el=document.createElement('div'); el.className='msg '+role;
  el.innerHTML='<div class="av">'+(role==='user'?'🧑':'🤖')+'</div><div class="bub">'+(role==='user'?esc(text):mdChat(text))+'</div>';
  apAppendImgs(el.querySelector('.bub'),imgs);
  c.appendChild(el); c.scrollTop=c.scrollHeight;
}
