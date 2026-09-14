/* IndexedDB v1. Every record belongs to a member key on this browser origin.
   Schema upgrades add stores; they never delete existing member data. */
const MEMBER_TABLES=['tasks','jobs','files','conversations','memories','episodes','scripts','sentences','hippocampus_examples','forage'];
class MemberBrowserStore {
  static async open(space) {
    const db=await new Promise((resolve,reject)=>{
      const r=indexedDB.open('indiebiz-member-workspace',1);
      r.onupgradeneeded=()=>{for(const name of MEMBER_TABLES)if(!r.result.objectStoreNames.contains(name))r.result.createObjectStore(name,{keyPath:['space','id']}).createIndex('space','space');};
      r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);
      r.onblocked=()=>reject(Error('다른 탭을 닫고 다시 연결하세요. 저장소 업데이트가 대기 중입니다.'));
    });
    const store=new MemberBrowserStore();store.db=db;store.space=space;
    db.onversionchange=()=>{db.close();location.reload()};return store;
  }
  async get(table,id){return this.read(table,s=>s.get([this.space,id])).then(row=>row?.value)}
  async all(table){return this.read(table,s=>s.index('space').getAll(this.space)).then(rows=>rows.map(r=>r.value))}
  read(table,make){return new Promise((resolve,reject)=>{const tx=this.db.transaction(table);const r=make(tx.objectStore(table));r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);})}
  change(table,id,update){return new Promise((resolve,reject)=>{
    const tx=this.db.transaction(table,'readwrite'),s=tx.objectStore(table);let value;
    const r=s.get([this.space,id]);r.onsuccess=()=>{try{value=update(r.result?.value);if(value===undefined)s.delete([this.space,id]);else s.put({space:this.space,id,value})}catch(e){tx.abort();reject(e)}};
    tx.oncomplete=()=>resolve(value);tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error||Error('저장하지 못했습니다'));
  })}
  put(table,id,value){return this.change(table,id,()=>value)}
  async recover(){for(const name of ['tasks','jobs'])for(const r of await this.all(name))if(['received','running'].includes(r.state)){r.state='unknown';await this.put(name,r.id,r)}}
  async backup(){const tables={};for(const t of MEMBER_TABLES)tables[t]=await this.all(t);return {format:'indiebiz-member-browser',version:1,tables}}
  async restore(archive){
    if(archive?.format!=='indiebiz-member-browser'||archive.version!==1||!archive.tables)throw Error('지원하는 회원 백업 파일이 아닙니다');
    const rows=[],seen=new Set();
    for(const [table,values] of Object.entries(archive.tables)){
      if(!MEMBER_TABLES.includes(table)||!Array.isArray(values))throw Error('백업 형식을 확인하세요');
      for(const value of values){
        if(!value||typeof value.id!=='string'||!value.id||value.id.length>512)throw Error('잘못된 백업 기록입니다');
        const key=table+'\0'+value.id;if(seen.has(key))throw Error('백업에 중복 ID가 있습니다');seen.add(key);
        if(table==='files'){if(memberPath(value.id)!==value.id||typeof value.data!=='string'||value.data.length>45000000)throw Error('잘못된 파일 기록입니다')}
        if(table==='tasks'&&(!Array.isArray(value.events)||value.events.length>10000))throw Error('잘못된 작업 기록입니다');
        if(['received','running'].includes(value.state))value.state='unknown';rows.push({table,id:value.id,value});
      }
    }
    let added=0,skipped=0;
    await new Promise((resolve,reject)=>{
      const tx=this.db.transaction(MEMBER_TABLES,'readwrite');
      for(const row of rows){const s=tx.objectStore(row.table),r=s.get([this.space,row.id]);r.onsuccess=()=>{if(r.result)skipped++;else{s.put({space:this.space,id:row.id,value:row.value});added++}}}
      tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error);
    });return {success:true,added,skipped};
  }
}
async function memberHashBytes(data){const bytes=await crypto.subtle.digest('SHA-256',data);return Array.from(new Uint8Array(bytes),v=>v.toString(16).padStart(2,'0')).join('')}
async function memberDigest(text){return memberHashBytes(new TextEncoder().encode(text))}
function memberDownload(blob,name){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000)}
function memberPath(raw){
  const path=String(raw||'.').replaceAll('\\','/');
  if(path.startsWith('/')||/^[A-Za-z]:/.test(path)||path.includes('\0'))throw Error('브라우저 작업 공간의 상대 경로를 사용하세요');
  const parts=path.split('/').filter(p=>p&&p!=='.');if(parts.includes('..'))throw Error('작업 공간 밖의 경로입니다');
  return parts.join('/')||'.';
}
function memberBase64(bytes){let s='';for(let i=0;i<bytes.length;i+=8192)s+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(s)}
function memberBytes(data){return Uint8Array.from(atob(data),c=>c.charCodeAt(0))}
