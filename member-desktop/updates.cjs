/* Compatible UI + Go runtime updates. The installed Electron shell is the trust root. */
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const {execFile}=require('node:child_process');
const {promisify}=require('node:util');
const execFileAsync=promisify(execFile);
const SHELL_VERSION=1;
const MAX_FILE=128*1024*1024;
function atomic(file,value){fs.mkdirSync(path.dirname(file),{recursive:true,mode:0o700});const temp=file+'.tmp';fs.writeFileSync(temp,JSON.stringify(value),{mode:0o600});fs.renameSync(temp,file);}
function read(file,fallback){try{return JSON.parse(fs.readFileSync(file,'utf8'));}catch(e){if(e.code==='ENOENT')return fallback;throw e;}}
function digest(data){return crypto.createHash('sha256').update(data).digest('hex');}
function https(raw){const u=new URL(raw);if(u.protocol!=='https:'||u.username||u.password||u.hash)throw Error('업데이트 주소는 HTTPS여야 합니다.');return u;}
function verify(envelope,trust,{platform=process.platform,arch=process.arch,now=Date.now()/1000,boot=false}={}){
 if(!trust?.publicKey||!trust?.feed)throw Error('배포자가 서명된 업데이트 채널을 설정하지 않았습니다.');
 const bytes=Buffer.from(envelope.manifest||'','base64');
 if(!bytes.length||bytes.length>65536||!crypto.verify(null,bytes,trust.publicKey,Buffer.from(envelope.signature||'','base64')))throw Error('업데이트 서명을 확인할 수 없습니다.');
 const m=JSON.parse(bytes);
 const names=['workspace.html','workspace.cjs','indiebiz-member'+(platform==='win32'?'.exe':'')];
 if(m.format!=='indiebiz-member-runtime'||m.platform!==platform||m.arch!==arch||m.protocol!==2||m.shell!==SHELL_VERSION||!Number.isSafeInteger(m.sequence)||m.sequence<1||!/^\d+\.\d+\.\d+$/.test(m.version)||!Number.isFinite(m.expires)||(!boot&&m.expires<now))throw Error('호환되지 않거나 만료된 업데이트입니다. 설치 앱을 갱신하세요.');
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
 constructor({root,trust,baseline,session,show,fetcher=fetch,backup}){
  Object.assign(this,{root,trust,baseline,session,show,fetcher});this.dir=path.join(root,'updates');this.stateFile=path.join(this.dir,'state.json');this.state=read(this.stateFile,{active:null,highest:0,auto:false,rejected:[]});this.status={state:trust?.publicKey&&trust?.feed?'idle':'unconfigured'};this.busy=false;
  this.backup=backup||((exe,source,target)=>execFileAsync(exe,['--member-db-backup',source,target],{timeout:30000,windowsHide:true}));
 }
 save(){atomic(this.stateFile,this.state);}
 location(sequence){if(!Number.isSafeInteger(sequence)||sequence<1)throw Error('업데이트 상태 오류');return path.join(this.dir,'releases',String(sequence));}
 release(sequence){
  if(sequence==null)return this.baseline;
  const dir=this.location(sequence),envelope=read(path.join(dir,'manifest.json'));
  const m=verify(envelope,this.trust,{boot:true});if(m.sequence!==sequence)throw Error('업데이트 판본 불일치');
  for(const f of m.files){const file=path.join(dir,f.name);const stat=fs.lstatSync(file);if(!stat.isFile()||stat.isSymbolicLink()||stat.size!==f.size||digest(fs.readFileSync(file))!==f.sha256)throw Error('설치된 업데이트가 변경되었습니다.');}
  return {workspace:path.join(dir,'workspace.html'),executable:path.join(dir,'indiebiz-member'+(process.platform==='win32'?'.exe':'')),version:m.version};
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
  if(this.state.pending){const p=this.state.pending;this.restore(p);this.state.active=p.previous;this.state.activeVersion=this.release(p.previous).version;this.state.rejected=[...new Set([...(this.state.rejected||[]),p.candidate])];delete this.state.pending;this.save();this.status={state:'rolled_back',message:'새 실행부의 시작을 확인하지 못해 이전 판본과 DB를 복구했습니다.'};}
  return this.release(this.state.active);
 }
 publicState(){return {...this.status,auto:!!this.state.auto,version:this.state.active==null?this.baseline.version:this.state.activeVersion,configured:!!(this.trust?.publicKey&&this.trust?.feed)};}
 setAuto(enabled){if(enabled&&!this.trust?.publicKey)throw Error('업데이트 채널이 설정되지 않았습니다.');this.state.auto=!!enabled;this.save();return this.publicState();}
 async check(){
  if(this.busy)return this.publicState();this.busy=true;
  try{
   this.status={state:'checking'};const envelope=JSON.parse((await download(this.trust.feed,131072,this.fetcher)).toString());const m=verify(envelope,this.trust);
   if(m.sequence<=this.state.highest||(this.state.rejected||[]).includes(m.sequence)){this.status={state:'current'};return this.publicState();}
   const dir=this.location(m.sequence);fs.mkdirSync(dir,{recursive:true,mode:0o700});
   for(const f of m.files){const bytes=await download(f.url,f.size,this.fetcher);if(bytes.length!==f.size||digest(bytes)!==f.sha256)throw Error('업데이트 파일 지문이 일치하지 않습니다.');const file=path.join(dir,f.name);fs.writeFileSync(file+'.part',bytes,{mode:f.name.startsWith('indiebiz-member')?0o700:0o600});fs.renameSync(file+'.part',file);}
   atomic(path.join(dir,'manifest.json'),envelope);this.release(m.sequence);this.staged=m.sequence;this.status={state:'ready',version:m.version};return this.publicState();
  }catch(e){this.status={state:'error',message:e.message};throw e;}finally{this.busy=false;}
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
 async apply(){
  if(this.busy||!this.staged)return this.publicState();this.busy=true;this.session.updating=true;
  const previous=this.state.active;let pending=false;
  if(!this.session.config){this.session.updating=false;this.busy=false;throw Error('기기를 등록한 뒤 업데이트를 적용하세요.');}
  try{
   this.status={state:'waiting'};
   if(this.session.bridge){while(!(await this.session.maintenance(true)).idle){await new Promise(r=>setTimeout(r,1000));}}
   const sequence=this.staged,candidate=this.release(sequence);
   this.session.updateTrial=true;await this.session.stop();const snapshot=await this.snapshot();
   this.state.pending={candidate:sequence,previous,snapshot};this.save();pending=true;
   this.status={state:'testing'};this.session.executable=candidate.executable;
   await this.session.start(undefined,{maintenance:true});
   if(this.session.bridge){const health=await this.session.internalRequest('health');if(!health.success||health.protocol!==2)throw Error('새 실행부의 DB·프로토콜 검사가 실패했습니다.');}
   await this.show(candidate.workspace,true);
   if(this.session.bridge)await this.session.maintenance(false);
   this.state.active=sequence;this.state.activeVersion=candidate.version;this.state.highest=sequence;delete this.state.pending;this.save();pending=false;this.staged=null;
   this.status={state:'updated'};return this.publicState();
  }catch(e){
   await this.session.stop();
   if(pending){this.recover();}else{this.state.active=previous;}
   const old=this.release(previous);this.session.executable=old.executable;
   await this.session.start();await this.show(old.workspace,false);
   this.status={state:'rolled_back',message:'업데이트를 적용하지 못해 이전 판본을 유지합니다: '+e.message};return this.publicState();
  }finally{this.session.updating=false;this.session.updateTrial=false;this.busy=false;}
 }
}
module.exports={RuntimeUpdates,verify,download,digest,SHELL_VERSION};
