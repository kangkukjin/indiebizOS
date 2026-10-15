const fs=require('node:fs');
const path=require('node:path');
const {spawn}=require('node:child_process');
const crypto=require('node:crypto');
const {hubAddress,installation,exchangeProof,safeEndpoint}=require('./security.cjs');
class MemberSession {
  constructor({root,safeStorage,executable,onExit}) {Object.assign(this,{root,safeStorage,executable,onExit});this.child=null;this.bridge=null;this.config=null;fs.mkdirSync(root,{recursive:true,mode:0o700});}
  file(){return path.join(this.root,'connection.enc');}
  secure(){if(!this.safeStorage.isEncryptionAvailable() || this.safeStorage.getSelectedStorageBackend?.()==='basic_text')throw Error('OS 자격 보관소를 사용할 수 없습니다. OS 로그인을 확인하세요.');}
  read(){if(!fs.existsSync(this.file()))return null;this.secure();return JSON.parse(this.safeStorage.decryptString(fs.readFileSync(this.file())));}
  save(config){this.secure();const tmp=this.file()+'.tmp';fs.writeFileSync(tmp,this.safeStorage.encryptString(JSON.stringify(config)),{mode:0o600});fs.renameSync(tmp,this.file());}
  async enroll(raw,code){
    this.secure();const base=hubAddress(raw);if(!/^[A-Z2-7]{16}$/.test(code))throw Error('등록 코드는 16자리입니다.');
    const previous=this.read();
    const pending=previous?.pending?.base===base&&previous.pending.code===code?previous.pending:{base,code,...(previous?.base===base&&previous?.private_key?{installation_id:previous.installation_id,private_key:previous.private_key,public_key:previous.public_key}:installation()),request_id:crypto.randomUUID()};
    this.save({...previous,pending});
    const body={code,request_id:pending.request_id,installation_id:pending.installation_id,public_key:pending.public_key,signature:exchangeProof(pending,code,pending.request_id)};
    const response=await fetch(base+'/m/enroll/exchange',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),redirect:'error',signal:AbortSignal.timeout(20000)});
    const result=await response.json();if(!response.ok||!result.success)throw Error(result.detail||result.error||'등록하지 못했습니다.');
    const config={base,key:result.key,alias:result.alias,device_id:result.device_id,hub_id:result.hub_id,installation_id:pending.installation_id,private_key:pending.private_key,public_key:pending.public_key};
    await this.stop();this.save(config);await this.start(config);return this.publicState();
  }
  publicState(){return {connected:!!this.bridge,hub:this.config?.base||'',name:this.config?.alias||'',device_id:this.config?.device_id||''};}
  async start(config=this.read()){
    if(!config?.key)return false;if(this.child)return true;this.config=config;
    const namespace=crypto.createHash('sha256').update(config.hub_id+'\0'+config.device_id+'\0'+config.installation_id).digest('hex');
    const dir=path.join(this.root,'workspaces',namespace);fs.mkdirSync(dir,{recursive:true,mode:0o700});
    this.child=spawn(this.executable,['--member-desktop'],{stdio:['pipe','pipe','ignore'],windowsHide:true,env:{...process.env,INDIEBIZ_MEMBER_NO_BROWSER:'1'}});
    const child=this.child;
    child.once('exit',()=>{if(this.child===child){this.child=null;this.bridge=null;this.onExit?.();}});
    try {
      const ready=new Promise((resolve,reject)=>{
        let text='';const timer=setTimeout(()=>reject(Error('로컬 실행부를 시작하지 못했습니다.')),20000);
        const finish=(err,value)=>{clearTimeout(timer);err?reject(err):resolve(value);};
        child.once('error',e=>finish(e));child.once('exit',()=>finish(Error('로컬 실행부가 종료됐습니다.')));
        child.stdout.on('data',data=>{text+=data.toString();if(text.length>4096)return finish(Error('실행부 응답 오류'));if(text.includes('\n')){try{const r=JSON.parse(text.split('\n')[0]);const u=new URL(r.origin);if(u.hostname!=='127.0.0.1'||u.protocol!=='http:'||!r.token||r.protocol!==2)throw Error();child.stdout.removeAllListeners('data');child.stdout.resume();finish(null,r);}catch{finish(Error('실행부 응답 오류'));}}});
      });
      child.stdin.write(JSON.stringify({...config,mode:'member',desktop:true,data_dir:dir})+'\n');
      this.bridge=await ready;return true;
    }catch(e){await this.stop();throw e;}
  }
  async request(raw,body){
    const endpoint=safeEndpoint(raw,body);if(!this.bridge)throw Error('로컬 실행부가 연결되지 않았습니다. 앱을 다시 여세요.');
    const r=await fetch(this.bridge.origin+'/member/'+endpoint,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-Member-Token':this.bridge.token},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(300000),redirect:'error'});
    if(!r.ok)throw Error('로컬 요청을 처리하지 못했습니다 ('+r.status+').');return r.json();
  }
  async stop(){const child=this.child;if(!child)return;try{await this.request('close',{});}catch{}child.stdin.end();await new Promise(resolve=>{if(child.exitCode!==null)return resolve();const timer=setTimeout(()=>{child.kill();resolve();},5000);child.once('exit',()=>{clearTimeout(timer);resolve();});});this.child=null;this.bridge=null;}
  async disconnect(){await this.stop();fs.rmSync(this.file(),{force:true});this.config=null;}
}
module.exports={MemberSession};
