const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {RuntimeUpdates,verify,digest,SHELL_VERSION}=require('../updates.cjs');
const keys=crypto.generateKeyPairSync('ed25519');
const trust={publicKey:keys.publicKey.export({type:'spki',format:'pem'}),feed:'https://updates.example/member/current.json'};
function release(sequence=1){
 const names=['workspace.html','workspace.cjs','indiebiz-member'+(process.platform==='win32'?'.exe':'')];
 const bytes=new Map(names.map(n=>['https://updates.example/member/'+n,Buffer.from('release-'+sequence+'-'+n)]));
 const manifest={format:'indiebiz-member-runtime',version:'0.1.1',sequence,platform:process.platform,arch:process.arch,protocol:2,shell:SHELL_VERSION,expires:Date.now()/1000+600,files:names.map(name=>({name,url:'https://updates.example/member/'+name,size:bytes.get('https://updates.example/member/'+name).length,sha256:digest(bytes.get('https://updates.example/member/'+name))}))};
 return {manifest,bytes,envelope:()=>sign(manifest)};
}
function sign(m){const raw=Buffer.from(JSON.stringify(m));return {manifest:raw.toString('base64'),signature:crypto.sign(null,raw,keys.privateKey).toString('base64')};}
function fixture(t){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'member-update-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const namespace='a'.repeat(64),dir=path.join(root,'workspaces',namespace);fs.mkdirSync(dir,{recursive:true});const db=path.join(dir,'member.db');fs.writeFileSync(db,'original-database');
 const r=release();const events=[];
 const session={config:{key:'synthetic'},executable:'old-helper',bridge:{},maintenance:async pause=>{events.push(['maintenance',pause]);return {idle:true}},stop:async()=>{events.push(['stop']);session.bridge=null},start:async(_,options)=>{events.push(['start',session.executable,options]);session.bridge={}},internalRequest:async()=>({success:true,protocol:2})};
 const options={root,trust,session,verifyExecutable:()=>{},baseline:{version:'0.1.0',workspace:'old-ui',executable:'old-helper'},show:async(file,trial)=>events.push(['show',trial,session.updating]),backup:async(exe,source,target)=>fs.copyFileSync(source,target),fetcher:async(url)=>new Response(url===trust.feed?JSON.stringify(r.envelope()):r.bytes.get(url))};
 return {root,db,r,events,session,options,u:new RuntimeUpdates(options)};
}
test('signed manifest rejects tamper, wrong platform, expired release and foreign artifact origin',()=>{
 const r=release();assert.equal(verify(r.envelope(),trust).sequence,1);
 const tampered=r.envelope();tampered.manifest=Buffer.from('{}').toString('base64');assert.throws(()=>verify(tampered,trust));
 for(const change of [{platform:'other'},{expires:0},{shell:999},{protocol:1},{files:[...r.manifest.files,r.manifest.files[0]]}])assert.throws(()=>verify(sign({...r.manifest,...change}),trust));
 r.manifest.files[0].url='https://untrusted.example/file';assert.throws(()=>verify(r.envelope(),trust));
});
test('downloaded file digest is checked before applying a release',async t=>{
 const f=fixture(t);f.r.bytes.set(f.r.manifest.files[0].url,Buffer.from('tampered'));await f.u.check();await assert.rejects(()=>f.u.apply(1));assert.deepEqual(f.events,[]);assert.equal(f.u.state.active,null);
});
test('apply pauses admissions, snapshots DB, verifies helper and UI before opening admissions',async t=>{
 const f=fixture(t);await f.u.check();const result=await f.u.apply(1);assert.equal(result.state,'updated');assert.equal(f.u.state.active,1);assert.equal(f.u.state.highest,1);assert.equal(f.session.updating,false);
 assert.equal(fs.readFileSync(f.db,'utf8'),'original-database');assert.deepEqual(f.events[0],['maintenance',true]);assert(f.events.some(e=>e[0]==='show'&&e[1]&&e[2]));assert.deepEqual(f.events.at(-1),['maintenance',false]);
 await f.u.check();assert.equal(f.u.status.state,'current');
});
test('failed renderer boot restores pre-migration DB and previous binary',async t=>{
 const f=fixture(t);f.u.show=async(file,trial)=>{if(trial){fs.writeFileSync(f.db,'migrated-database');fs.writeFileSync(f.db+'-wal','candidate WAL');throw Error('renderer failed')}};
 await f.u.check();const result=await f.u.apply(1);assert.equal(result.state,'rolled_back');assert.equal(f.session.executable,'old-helper');assert.equal(fs.readFileSync(f.db,'utf8'),'original-database');assert(!fs.existsSync(f.db+'-wal'));assert.equal(f.u.state.active,null);assert.deepEqual(f.u.state.rejected,[1]);
 await f.u.check();assert.equal(f.u.status.state,'current');
});
test('crash during trial is recovered before any executor is started',async t=>{
 const f=fixture(t);const snapshot=await f.u.snapshot();f.u.state.pending={candidate:2,previous:null,snapshot};f.u.save();fs.writeFileSync(f.db,'unconfirmed-migration');
 const next=new RuntimeUpdates(f.options);assert.equal(next.recover().executable,'old-helper');assert.equal(fs.readFileSync(f.db,'utf8'),'original-database');assert(!next.state.pending);assert.deepEqual(f.events,[]);
});
test('busy task keeps running while new admissions stay paused',async t=>{
 const f=fixture(t);let polls=0;f.session.maintenance=async pause=>({idle:!pause||++polls>1});await f.u.check();await f.u.apply(1);assert.equal(polls,2);assert.equal(f.u.status.state,'updated');
});
test('renderer cannot request maintenance or health through general IPC proxy',()=>{
 const {safeEndpoint}=require('../security.cjs');assert.throws(()=>safeEndpoint('maintenance',{pause:false}));assert.throws(()=>safeEndpoint('health'));
});
test('offline publisher emits a verifiable release and never copies the private key',()=>{
 const {publish}=require('../publish-runtime.cjs');
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'member-publish-'));
 try{
  const pair=crypto.generateKeyPairSync('ed25519');
  const source=path.join(root,'source'),out=path.join(root,'public');fs.mkdirSync(source);
  for(const name of ['workspace.html','workspace.cjs','helper'])fs.writeFileSync(path.join(source,name),'synthetic '+name);
  const key=path.join(root,'private.pem');fs.writeFileSync(key,pair.privateKey.export({type:'pkcs8',format:'pem'}));
  const args={source,helper:path.join(source,'helper'),out,base:'https://release.example/mac-arm64/',version:'0.1.2',sequence:2,platform:'darwin',arch:'arm64',key,expires:Date.now()/1000+60};
  const result=publish(args);const envelope=JSON.parse(fs.readFileSync(path.join(out,'current.json')));
  assert.equal(verify(envelope,result,{platform:'darwin',arch:'arm64'}).sequence,2);
  assert.deepEqual(fs.readdirSync(out).sort(),['2','current.json']);
  assert.deepEqual(fs.readdirSync(path.join(out,'2')).sort(),['indiebiz-member','workspace.cjs','workspace.html']);
  assert.throws(()=>publish(args));
 }finally{fs.rmSync(root,{recursive:true,force:true});}
});

