"""회원 작업 공간: 로컬 작업 목록·자율주행·공통 앱 프레임·파일 편집."""
import json
from member_app_frame import frame_html

WORKSPACE_STYLE = r'''
[hidden]{display:none!important}
main{max-width:1500px;height:100dvh;display:flex;flex-direction:column;padding:22px 28px}
header{gap:16px;flex-shrink:0}header h1{margin:0;font-size:22px}#notice{margin:12px 0 6px}
#workspaceLayout{display:flex;flex-direction:column;margin-top:20px;flex:1;min-height:0}
#workArea{display:flex;flex-direction:column;flex:1;min-width:0;min-height:0}
#taskSessionMenu{display:flex;gap:8px;justify-content:flex-end;margin-bottom:12px;flex-shrink:0}
#taskHistory{margin:auto;padding:20px;width:560px;max-width:92vw;max-height:85dvh;border:1px solid #d4ded7;border-radius:16px;background:#f7f8f2;color:#284f3e}
#taskHistory::backdrop{background:rgba(0,0,0,.35)}#taskHistoryHead{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
#taskList{max-height:60dvh;overflow:auto}#taskList button{display:block;background:transparent;color:#355548;text-align:left;width:100%;margin:4px 0;padding:12px}
#taskList button:hover{background:#edf0e9}#taskList button.active{background:#e2eee7}
.sessionTitle{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600}
.sessionState{display:block;font-size:12px;color:#62716d;margin-top:5px}.sessionEmpty{color:#62716d;font-size:14px;line-height:1.7;padding:10px}
#workspaceSettings{padding-top:14px;border-top:1px solid #d4ded7;margin-top:16px}#workspacePath{display:block;overflow-wrap:anywhere;margin:14px 0;font-size:12px}
#workspacePicker{width:100%;padding:10px;box-sizing:border-box}#setWorkspace{margin-top:8px}
#memberNav{display:flex;gap:8px;margin:0 0 16px;flex-shrink:0}#memberNav button{background:#e2e8e2;color:#284f3e}#memberNav button.active{background:#245644;color:white}
#drivePanel{display:flex;flex-direction:column;min-height:0;flex:1}#taskTitle{font-size:22px;margin:4px 0 8px}
#conversationScroll{overflow:auto;flex:1;min-height:180px;overscroll-behavior:contain;padding:0 12px 12px 0}
#chat{min-height:0;margin:20px 0}.bubble{line-height:1.75;font-size:15px}.bubble::before{display:block;font-size:12px;color:#62716d;font-weight:600;margin-bottom:8px}
.bubble.user::before{content:'나'}.bubble.assistant::before{content:'IndieBiz'}
#chatEmpty{display:flex;min-height:260px;height:100%;align-items:center;justify-content:center;flex-direction:column;text-align:center;color:#62716d;padding:30px}
#chatEmpty h3{color:#284f3e;font-size:24px;margin:0 0 14px}#chatEmpty p{max-width:440px;line-height:1.8;margin:4px 0}
#send{position:static;margin:0;padding:14px 0 8px;align-items:flex-end;flex-shrink:0}#message{min-width:0;resize:vertical;max-height:180px}#sessionHint{font-size:12px;color:#62716d;margin:0 0 8px}
#taskControls{display:flex;gap:12px;align-items:center;justify-content:space-between;min-height:26px;margin-bottom:10px}#taskStateLabel{font-size:13px;color:#5b7266}
#taskStop{padding:8px 12px}#taskQuestion{padding:16px;background:#fff5dc;border-radius:12px;white-space:pre-wrap}
#taskProgress{color:#5b7266;font-size:13px;max-height:180px;overflow:auto}#taskQuestion:empty,#taskProgress:empty{display:none}
#appsPanel,#filesPanel{flex:1;min-height:0;overflow:auto}#appsPanel h2{margin:4px 0 16px;font-size:22px}#appFrame{width:100%;height:calc(100% - 125px);min-height:360px;border:0}
#fileEditor{width:100%;min-height:300px;font:14px ui-monospace,monospace}#fileRows button{margin:5px;background:#e7eee8;color:#264b37}#filePath{width:70%;padding:12px;border:1px solid #b9c9c0;border-radius:8px}.fileActions{display:flex;gap:10px;margin:12px 0}
#approvals{max-height:35vh;overflow:auto;flex-shrink:0}
@media(max-width:700px){main{height:auto;min-height:100dvh;padding:16px}#workspaceLayout{margin-top:12px}#workspaceSettings{margin-top:8px;padding-top:8px}#conversationScroll{max-height:60vh}#chatEmpty{min-height:200px}header h1{font-size:18px}#send{position:sticky;bottom:0}#appFrame{height:70vh}.user{margin-left:20px}.assistant{margin-right:0}}
'''
SIDEBAR = '''<div id="workspaceLayout"><div id="workArea"><div id="taskSessionMenu" aria-label="대화 세션 메뉴"><button id="taskHistoryOpen" class="secondary">히스토리</button><button id="newTask">＋ 새 세션</button></div><dialog id="taskHistory" aria-label="대화 히스토리"><div id="taskHistoryHead"><strong>대화 히스토리</strong><button id="taskHistoryClose" class="secondary">닫기</button></div><div id="taskList"></div></dialog><nav id="memberNav" aria-label="작업 표면"><button data-view="drive" class="active" aria-pressed="true">자율주행</button><button data-view="apps" aria-pressed="false">앱</button></nav><div id="taskControls"><span id="taskStateLabel" role="status"></span><button type="button" class="secondary" id="taskStop" hidden>작업 중단</button></div><section id="drivePanel"><h2 id="taskTitle">새 세션</h2><div id="conversationScroll"><div id="chatEmpty"><h3>어떤 일을 함께 할까요?</h3><p>메시지를 보내면 이곳에 나의 요청과 AI의 답변이 차례로 표시됩니다.</p><p>위의 히스토리에서 이전 대화를 열거나 새 세션을 시작할 수 있습니다.</p></div><div id="taskQuestion" aria-live="polite"></div><div id="taskProgress" aria-live="polite"></div>'''
PANELS = '''</section><section id="appsPanel" hidden><h2>내 앱</h2><details id="workspaceSettings"><summary>내 작업 폴더</summary><small id="workspacePath"></small><input id="workspacePicker" aria-label="작업 폴더" placeholder="이 컴퓨터의 폴더 경로"><button id="setWorkspace" class="secondary">폴더 선택</button></details><button id="reloadApps" class="secondary">앱 새로고침</button><button id="openMemberFiles" class="secondary">내 파일 · 가져오기 · 내려받기</button><p id="appStatus"></p><iframe id="appFrame" title="내 기기에서 쓰는 앱" sandbox="allow-scripts"></iframe></section><section id="filesPanel" hidden><button id="backToApps" class="secondary">앱으로 돌아가기</button><input id="filePath" value="." aria-label="파일 경로"><div class="fileActions"><button id="browseFiles">폴더 열기</button><button id="readFile">파일 읽기</button><button id="saveFile">저장</button><input id="importFile" type="file" aria-label="파일 가져오기"></div><div id="fileRows"></div><textarea id="fileEditor" aria-label="파일 내용" placeholder="파일을 열거나 새 내용을 쓰세요"></textarea><p id="fileStatus"></p></section></div></div>'''


