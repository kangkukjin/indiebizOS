/* Files live in IndexedDB on the member device; no hub filesystem fallback. */
class MemberBrowserFiles {
  constructor(store){this.store=store}
  async execute(c){
    const path=memberPath(c.path);
    if(c.op==='list'){
      const prefix=path==='.'?'':path+'/',items=new Map();
      for(const file of await this.store.all('files')){
        if(!file.id.startsWith(prefix)||file.id===path)continue;
        const relative=file.id.slice(prefix.length),name=relative.split('/')[0],directory=relative.includes('/')||file.directory;
        items.set(name,{name,path:prefix+name,type:directory?'directory':'file',dir:directory,bytes:file.size||0});
      }
      return {success:true,path,items:[...items.values()]};
    }
    if(path==='.')throw Error('파일 이름을 입력하세요');
    if(c.op==='read'){
      const file=await this.store.get('files',path);if(!file||file.directory)throw Error('파일이 없습니다: '+path);
      return {success:true,path,content:c.encoding==='base64'?file.data:new TextDecoder().decode(memberBytes(file.data))};
    }
    if(c.op==='write'||c.op==='mkdir'){
      const bytes=c.encoding==='base64'?memberBytes(c.content||''):new TextEncoder().encode(c.content||'');
      if(bytes.length>32*1024*1024)throw Error('파일은 32MB 이하여야 합니다');
      const rows=await this.store.all('files');
      if(rows.some(f=>!f.directory&&path.startsWith(f.id+'/')))throw Error('상위 경로가 파일입니다');
      if(c.op==='write'&&rows.some(f=>f.id.startsWith(path+'/')))throw Error('폴더에 파일을 덮어쓸 수 없습니다');
      await this.store.change('files',path,old=>{if(old&&Boolean(old.directory)!==(c.op==='mkdir'))throw Error('파일과 폴더를 서로 덮어쓸 수 없습니다');return {id:path,data:memberBase64(bytes),size:bytes.length,directory:c.op==='mkdir',mime:c.mime||'application/octet-stream'}});
      return {success:true,saved:true,path,size:bytes.length,sha256:await memberHashBytes(bytes)};
    }
    if(c.op==='file_move'){
      const dest=memberPath(c.dest),file=await this.store.get('files',path);
      if(!file||file.directory)throw Error('이동할 파일이 없습니다');
      if(dest==='.'||await this.store.get('files',dest))throw Error('대상 파일이 이미 있거나 경로가 잘못됐습니다');
      await new Promise((resolve,reject)=>{const tx=this.store.db.transaction('files','readwrite'),s=tx.objectStore('files');s.put({space:this.store.space,id:dest,value:{...file,id:dest}});s.delete([this.store.space,path]);tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error)});
      return {success:true,path:dest};
    }
    throw Error('브라우저에서 지원하지 않는 파일 작업입니다');
  }
  async import(file){if(file.size>32*1024*1024)throw Error('파일은 32MB 이하여야 합니다');let path='imports/'+memberPath(file.name);if(await this.store.get('files',path))path='imports/'+crypto.randomUUID().slice(0,8)+'-'+memberPath(file.name);return this.execute({op:'write',path,content:memberBase64(new Uint8Array(await file.arrayBuffer())),encoding:'base64',mime:file.type})}
  async download(path){const r=await this.execute({op:'read',path,encoding:'base64'});memberDownload(new Blob([memberBytes(r.content)]),memberPath(path).split('/').pop());return {success:true}}
}
/* Code runs in a worker inside an opaque-origin frame. It receives input data
   only, with no keys, DOM, network, IndexedDB or parent-origin filesystem. */
function memberJavascript(code,input,signal){
  if(typeof code!=='string'||code.length>200000)return Promise.reject(Error('프로그램이 너무 큽니다'));
  return new Promise((resolve,reject)=>{
    const frame=document.createElement('iframe');frame.hidden=true;frame.sandbox='allow-scripts';let finished=false;
    const finish=(result,error)=>{if(finished)return;finished=true;clearTimeout(timer);window.removeEventListener('message',receive);signal?.removeEventListener('abort',cancel);frame.remove();error?reject(Error(error)):resolve(result)};
    const receive=e=>{if(e.source!==frame.contentWindow)return;if(e.data?.ready)frame.contentWindow.postMessage({code,input},'*');else if(e.data?.done)finish(e.data.result,e.data.error)};
    const cancel=()=>finish(null,'프로그램을 중단했습니다');signal?.addEventListener('abort',cancel,{once:true});
    window.addEventListener('message',receive);const timer=setTimeout(()=>finish(null,'브라우저 프로그램 시간 제한(15초)'),15000);
    if(signal?.aborted){cancel();return}
    frame.srcdoc=`<!doctype html><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval'; worker-src blob:; connect-src 'none'"><script>
    addEventListener('message',e=>{if(e.source!==parent)return;
      const source='onmessage=async e=>{try{const F=Object.getPrototypeOf(async function(){}).constructor;const result=await new F("input",e.data.code)(e.data.input);const data=JSON.stringify(result);if(data&&data.length>32*1024*1024)throw Error("결과 크기 제한(32MB)");postMessage({done:true,result})}catch(err){postMessage({done:true,error:String(err.message)})}}';
      const url=URL.createObjectURL(new Blob([source],{type:'text/javascript'}));const worker=new Worker(url);URL.revokeObjectURL(url);
      const timer=setTimeout(()=>{worker.terminate();parent.postMessage({done:true,error:'프로그램 시간 제한'},'*')},14000);
      worker.onmessage=m=>{clearTimeout(timer);worker.terminate();parent.postMessage(m.data,'*')};
      worker.onerror=()=>{clearTimeout(timer);worker.terminate();parent.postMessage({done:true,error:'프로그램 실행 실패'},'*')};worker.postMessage(e.data);
    },{once:true});parent.postMessage({ready:true},'*');<\/script>`;
    document.body.append(frame);
  });
}