test('repeated discovery only fetches metadata and leaves running work alone',async t=>{
 const f=fixture(t),urls=[];const fetcher=f.u.fetcher;f.u.fetcher=async url=>{urls.push(url);return fetcher(url)};
 for(const sequence of [1,1,2,3]){
  f.r.manifest.sequence=sequence;
  const state=await f.u.check();assert.equal(state.state,'available');assert.equal(state.canUpdate,true);assert.equal(state.sequence,sequence);
 }
 assert.deepEqual(urls,Array(4).fill(trust.feed));assert.deepEqual(f.events,[]);assert.equal(f.u.state.active,null);
 assert(!fs.existsSync(path.join(f.u.dir,'releases')));
});
test('install click refreshes latest offer; cancel downloads nothing and consent installs that offer',async t=>{
 const f=fixture(t),urls=[];const fetcher=f.u.fetcher;f.u.fetcher=async url=>{urls.push(url);return fetcher(url)};
 await f.u.check();f.r.manifest.sequence=2;f.r.manifest.version='0.1.2';
 await f.u.requestInstall(async state=>{
  assert.equal(state.sequence,2);assert.equal(state.availableVersion,'0.1.2');
  await f.u.check();await f.u.requestInstall(()=>assert.fail('duplicate prompt'));
  assert.deepEqual(urls,[trust.feed,trust.feed]);return false;
 });
 assert.deepEqual(f.events,[]);assert.equal(f.u.publicState().canUpdate,true);
 assert(!fs.existsSync(path.join(f.u.dir,'releases')));
 await f.u.check();assert.deepEqual(f.events,[]);
 await f.u.requestInstall(async state=>{
  assert.equal(state.sequence,2);assert(urls.every(url=>url===trust.feed));
  // A newer publication during the dialog must not replace what the user confirmed.
  f.r.manifest.sequence=3;await f.u.check();return true;
 });
 assert.equal(f.u.state.active,2);assert.equal(urls.filter(url=>url!==trust.feed).length,3);
});
test('full shell upgrade retires a verified old overlay while preserving user data and release files',async t=>{
 const f=fixture(t);await f.u.check();await f.u.apply(1);
 f.r.manifest.shell=1;const manifest=path.join(f.u.location(1),'manifest.json');fs.writeFileSync(manifest,JSON.stringify(f.r.envelope()));
 const next=new RuntimeUpdates(f.options);assert.equal(next.recover().workspace,'old-ui');
 assert.equal(next.state.active,null);assert.equal(next.state.highest,1);
 assert.equal(fs.readFileSync(f.db,'utf8'),'original-database');assert(fs.existsSync(manifest));
 f.u.save();const tampered=f.r.envelope();tampered.signature='invalid';fs.writeFileSync(manifest,JSON.stringify(tampered));
 assert.throws(()=>new RuntimeUpdates(f.options).recover(),/서명/);
});
test('old auto-install preferences are retired and approval binds the displayed release',async t=>{
 const f=fixture(t);f.u.state.auto=true;f.u.save();const next=new RuntimeUpdates(f.options);
 assert.equal(Object.hasOwn(next.state,'auto'),false);assert.equal(Object.hasOwn(JSON.parse(fs.readFileSync(next.stateFile)),'auto'),false);
 await next.check();assert.deepEqual(f.events,[]);await assert.rejects(()=>next.apply(2));assert.deepEqual(f.events,[]);
 f.r.manifest.sequence=2;await next.check();await assert.rejects(()=>next.apply(1));assert.deepEqual(f.events,[]);
});
test('an unconfigured installation does not fetch or offer an update',async t=>{
 const f=fixture(t);const next=new RuntimeUpdates({...f.options,trust:{},fetcher:()=>assert.fail('network access')});
 const state=await next.check();assert.equal(state.state,'unconfigured');assert.equal(state.canUpdate,false);assert.equal(state.sequence,undefined);
});

