/* Bundled UI additions. Never loaded from the hub. */
window.memberDesktopBoot=async()=>{
 const d=window.DesktopMember;if(!d)return;
 const $=id=>document.getElementById(id);
 d.onDisconnected(()=>{$('status').textContent='실행부 연결 종료 · 기록은 보존됩니다. 앱을 다시 여세요.';$('sendButton').disabled=true;});
 const settings=document.createElement('details');settings.innerHTML='<summary>이 PC의 연결 · 권한 · 백업</summary><p id="desktopInfo"></p><label><input id="desktopStartup" type="checkbox"> 로그인할 때 시작</label> <label><input id="desktopScreen" type="checkbox"> 화면 캡처와 마우스·키보드 사용 허용</label><p>화면 조작은 매번 승인합니다. 셸 명령은 선택 폴더에서 시작하지만 OS 계정 권한으로 실행되므로 승인 전에 명령을 확인하세요.</p><button id="desktopImport" class="secondary">백업 가져오기 (JSON·ZIP)</button> <button id="desktopDisconnect" class="secondary">연결 종료</button><button id="desktopDiagnostics" class="secondary">표시된 진단 정보 내보내기</button><pre id="desktopDiagnosticPreview"></pre><p id="desktopMessage" role="status"></p>';
 $('notice').after(settings);
 const report=e=>$('desktopMessage').textContent=e.message||String(e);
 try{const s=await d.settings();$('desktopInfo').textContent=s.name+' · '+s.hub;$('desktopStartup').checked=s.startup;const c=await d.request('connection');$('desktopScreen').checked=c.screen;$('desktopDiagnosticPreview').textContent=JSON.stringify(c,null,2);}catch(e){report(e)}
 $('desktopDiagnostics').onclick=()=>d.saveDiagnostics().catch(report);
 $('desktopStartup').onchange=e=>d.startup(e.target.checked).catch(report);
 $('desktopScreen').onchange=async e=>{try{await d.request('permissions',{screen:e.target.checked});$('desktopMessage').textContent='다음 작업부터 적용합니다. OS의 화면 기록·접근성 권한도 필요합니다.';}catch(error){report(error)}};
 $('desktopDisconnect').onclick=()=>d.disconnect().catch(report);
 $('desktopImport').onclick=async()=>{try{const r=await d.importArchive();if(!r.cancelled){if(!r.success)throw Error(r.message||r.error);$('desktopMessage').textContent=`가져온 파일 ${r.files}개 · 기록 ${r.records}개 · ${r.path}`;refreshTasks();}}catch(e){report(e)}};
 $('workspacePicker').hidden=true;
 $('setWorkspace').onclick=async()=>{try{const r=await d.chooseWorkspace();if(r.cancelled)return;if(!r.success)throw Error(r.message||r.error);$('workspacePath').textContent=r.workspace;$('newTask').click();await refreshApps();}catch(e){report(e)}};
 $('importFile').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;if(file.size>32*1024*1024)throw Error('파일은 32MB 이하여야 합니다.');const bytes=new Uint8Array(await file.arrayBuffer());let text='';for(let i=0;i<bytes.length;i+=8192)text+=String.fromCharCode(...bytes.subarray(i,i+8192));const r=await d.request('file',{op:'write',task_id:currentTask,path:'imports/'+crypto.randomUUID().slice(0,8)+'-'+file.name,content:btoa(text),encoding:'base64',expected_hash:'missing'});$('fileStatus').textContent=r.path||r.message||r.error;}catch(e){report(e)}};
 const open=document.createElement('button');open.textContent='기본 앱에서 열기';open.onclick=()=>d.openFile(currentTask,$('filePath').value).catch(report);$('saveFile').after(open);
 const changes=document.createElement('details');changes.innerHTML='<summary>파일 변경과 되돌리기</summary><button id="desktopChanges" class="secondary">변경 목록 새로고침</button><div id="desktopChangeRows"></div>'; $('results').after(changes);
 const diff=document.createElement('button');diff.textContent='Git 변경 보기';const diffText=document.createElement('pre');diffText.style.cssText='white-space:pre-wrap;max-height:400px;overflow:auto';changes.append(diff,diffText);diff.onclick=async()=>{const r=await d.request('file',{op:'diff',task_id:currentTask});diffText.textContent=r.success?(r.notice+'\n'+r.diff):(r.message||r.error);};
 $('desktopChanges').onclick=async()=>{try{const rows=await d.request('changes?id='+encodeURIComponent(currentTask||'local-browser'));$('desktopChangeRows').replaceChildren();for(const row of rows){const line=document.createElement('p');line.textContent=row.path+' · '+new Date(row.created*1000).toLocaleString()+' ';const undo=document.createElement('button');undo.textContent='이 변경 되돌리기';undo.onclick=async()=>{const r=await d.request('file',{op:'undo',task_id:row.task_id,change_id:row.id});$('desktopMessage').textContent=r.success?'파일을 되돌렸습니다.':r.message||r.error;};line.append(undo);$('desktopChangeRows').append(line)}}catch(e){report(e)}};
 const originalExport=$('export').onclick;$('export').onclick=async()=>{await originalExport();$('desktopMessage').textContent='기억 ZIP은 이 앱의 데이터 폴더에 보존됩니다.'};
 const updateBox=document.createElement('details');updateBox.innerHTML='<summary>앱 업데이트</summary><p id="desktopUpdateStatus" role="status"></p><p><button id="desktopUpdateCheck" class="secondary">업데이트 확인</button> <button id="desktopUpdateApply" class="secondary">업데이트</button></p>';
 settings.after(updateBox);
 const indicator=document.createElement('button');indicator.id='desktopUpdateAvailable';indicator.className='secondary';indicator.hidden=true;
 indicator.style.cssText='margin-left:auto;font-size:12px;padding:4px 8px';indicator.textContent='새 업데이트 있음';
 $('memberNav').append(indicator);
 const updateLabels={unconfigured:'배포자가 업데이트 채널을 아직 설정하지 않았습니다.',idle:'업데이트를 확인할 수 있습니다.',checking:'업데이트를 확인하고 있습니다.',current:'최신 호환 판본입니다.',available:'새 업데이트가 있습니다.',downloading:'선택한 업데이트를 받고 있습니다.',waiting:'현재 작업이 끝나면 업데이트합니다.',testing:'새 버전을 확인하고 있습니다.',updated:'업데이트를 적용했습니다.',rolled_back:'이전 판본으로 복구했습니다.',error:'업데이트를 진행하지 못했습니다.'};
 let updatePending=false;
 const updateStatus=async()=>{
  const r=await d.updateStatus();
  $('desktopUpdateStatus').textContent=(updateLabels[r.state]||r.state)+(r.version?' · 현재 '+r.version:'')+(r.availableVersion?' → '+r.availableVersion:'')+(r.message?' '+r.message:'');
  const working=['downloading','waiting','testing'].includes(r.state);
  $('desktopUpdateCheck').disabled=!r.configured||working||updatePending;
  $('desktopUpdateApply').disabled=!r.canUpdate||updatePending;
  indicator.hidden=!(r.sequence||working);
  indicator.textContent=working?'업데이트 중…':'새 업데이트 있음';
  indicator.title=working?updateLabels[r.state]:'최신 버전 '+(r.availableVersion||'')+' · 눌러서 설치';
  indicator.disabled=!r.canUpdate||updatePending;
 };
 const applyUpdate=async()=>{if(updatePending)return;updatePending=true;try{await updateStatus();await d.updateApply()}catch(e){report(e)}finally{updatePending=false;await updateStatus()}};
 $('desktopUpdateCheck').onclick=async()=>{try{await d.updateCheck()}catch(e){report(e)}await updateStatus()};
 $('desktopUpdateApply').onclick=applyUpdate;indicator.onclick=applyUpdate;
 await updateStatus();setInterval(()=>updateStatus().catch(()=>{}),3000);
 await d.ready();

};
