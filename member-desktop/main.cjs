const {app,BrowserWindow,ipcMain,safeStorage,dialog,shell,Tray,Menu,nativeImage}=require('electron');
const path=require('node:path');
const fs=require('node:fs');
const {fileURLToPath}=require('node:url');
const {MemberSession}=require('./session.cjs');
const {invitation}=require('./security.cjs');
const {RuntimeUpdates}=require('./updates.cjs');
let win,tray,session,updates,bootReady,quitting=false,pending={},error='';
const setupFile=path.join(__dirname,'setup.html');let workspaceFile=path.join(__dirname,'workspace.html');
function liveWindow(){return !quitting&&win&&!win.isDestroyed()?win:null;}
function showWindow(file){const current=liveWindow();if(!current)return;if(file)void current.loadFile(file).catch(e=>{error=e.message;});current.show();}
function acceptLink(raw){if(quitting)return;try{pending=invitation(raw);showWindow(setupFile);}catch{error='등록 링크를 확인하세요.';}}
if(!app.requestSingleInstanceLock())app.quit();
else {
app.setName('IndieBiz Member');
app.on('second-instance',(_,argv)=>{const link=argv.find(a=>a.startsWith('indiebiz-member:'));if(link)acceptLink(link);showWindow();});
app.on('open-url',(e,url)=>{e.preventDefault();acceptLink(url);});
// Resume quit on the next event-loop turn, after Electron unwinds the cancelled quit.
app.on('before-quit',e=>{if(!quitting){e.preventDefault();quitting=true;Promise.resolve().then(()=>session?.stop()).catch(e=>{console.error('회원 실행부 종료 실패:',e);}).finally(()=>setImmediate(()=>app.quit()));}});
// Closing normally hides to the tray; a destroyed last window must not strand the app.
app.on('window-all-closed',()=>{if(!quitting)app.quit();});
app.on('activate',()=>showWindow());
app.whenReady().then(async()=>{
  const root=app.getPath('userData');
  const executable=app.isPackaged?path.join(process.resourcesPath,'member','indiebiz-member'+(process.platform==='win32'?'.exe':'')):path.join(__dirname,'resources','indiebiz-member'+(process.platform==='win32'?'.exe':''));
  session=new MemberSession({root,safeStorage,executable,onExit:()=>{error='로컬 실행부가 종료됐습니다. 기록은 보존되며 작업은 자동 재실행하지 않습니다.';const current=liveWindow();if(current&&!current.webContents.isDestroyed())current.webContents.send('member:disconnected');}});
  let trust={};const trustFile=path.join(__dirname,'update-trust.json');if(fs.existsSync(trustFile))trust=JSON.parse(fs.readFileSync(trustFile,'utf8'));
  const show=async(file,trial)=>{
    workspaceFile=file;
    if(!trial){await win.loadFile(file);return;}
    let timer;const ready=new Promise((resolve,reject)=>{timer=setTimeout(()=>reject(Error('새 화면을 시작하지 못했습니다.')),25000);bootReady=resolve;});
    try{await win.loadFile(file);await ready;}finally{clearTimeout(timer);bootReady=null;}
  };
  updates=new RuntimeUpdates({root,trust,session,show,baseline:{workspace:workspaceFile,executable,version:require('./package.json').version}});
  try{const runtime=updates.recover();workspaceFile=runtime.workspace;session.executable=runtime.executable;}catch(e){dialog.showErrorBox('업데이트 복구 필요',e.message);quitting=true;app.quit();return;}
  win=new BrowserWindow({width:1280,height:900,minWidth:760,minHeight:560,title:'IndieBiz Member',webPreferences:{preload:path.join(__dirname,'preload.cjs'),nodeIntegration:false,contextIsolation:true,sandbox:true,webSecurity:true}});
  win.on('close',e=>{if(!quitting){e.preventDefault();win.hide();}});
  win.on('closed',()=>{win=null;});
  win.webContents.on('will-navigate',(e,url)=>{try{if(![setupFile,workspaceFile].includes(fileURLToPath(url)))e.preventDefault();}catch{e.preventDefault();}});
  win.webContents.setWindowOpenHandler(({url})=>{if(/^https?:\/\//.test(url))void shell.openExternal(url);return {action:'deny'};});
  win.webContents.session.setPermissionRequestHandler((_,permission,callback)=>callback(false));
  // No scripts, fonts, or frames can be loaded from the hub. Only media has a remote source.
  win.webContents.session.webRequest.onBeforeRequest((details,callback)=>callback({cancel:/^https?:/.test(details.url)&&details.resourceType!=='media'}));
  const icon=nativeImage.createFromDataURL('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAFElEQVR42mNk+M/wn4ECwESJ5lEDAAArhQIfO3u8VgAAAABJRU5ErkJggg==');
  tray=new Tray(icon);tray.setToolTip('IndieBiz Member');tray.setContextMenu(Menu.buildFromTemplate([{label:'작업 공간 열기',click:()=>showWindow()},{label:'연결 설정',click:()=>showWindow(setupFile)},{type:'separator'},{label:'앱 종료 (작업 중단)',click:()=>app.quit()}]));tray.on('click',()=>showWindow());
  Menu.setApplicationMenu(Menu.buildFromTemplate([{label:'IndieBiz Member',submenu:[{role:'about'},{label:'작업 공간 열기',click:()=>showWindow(session.bridge?workspaceFile:setupFile)},{role:'quit'}]},{role:'editMenu'},{role:'viewMenu'},{role:'windowMenu'}]));
  app.setAsDefaultProtocolClient('indiebiz-member');
  function trusted(event,setupOnly=false){if(event.sender!==win.webContents||event.senderFrame!==win.webContents.mainFrame)throw Error('허용되지 않은 창');const filename=fileURLToPath(event.senderFrame.url);if(![setupFile,...(setupOnly?[]:[workspaceFile])].includes(filename))throw Error('허용되지 않은 화면');}
  function handle(name,fn,setupOnly=false){ipcMain.handle('member:'+name,async(e,arg)=>{trusted(e,setupOnly);if(session.updating&&!['request','ready','setup','settings','updateStatus'].includes(name))throw Error('업데이트 중입니다. 완료 후 다시 시도하세요.');return fn(arg);});}
  handle('ready',()=>{bootReady?.();return {success:true};});
  handle('updateStatus',()=>updates.publicState());
  handle('updateCheck',()=>updates.check());
  handle('updateApply',()=>updates.apply());
  handle('updateAuto',enabled=>updates.setAuto(Boolean(enabled)));
  handle('setup',()=>({...session.publicState(),...pending,error}));
  handle('enroll',async({hub,code})=>{const existing=session.config;if(existing){const answer=await dialog.showMessageBox(win,{type:'question',buttons:['취소','새 PC 등록으로 전환'],defaultId:0,message:'진행 중 작업을 중단하고 다른 등록으로 연결할까요?',detail:'기존 파일과 로컬 기록은 보존합니다.'});if(answer.response!==1)throw Error('연결 변경을 취소했습니다.');}const state=await session.enroll(hub,code);pending={};error='';await win.loadFile(workspaceFile);return state;},true);
  handle('request',({path,body})=>session.request(path,body));
  handle('folder',async()=>{const r=await dialog.showOpenDialog(win,{properties:['openDirectory','createDirectory']});if(r.canceled)return {cancelled:true};return session.request('workspace',{path:r.filePaths[0]});});
  handle('diagnostics',async()=>{const data=await session.request('connection');const r=await dialog.showSaveDialog(win,{defaultPath:'indiebiz-member-diagnostics.json',filters:[{name:'진단 JSON',extensions:['json']}]});if(r.canceled)return {cancelled:true};fs.writeFileSync(r.filePath,JSON.stringify(data,null,2),{mode:0o600});return {success:true};});
  handle('settings',()=>({...session.publicState(),startup:app.getLoginItemSettings().openAtLogin}));
  handle('startup',enabled=>{app.setLoginItemSettings({openAtLogin:enabled});return {success:true};});
  handle('disconnect',async()=>{const r=await dialog.showMessageBox(win,{buttons:['취소','연결 종료'],defaultId:0,message:'작업을 중단하고 이 앱의 연결 자격을 지울까요?',detail:'로컬 파일과 작업 기록은 보존합니다.'});if(r.response!==1)return {cancelled:true};await session.disconnect();await win.loadFile(setupFile);return {success:true};});
  handle('open',async({taskId,path:target,reveal})=>{const r=await session.request('file',{op:'resolve',task_id:taskId,path:target});if(!r.success)throw Error(r.error);if(reveal){shell.showItemInFolder(r.path);return {success:true};}const failure=await shell.openPath(r.path);return {success:!failure,error:failure};});
  handle('import',async()=>{const r=await dialog.showOpenDialog(win,{properties:['openFile'],filters:[{name:'회원 백업',extensions:['json','zip']}]});if(r.canceled)return {cancelled:true};const stat=fs.statSync(r.filePaths[0]);if(stat.size>32*1024*1024)throw Error('백업은 32MB 이하여야 합니다.');return session.request('restore',path.extname(r.filePaths[0]).toLowerCase()==='.zip'?{zip_base64:fs.readFileSync(r.filePaths[0]).toString('base64')}:{archive:JSON.parse(fs.readFileSync(r.filePaths[0],'utf8'))});});
  try{await session.start();}catch(e){error=e.message;}
  const link=process.argv.find(a=>a.startsWith('indiebiz-member:'));if(link)acceptLink(link);
  await win.loadFile(Object.keys(pending).length?setupFile:session.bridge?workspaceFile:setupFile);
  const automatic=async()=>{if(!updates.state.auto||!session.config)return;try{await updates.check();if(updates.staged)await updates.apply();}catch(e){error=e.message;}};
  setTimeout(automatic,60000).unref();setInterval(automatic,6*60*60*1000).unref();
});}