function uiOffer(f,sequence=1){
 const display={format:'indiebiz-display-1',surface:'desktop',state:1,host:'a'.repeat(64),version:'candidate',names:[],code:'',styles:[],template:'<main></main>'};
 const data=Buffer.from(JSON.stringify(display)),url='https://updates.example/member/ui/'+sequence+'/display.json';
 f.r.manifest={...f.r.manifest,kind:'ui',sequence,host:display.host,state:1,files:[{name:'display.json',url,size:data.length,sha256:digest(data)}]};
 f.r.envelope=()=>sign(f.r.manifest);f.r.bytes.set(url,data);f.u.showUI=async value=>{f.events.push(['display',value.version]);return {version:value.version}};
 return display;
}
test('UI install preserves executor, admissions and DB with separate monotonic sequence',async t=>{
 const f=fixture(t);f.u.state.highest=100;uiOffer(f,1);await f.u.check();assert.equal(f.u.publicState().kind,'ui');assert.equal(f.u.publicState().canUpdate,true);
 await f.u.requestInstall(async offer=>{assert.equal(offer.kind,'ui');assert.equal(offer.sequence,1);return true});
 assert.deepEqual(f.events,[['display','candidate']]);assert.equal(f.session.executable,'old-helper');assert.equal(f.session.updating,undefined);
 assert.equal(fs.readFileSync(f.db,'utf8'),'original-database');assert.equal(f.u.state.highest,100);assert.equal(f.u.state.ui.highest,1);assert.equal(f.u.state.active,null);
 assert(!fs.existsSync(path.join(f.u.dir,'snapshots')));assert(!f.u.state.pending);
 await f.u.check();assert.equal(f.u.publicState().state,'current');
 f.r.manifest=release(101).manifest;f.r.bytes=release(101).bytes;await f.u.check();assert.equal(f.u.publicState().canUpdate,true);
});
test('UI preparation failure and interrupted UI trial never invoke database recovery',async t=>{
 const f=fixture(t);uiOffer(f);f.u.showUI=async()=>{throw Error('incompatible display host')};await f.u.check();await f.u.apply(1);
 assert.equal(f.u.publicState().state,'rolled_back');assert.deepEqual(f.events,[]);assert.equal(f.u.state.ui.active,null);assert.deepEqual(f.u.state.ui.rejected,[1]);
 f.u.state.pending={kind:'ui',candidate:2,previous:null};f.u.save();fs.writeFileSync(f.db,'new-task-result');
 const next=new RuntimeUpdates(f.options);next.restore=()=>assert.fail('UI recovery cannot restore a DB');next.recover();
 assert.equal(fs.readFileSync(f.db,'utf8'),'new-task-result');assert.equal(next.state.ui.active,null);assert.deepEqual(next.state.ui.rejected,[1,2]);assert(!next.state.pending);
});
test('UI manifest rejects executable files, unknown kinds and missing compatibility',()=>{
 const r=release();
 for(const change of [{kind:'ui',host:'a'.repeat(64),state:1},{kind:'other'},{kind:'ui',files:[]}])assert.throws(()=>verify(sign({...r.manifest,...change}),trust));
});
test('UI publisher signs only the display module and separates runtime sequence directory',t=>{
 const f=fixture(t),{publish}=require('../publish-runtime.cjs'),display=uiOffer(f);
 const source=path.join(f.root,'source'),out=path.join(f.root,'out');fs.mkdirSync(source);fs.writeFileSync(path.join(source,'display.json'),JSON.stringify(display));
 const key=path.join(f.root,'private.pem');fs.writeFileSync(key,keys.privateKey.export({type:'pkcs8',format:'pem'}));
 const result=publish({source,out,kind:'ui',base:'https://updates.example/member/',version:'0.1.3',sequence:1,platform:process.platform,arch:process.arch,key,expires:Date.now()/1000+600});
 const verified=verify(JSON.parse(fs.readFileSync(path.join(out,'current.json'))),result);
 assert.equal(verified.kind,'ui');assert.deepEqual(fs.readdirSync(path.join(out,'ui','1')),['display.json']);
});

