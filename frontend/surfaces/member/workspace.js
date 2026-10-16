
let memberFileHash='',memberFileHashPath='';let memberView='drive';let currentTask='',taskSignature='',taskListSignature='',taskBusy=false,frameReady=false;let memberApps=[];
let taskSelectionReady=false,taskSelectionVersion=0,taskSubmitting=false;
const memberDrafts=new Map();
function setMemberView(view){
 memberView=view;
 for(const b of document.querySelectorAll('#memberNav button')){const active=b.dataset.view===(view==='files'?'apps':view);b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active))}
 document.getElementById('appsPanel').hidden=view!=='apps';
 document.getElementById('filesPanel').hidden=view!=='files';
 document.getElementById('drivePanel').hidden=view!=='drive';
 document.getElementById('taskSessionMenu').hidden=view!=='drive';
 document.getElementById('send').hidden=view!=='drive';
 document.getElementById('taskStateLabel').hidden=view!=='drive';
 if(view==='apps')refreshApps();
}
function selectMemberSession(id=''){
 document.getElementById('taskHistory').close();
 memberDrafts.set(currentTask,document.getElementById('message').value);
 memberVisibleStart=null;memberCurrentSnapshot=null;document.getElementById('taskOlder').hidden=true;
 currentTask=id;taskSelectionReady=true;taskSelectionVersion++;taskSignature='';taskListSignature='';
 if(!id)memberDrafts.delete('');
 document.getElementById('message').value=memberDrafts.get(id)||'';
 for(const name of ['taskQuestion','taskStateLabel','taskProgress','chat'])document.getElementById(name).replaceChildren();
 document.getElementById('chatEmpty').hidden=false;
 document.getElementById('taskTitle').textContent=id?'대화 불러오는 중…':'새 세션';
 document.getElementById('sendButton').disabled=taskSubmitting||!!id;
 if(typeof showMemberArtifacts==='function')showMemberArtifacts();
 setMemberView('drive');refreshTasks();refreshApps();document.getElementById('message').focus();
}
async function @@boot_name@@(){
 getConversation().arrange(document.getElementById('taskSessionMenu'),{older:'taskOlder',history:'taskHistoryOpen',new:'newTask',dictionary:'memberDictionaryOpen'});
 const dictionary=document.getElementById('memberDictionary');
 document.getElementById('memberDictionaryOpen').onclick=()=>{dictionary.showModal();renderMemberDictionary();refreshApps()};
 document.getElementById('memberDictionaryClose').onclick=()=>dictionary.close();
 dictionary.onclick=e=>{if(e.target===dictionary)dictionary.close()};
 document.getElementById('memberDictionarySearch').oninput=()=>renderMemberDictionary();
 document.getElementById('taskOlder').onclick=()=>{if(memberCurrentSnapshot){memberVisibleStart=getConversation().visibleStart(0x7fffffff,memberVisibleStart,true);renderMemberConversation(memberCurrentSnapshot,true)}};

 const history=document.getElementById('taskHistory');
 document.getElementById('taskHistoryOpen').onclick=()=>history.showModal();
 document.getElementById('taskHistoryClose').onclick=()=>history.close();
 history.onclick=e=>{if(e.target===history)history.close()};
 if(window.MemberBridge){document.getElementById('importFile').hidden=true}
 document.getElementById('appFrame').srcdoc=MEMBER_FRAME_HTML;
 document.querySelectorAll('#memberNav button').forEach(b=>b.onclick=()=>setMemberView(b.dataset.view));
 document.getElementById('newTask').onclick=async()=>{const button=document.getElementById('newTask');button.disabled=true;try{const r=await memberRequest('task/start',{create_only:true});if(!r.success)throw Error(r.message||r.error);selectMemberSession(r.task_id)}catch(e){document.getElementById('status').textContent=e.message}finally{button.disabled=false}};
 document.getElementById('setWorkspace').onclick=async()=>{const r=await memberRequest('workspace',{path:document.getElementById('workspacePicker').value});if(!r.success)return alert(r.message||r.error);document.getElementById('workspacePath').textContent=r.workspace;document.getElementById('newTask').click();refreshApps()};
 try{const r=await memberRequest('workspace');document.getElementById('workspacePath').textContent=r.workspace;document.getElementById('workspacePicker').value=r.workspace||'';if(r.fixed){document.getElementById('workspacePicker').disabled=true;document.getElementById('setWorkspace').hidden=true}}catch(e){}
 memberRequest('profile',{}).then(r=>document.getElementById('status').textContent=r.success?'':r.error).catch(()=>document.getElementById('status').textContent='오프라인 · 작업 기록은 이 컴퓨터에 보존됩니다');
 document.getElementById('reloadApps').onclick=refreshApps;document.getElementById('openMemberFiles').onclick=()=>{setMemberView('files');memberFiles('list')};document.getElementById('backToApps').onclick=()=>setMemberView('apps');refreshApps();
 document.getElementById('send').onsubmit=async e=>{
  e.preventDefault();const input=document.getElementById('message'),text=input.value.trim();if(!text||taskSubmitting)return;
  const requestedTask=currentTask,selectionVersion=taskSelectionVersion;taskSubmitting=true;taskSelectionReady=true;document.getElementById('sendButton').disabled=true;
  input.value='';memberDrafts.delete(requestedTask);
  try{const r=await memberRequest('task/start',{task_id:requestedTask,message:text});if(!r.success)throw Error(r.message||r.error);
   if(selectionVersion===taskSelectionVersion){currentTask=r.task_id;taskSignature='';}
   await refreshTasks();
  }catch(e){document.getElementById('status').textContent=e.message;if(selectionVersion===taskSelectionVersion&&!input.value)input.value=text}
  finally{taskSubmitting=false;taskSignature='';await refreshTasks()}
 };
 document.getElementById('cancel').hidden=true;document.getElementById('taskStop').onclick=()=>{memberAppGeneration++;return memberRequest('close',{})};
 document.getElementById('export').onclick=async()=>{const r=await memberRequest('export',{});memberBubble('assistant',r.success?'내보내기 완료: '+r.path:r.error)};
 document.getElementById('browseFiles').onclick=()=>memberFiles('list');document.getElementById('readFile').onclick=()=>memberFiles('read');document.getElementById('saveFile').onclick=()=>memberFiles('write');
 document.getElementById('importFile').onchange=async e=>{const file=e.target.files[0];if(!file)return;const r=await fetch('/member/upload?name='+encodeURIComponent(file.name)+'&task_id='+encodeURIComponent(currentTask),{method:'POST',headers:{'X-Member-Token':memberToken},body:file});const d=await r.json();document.getElementById('fileStatus').textContent=d.path||d.error;};
 setInterval(memberApprovals,1000);if(!window.MemberBridge)setInterval(memberMedia,500);setInterval(refreshTasks,1000);setInterval(refreshMemberResults,5000);refreshMemberResults();refreshTasks();
 if(window.memberDesktopBoot)await window.memberDesktopBoot();
}
async function refreshApps(){try{const r=await memberRequest('apps',{task_id:currentTask});memberApps=r.instruments||[];memberWords=r.dictionary||(r.open_words||[]).map(id=>({id}));memberDictionaryError=r.error||'';renderMemberDictionary();document.getElementById('appStatus').textContent=r.local_error||r.error||(!memberApps.length?'현재 이 기기에서 사용할 수 있는 앱이 없습니다.':'');if(frameReady)sendApps()}catch(e){memberDictionaryError=e.message;renderMemberDictionary();document.getElementById('appStatus').textContent=e.message}}
function sendApps(){document.getElementById('appFrame').contentWindow.postMessage({memberFrame:'apps',instruments:memberApps},'*')}
let memberAppGeneration=0;let memberAppQueue=Promise.resolve();
window.addEventListener('message',e=>{
 const frame=document.getElementById('appFrame');if(!frame||e.source!==frame.contentWindow)return;
 const m=e.data||{};if(m.memberFrame==='ready'){frameReady=true;sendApps();return}
 if(m.memberFrame==='import'){
  (async()=>{try{if(typeof memberBrowser==='undefined'||!memberBrowser)throw Error('내 파일에서 가져오세요');const result=await memberBrowser.files.import(m.file);frame.contentWindow.postMessage({memberFrame:'result',id:m.id,result},'*')}catch(error){frame.contentWindow.postMessage({memberFrame:'result',id:m.id,error:error.message},'*')}})();return;
 }
 if(!['execute','request'].includes(m.memberFrame))return;
 const writing=m.memberFrame==='request';
 if(writing?(typeof m.action_id!=='string'||!m.args||typeof m.args!=='object'):(typeof m.code!=='string'||m.code.length>64000))return;
 if(!writing&&typeof memberBrowser!=='undefined'&&memberBrowser){frame.contentWindow.postMessage({memberFrame:'result',id:m.id,error:'앱을 새로고침한 뒤 다시 실행하세요'},'*');return}
 const generation=memberAppGeneration,requestedTask=currentTask,requestedSelection=taskSelectionVersion;
 memberAppQueue=memberAppQueue.then(async()=>{try{
  if(generation!==memberAppGeneration)throw Error('작업을 중단했습니다');
  const app=m.app_id||m.action_id?.split(':')[0];
  const r=await memberRequest('task/start',writing?{task_id:requestedTask,message:'',action_id:m.action_id,args:m.args,title:m.title,app_id:app}:{task_id:requestedTask,message:'앱 실행',code:m.code});
  if(!r.success)throw Error(r.message||r.error);
  if(currentTask===requestedTask&&taskSelectionVersion===requestedSelection){currentTask=r.task_id;taskSelectionReady=true;}taskSignature='';await refreshTasks();
  const result=await waitMemberTask(r.task_id);
  frame.contentWindow.postMessage({memberFrame:'result',id:m.id,result:result.app_result||result,error:result.success===false?result.error:null},'*');
  if(typeof showMemberArtifacts==='function')showMemberArtifacts(result);await refreshTasks();
 }catch(error){frame.contentWindow.postMessage({memberFrame:'result',id:m.id,error:error.message},'*')}});
});
async function waitMemberTask(id){for(;;){const t=await memberRequest('task?id='+encodeURIComponent(id));if(t.state!=='running')return t.result||{success:false,error:t.state};await new Promise(r=>setTimeout(r,600))}}
const memberTaskStates={idle:'새 세션',running:'진행 중',input_required:'답변 대기',completed:'완료',failed:'확인 필요',unknown:'결과 확인 필요',cancelled:'중단됨'};
async function refreshTasks(){
 if(taskBusy)return;taskBusy=true;
 try{
  const tasks=(await memberRequest('tasks'))||[];
  const running=(tasks||[]).some(t=>t.state==='running');
  document.getElementById('taskStop').hidden=!running;
  if(!taskSelectionReady){taskSelectionReady=true;currentTask=(tasks.find(t=>t.state==='running')||tasks[0])?.id||''}
  const list=document.getElementById('taskList'),listSignature=JSON.stringify([tasks,currentTask]);
  if(listSignature!==taskListSignature){
   taskListSignature=listSignature;list.replaceChildren();
   if(!tasks.length){const p=document.createElement('p');p.className='sessionEmpty';p.textContent='첫 대화를 시작하면 세션이 여기에 남습니다.';list.append(p)}
   let previousDay='';
   for(const t of tasks){
    const stamp=t.updated||t.created;const date=new Date(typeof stamp==='number'&&stamp<1e12?stamp*1000:stamp);
    const day=isNaN(date)?'날짜 미상':date.toLocaleDateString();
    if(day!==previousDay){previousDay=day;const heading=document.createElement('h3');heading.textContent=day;list.append(heading)}
    const b=document.createElement('button');b.className=t.id===currentTask?'active':'';b.setAttribute('aria-current',String(t.id===currentTask));
    const title=document.createElement('span');title.className='sessionTitle';title.textContent=t.title||'이름 없는 세션';b.title=title.textContent;
    const state=document.createElement('span');state.className='sessionState';state.textContent=memberTaskStates[t.state]||t.state;
    b.append(title,state);b.onclick=()=>selectMemberSession(t.id);list.append(b);
   }
  }
  document.getElementById('sendButton').disabled=taskSubmitting||running;
  if(!currentTask)return;
  const id=currentTask,version=taskSelectionVersion;
  const t=await memberRequest('task?id='+encodeURIComponent(id));
  if(id!==currentTask||version!==taskSelectionVersion)return;
  if(t.success===false)throw Error(t.message||t.error||'대화를 불러오지 못했습니다');
  const signature=JSON.stringify(t);if(signature===taskSignature)return;taskSignature=signature;
  document.getElementById('taskTitle').textContent=t.title;
  if(typeof showMemberArtifacts==='function')showMemberArtifacts(t.result);
  document.getElementById('workspacePath').textContent=t.workspace;
  document.getElementById('taskStateLabel').textContent=({running:window.DesktopMember?'처리 중 · 창을 닫아도 앱은 계속 실행됩니다':'처리 중 · 이 화면을 열어 두세요',input_required:'답변을 기다리고 있습니다',completed:'',failed:'작업을 완료하지 못했습니다',cancelled:'중단됨 · 이미 저장한 파일은 유지됩니다',unknown:'최종 결과를 확인하지 못했습니다 · 저장된 결과를 확인하세요'}[t.state]||'');
  document.getElementById('taskQuestion').textContent=t.state==='input_required'?(t.result?.input_required||'추가 내용을 알려주세요'):'';
  memberCurrentSnapshot=t;renderMemberConversation(t);
 }catch(e){document.getElementById('status').textContent='대화 목록 확인 실패 · '+e.message}
 finally{taskBusy=false}
}

let memberFileDisplay=null;
let memberVisibleStart=null,memberCurrentSnapshot=null,memberWords=[],memberDictionaryError='';




async function memberFiles(op){const release=window.IndieDisplay?.hold();try{const r=await memberRequest('file',{op,path:document.getElementById('filePath').value,task_id:currentTask,content:document.getElementById('fileEditor').value,expected_hash:memberFileHashPath===document.getElementById('filePath').value?memberFileHash:'missing'});if(r.error)throw Error(r.message||r.error);if(op==='read'||op==='write'){memberFileHash=r.sha256||'';memberFileHashPath=document.getElementById('filePath').value}if(op==='read')document.getElementById('fileEditor').value=r.content||'';memberFileDisplay={op,result:r};renderMemberFiles(memberFileDisplay)}catch(e){document.getElementById('fileStatus').textContent=e.message}finally{if(release)release()}}