def workspace_js():
    return 'const MEMBER_FRAME_HTML=' + json.dumps(frame_html(), ensure_ascii=False).replace('</','<\\/') + ';\n' + r'''
let memberFileHash='',memberFileHashPath='';let memberView='drive';let currentTask='',taskSignature='',taskListSignature='',taskBusy=false,frameReady=false;let memberApps=[];
let taskSelectionReady=false,taskSelectionVersion=0,taskSubmitting=false;
const memberDrafts=new Map();
function setMemberView(view){
 memberView=view;
 for(const b of document.querySelectorAll('#memberNav button')){const active=b.dataset.view===(view==='files'?'apps':view);b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active))}
 document.getElementById('appsPanel').hidden=view!=='apps';
 document.getElementById('filesPanel').hidden=view!=='files';
 document.getElementById('drivePanel').hidden=view!=='drive';
 document.getElementById('taskStateLabel').hidden=view!=='drive';
 if(view==='apps')refreshApps();
}
function selectMemberSession(id=''){
 document.getElementById('taskHistory').close();
 memberDrafts.set(currentTask,document.getElementById('message').value);
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
async function memberBoot(){
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
 memberRequest('profile',{}).then(r=>document.getElementById('status').textContent=r.success?'연결됨 · 요청을 처리하고 결과를 이 기기로 받습니다':r.error).catch(()=>document.getElementById('status').textContent='오프라인 · 작업 기록은 이 컴퓨터에 보존됩니다');
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
async function refreshApps(){try{const r=await memberRequest('apps',{task_id:currentTask});memberApps=r.instruments||[];document.getElementById('appStatus').textContent=r.local_error||r.error||(!memberApps.length?'현재 이 기기에서 사용할 수 있는 앱이 없습니다.':'');if(frameReady)sendApps()}catch(e){document.getElementById('appStatus').textContent=e.message}}
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
  document.getElementById('taskStateLabel').textContent=({running:window.DesktopMember?'처리 중 · 창을 닫아도 앱은 계속 실행됩니다':'처리 중 · 이 화면을 열어 두세요',input_required:'답변을 기다리고 있습니다',completed:'완료',failed:'작업을 완료하지 못했습니다',cancelled:'중단됨 · 이미 저장한 파일은 유지됩니다',unknown:'최종 결과를 확인하지 못했습니다 · 저장된 결과를 확인하세요'}[t.state]||'');
  document.getElementById('taskQuestion').textContent=t.state==='input_required'?(t.result?.input_required||'추가 내용을 알려주세요'):'';
  const chat=document.getElementById('chat'),scroll=document.getElementById('conversationScroll');
  const previousTop=scroll.scrollTop,follow=scroll.scrollHeight-scroll.clientHeight-previousTop<80||!chat.childElementCount;
  chat.replaceChildren();const progress=document.getElementById('taskProgress');progress.replaceChildren();
  for(const event of t.events||[]){
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
  scroll.scrollTop=follow?scroll.scrollHeight:previousTop;
 }catch(e){document.getElementById('status').textContent='대화 목록 확인 실패 · '+e.message}
 finally{taskBusy=false}
}
function memberProgressText(v){if(v.type==='command_output')return v.tail||'';const e=v.detail||v;const label={accepted:'요청을 받았습니다',result_ready:'결과를 이 기기로 보내고 있습니다',delivered:'이 기기에 저장했습니다',input_required:'추가 답변이 필요합니다',client_action_required:'이 기기에서 처리하고 있습니다',tool_start:'요청에 필요한 자료와 도구를 확인하고 있습니다',tool_result:'처리 결과를 확인하고 있습니다',thinking:'답변을 준비하고 있습니다',error:'작업을 완료하지 못했습니다'};return label[v.type]||label[e.type]||''}
async function memberFiles(op){try{const r=await memberRequest('file',{op,path:document.getElementById('filePath').value,task_id:currentTask,content:document.getElementById('fileEditor').value,expected_hash:memberFileHashPath===document.getElementById('filePath').value?memberFileHash:'missing'});if(r.error)throw Error(r.message||r.error);if(op==='read'||op==='write'){memberFileHash=r.sha256||'';memberFileHashPath=document.getElementById('filePath').value}if(op==='read')document.getElementById('fileEditor').value=r.content||'';if(op==='list'){const rows=document.getElementById('fileRows');rows.replaceChildren();for(const f of r.files||r.items||[]){const b=document.createElement('button');b.textContent=f.name;b.onclick=()=>{document.getElementById('filePath').value=f.path||f.name;memberFiles((f.dir||f.is_dir||['directory','dir'].includes(f.type))?'list':'read')};rows.append(b)}}document.getElementById('fileStatus').textContent=op==='write'?'내 컴퓨터에 저장했습니다':r.path||''}catch(e){document.getElementById('fileStatus').textContent=e.message}}
'''