test('UI persistence failure rolls the renderer back and keeps current DB writes',async t=>{
 const f=fixture(t);uiOffer(f);const save=f.u.save.bind(f.u);let fail=true;
 f.u.save=()=>{if(f.u.state.ui.active===1&&fail){fail=false;throw Error('disk write failed')}return save()};
 f.u.revertUI=async version=>{assert.equal(version,'candidate');f.events.push(['revert',version])};
 f.u.showUI=async()=>{fs.writeFileSync(f.db,'new work during installation');f.events.push(['display','candidate'])};
 await f.u.check();const state=await f.u.apply(1);
 assert.equal(state.state,'rolled_back');assert.equal(f.u.state.ui.active,null);assert.equal(f.u.state.ui.highest,0);
 assert.equal(fs.readFileSync(f.db,'utf8'),'new work during installation');assert.deepEqual(f.events,[['display','candidate'],['revert','candidate']]);assert(!f.u.state.pending);
});

// These fixtures isolate lifecycle transitions; native-signature.test.cjs runs real codesign.
test('native identity rejection happens before executor shutdown or DB snapshot',async t=>{
 const f=fixture(t);f.u.verifyExecutable=()=>{throw Error('native identity rejected')};
 await f.u.check();await assert.rejects(()=>f.u.apply(1),/native identity rejected/);
 assert.deepEqual(f.events,[]);assert.equal(f.session.executable,'old-helper');
 assert.equal(fs.readFileSync(f.db,'utf8'),'original-database');
 assert(!fs.existsSync(path.join(f.u.dir,'snapshots')));assert.equal(f.u.state.active,null);
});
test('UI-only update never checks or changes native executable identity',async t=>{
 const f=fixture(t);f.u.verifyExecutable=()=>assert.fail('UI must keep the executable');
 uiOffer(f);await f.u.check();await f.u.apply(1);assert.equal(f.u.publicState().state,'updated');
 assert.deepEqual(f.events,[['display','candidate']]);
});
