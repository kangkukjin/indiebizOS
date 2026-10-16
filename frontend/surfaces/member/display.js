function renderMemberConversation(t,prepend=false){
  const chat=document.getElementById('chat'),scroll=document.getElementById('conversationScroll');
  const previousHeight=scroll.scrollHeight;
  const previousTop=scroll.scrollTop,follow=(!prepend)&&(scroll.scrollHeight-scroll.clientHeight-previousTop<80||!chat.childElementCount);
  chat.replaceChildren();const progress=document.getElementById('taskProgress');progress.replaceChildren();
  const events=t.events||[],messages=events.filter(e=>e.kind==='user'||e.kind==='assistant');
  if(memberVisibleStart===null)memberVisibleStart=getConversation().visibleStart(messages.length,null,false);
  const start=messages[memberVisibleStart],offset=start?events.indexOf(start):0;
  document.getElementById('taskOlder').hidden=memberVisibleStart===0;
  for(const event of events.slice(offset)){
   if(event.kind==='user'||event.kind==='assistant'){
    if(event.kind==='user')progress.replaceChildren();
    if(event.value)memberBubble(event.kind,event.value,false);
   }else if(event.kind==='progress'){
    const p=document.createElement('div');p.textContent=memberProgressText(event.value||{});
    if(p.textContent&&progress.lastChild?.textContent!==p.textContent)progress.append(p);
    while(progress.childElementCount>3)progress.firstChild.remove();
   }
  }
  document.getElementById('chatEmpty').hidden=!!chat.childElementCount;
  if(t.state!=='running')progress.replaceChildren();
  scroll.scrollTop=prepend?previousTop+scroll.scrollHeight-previousHeight:follow?scroll.scrollHeight:previousTop;
}
function renderMemberDictionary(){
 const list=document.getElementById('memberDictionaryList');if(!list)return;
 const query=document.getElementById('memberDictionarySearch').value.trim().toLowerCase();list.replaceChildren();
 const rows=memberWords.filter(w=>getConversation().matchesWord(w.id+' '+(w.description||''),query));
 if(!rows.length){list.textContent=memberDictionaryError|| (query?'찾는 낱말이 없습니다.':'이 회원에게 공개된 낱말이 없습니다.');return}
 for(const word of rows){
  const button=document.createElement('button'),title=document.createElement('strong'),description=document.createElement('small');
  title.textContent='['+word.id+']';description.textContent=word.description||'';button.append(title,description);
  button.onclick=()=>{const field=document.getElementById('message');field.value=getConversation().insertWord(field.value,word.id);memberDrafts.set(currentTask,field.value);document.getElementById('memberDictionary').close();field.focus()};
  list.append(button);
 }
}
function memberProgressText(v){if(v.type==='command_output')return v.tail||'';const e=v.detail||v;const label={accepted:'요청을 받았습니다',result_ready:'결과를 이 기기로 보내고 있습니다',delivered:'이 기기에 저장했습니다',input_required:'추가 답변이 필요합니다',client_action_required:'이 기기에서 처리하고 있습니다',tool_start:'요청에 필요한 자료와 도구를 확인하고 있습니다',tool_result:'처리 결과를 확인하고 있습니다',thinking:'답변을 준비하고 있습니다',error:'작업을 완료하지 못했습니다'};return label[v.type]||label[e.type]||''}
function memberBubble(role,text,follow=true){const d=document.createElement('div');d.className='bubble '+role;d.innerHTML=mdChat(text);document.getElementById('chat').append(d);const empty=document.getElementById('chatEmpty');if(empty)empty.hidden=true;if(follow)d.scrollIntoView({block:'nearest'});}

function renderMemberFiles(value){if(!value)return;const op=value.op,r=value.result;if(op==='list'){const rows=document.getElementById('fileRows');rows.replaceChildren();for(const f of r.files||r.items||[]){const b=document.createElement('button');b.textContent=f.name;b.onclick=()=>{document.getElementById('filePath').value=f.path||f.name;memberFiles((f.dir||f.is_dir||['directory','dir'].includes(f.type))?'list':'read')};rows.append(b)}}document.getElementById('fileStatus').textContent=op==='write'?'이 기기에 저장했습니다':r.path||''}
