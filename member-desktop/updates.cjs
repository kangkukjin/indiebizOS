/* Compatible UI + Go runtime updates. The installed Electron shell is the trust root. */
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const {validateExecutable}=require('./native-signature.cjs');
const {execFile}=require('node:child_process');
const {promisify}=require('node:util');
const execFileAsync=promisify(execFile);
const SHELL_VERSION=4;
const MAX_FILE=128*1024*1024;
function atomic(file,value){fs.mkdirSync(path.dirname(file),{recursive:true,mode:0o700});const temp=file+'.tmp';const fd=fs.openSync(temp,'w',0o600);try{fs.writeFileSync(fd,JSON.stringify(value));fs.fsyncSync(fd)}finally{fs.closeSync(fd)}fs.renameSync(temp,file);}
function read(file,fallback){try{return JSON.parse(fs.readFileSync(file,'utf8'));}catch(e){if(e.code==='ENOENT')return fallback;throw e;}}
function digest(data){return crypto.createHash('sha256').update(data).digest('hex');}
function https(raw){const u=new URL(raw);if(u.protocol!=='https:'||u.username||u.password||u.hash)throw Error('업데이트 주소는 HTTPS여야 합니다.');return u;}
function verify(envelope,trust,{platform=process.platform,arch=process.arch,now=Date.now()/1000,boot=false,allowOlderShell=false}={}){
 if(!trust?.publicKey||!trust?.feed)throw Error('배포자가 서명된 업데이트 채널을 설정하지 않았습니다.');
 const bytes=Buffer.from(envelope.manifest||'','base64');
 if(!bytes.length||bytes.length>65536||!crypto.verify(null,bytes,trust.publicKey,Buffer.from(envelope.signature||'','base64')))throw Error('업데이트 서명을 확인할 수 없습니다.');
 const m=JSON.parse(bytes);
 const kind=m.kind||'runtime';
 if(!['runtime','ui'].includes(kind))throw Error('알 수 없는 업데이트 종류입니다.');
 const names=kind==='ui'?['display.json']:['workspace.html','workspace.cjs','indiebiz-member'+(platform==='win32'?'.exe':'')];
 if(kind==='ui'&&(!/^[a-f0-9]{64}$/.test(m.host)||m.state!==1))throw Error('화면 호환 계약이 올바르지 않습니다.');
 if(m.format!=='indiebiz-member-runtime'||m.platform!==platform||m.arch!==arch||m.protocol!==2||!(m.shell===SHELL_VERSION||(allowOlderShell&&[1,2,3].includes(m.shell)))||!Number.isSafeInteger(m.sequence)||m.sequence<1||!/^\d+\.\d+\.\d+$/.test(m.version)||!Number.isFinite(m.expires)||(!boot&&m.expires<now))throw Error('호환되지 않거나 만료된 업데이트입니다. 설치 앱을 갱신하세요.');
 if(!Array.isArray(m.files)||m.files.length!==names.length||new Set(m.files.map(f=>f.name)).size!==names.length)throw Error('업데이트 파일 구성이 올바르지 않습니다.');
 const origin=https(trust.feed).origin;
 for(const f of m.files){if(!names.includes(f.name)||!Number.isSafeInteger(f.size)||f.size<1||f.size>MAX_FILE||!/^[a-f0-9]{64}$/.test(f.sha256)||https(f.url).origin!==origin)throw Error('업데이트 파일 검증 실패');}
 return m;
}
async function download(url,limit,fetcher=fetch){
 const r=await fetcher(https(url).href,{redirect:'error',signal:AbortSignal.timeout(120000)});
 if(!r.ok||Number(r.headers.get('content-length'))>limit)throw Error('업데이트를 내려받지 못했습니다.');
 const chunks=[];let size=0;for await(const chunk of r.body){size+=chunk.length;if(size>limit)throw Error('업데이트 크기 제한을 초과했습니다.');chunks.push(Buffer.from(chunk));}return Buffer.concat(chunks);
}
class RuntimeUpdates {
 constructor({root,trust,baseline,session,show,showUI,revertUI,fetcher=fetch,backup,verifyExecutable=validateExecutable}){
  Object.assign(this,{root,trust,baseline,session,show,showUI,revertUI,fetcher,verifyExecutable});this.dir=path.join(root,'updates');this.stateFile=path.join(this.dir,'state.json');this.state=read(this.stateFile,{active:null,highest:0,rejected:[]});this.status={state:trust?.publicKey&&trust?.feed?'idle':'unconfigured'};this.busy=false;
  this.state.ui ||= {active:null,highest:0,rejected:[]};
  // Previous automatic-install preferences never authorize a new update.
  if(Object.hasOwn(this.state,'auto')||Object.hasOwn(this.state,'deferred')){delete this.state.auto;delete this.state.deferred;this.save();}
  this.backup=backup||((exe,source,target)=>execFileAsync(exe,['--member-db-backup',source,target],{timeout:30000,windowsHide:true}));
 }
 save(){atomic(this.stateFile,this.state);}
 location(sequence,kind='runtime'){if(!Number.isSafeInteger(sequence)||sequence<1)throw Error('업데이트 상태 오류');return path.join(this.dir,kind==='ui'?'ui':'releases',String(sequence));}
 release(sequence,allowOlderShell=false,kind='runtime'){
  if(sequence==null)return this.baseline;
  const dir=this.location(sequence,kind),envelope=read(path.join(dir,'manifest.json'));
  const m=verify(envelope,this.trust,{boot:true,allowOlderShell});if(m.sequence!==sequence||(m.kind||'runtime')!==kind)throw Error('업데이트 판본 불일치');
  for(const f of m.files){const file=path.join(dir,f.name);const stat=fs.lstatSync(file);if(!stat.isFile()||stat.isSymbolicLink()||stat.size!==f.size||digest(fs.readFileSync(file))!==f.sha256)throw Error('설치된 업데이트가 변경되었습니다.');}
  if(kind==='ui'){const display=read(path.join(dir,'display.json'));if(display.format!=='indiebiz-display-1'||display.surface!=='desktop'||display.host!==m.host||display.state!==m.state)throw Error('화면 계약 불일치');return {display,version:m.version,shell:m.shell};}
  const executable=path.join(dir,'indiebiz-member'+(process.platform==='win32'?'.exe':''));
  // Retired overlays are verified as data but never executed by a new shell.
  if(!allowOlderShell||m.shell===SHELL_VERSION)this.verifyExecutable(executable,this.baseline.executable);
  return {workspace:path.join(dir,'workspace.html'),executable,version:m.version,shell:m.shell};
 }
 restore(pending){
  // Trial never accepts user writes. Preserve failed DBs for diagnosis before restoring snapshots.
  if(!/^[a-f0-9-]{36}$/.test(pending.snapshot))throw Error('백업 식별자 오류');
  const snapshots=read(path.join(this.dir,'snapshots',pending.snapshot,'index.json'));
  for(const row of snapshots){if(!/^[a-f0-9]{64}$/.test(row.namespace))throw Error('백업 경로 오류');if(row.existed&&digest(fs.readFileSync(path.join(this.dir,'snapshots',pending.snapshot,row.namespace+'.db')))!==row.sha256)throw Error('복구 사본 지문 오류');}
  for(const row of snapshots){
   if(!/^[a-f0-9]{64}$/.test(row.namespace))throw Error('백업 경로 오류');
   const dir=path.join(this.root,'workspaces',row.namespace);fs.mkdirSync(dir,{recursive:true,mode:0o700});
   for(const suffix of ['','-wal','-shm']){const file=path.join(dir,'member.db'+suffix);if(fs.existsSync(file))fs.renameSync(file,file+'.failed-'+pending.snapshot+'-'+crypto.randomUUID());}
   if(row.existed){const source=path.join(this.dir,'snapshots',pending.snapshot,row.namespace+'.db');if(digest(fs.readFileSync(source))!==row.sha256)throw Error('복구 사본 지문 오류');fs.copyFileSync(source,path.join(dir,'member.db'));}
  }
 }
 recover(){
  if(this.state.pending?.kind==='ui'){const p=this.state.pending;this.state.ui.active=p.previous;this.state.ui.rejected=[...new Set([...this.state.ui.rejected,p.candidate])];delete this.state.pending;this.save();this.status={state:'rolled_back',message:'확인되지 않은 화면 후보를 취소했습니다. 작업과 파일은 유지됩니다.'};}
  if(this.state.pending){const p=this.state.pending;this.restore(p);this.state.active=p.previous;this.state.rejected=[...new Set([...(this.state.rejected||[]),p.candidate])];delete this.state.pending;this.save();this.status={state:'rolled_back',message:'새 실행부의 시작을 확인하지 못해 이전 판본과 DB를 복구했습니다.'};}
  const runtime=this.release(this.state.active,true);
  // A full installer replaces the shell. Retire a verified older overlay, keeping user data.
  if(this.state.active!=null&&runtime.shell<SHELL_VERSION){this.state.active=null;delete this.state.activeVersion;this.save();return this.baseline;}
  if(this.state.active!=null&&this.state.activeVersion!==runtime.version){this.state.activeVersion=runtime.version;this.save();}
  return runtime;
 }
 publicState(){
  const offer=this.available?.manifest;
  return {...this.status,version:this.state.active==null?this.baseline.version:this.state.activeVersion,
   uiVersion:this.state.ui.version,kind:offer?.kind||'runtime',configured:!!(this.trust?.publicKey&&this.trust?.feed),availableVersion:offer?.version,sequence:offer?.sequence,
   canUpdate:!!offer&&!this.busy&&!this.prompting};
 }
 async requestInstall(confirm){
  if(this.busy||this.prompting)return this.publicState();
  await this.check();
  if(!this.available||this.prompting)return this.publicState();
  this.prompting=true;
  try{
   const offer=this.publicState();
   if(await confirm(offer))return await this.apply(offer.sequence);
   return this.publicState();
  }finally{this.prompting=false;}
 }
 async check(){
  if(this.busy||this.prompting)return this.publicState();
  if(!this.trust?.publicKey||!this.trust?.feed){this.status={state:'unconfigured'};return this.publicState();}
  this.busy=true;
  try{
   this.status={state:'checking'};const envelope=JSON.parse((await download(this.trust.feed,131072,this.fetcher)).toString());const m=verify(envelope,this.trust);
   const selected=m.kind==='ui'?this.state.ui:this.state;
   if(m.sequence<=selected.highest||(selected.rejected||[]).includes(m.sequence)){this.available=null;this.status={state:'current'};}
   else{this.available={manifest:m,envelope};this.status={state:'available'};}
  }catch(e){this.status={state:'error',message:e.message};throw e;}finally{this.busy=false;}
  return this.publicState();
 }
 async downloadSelected(sequence){
  const offer=this.available;
  if(!offer||sequence!==offer.manifest.sequence)throw Error('표시된 업데이트를 다시 확인하고 선택하세요.');
  const m=verify(offer.envelope,this.trust);
  this.status={state:'downloading'};
  const dir=this.location(m.sequence,m.kind||'runtime');fs.mkdirSync(dir,{recursive:true,mode:0o700});
  for(const f of m.files){const bytes=await download(f.url,f.size,this.fetcher);if(bytes.length!==f.size||digest(bytes)!==f.sha256)throw Error('업데이트 파일 지문이 일치하지 않습니다.');const file=path.join(dir,f.name);fs.writeFileSync(file+'.part',bytes,{mode:f.name.startsWith('indiebiz-member')?0o700:0o600});fs.renameSync(file+'.part',file);}
  atomic(path.join(dir,'manifest.json'),offer.envelope);this.release(m.sequence,false,m.kind||'runtime');return m.sequence;
 }
 async resumeUI(){
  if(this.state.ui.active==null)return;
  if(!this.showUI)throw Error('화면 업데이트를 지원하는 설치 앱이 필요합니다.');
  const selected=this.release(this.state.ui.active,true,'ui');
  if(selected.shell<SHELL_VERSION){this.state.ui.active=null;delete this.state.ui.version;this.save();return;}
  await this.showUI(selected.display);
 }
 async applyUI(sequence){
  const previous=this.state.ui.active,previousState={...this.state.ui};let pending=false,applied=false,candidate;
  try{
   if(!this.showUI)throw Error('화면 업데이트를 지원하는 설치 앱이 필요합니다.');
   candidate=this.release(sequence,false,'ui');
   this.state.pending={kind:'ui',candidate:sequence,previous};this.save();pending=true;
   this.status={state:'testing'};
   await this.showUI(candidate.display);applied=true;
   this.state.ui={...this.state.ui,active:sequence,version:candidate.version,highest:sequence};
   delete this.state.pending;this.save();pending=false;this.available=null;
   this.status={state:'updated'};
  }catch(e){
   if(applied){if(!this.revertUI)throw Error('화면 확정 실패 뒤 복구 콜백이 없습니다');await this.revertUI(candidate.display.version);}
   this.state.ui={...previousState};
   if(pending){this.state.ui.active=previous;this.state.ui.rejected=[...new Set([...this.state.ui.rejected,sequence])];delete this.state.pending;this.save();}else delete this.state.pending;
   this.available=null;this.status={state:'rolled_back',message:'새 화면을 적용하지 못해 이전 화면을 유지합니다: '+e.message};
  }finally{this.busy=false;}
  return this.publicState();
 }
 async snapshot(){
  const id=crypto.randomUUID(),dir=path.join(this.dir,'snapshots',id);fs.mkdirSync(dir,{recursive:true,mode:0o700});const rows=[];
  const workspaces=path.join(this.root,'workspaces');
  for(const namespace of fs.existsSync(workspaces)?fs.readdirSync(workspaces):[]){
   if(!/^[a-f0-9]{64}$/.test(namespace))continue;
   const source=path.join(workspaces,namespace,'member.db'),target=path.join(dir,namespace+'.db');const row={namespace,existed:fs.existsSync(source)};
   if(row.existed){await this.backup(this.session.executable,source,target);row.sha256=digest(fs.readFileSync(target));}rows.push(row);
  }
  atomic(path.join(dir,'index.json'),rows);return id;
 }
 async apply(sequence){
  if(this.busy)return this.publicState();
  if(!this.available||sequence!==this.available.manifest.sequence)throw Error('표시된 업데이트를 다시 확인하고 선택하세요.');
  if(!this.session.config)throw Error('기기를 등록한 뒤 업데이트를 적용하세요.');
  this.busy=true;
  try{await this.downloadSelected(sequence);}catch(e){this.status={state:'error',message:e.message};this.busy=false;throw e;}
  if(this.available.manifest.kind==='ui')return this.applyUI(sequence);
  this.session.updating=true;
  const previous=this.state.active;let pending=false;
  if(!this.session.config){this.session.updating=false;this.busy=false;throw Error('기기를 등록한 뒤 업데이트를 적용하세요.');}
  try{
   this.status={state:'waiting'};
   if(this.session.bridge){while(!(await this.session.maintenance(true)).idle){await new Promise(r=>setTimeout(r,1000));}}
   const candidate=this.release(sequence);
   this.session.updateTrial=true;await this.session.stop();const snapshot=await this.snapshot();
   this.state.pending={candidate:sequence,previous,snapshot};this.save();pending=true;
   this.status={state:'testing'};this.session.executable=candidate.executable;
   await this.session.start(undefined,{maintenance:true});
   if(this.session.bridge){const health=await this.session.internalRequest('health');if(!health.success||health.protocol!==2)throw Error('새 실행부의 DB·프로토콜 검사가 실패했습니다.');}
   await this.show(candidate.workspace,true);
   if(this.session.bridge)await this.session.maintenance(false);
   this.state.active=sequence;this.state.activeVersion=candidate.version;this.state.ui.active=null;delete this.state.ui.version;this.state.highest=sequence;delete this.state.pending;this.save();pending=false;this.available=null;
   this.status={state:'updated'};
  }catch(e){
   await this.session.stop();
   if(pending){this.recover();this.available=null;}else{this.state.active=previous;}
   const old=this.release(previous);this.session.executable=old.executable;
   await this.session.start();await this.show(old.workspace,false);
   this.status={state:'rolled_back',message:'업데이트를 적용하지 못해 이전 판본을 유지합니다: '+e.message};
  }finally{this.session.updating=false;this.session.updateTrial=false;this.busy=false;}
  return this.publicState();
 }
}
module.exports={RuntimeUpdates,verify,download,digest,SHELL_VERSION};
