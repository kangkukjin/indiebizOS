class MemberBrowserRuntime {
  constructor(key,store){this.key=key;this.store=store;this.files=new MemberBrowserFiles(store);this.approvals=new Map();this.active=false;this.session='';this.running='';this.abort=null;this.stopped=new Set();this.programAbort=null}
  async http(path,body={},options={}){
    const r=await fetch(path,{method:'POST',credentials:'omit',headers:{'Content-Type':'application/json'},body:JSON.stringify({...body,key:this.key}),...options});
    if(!r.ok)throw Error('허브 응답 '+r.status);return r.json();
  }
  async connect(){
    const profile=await this.http('/m/profile');if(!profile.success)throw Error(profile.message||profile.error);
    const hello=await this.http('/limb/connect',{mode:'member',host:'회원 웹 브라우저',env:{mode:'member',os:'browser',client:'web'}});
    if(!hello.success||!hello.approved)throw Error(hello.error||'기기 승인을 확인하세요');
    this.epoch=profile.client_protocol?.epoch||'';this.session=hello.session;this.active=true;this.poll();return profile;
  }
  async poll(){while(this.active){try{
    const r=await this.http('/limb/poll',{session:this.session,wait:25});
    if(!r.success||!r.approved||r.stale){this.active=false;await this.stop();document.getElementById('status').textContent=r.stale?'다른 기기에서 연결했습니다. 이 창의 실행은 중단됐습니다.':'연결이 만료됐습니다. 다시 로그인하세요.';break}
    for(const job of r.jobs||[]){if(!this.active)break;let result;try{result=await this.run(JSON.parse(job.code))}catch(e){result={success:false,error:e.message}}
      // Network retries send the saved receipt, never execute the command again.
      for(let attempt=0;attempt<3&&this.active;attempt++){try{await this.http('/limb/result',{job_id:job.id,session:this.session,result});break}catch(e){await new Promise(r=>setTimeout(r,1000))}}
    }
  }catch(e){if(this.active)await new Promise(r=>setTimeout(r,2000))}}}
  async approve(command){
    // 회원이 시작한 작업의 브라우저 내부 저장·계산은 기능마다 재승인하지 않는다.
    // run()의 작업/세션 검사와 프로그램 sandbox는 그대로 적용된다.
    if(['read','list','info','memory_recall','result_query','write','mkdir','file_move','memory_save','javascript','script','media','location'].includes(command.op))return true;
    if(command.op==='media'&&command.action==='status')return true;
    return new Promise(resolve=>{const timer=setTimeout(()=>answer(false),110000);const answer=allow=>{clearTimeout(timer);this.approvals.delete(command.request_key);resolve(allow)};this.approvals.set(command.request_key,{key:command.request_key,command,answer});memberApprovals()});
  }
  async run(c){
    if(!c.member||!c.request_key||c.body_session!==this.session)return {success:false,error:'현재 브라우저에 발급된 명령이 아닙니다'};
    if(!c.task_id||!await this.store.get('tasks',c.task_id)||this.stopped.has(c.task_id))return {success:false,error:'종료되었거나 알 수 없는 작업입니다'};
    if(c.op==='result_query')return (await this.store.get('jobs',c.query_key))?.result||{success:false,error:'result_unknown'};
    const fingerprint=await memberDigest(JSON.stringify(c));let claimed=false;
    const row=await this.store.change('jobs',c.request_key,old=>{
      if(old){if(old.fingerprint!==fingerprint)throw Error('요청 키 내용 충돌');return old}
      claimed=true;return {id:c.request_key,fingerprint,state:'received',command:c};
    });
    if(!claimed)return row.result||{success:false,error:'result_unknown',state:row.state};
    let result;
    try{
      if(c.op==='script'&&c.action==='run'){const script=await this.store.get('scripts',c.id);if(!script)throw Error('등록된 프로그램이 없습니다');c={...c,program_source:(await this.files.execute({op:'read',path:script.path})).content}}
      if(!await this.approve(c)||this.stopped.has(c.task_id))result={success:false,error:'회원이 실행을 승인하지 않았습니다'};
      else{await this.store.put('jobs',row.id,{...row,state:'running'});result=await this.execute(c)}
    }catch(e){result={success:false,error:e.message}}
    result={...result,request_key:row.id};
    try{await this.store.put('jobs',row.id,{...row,state:'completed',result})}catch(e){return {success:false,error:'result_unknown',message:'실행 결과를 저장하지 못했습니다. 자동 재실행하지 마세요.'}}
    return result;
  }
  async execute(c){
    if(['read','write','list','mkdir','file_move'].includes(c.op))return this.files.execute(c);
    if(c.op==='memory_recall'){
      const allHistory=(await this.store.all('conversations')).filter(r=>r.task_id===c.task_id).sort((a,b)=>a.created-b.created).slice(-40).flatMap(r=>[{role:'user',content:r.user},{role:'assistant',content:r.assistant}]);
      // 회상 결과 자체/바이너리 파일/이전 회상 봉투를 다시 회상하면 대화마다 본문이 증폭된다.
      let remaining=32000,truncated=false;
      const bounded=rows=>{const kept=[];for(const row of [...rows].reverse()){const size=JSON.stringify(row).length;if(size>remaining){truncated=true;continue}remaining-=size;kept.unshift(row)}return kept};
      const history=bounded(allHistory),memories=bounded((await this.store.all('memories')).slice(-40));
      const recent_results=(await this.store.all('jobs')).filter(r=>r.command?.task_id===c.task_id&&!['memory_recall','memory_save'].includes(r.command.op)).slice(-20).map(r=>({op:r.command.op,state:r.state,path:r.result?.path,success:r.result?.success,error:r.result?.error,size:r.result?.size,sha256:r.result?.sha256}));
      return {success:true,history,memories,sentences:await this.store.all('sentences'),recent_results,context_truncated:truncated,workspace:'브라우저의 내 작업 공간',shell_available:false,javascript_available:true};
    }
    if(c.op==='memory_save'){
      const r=c.record;if(!r?.id)throw Error('기억 ID가 없습니다');
      if(typeof r.content==='string')await this.store.put('memories',r.id,r);
      else{await this.store.put('conversations',r.id,{...r,task_id:c.task_id,created:Date.now()});if(r.episode)await this.store.put('episodes',r.id,{id:r.id,...r.episode})}
      return {success:true,saved:true,id:r.id};
    }
    if(c.op==='javascript'){const result=await this.program(c.code,c.input);return {success:true,result}}
    if(c.op==='script'){
      if(!c.action||c.action==='list')return {success:true,items:await this.store.all('scripts')};
      if(c.action==='register'){
        if(!c.id||!['javascript','js'].includes(c.interpreter))throw Error('웹앱은 JavaScript 프로그램만 등록합니다. interpreter: javascript를 사용하세요.');
        await this.files.execute({op:'read',path:c.path});await this.store.put('scripts',c.id,{id:c.id,path:memberPath(c.path),interpreter:'javascript'});return {success:true,id:c.id};
      }
      if(c.action==='run'){
        const script=await this.store.get('scripts',c.id);if(!script)throw Error('등록된 프로그램이 없습니다');
        const result=await this.program(c.program_source,c.args||{});
        return {success:true,stdout:typeof result==='string'?result:JSON.stringify(result),result};
      }
      throw Error('지원하지 않는 프로그램 동작입니다');
    }
    if(c.op==='media'){
      const audio=document.getElementById('memberAudio');const action=c.action||'play';
      if(action==='play'){const url=new URL(c.url);if(!['https:','http:'].includes(url.protocol))throw Error('스트림 주소 오류');audio.hidden=false;audio.src=url.href;await this.playAudio(audio)}
      else if(action==='stop'){audio.pause();audio.removeAttribute('src');audio.load();audio.hidden=true}
      else if(!['status','volume'].includes(action))throw Error('지원하지 않는 재생 동작');
      if(c.volume!==undefined){if(c.volume<0||c.volume>100)throw Error('음량 범위 오류');audio.volume=c.volume/100}
      return {success:true,playing:!audio.paused,volume:Math.round(audio.volume*100)};
    }
    if(c.op==='location')return new Promise((resolve,reject)=>{if(!navigator.geolocation)return reject(Error('이 브라우저에서 위치를 지원하지 않습니다'));navigator.geolocation.getCurrentPosition(p=>resolve({success:true,latitude:p.coords.latitude,longitude:p.coords.longitude,accuracy:p.coords.accuracy}),e=>reject(Error(e.message)),{timeout:15000,maximumAge:0})});
    if(c.op==='info')return {success:true,os:'browser',workspace:'브라우저의 내 작업 공간'};
    return {success:false,error:'이 기능은 설치 없는 웹앱에서 지원하지 않습니다. 허브 기기에서 대신 실행하지 않습니다.'};
  }
  async playAudio(audio){
    this.mediaAbort=new AbortController();const signal=this.mediaAbort.signal;
    try{await new Promise((resolve,reject)=>{
      let timer;
      const finish=error=>{clearTimeout(timer);audio.removeEventListener('playing',played);audio.removeEventListener('error',failed);signal.removeEventListener('abort',cancel);if(error){audio.pause();reject(error)}else resolve()};
      const played=()=>finish(),failed=()=>finish(Error('이 브라우저에서 방송을 재생하지 못했습니다. 다른 방송을 선택하세요.'));
      const cancel=()=>finish(Error('재생 요청을 중단했습니다'));
      audio.addEventListener('playing',played,{once:true});audio.addEventListener('error',failed,{once:true});signal.addEventListener('abort',cancel,{once:true});
      timer=setTimeout(()=>finish(Error('재생을 확인하지 못했습니다. 방송과 인터넷 연결을 확인하세요.')),30000);
      audio.play().then(played).catch(e=>{if(e.name==='NotAllowedError')document.getElementById('status').textContent='위 재생 버튼을 누르면 이 기기에서 방송이 시작됩니다';else failed()});
    })}finally{this.mediaAbort=null}
  }
  async program(code,input){this.programAbort=new AbortController();try{return await memberJavascript(code,input,this.programAbort.signal)}finally{this.programAbort=null}}
  async start(body){
    if(!this.active)throw Error('허브에 다시 연결하세요');if(this.running)throw Error('진행 중인 작업을 완료하거나 중단하세요');
    // 산출물 경로는 기기에서만 해소한다. 허브 요청에는 보내지 않는다.
    if(body.output){const output=memberPath(body.output);if(output==='.')throw Error('산출물 파일 이름이 필요합니다');body={...body,output};}
    let task=body.task_id?await this.store.get('tasks',body.task_id):null;
    if(body.task_id&&!task)throw Error('작업이 없습니다');
    const message=String(body.message||'').trim();if(!message&&!body.code&&!body.action_id)throw Error('요청을 입력하세요');
    const title=typeof body.title==='string'?body.title.slice(0,100):'';
    if(!task)task={id:crypto.randomUUID(),title:title||message.slice(0,60)||'앱 실행',workspace:'브라우저의 내 작업 공간',events:[],created:Date.now()};
    if(task.state==='input_required'&&!body.action_id)body={...body,reply_to:task.request_id};
    task.state='running';task.updated=Date.now();task.events.push({kind:'user',value:title||message});this.running=task.id;this.stopped.delete(task.id);
    try{await this.store.put('tasks',task.id,task)}catch(e){this.running='';throw e}
    body={...body,request_id:crypto.randomUUID()};await this.store.change('tasks',task.id,t=>({...t,request_id:body.request_id,origin:body.app_id||t.origin}));
    this.runTask(task.id,body);return {success:true,task_id:task.id,queued:true};
  }
  async event(id,kind,value){return this.store.change('tasks',id,t=>({...t,events:[...t.events,{kind,value}].slice(-500)}))}
  async runTask(id,body){
    this.abort=new AbortController();let result={success:false,error:'연결이 끊겼습니다. 결과를 확인하세요.'},state='unknown';
    try{
      const {output,title,app_id,...request}=body;request.version=1;request.epoch=this.epoch||'';request.request_id=request.request_id||crypto.randomUUID();request.capabilities={files:true,javascript:true};if(request.action_id?.startsWith('local_'))request.local_apps=this.localApps||[];
      const r=await fetch('/m/run',{method:'POST',credentials:'omit',headers:{'Content-Type':'application/json'},body:JSON.stringify({...request,key:this.key,task_id:id,body_session:this.session}),signal:this.abort.signal});
      if(!r.ok)throw Error('허브 응답 '+r.status);
      if(!r.headers.get('content-type')?.includes('ndjson')){result=await r.json();state='failed'}
      else{
        const reader=r.body.getReader(),decoder=new TextDecoder();let pending='';
        const receive=async line=>{if(!line.trim())return;const e=JSON.parse(line);if(e.type==='event')await this.event(id,'progress',e.event);if(e.type==='result'){result=e.result;state=result.error_type==='cancelled'?'cancelled':result.input_required?'input_required':result.success?'completed':'failed'}};
        for(;;){const {value,done}=await reader.read();if(done){pending+=decoder.decode();if(pending.trim())await receive(pending);break}pending+=decoder.decode(value,{stream:true});if(pending.length>48*1024*1024)throw Error('응답 크기 제한');let n;while((n=pending.indexOf('\n'))>=0){await receive(pending.slice(0,n));pending=pending.slice(n+1)}}
      }
    }catch(e){if(state==='unknown')result={success:false,error:e.name==='AbortError'?'작업을 중단했습니다. 이미 실행된 결과는 최근 작업 결과에서 확인하세요.':e.message}}
    if(state==='completed'&&result.success&&result.artifacts?.length){
      try{
        if(this.stopped.has(id)||!this.active)throw Error('작업이 중단되어 산출물을 저장하지 않았습니다');
        result.files=[];
        for(const artifact of result.artifacts){
          const bytes=memberBytes(artifact.data);
          const hash=await memberHashBytes(bytes);
          if(hash!==artifact.sha256||bytes.length!==artifact.size||!/^[a-f0-9]{32}$/.test(artifact.id))throw Error('산출물 무결성 확인 실패');
          const path='reports/'+artifact.id+'-'+memberPath(artifact.name);
          const receipt=await this.files.execute({op:'write',path,encoding:'base64',content:artifact.data,mime:artifact.mime});
          const stored=await this.files.execute({op:'read',path,encoding:'base64'});
          if(!receipt.success||!receipt.saved||stored.content!==artifact.data)throw Error('이 기기의 산출물 저장을 확인하지 못했습니다');
          result.files.push({path,on:'body',saved:true,sha256:hash});
          const ack=await this.http('/m/receipts',{request_id:result.request_id,artifact_id:artifact.id,sha256:hash,size:bytes.length,body_session:this.session,epoch:result.epoch});
          if(!ack.success)throw Error('기기에는 저장했지만 허브의 수신 확인이 완료되지 않았습니다');
        }
        result={...result,saved:true,delivery:'delivered'};await this.event(id,'progress',{type:'delivered'});
      }catch(e){state='failed';result={...result,success:false,saved:false,error:e.message}}
    }
    if(this.stopped.has(id)){state='cancelled';result={...result,success:false,error_type:'cancelled',error:'작업을 중단했습니다. 이미 저장한 파일은 아래에서 받을 수 있습니다.'}}
    try{
      const prior=await this.store.get('tasks',id);
      const files=new Map([...(prior?.result?.files||[]),...(result.files||[])].map(f=>[f.path,f]));
      for(const job of await this.store.all('jobs')){
        if(job.command?.task_id===id&&job.command.op==='write'&&job.state==='completed'&&job.result?.success&&job.result?.saved)
          files.set(job.result.path,{...(files.get(job.result.path)||{}),path:job.result.path,on:'body',saved:true,sha256:job.result.sha256});
      }
      result.files=[...files.values()];
      await this.event(id,'assistant',result.success===false?result.error:result.input_required||(body.action_id&&!result.artifacts?.length?'요청을 처리했습니다. 앱에서 결과를 확인하세요.':result.response)||'결과를 확인하세요');await this.store.change('tasks',id,t=>({...t,state,result,updated:Date.now()}))}
    catch(e){document.getElementById('status').textContent='작업 기록을 저장하지 못했습니다: '+e.message}
    finally{this.running='';this.abort=null}
  }
  async stop(){if(!this.running)return {success:true};if(this.running)this.stopped.add(this.running);for(const a of this.approvals.values())a.answer(false);this.abort?.abort();this.programAbort?.abort();this.mediaAbort?.abort();return this.http('/m/session/close',{body_session:this.session}).catch(()=>({success:false,error:'허브 연결 끊김'}))}
  async request(path,body={}){
    if(path==='workspace')return {success:true,fixed:true,workspace:'브라우저의 내 작업 공간'};
    if(path==='profile')return this.http('/m/profile');
    if(path==='tasks')return (await this.store.all('tasks')).sort((a,b)=>b.updated-a.updated);
    if(path.startsWith('task?'))return await this.store.get('tasks',new URLSearchParams(path.split('?')[1]).get('id'))||{success:false,error:'작업 없음'};
    if(path==='task/start')return this.start(body);
    if(path==='file')return this.files.execute(body);
    if(path==='results')return (await this.store.all('jobs')).slice(-40).map(r=>({...r,key:r.id}));
    if(path==='approvals')return [...this.approvals.values()].map(({key,command})=>({key,command}));
    if(path==='approve'){const a=this.approvals.get(body.key);a?.answer(body.allow===true);return {success:!!a}}
    if(path==='close')return this.stop();
    if(path==='export'){memberDownload(new Blob([JSON.stringify(await this.store.backup())],{type:'application/json'}),'indiebiz-member-backup.json');return {success:true,path:'브라우저에 백업 다운로드 요청'}}
    if(path==='apps'){
      let local=[];
      const file=await this.store.get('files','apps.json');
      if(file)try{local=JSON.parse(new TextDecoder().decode(memberBytes(file.data)));if(!Array.isArray(local))throw Error()}catch(e){return {...await this.http('/m/apps'),local_error:'apps.json 형식을 확인하세요'}}
      const remote=await this.http('/m/apps',{local_apps:local});
      if(remote.success)this.localApps=local;
      return remote;
    }
    throw Error('지원하지 않는 웹 작업 요청입니다');
  }
}
