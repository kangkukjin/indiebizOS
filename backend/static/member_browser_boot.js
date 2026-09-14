let memberBrowser=null,memberBrowserRelease=null,memberBrowserReady=false;
function showMemberArtifacts(result){
  const box=document.getElementById('memberArtifacts');box.replaceChildren();
  for(const file of result?.files||[]){
    if(file.on!=='body'||!file.saved||typeof file.path!=='string')continue;
    const row=document.createElement('p'),label=document.createElement('span'),button=document.createElement('button');
    label.textContent='결과 파일이 이 기기에 저장됐습니다. ';label.title=file.path;
    button.textContent='내려받기';button.onclick=async()=>{try{await memberBrowser.files.download(file.path)}catch(e){document.getElementById('status').textContent=e.message}};
    row.append(label,button);box.append(row);
  }
}
async function memberRequest(path,body){if(!memberBrowser)throw Error('회원 키로 먼저 연결하세요');return memberBrowser.request(path,body)}
// The browser runtime controls its audio directly. The helper-only media poll is unused.
async function memberMedia(){}
async function memberBoot(){
  document.getElementById('browserLoginForm').onsubmit=async e=>{e.preventDefault();await browserLogin(document.getElementById('browserKey').value.trim())};
  document.getElementById('browserRestore').onchange=async e=>{
    const file=e.target.files[0];if(!file||!memberBrowser)return;
    const status=document.getElementById('browserStorageStatus');
    try{if(file.size>128*1024*1024)throw Error('백업은 128MB 이하여야 합니다');const result=await memberBrowser.store.restore(JSON.parse(await file.text()));status.textContent=`복원: ${result.added}개 추가, 기존 ${result.skipped}개 유지`;taskSignature='';taskListSignature='';refreshTasks();refreshApps()}catch(error){status.textContent=error.message}finally{e.target.value=''};
  };
  document.getElementById('browserPersist').onclick=async()=>{
    const granted=await navigator.storage?.persist?.();document.getElementById('browserStorageStatus').textContent=granted?'이 브라우저에 지속 보관을 설정했습니다. 사이트 데이터 삭제 전에는 백업하세요.':'브라우저가 지속 보관을 허용하지 않았습니다. 기억 내보내기로 백업하세요.';
  };
  document.getElementById('browserLogout').onclick=async()=>{if(memberBrowser){await memberBrowser.stop();memberBrowser.active=false}sessionStorage.removeItem('member-web-key');memberBrowserRelease?.();location.reload()};
  const remembered=sessionStorage.getItem('member-web-key');if(remembered)await browserLogin(remembered);
}
async function browserLogin(key){
  const status=document.getElementById('browserLoginStatus'),button=document.getElementById('browserConnect');
  if(!key)return;button.disabled=true;status.textContent='회원 확인과 기기 저장소 연결 중…';
  try{
    if(!window.isSecureContext||!window.indexedDB||!navigator.locks)throw Error('HTTPS 주소에서 최신 브라우저로 열어 주세요. 로컬 저장소와 탭 잠금 기능이 필요합니다.');
    const space=await memberDigest(key);
    await new Promise((resolve,reject)=>{navigator.locks.request('indiebiz-member-'+space,{ifAvailable:true},async lock=>{
      if(!lock){reject(Error('이 회원의 작업 공간이 다른 탭에 열려 있습니다. 그 탭에서 계속하세요.'));return}
      await new Promise(release=>{memberBrowserRelease=release;resolve()});
    }).catch(reject)});
    const store=await MemberBrowserStore.open(space);await store.recover();memberBrowser=new MemberBrowserRuntime(key,store);
    await memberBrowser.connect();sessionStorage.setItem('member-web-key',key);document.getElementById('browserKey').value='';
    document.getElementById('memberLogin').hidden=true;document.getElementById('memberWorkspace').hidden=false;
    if(!memberBrowserReady){memberBrowserReady=true;await workspaceBoot();
      document.getElementById('importFile').onchange=async e=>{const file=e.target.files[0];if(!file)return;try{const r=await memberBrowser.files.import(file);document.getElementById('filePath').value=r.path;document.getElementById('fileStatus').textContent='이 기기에 가져왔습니다: '+r.path}catch(error){document.getElementById('fileStatus').textContent=error.message}finally{e.target.value=''}};
      document.getElementById('browserDownloadFile').onclick=async()=>{try{await memberBrowser.files.download(document.getElementById('filePath').value);document.getElementById('fileStatus').textContent='브라우저에 다운로드를 요청했습니다'}catch(e){document.getElementById('fileStatus').textContent=e.message}};
    }
    document.getElementById('status').textContent='연결됨 · 설치 없이 이 브라우저에서 작업합니다';
    const persistent=await navigator.storage?.persisted?.();document.getElementById('browserStorageStatus').textContent=persistent?'이 기기에 지속 보관 중 · 사이트 데이터 삭제 전 백업하세요':'기억과 파일은 이 브라우저에 저장됩니다. 지속 보관과 백업을 사용할 수 있습니다.';
  }catch(error){if(memberBrowser)memberBrowser.active=false;memberBrowser?.store?.db.close();memberBrowser=null;memberBrowserRelease?.();memberBrowserRelease=null;status.textContent=error.message;sessionStorage.removeItem('member-web-key')}
  finally{button.disabled=false}
}
addEventListener('beforeunload',()=>{
  if(!memberBrowser?.running)return;
  fetch('/m/session/close',{method:'POST',credentials:'omit',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:memberBrowser.key,body_session:memberBrowser.session}),keepalive:true}).catch(()=>{});
});
